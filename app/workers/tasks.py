import asyncio
from celery.utils.log import get_task_logger
from sqlalchemy import delete

from app.workers.celery_app import celery
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.question import Question
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.services.simulation_service import generate_question_stub
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


@celery.task(name="generate_question_for_segment")
def generate_question_for_segment(session_id: int, segment_id: int) -> dict:
    return asyncio.run(_generate_question_for_segment_async(session_id, segment_id))


async def _generate_question_for_segment_async(session_id: int, segment_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        segment = await db.get(TranscriptSegment, segment_id)
        if not segment or segment.session_id != session_id:
            return {"ok": False, "error": "Segmento não encontrado para a sessão"}

        session = await db.get(Session, session_id)
        if not session:
            return {"ok": False, "error": "Sessão não encontrada"}

        doc = None
        if session.document_id is not None:
            doc = await db.get(Document, session.document_id)

        payload = await generate_question_stub(db, session_id=session_id, segment_text=segment.text)

        question = Question(
            session_id=session_id,
            question_text=payload["question_text"],
            intent=payload["intent"],
            difficulty=payload["difficulty"],
            evidence_chunk_ids=payload["evidence_chunk_ids"],
        )
        db.add(question)
        await db.commit()

        return {
            "ok": True,
            "session_id": session_id,
            "segment_id": segment_id,
            "question_id": question.id,
            "has_document": doc is not None,
        }
