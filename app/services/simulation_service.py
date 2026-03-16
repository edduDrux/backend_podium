"""
Simulation Service — monta o prompt e gera perguntas contextuais.

Fluxo:
1. Busca chunks relevantes via Full-Text Search (Postgres)
2. Carrega o prompt de sistema (base + perfil)
3. Chama o LLM via llm_service
4. Se nenhuma API key configurada ou falha, usa stub de template

"""
import logging
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.profile import SimulationProfile
from app.models.session import Session

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _load_system_prompt(profile_key: str | None) -> str:
    base_file = _PROMPTS_DIR / "base.md"
    base = base_file.read_text(encoding="utf-8") if base_file.exists() else ""

    if profile_key:
        profile_file = _PROMPTS_DIR / "profiles" / f"{profile_key}.md"
        if profile_file.exists():
            profile_text = profile_file.read_text(encoding="utf-8")
            return f"{base}\n\n---\n\n{profile_text}"

    return base


def _build_full_prompt(system_prompt: str, segment_text: str, chunks: list[str]) -> str:
    if chunks:
        evidence_lines = "\n\n".join(
            f"[Trecho {i + 1}]: {c.strip()[:400]}" for i, c in enumerate(chunks)
        )
    else:
        evidence_lines = "(Nenhum trecho relevante encontrado no documento)"

    return (
        f"{system_prompt}\n\n"
        "---\n\n"
        "## Segmento de fala (o que o apresentador acabou de dizer)\n\n"
        f"{segment_text.strip()[:600]}\n\n"
        "## Evidências do documento\n\n"
        f"{evidence_lines}\n\n"
        "---\n\n"
        "Gere agora a pergunta no formato JSON especificado acima."
    )


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

async def generate_question_stub(
    db: AsyncSession,
    session_id: int,
    segment_text: str,
) -> dict:
    """
    Gera uma pergunta para o segmento de fala.
    Tenta usar o LLM real (OpenAI/Gemini). Usa stub de template como fallback.
    """
    session = await db.get(Session, session_id)

    # Resolve profile key
    profile_key: str | None = None
    if session and session.profile_id is not None:
        profile = await db.get(SimulationProfile, session.profile_id)
        if profile:
            profile_key = profile.key

    # Busca chunks relevantes via FTS
    chunks_content: list[str] = []
    evidence_chunk_ids: list[int] = []

    if session and session.document_id is not None:
        doc = await db.get(Document, session.document_id)
        if doc:
            tsv = func.to_tsvector("portuguese", DocumentChunk.content)
            tsq = func.plainto_tsquery("portuguese", segment_text)
            rank = func.ts_rank_cd(tsv, tsq)

            stmt = (
                select(DocumentChunk, rank.label("rank"))
                .where(DocumentChunk.document_id == session.document_id)
                .where(tsv.op("@@")(tsq))
                .order_by(desc(rank))
                .limit(5)
            )
            result = await db.execute(stmt)
            rows = result.all()

            if rows:
                fetched_chunks = [chunk for (chunk, _rank) in rows]
                evidence_chunk_ids = [c.id for c in fetched_chunks]
                chunks_content = [c.content for c in fetched_chunks]

    # Tenta LLM real
    try:
        from app.services.llm_service import generate_question

        system_prompt = _load_system_prompt(profile_key)
        full_prompt = _build_full_prompt(system_prompt, segment_text, chunks_content)
        result = await generate_question(full_prompt)
        return {**result, "evidence_chunk_ids": evidence_chunk_ids}

    except RuntimeError as exc:
        logger.debug("LLM não configurado, usando stub. Motivo: %s", exc)
    except Exception as exc:
        # Falha na chamada LLM — loga e usa stub
        logger.warning("Falha ao chamar LLM, usando stub. Erro: %s", exc)

    # ---------------------
    # Stub fallback
    # ---------------------
    topic = segment_text.strip().replace("\n", " ")[:80].rstrip() or "esse ponto"

    evidence_point = "algum ponto relevante do documento"
    if chunks_content:
        snippet = chunks_content[0].strip().replace("\n", " ")
        evidence_point = snippet[:120].rstrip() + ("..." if len(snippet) > 120 else "")

    return {
        "question_text": (
            f"Explique melhor: {topic}. "
            f"Como isso se relaciona com {evidence_point}?"
        ),
        "intent": "general",
        "difficulty": 3,
        "evidence_chunk_ids": evidence_chunk_ids,
    }
