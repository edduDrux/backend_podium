"""
Vector Service — geração e busca de embeddings via OpenAI text-embedding-3-small.

Usado para busca semântica de chunks como alternativa/complemento ao FTS.
Requer OPENAI_API_KEY configurada no .env.
"""
import math
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIMS = 1536


async def get_embedding(text: str) -> list[float] | None:
    """
    Gera o embedding de um texto via OpenAI.
    Retorna None se OPENAI_API_KEY não estiver configurada ou se falhar.
    """
    if not settings.openai_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"input": text[:8000], "model": _EMBEDDING_MODEL},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception as exc:
        logger.warning("Falha ao gerar embedding: %s", exc)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similaridade cosseno entre dois vetores."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def rank_chunks_by_similarity(
    query_embedding: list[float],
    chunks: list[tuple[int, list[float] | None, str]],
    top_k: int = 5,
) -> list[tuple[int, float, str]]:
    """
    Dado um embedding de query e uma lista de (chunk_id, embedding, content),
    retorna os top_k chunks ordenados por similaridade cosseno.
    Ignora chunks sem embedding.
    """
    scored = []
    for chunk_id, emb, content in chunks:
        if emb is None:
            continue
        score = cosine_similarity(query_embedding, emb)
        scored.append((chunk_id, score, content))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
