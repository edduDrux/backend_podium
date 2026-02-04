from pathlib import Path
import uuid

from fastapi import UploadFile

from app.core.config import settings


async def save_upload(file: UploadFile) -> str:
    uploads = Path(settings.uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = uploads / safe_name

    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    await file.close()
    return str(dest)
