"""
STT Service — transcrição de áudio via OpenAI Whisper API.

Arquivos <= 24MB são enviados diretamente.
Arquivos > 24MB são divididos em chunks com 2s de overlap via pydub.
"""
import asyncio
import logging
import tempfile
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_CHUNK_MAX_BYTES = 24 * 1024 * 1024  # 24MB (Whisper limit = 25MB)
_OVERLAP_MS = 2000
_MAX_RETRIES = 2

SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}


async def transcribe_audio(file_path: Path, language: str = "pt") -> str:
    """
    Transcreve áudio via OpenAI Whisper.

    <= 24MB: envio direto.
    > 24MB: divide em chunks de ~24MB com 2s de overlap (pydub).

    Returns: transcrição completa como string.
    """
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada. STT requer OpenAI Whisper.")

    file_path = Path(file_path)

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Formato de áudio não suportado: {suffix}. "
            f"Use: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    file_size = file_path.stat().st_size

    if file_size <= _CHUNK_MAX_BYTES:
        return await _transcribe_file(file_path, language)

    return await _transcribe_chunked(file_path, language)


async def _transcribe_file(file_path: Path, language: str) -> str:
    """Transcreve um único arquivo via Whisper API com retry."""
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=120.0)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language=language,
                )
            return response.text
        except Exception as exc:
            if attempt < _MAX_RETRIES:
                logger.warning("Whisper retry %d/%d: %s", attempt, _MAX_RETRIES, exc)
                await asyncio.sleep(2)
                continue
            logger.error("Falha no Whisper após %d tentativas: %s", _MAX_RETRIES, exc)
            raise


async def _transcribe_chunked(file_path: Path, language: str) -> str:
    """Divide áudio grande em chunks via pydub e transcreve cada um."""
    from pydub import AudioSegment

    logger.info(
        "Arquivo grande (%d bytes), dividindo em chunks",
        file_path.stat().st_size,
    )

    audio = AudioSegment.from_file(str(file_path))
    file_size = file_path.stat().st_size
    total_ms = len(audio)

    if total_ms == 0:
        return ""

    # Chunk duration estimated from source bitrate, with 80% safety margin
    bytes_per_ms = file_size / total_ms
    chunk_ms = int((_CHUNK_MAX_BYTES * 0.8) / bytes_per_ms)
    chunk_ms = max(chunk_ms, 10_000)  # minimum 10s per chunk

    parts: list[str] = []
    start = 0
    chunk_num = 0
    uploads_dir = Path(settings.uploads_dir)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    while start < total_ms:
        end = min(start + chunk_ms, total_ms)
        segment = audio[start:end]
        chunk_num += 1

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=str(uploads_dir)
            ) as tmp:
                tmp_path = Path(tmp.name)

            segment.export(str(tmp_path), format="mp3")

            logger.info("Transcrevendo chunk %d (%d–%d ms)", chunk_num, start, end)
            text = await _transcribe_file(tmp_path, language)
            if text.strip():
                parts.append(text.strip())
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        if end >= total_ms:
            break

        next_start = end - _OVERLAP_MS
        if next_start <= start:
            next_start = end
        start = next_start

    return " ".join(parts)
