"""
Vector Service — embedding generation and semantic search via pgvector.

Uses OpenAI text-embedding-3-small (1536 dims) for embeddings.
Uses pgvector's <=> operator (cosine distance) for similarity search.
"""
import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.models.session import Session

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100


async def embed_text(text: str) -> list[float]:
    """
    Gera embedding de um texto via OpenAI text-embedding-3-small.
    Raises RuntimeError se OPENAI_API_KEY não estiver configurada.
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada para embeddings.")

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)
    response = await client.embeddings.create(
        input=text[:8000],
        model=_EMBEDDING_MODEL,
    )
    return response.data[0].embedding


async def embed_chunks(db: AsyncSession, chunks: list[DocumentChunk]) -> None:
    """
    Gera embeddings para uma lista de chunks em batches de 100.
    Persiste os vetores via SQLAlchemy (flush após cada batch).
    Silencia erros — chunks sem embedding usarão FTS como fallback.
    """
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY não configurada — embeddings não gerados")
        return

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=60.0)

    for i in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[i : i + _BATCH_SIZE]
        texts = [c.content[:8000] for c in batch]

        try:
            response = await client.embeddings.create(
                input=texts,
                model=_EMBEDDING_MODEL,
            )
            for chunk, data in zip(batch, response.data):
                chunk.embedding = data.embedding
        except Exception as exc:
            logger.warning(
                "Falha ao gerar embeddings (batch %d): %s",
                i // _BATCH_SIZE,
                exc,
            )

    await db.flush()


async def search_similar_chunks(
    db: AsyncSession,
    session_id: int,
    query_text: str,
    limit: int = 5,
) -> list[DocumentChunk]:
    """
    Busca chunks semanticamente similares via cosine distance (<=>).
    Filtra por documento da sessão. Retorna lista vazia se embedding falhar.
    """
    session = await db.get(Session, session_id)
    if not session or session.document_id is None:
        return []

    try:
        query_embedding = await embed_text(query_text)
    except Exception as exc:
        logger.warning("Falha ao gerar embedding da query: %s", exc)
        return []

    stmt = (
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == session.document_id,
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())
