import asyncio
import difflib
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import delete, func, select

from app.workers.celery_app import celery
from app.core.database import AsyncSessionLocal
from app.core.enums import DocumentStatus, SessionStatus
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.profile import SimulationProfile
from app.models.question import Question
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.services.redis_service import publish_session_event
from app.services.simulation_service import generate_question_stub
from app.services.document_service import extract_text, chunk_text

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# STT task
# ---------------------------------------------------------------------------

@celery.task(name="process_audio_transcription")
def process_audio_transcription(session_id: int, file_path: str, filename: str) -> dict:
    # pool=solo no Windows suporta asyncio.run()
    return asyncio.run(_process_audio_transcription_async(session_id, file_path, filename))


async def _process_audio_transcription_async(
    session_id: int, file_path: str, filename: str
) -> dict:
    async with AsyncSessionLocal() as db:
        session = await db.get(Session, session_id)
        if not session:
            return {"ok": False, "error": "Sessão não encontrada"}

        try:
            from app.services.stt_service import transcribe_audio

            segments = await transcribe_audio(file_path, filename)
            if not segments:
                return {"ok": True, "session_id": session_id, "segments_created": 0}

            created = 0
            for seg in segments:
                transcript_seg = TranscriptSegment(
                    session_id=session_id,
                    text=seg.text,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                )
                db.add(transcript_seg)
                if session.status == SessionStatus.READY:
                    session.status = SessionStatus.RUNNING

                await db.flush()
                generate_question_for_segment.delay(session_id, transcript_seg.id)
                created += 1

            await db.commit()
            logger.info(
                "STT: sessão %s — %s segmentos criados de '%s'",
                session_id, created, filename,
            )
            return {"ok": True, "session_id": session_id, "segments_created": created}

        except Exception as exc:
            logger.exception("Falha no STT para sessão %s: %s", session_id, exc)
            return {"ok": False, "session_id": session_id, "error": str(exc)}


# ---------------------------------------------------------------------------
# Feedback task
# ---------------------------------------------------------------------------

@celery.task(name="generate_session_feedback")
def generate_session_feedback(session_id: int) -> dict:
    # pool=solo no Windows suporta asyncio.run()
    return asyncio.run(_generate_session_feedback_async(session_id))


async def _generate_session_feedback_async(session_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        session = await db.get(Session, session_id)
        if not session:
            return {"ok": False, "error": "Sessão não encontrada"}

        # Coleta segmentos
        seg_stmt = (
            select(TranscriptSegment)
            .where(TranscriptSegment.session_id == session_id)
            .order_by(TranscriptSegment.id.asc())
        )
        segments = list((await db.execute(seg_stmt)).scalars().all())

        # Coleta perguntas geradas
        q_stmt = (
            select(Question)
            .where(Question.session_id == session_id)
            .order_by(Question.id.asc())
        )
        questions = list((await db.execute(q_stmt)).scalars().all())

        if not segments:
            session.feedback_text = "Nenhum segmento de fala registrado para gerar feedback."
            await db.commit()
            return {"ok": True, "session_id": session_id, "generated": False}

        # Monta resumo da apresentação (separador claro entre segmentos)
        transcript_summary = " | ".join(s.text for s in segments)[:3000]
        questions_summary = "\n".join(
            f"- [{q.intent}] {q.question_text}" for q in questions[:20]
        )

        prompt = (
            "Você é um coach de oratória especializado. "
            "Analise a apresentação abaixo e forneça um feedback construtivo em português.\n\n"
            "## Transcrição da apresentação (resumo)\n\n"
            f"{transcript_summary}\n\n"
            "## Perguntas geradas durante a sessão\n\n"
            f"{questions_summary or '(nenhuma pergunta gerada)'}\n\n"
            "## Sua tarefa\n\n"
            "Escreva um feedback em 3 partes:\n"
            "1. **Pontos fortes** — o que foi bem comunicado\n"
            "2. **Pontos de melhoria** — o que pode ser aprimorado\n"
            "3. **Recomendação principal** — uma ação concreta para a próxima apresentação\n\n"
            "Seja específico, direto e encorajador. Máximo de 300 palavras."
        )

        feedback_text = None
        try:
            from app.services.llm_service import _call_openai, _call_gemini
            from app.core.config import settings

            if settings.openai_api_key:
                feedback_text = await _call_openai(prompt, settings.openai_api_key)
            elif settings.google_api_key:
                feedback_text = await _call_gemini(prompt, settings.google_api_key)

            if feedback_text:
                feedback_text = feedback_text.strip()
        except Exception as exc:
            logger.warning("Falha ao gerar feedback via LLM: %s", exc)

        if not feedback_text:
            # Stub de feedback quando LLM não está disponível
            feedback_text = (
                f"Sessão concluída com {len(segments)} segmento(s) de fala "
                f"e {len(questions)} pergunta(s) gerada(s). "
                "Configure OPENAI_API_KEY ou GOOGLE_API_KEY para feedback detalhado."
            )

        session.feedback_text = feedback_text
        session.status = SessionStatus.FINISHED
        await db.commit()

        logger.info("Feedback gerado para sessão %s", session_id)
        return {"ok": True, "session_id": session_id, "generated": True}


# ---------------------------------------------------------------------------
# Helpers de deduplicação
# ---------------------------------------------------------------------------

def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _is_similar_question_text(a: str, b: str) -> bool:
    """Retorna True se as perguntas tiverem > 75% de similaridade."""
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    if a_norm == b_norm:
        return True
    ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
    return ratio > 0.75


# ---------------------------------------------------------------------------
# Document processing task
# ---------------------------------------------------------------------------

@celery.task(name="extract_document_text")
def extract_document_text(document_id: int) -> dict:
    # pool=solo no Windows suporta asyncio.run()
    return asyncio.run(_extract_document_text_async(document_id))


async def _extract_document_text_async(document_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        doc = await db.get(Document, document_id)
        if not doc:
            return {"ok": False, "error": "Documento não encontrado"}

        try:
            doc.status = DocumentStatus.PROCESSING
            await db.commit()

            text = extract_text(doc.storage_path, doc.content_type)
            doc.extracted_text = text

            chunks = chunk_text(text, max_chars=1200, overlap=200)

            # remove chunks antigos (reprocessamento seguro)
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )

            # gera embeddings (opcional — requer OPENAI_API_KEY)
            from app.services.vector_service import get_embedding
            embeddings: list[list[float] | None] = []
            for c in chunks:
                emb = await get_embedding(c)
                embeddings.append(emb)

            # salva chunks novos com embeddings
            for i, (c, emb) in enumerate(zip(chunks, embeddings)):
                db.add(DocumentChunk(
                    document_id=doc.id,
                    chunk_index=i,
                    content=c,
                    embedding=emb,
                ))

            doc.status = DocumentStatus.CHUNKED
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
            doc.status = DocumentStatus.FAILED
            await db.commit()
            logger.exception("Falha ao processar documento %s: %s", doc.id, e)
            return {"ok": False, "document_id": doc.id, "error": str(e)}


# ---------------------------------------------------------------------------
# Question generation task
# ---------------------------------------------------------------------------

@celery.task(name="generate_question_for_segment")
def generate_question_for_segment(session_id: int, segment_id: int) -> dict:
    # pool=solo no Windows suporta asyncio.run()
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

        # Cooldown configurável via perfil, fallback 15s
        cooldown_seconds = int(profile_config.get("cooldown_seconds", 15))

        if last_question and last_question.created_at is not None:
            created_at = last_question.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (now_utc - created_at).total_seconds() < cooldown_seconds:
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
