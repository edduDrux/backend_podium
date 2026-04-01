"""
Testes do STT service — mocka a API Whisper da OpenAI.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.stt_service import transcribe_audio


def _make_whisper_response(text: str):
    """Cria mock que imita o retorno de audio.transcriptions.create."""
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Arquivo pequeno (envio direto)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.stt_service.settings")
@patch("app.services.stt_service.AsyncOpenAI")
async def test_transcribe_small_file(mock_openai_cls, mock_settings, tmp_path):
    """Arquivo <= 24MB é transcrito diretamente."""
    mock_settings.openai_api_key = "test-key"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        return_value=_make_whisper_response(
            "O modelo de negócio é baseado em assinaturas recorrentes."
        )
    )
    mock_openai_cls.return_value = mock_client

    audio_file = tmp_path / "small.mp3"
    audio_file.write_bytes(b"\x00" * 1000)

    result = await transcribe_audio(audio_file)

    assert "assinaturas recorrentes" in result
    mock_client.audio.transcriptions.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# Arquivo grande (chunking via pydub)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.stt_service._transcribe_file", new_callable=AsyncMock)
@patch("app.services.stt_service.settings")
async def test_transcribe_large_file_chunks(mock_settings, mock_transcribe, tmp_path):
    """Arquivo > 24MB é dividido em chunks e cada chunk é transcrito."""
    mock_settings.openai_api_key = "test-key"
    mock_settings.uploads_dir = str(tmp_path)

    mock_transcribe.return_value = "Trecho transcrito."

    # Create a file and patch the threshold so it triggers chunking
    audio_file = tmp_path / "big.mp3"
    audio_file.write_bytes(b"\x00" * 2000)

    # Mock pydub AudioSegment (60s audio, 2000 bytes → ~24s per chunk at 1000B limit)
    mock_audio = MagicMock()
    mock_audio.__len__ = MagicMock(return_value=60_000)  # 60 seconds

    # Make slicing return a segment that can be exported
    mock_chunk = MagicMock()
    mock_chunk.export = MagicMock()
    mock_audio.__getitem__ = MagicMock(return_value=mock_chunk)

    with patch("app.services.stt_service._CHUNK_MAX_BYTES", 1000), \
         patch("pydub.AudioSegment.from_file", return_value=mock_audio):
        result = await transcribe_audio(audio_file)

    assert "Trecho transcrito" in result
    assert mock_transcribe.await_count >= 2


# ---------------------------------------------------------------------------
# Formato não suportado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.stt_service.settings")
async def test_transcribe_unsupported_format(mock_settings, tmp_path):
    """Extensão não suportada deve levantar ValueError."""
    mock_settings.openai_api_key = "test-key"

    bad_file = tmp_path / "audio.txt"
    bad_file.write_bytes(b"not audio")

    with pytest.raises(ValueError, match="não suportado"):
        await transcribe_audio(bad_file)


# ---------------------------------------------------------------------------
# Sem API key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.stt_service.settings")
async def test_transcribe_without_api_key(mock_settings, tmp_path):
    """Sem OPENAI_API_KEY deve levantar RuntimeError."""
    mock_settings.openai_api_key = None

    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"\x00" * 100)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await transcribe_audio(audio_file)


# ---------------------------------------------------------------------------
# Retry em falha
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.stt_service.asyncio.sleep", new_callable=AsyncMock)
@patch("app.services.stt_service.settings")
@patch("app.services.stt_service.AsyncOpenAI")
async def test_transcribe_retries_on_failure(
    mock_openai_cls, mock_settings, mock_sleep, tmp_path
):
    """Primeira tentativa falha, segunda retorna resultado."""
    mock_settings.openai_api_key = "test-key"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=[
            Exception("Connection error"),
            _make_whisper_response("Transcrição após retry."),
        ]
    )
    mock_openai_cls.return_value = mock_client

    audio_file = tmp_path / "retry.wav"
    audio_file.write_bytes(b"\x00" * 500)

    result = await transcribe_audio(audio_file)

    assert "Transcrição após retry" in result
    assert mock_client.audio.transcriptions.create.await_count == 2
    mock_sleep.assert_awaited_once_with(2)
