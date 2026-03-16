"""
Testes unitários do LLM service — focados no parser de resposta.
Não fazem chamadas reais à API.
"""
import pytest

from app.services.llm_service import _parse_response


def test_parse_valid_json():
    """JSON direto deve ser parseado corretamente."""
    raw = '{"question_text": "O que é aprendizado por reforço?", "intent": "deep_dive", "difficulty": 4}'
    result = _parse_response(raw)
    assert result["question_text"] == "O que é aprendizado por reforço?"
    assert result["intent"] == "deep_dive"
    assert result["difficulty"] == 4


def test_parse_markdown_fence_json():
    """JSON dentro de bloco ```json deve ser extraído corretamente."""
    raw = '```json\n{"question_text": "Explique redes convolucionais.", "intent": "clarification", "difficulty": 3}\n```'
    result = _parse_response(raw)
    assert "redes convolucionais" in result["question_text"]
    assert result["intent"] == "clarification"


def test_parse_plain_markdown_fence():
    """JSON dentro de bloco ``` sem linguagem deve funcionar."""
    raw = '```\n{"question_text": "Como funciona o backpropagation?", "intent": "general", "difficulty": 2}\n```'
    result = _parse_response(raw)
    assert "backpropagation" in result["question_text"]


def test_parse_invalid_json_fallback():
    """Resposta sem JSON válido deve retornar fallback com o texto como question_text."""
    raw = "Isso aqui é uma resposta em texto livre sem JSON."
    result = _parse_response(raw)
    assert result["question_text"] == raw
    assert result["intent"] == "general"
    assert result["difficulty"] == 3


def test_parse_difficulty_clamped():
    """Dificuldade fora de 1-5 deve ser fixada no intervalo."""
    raw = '{"question_text": "Teste", "intent": "general", "difficulty": 99}'
    result = _parse_response(raw)
    assert result["difficulty"] == 5

    raw2 = '{"question_text": "Teste", "intent": "general", "difficulty": -1}'
    result2 = _parse_response(raw2)
    assert result2["difficulty"] == 1


def test_parse_missing_fields_use_defaults():
    """Campos ausentes no JSON devem usar valores padrão."""
    raw = '{"question_text": "Somente o texto"}'
    result = _parse_response(raw)
    assert result["question_text"] == "Somente o texto"
    assert result["intent"] == "general"
    assert result["difficulty"] == 3


def test_parse_empty_string_fallback():
    """String vazia deve retornar fallback com mensagem padrão."""
    result = _parse_response("")
    assert result["question_text"] == "Pergunta não disponível."
