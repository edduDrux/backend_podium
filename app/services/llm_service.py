"""
LLM Service — integração real com OpenAI via cliente oficial.

Usa structured outputs (JSON schema) para garantir formato consistente.
Retry com exponential backoff em rate limits. Timeout de 15s por chamada.
"""
import asyncio
import json
import logging
from pathlib import Path

from openai import AsyncOpenAI, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_QUESTION_SCHEMA = {
    "name": "question_response",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "question_text": {"type": "string"},
            "intent": {
                "type": "string",
                "enum": [
                    "validate_methodology",
                    "test_concepts",
                    "challenge_assumptions",
                    "assess_business_value",
                    "probe_resume",
                    "behavioral_assessment",
                    "stress_test",
                    "general",
                ],
            },
            "difficulty": {"type": "integer"},
        },
        "required": ["question_text", "intent", "difficulty"],
        "additionalProperties": False,
    },
}

_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _load_system_prompt(profile_key: str) -> str:
    base_file = _PROMPTS_DIR / "base.md"
    base = base_file.read_text(encoding="utf-8") if base_file.exists() else ""

    profile_file = _PROMPTS_DIR / "profiles" / f"{profile_key}.md"
    if profile_file.exists():
        profile_text = profile_file.read_text(encoding="utf-8")
        return f"{base}\n\n---\n\n{profile_text}"

    return base


def _build_user_message(
    document_chunks: list[str],
    transcription_segment: str,
    previous_questions: list[str],
) -> str:
    if document_chunks:
        evidence = "\n\n".join(
            f"[Trecho {i + 1}]: {c.strip()[:400]}"
            for i, c in enumerate(document_chunks)
        )
    else:
        evidence = "(Nenhum trecho relevante encontrado no documento)"

    parts = [
        "## Segmento de fala (o que o apresentador acabou de dizer)\n\n",
        transcription_segment.strip()[:600],
        "\n\n## Evidências do documento\n\n",
        evidence,
    ]

    if previous_questions:
        prev = "\n".join(f"- {q}" for q in previous_questions[-5:])
        parts.append(f"\n\n## Perguntas já feitas (NÃO repita)\n\n{prev}")

    parts.append("\n\n---\n\nGere agora a pergunta no formato JSON especificado.")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Main function — question generation
# ---------------------------------------------------------------------------

async def generate_question(
    profile_key: str,
    document_chunks: list[str],
    transcription_segment: str,
    previous_questions: list[str] = [],
) -> dict | None:
    """
    Gera uma pergunta contextual via OpenAI com structured outputs.

    Returns dict com question_text, intent, difficulty (int 1-5).
    Returns None se o LLM falhar ou não gerar pergunta coerente.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY não configurada — retornando None")
        return None

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=15.0,
    )

    system_prompt = _load_system_prompt(profile_key)
    user_message = _build_user_message(
        document_chunks, transcription_segment, previous_questions,
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.7,
                max_tokens=400,
                response_format={
                    "type": "json_schema",
                    "json_schema": _QUESTION_SCHEMA,
                },
            )

            raw = response.choices[0].message.content
            if not raw:
                logger.warning("LLM retornou conteúdo vazio")
                return None

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("LLM retornou JSON inválido: %s", raw[:200])
                return None

            question_text = data.get("question_text", "").strip()
            if not question_text:
                logger.warning("LLM retornou question_text vazio")
                return None

            return {
                "question_text": question_text[:1000],
                "intent": data.get("intent", "general"),
                "difficulty": max(1, min(5, int(data.get("difficulty", 3)))),
            }

        except RateLimitError:
            if attempt < _MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning(
                    "Rate limit (tentativa %d/%d), retry em %ds",
                    attempt, _MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
                continue
            logger.error("Rate limit após %d tentativas", _MAX_RETRIES)
            return None

        except Exception as exc:
            logger.error("Falha na chamada LLM: %s", exc)
            return None

    return None


# ---------------------------------------------------------------------------
# Helper for unstructured LLM calls (e.g. feedback generation)
# ---------------------------------------------------------------------------

async def call_llm(prompt: str) -> str | None:
    """
    Chamada simples ao LLM para respostas em texto livre (ex: feedback).
    Returns None se falhar.
    """
    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=15.0,
    )

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("Falha na chamada LLM (feedback): %s", exc)
        return None
