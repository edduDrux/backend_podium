import asyncio
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import delete, func, select

from app.workers.celery_app import celery
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.profile import SimulationProfile
from app.models.question import Question
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.services.redis_service import publish_session_event
from app.services.simulation_service import generate_question_stub
from app.services.document_service import extract_text_from_pdf, chunk_text

logger = get_task_logger(__name__)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _is_similar_question_text(a: str, b: str) -> bool:
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    return a_norm == b_norm or a_norm in b_norm or b_norm in a_norm


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

        profile_config = {}
        if session.profile_id is not None:
            profile = await db.get(SimulationProfile, session.profile_id)
            if profile and isinstance(profile.config, dict):
                profile_config = profile.config

        max_questions_per_minute = int(profile_config.get("max_questions_per_minute", 3))
        if max_questions_per_minute < 1:
            max_questions_per_minute = 1

        now_utc = datetime.now(timezone.utc)
        minute_ago = now_utc - timedelta(seconds=60)

        count_stmt = select(func.count(Question.id)).where(
            Question.session_id == session_id,
            Question.created_at >= minute_ago,
        )
        recent_count = int((await db.execute(count_stmt)).scalar_one())
        if recent_count >= max_questions_per_minute:
            return {
                "ok": True,
                "session_id": session_id,
                "segment_id": segment_id,
                "created": False,
                "reason": "rate_limited",
                "max_questions_per_minute": max_questions_per_minute,
            }

        last_question_stmt = (
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.id.desc())
            .limit(1)
        )
        last_question = (await db.execute(last_question_stmt)).scalars().first()

        if last_question and last_question.created_at is not None:
            created_at = last_question.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (now_utc - created_at).total_seconds() < 15:
                return {
                    "ok": True,
                    "session_id": session_id,
                    "segment_id": segment_id,
                    "created": False,
                    "reason": "cooldown",
                }

        doc = None
        if session.document_id is not None:
            doc = await db.get(Document, session.document_id)

        payload = await generate_question_stub(db, session_id=session_id, segment_text=segment.text)

        if last_question and _is_similar_question_text(payload["question_text"], last_question.question_text):
            payload["question_text"] = f"{payload['question_text']} Pode trazer um exemplo prático?"

            if _is_similar_question_text(payload["question_text"], last_question.question_text):
                return {
                    "ok": True,
                    "session_id": session_id,
                    "segment_id": segment_id,
                    "created": False,
                    "reason": "duplicate",
                }

        question = Question(
            session_id=session_id,
            question_text=payload["question_text"],
            intent=payload["intent"],
            difficulty=payload["difficulty"],
            evidence_chunk_ids=payload["evidence_chunk_ids"],
        )
        db.add(question)
        await db.commit()
        await db.refresh(question)

        await publish_session_event(
            session_id,
            {
                "type": "question.created",
                "session_id": session_id,
                "question": {
                    "id": question.id,
                    "session_id": question.session_id,
                    "question_text": question.question_text,
                    "intent": question.intent,
                    "difficulty": question.difficulty,
                    "evidence_chunk_ids": question.evidence_chunk_ids,
                    "created_at": question.created_at.isoformat() if question.created_at else None,
                },
            },
        )

        return {
            "ok": True,
            "session_id": session_id,
            "segment_id": segment_id,
            "created": True,
            "question_id": question.id,
            "has_document": doc is not None,
        }
