from pathlib import Path
import uuid

from fastapi import HTTPException, UploadFile

from app.core.config import settings

MAX_PDF_SIZE = 100 * 1024 * 1024   # 100 MB
MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50 MB

ALLOWED_EXTENSIONS = {"pdf", "pptx", "docx", "wav", "mp3", "mp4", "webm", "ogg"}
AUDIO_EXTENSIONS = {"wav", "mp3", "mp4", "webm", "ogg"}


async def save_upload(file: UploadFile) -> str:
    ext = Path(file.filename).suffix.lstrip(".").lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Tipo de arquivo não suportado: .{ext}")

    max_size = MAX_AUDIO_SIZE if ext in AUDIO_EXTENSIONS else MAX_PDF_SIZE

    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}.{ext}"
    dest = uploads / safe_name

    total = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_size:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Arquivo muito grande")
            f.write(chunk)

    await file.close()
    return str(dest)
