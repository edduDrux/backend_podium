"""
Testes do LLM service — mocka o cliente OpenAI.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_service import generate_question


def _make_openai_response(content: str):
    """Cria um objeto mock que imita ChatCompletion da OpenAI."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
@patch("app.services.llm_service.settings")
@patch("app.services.llm_service.AsyncOpenAI")
async def test_returns_dict_with_correct_fields(mock_openai_cls, mock_settings):
    """Resposta JSON válida deve retornar dict com question_text, intent, difficulty."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_model = "gpt-4o-mini"

    payload = {
        "question_text": "Como você justifica essa metodologia?",
        "intent": "validate_methodology",
        "difficulty": 4,
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response(json.dumps(payload))
    )
    mock_openai_cls.return_value = mock_client

    result = await generate_question(
        profile_key="academic",
        document_chunks=["Trecho sobre metodologia qualitativa."],
        transcription_segment="Utilizamos entrevistas semiestruturadas.",
        previous_questions=[],
    )

    assert result is not None
    assert result["question_text"] == "Como você justifica essa metodologia?"
    assert result["intent"] == "validate_methodology"
    assert result["difficulty"] == 4

    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.llm_service.settings")
@patch("app.services.llm_service.AsyncOpenAI")
async def test_returns_none_on_invalid_json(mock_openai_cls, mock_settings):
    """JSON inválido do LLM deve retornar None."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_model = "gpt-4o-mini"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response("isso não é json nenhum")
    )
    mock_openai_cls.return_value = mock_client

    result = await generate_question(
        profile_key="corporate",
        document_chunks=["Receita projetada de R$ 500k."],
        transcription_segment="Nosso modelo de negócio é B2B SaaS.",
    )

    assert result is None


@pytest.mark.asyncio
@patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.llm_service.settings")
@patch("app.services.llm_service.AsyncOpenAI")
async def test_retries_on_rate_limit(mock_openai_cls, mock_settings, mock_sleep):
    """RateLimitError deve causar retry e retornar resultado na segunda tentativa."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_model = "gpt-4o-mini"

    from openai import RateLimitError
    import httpx

    error = RateLimitError(
        message="Rate limit exceeded",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )

    payload = {
        "question_text": "Qual o diferencial competitivo?",
        "intent": "assess_business_value",
        "difficulty": 3,
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[error, _make_openai_response(json.dumps(payload))]
    )
    mock_openai_cls.return_value = mock_client

    result = await generate_question(
        profile_key="corporate",
        document_chunks=["Mercado de R$ 2 bilhões."],
        transcription_segment="Nosso produto resolve a dor X.",
    )

    assert result is not None
    assert result["question_text"] == "Qual o diferencial competitivo?"
    assert mock_client.chat.completions.create.await_count == 2
    mock_sleep.assert_awaited_once_with(2)  # 2^1 = 2s backoff


@pytest.mark.asyncio
@patch("app.services.llm_service.asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.llm_service.settings")
@patch("app.services.llm_service.AsyncOpenAI")
async def test_returns_none_after_max_retries(mock_openai_cls, mock_settings, mock_sleep):
    """Retorna None quando todas as 3 tentativas falharem com rate limit."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_model = "gpt-4o-mini"

    from openai import RateLimitError
    import httpx

    error = RateLimitError(
        message="Rate limit exceeded",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=error)
    mock_openai_cls.return_value = mock_client

    result = await generate_question(
        profile_key="academic",
        document_chunks=[],
        transcription_segment="Teste de resiliência.",
    )

    assert result is None
    assert mock_client.chat.completions.create.await_count == 3


@pytest.mark.asyncio
@patch("app.services.llm_service.settings")
async def test_returns_none_without_api_key(mock_settings):
    """Sem OPENAI_API_KEY, deve retornar None sem chamar a API."""
    mock_settings.openai_api_key = None

    result = await generate_question(
        profile_key="interview",
        document_chunks=["Experiência em liderança."],
        transcription_segment="Liderei uma equipe de 5 pessoas.",
    )

    assert result is None


@pytest.mark.asyncio
@patch("app.services.llm_service.settings")
@patch("app.services.llm_service.AsyncOpenAI")
async def test_clamps_difficulty_to_valid_range(mock_openai_cls, mock_settings):
    """Dificuldade fora do range 1-5 deve ser clamped."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.llm_model = "gpt-4o-mini"

    payload = {
        "question_text": "Teste de clamp",
        "intent": "general",
        "difficulty": 99,
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_openai_response(json.dumps(payload))
    )
    mock_openai_cls.return_value = mock_client

    result = await generate_question(
        profile_key="auditorium",
        document_chunks=[],
        transcription_segment="Teste.",
    )

    assert result is not None
    assert result["difficulty"] == 5
