"""
LLM Service — wrapper unificado para OpenAI (GPT-4o-mini) e Google Gemini.

Prioridade: OpenAI se OPENAI_API_KEY estiver configurada, senão Gemini.
Se nenhuma chave estiver disponível, lança RuntimeError para que o caller
possa usar o stub de fallback.
"""
import asyncio
import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def generate_question(prompt: str) -> dict:
    """
    Chama o LLM configurado e retorna dict com:
        question_text, intent, difficulty
    Lança RuntimeError se nenhuma API key estiver configurada.
    """
    if settings.openai_api_key:
        raw = await _call_openai(prompt, settings.openai_api_key)
    elif settings.google_api_key:
        raw = await _call_gemini(prompt, settings.google_api_key)
    else:
        raise RuntimeError(
            "Nenhuma API key de LLM configurada. "
            "Defina OPENAI_API_KEY ou GOOGLE_API_KEY no .env."
        )

    return _parse_response(raw)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

async def _call_openai(prompt: str, api_key: str) -> str:
    for attempt in range(1, 3):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 400,
                },
            )
            if resp.status_code in (429, 503) and attempt < 2:
                logger.warning(f"OpenAI retry {attempt}/2 após status {resp.status_code}")
                await asyncio.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data.get("choices") or len(data["choices"]) == 0:
                raise ValueError("Resposta OpenAI sem choices")
            return data["choices"][0]["message"]["content"]


async def _call_gemini(prompt: str, api_key: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        f"/models/gemini-1.5-flash:generateContent?key={api_key}"
    )
    for attempt in range(1, 3):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 400},
                },
            )
            if resp.status_code in (429, 503) and attempt < 2:
                logger.warning(f"Gemini retry {attempt}/2 após status {resp.status_code}")
                await asyncio.sleep(2)
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    """
    Extrai JSON do response do LLM.
    Remove blocos markdown (```json ... ```) se presentes.
    Retorna fallback seguro se o parse falhar.
    """
    text = raw.strip()

    # Remove fences ```json ... ``` ou ``` ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        # remove primeira e última linha (fences)
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner).strip()

    try:
        data = json.loads(text)
        return {
            "question_text": str(data.get("question_text", text))[:1000],
            "intent": str(data.get("intent", "general")),
            "difficulty": max(1, min(5, int(data.get("difficulty", 3)))),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        # LLM retornou texto livre em vez de JSON — usa como question_text
        return {
            "question_text": text[:1000] if text else "Pergunta não disponível.",
            "intent": "general",
            "difficulty": 3,
        }
