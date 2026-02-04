import asyncio
from celery.utils.log import get_task_logger
from sqlalchemy import delete

from app.workers.celery_app import celery
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_service import extract_text_from_pdf, chunk_text

logger = get_task_logger(__name__)


@celery.task(name="extract_document_text")
def extract_document_text(document_id: int) -> dict:
    return asyncio.run(_extract_document_text_async(document_id))


async def _extract_document_text_async(document_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, document_id)
        if not doc:
            return {"ok": False, "error": "Documento não encontrado"}

        try:
            doc.status = "PROCESSING"
            await db.commit()

            text = extract_text_from_pdf(doc.storage_path)
            doc.extracted_text = text

            chunks = chunk_text(text, max_chars=1200, overlap=200)

            # remove chunks antigos (reprocessamento seguro)
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )

            # salva chunks novos
            for i, c in enumerate(chunks):
                db.add(DocumentChunk(document_id=doc.id, chunk_index=i, content=c))

            doc.status = "CHUNKED"
            await db.commit()

            logger.info(
                "Documento %s processado: chars=%s chunks=%s",
                doc.id, len(text), len(chunks)
            )

            return {
                "ok": True,
                "document_id": doc.id,
                "chars": len(text),
                "chunks": len(chunks),
            }

        except Exception as e:
            doc.status = "FAILED"
            await db.commit()
            logger.exception("Falha ao processar documento %s: %s", doc.id, e)
            return {"ok": False, "document_id": doc.id, "error": str(e)}
