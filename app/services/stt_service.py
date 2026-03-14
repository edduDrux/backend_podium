"""
STT Service — transcrição de áudio via OpenAI Whisper API.

Envia o arquivo de áudio para a API e retorna a lista de segmentos
com timestamps (se verbose_json estiver disponível).
"""
import httpx

from app.core.config import settings


class TranscriptionSegment:
    def __init__(self, text: str, start_ms: int | None, end_ms: int | None):
        self.text = text
        self.start_ms = start_ms
        self.end_ms = end_ms


async def transcribe_audio(file_path: str, filename: str) -> list[TranscriptionSegment]:
    """
    Envia arquivo de áudio para Whisper e retorna lista de segmentos.
    Cada segmento tem text, start_ms e end_ms.
    Lança RuntimeError se nenhuma API key estiver configurada.
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY não configurada. STT requer OpenAI Whisper."
        )

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": (filename, audio_bytes)},
            data={
                "model": "whisper-1",
                "language": "pt",
                "response_format": "verbose_json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # verbose_json retorna {"segments": [{"text", "start", "end"}, ...]}
    raw_segments = data.get("segments", [])

    if raw_segments:
        return [
            TranscriptionSegment(
                text=seg["text"].strip(),
                start_ms=int(seg["start"] * 1000),
                end_ms=int(seg["end"] * 1000),
            )
            for seg in raw_segments
            if seg.get("text", "").strip()
        ]

    # Fallback: transcrição sem timestamps
    full_text = data.get("text", "").strip()
    if full_text:
        return [TranscriptionSegment(text=full_text, start_ms=None, end_ms=None)]

    return []
