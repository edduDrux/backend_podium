import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import get_current_user
from app.core.database import get_db
from app.core.enums import SessionStatus
from app.core.config import settings
from app.models.document import Document
from app.models.profile import SimulationProfile
from app.models.question import Question
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.schemas.question import QuestionOut
from app.schemas.session import SessionCreate, SessionOut
from app.schemas.transcript import SegmentIn, SegmentOut
from app.services.analytics_service import get_session_analytics
from app.workers.tasks import (
    generate_question_for_segment,
    generate_session_feedback,
    transcribe_and_process_audio,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------

@router.post("", response_model=SessionOut)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = await db.get(Document, payload.document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    profile = await db.get(SimulationProfile, payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de simulação não encontrado.")

    if document.status not in ("CHUNKED", "READY"):
        raise HTTPException(
            status_code=409,
            detail=f"Documento ainda não está pronto para simulação. Status: {document.status}",
        )

    session = Session(
        document_id=payload.document_id,
        profile_id=payload.profile_id,
        status=SessionStatus.READY,
        user_id=current_user.id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")
    return session


# ---------------------------------------------------------------------------
# Segmentos de transcrição
# ---------------------------------------------------------------------------

@router.post("/{session_id}/segments", response_model=SegmentOut)
async def create_segment(
    session_id: int,
    payload: SegmentIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    segment = TranscriptSegment(
        session_id=session_id,
        text=payload.text,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
    )
    db.add(segment)

    if session.status == SessionStatus.READY:
        session.status = SessionStatus.RUNNING

    await db.commit()
    await db.refresh(segment)

    generate_question_for_segment.delay(session_id, segment.id)

    return segment


@router.get("/{session_id}/segments", response_model=list[SegmentOut])
async def list_segments(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Perguntas
# ---------------------------------------------------------------------------

@router.get("/{session_id}/questions", response_model=list[QuestionOut])
async def list_questions(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    stmt = (
        select(Question)
        .where(Question.session_id == session_id)
        .order_by(Question.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Áudio (STT)
# ---------------------------------------------------------------------------

@router.post("/{session_id}/audio", status_code=202)
async def upload_audio(
    session_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload de áudio para transcrição via Whisper.
    Aceita mp3, mp4, mpeg, mpga, m4a, wav, webm (até 350MB).
    Retorna 202 com task_id para polling.
    """
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    ACCEPTED_EXTENSIONS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}
    ext = Path(file.filename).suffix.lstrip(".").lower() if file.filename else ""
    if ext not in ACCEPTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Formato não suportado: .{ext}. Use mp3, mp4, m4a, wav ou webm.",
        )

    max_bytes = settings.max_audio_upload_mb * 1024 * 1024
    uploads_dir = Path(settings.uploads_dir) / "audio"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = uploads_dir / f"{uuid.uuid4().hex}.{ext}"

    total = 0
    with dest.open("wb") as f_out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Arquivo excede o limite de {settings.max_audio_upload_mb}MB.",
                )
            f_out.write(chunk)

    result = transcribe_and_process_audio.delay(session_id, str(dest))

    return {
        "detail": "Áudio recebido. Transcrição em andamento.",
        "session_id": session_id,
        "task_id": result.id,
    }


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/{session_id}/analytics")
async def session_analytics(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    return await get_session_analytics(db, session_id)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@router.post("/{session_id}/feedback", status_code=202)
async def request_feedback(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enfileira a geração de feedback consolidado da sessão.
    O resultado ficará disponível em GET /sessions/{id}/feedback.
    Retorna 202 Accepted imediatamente.
    """
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    if session.status == SessionStatus.READY:
        raise HTTPException(
            status_code=409,
            detail="A sessão ainda não foi iniciada. Envie segmentos antes de solicitar feedback.",
        )

    generate_session_feedback.delay(session_id)
    return {"detail": "Geração de feedback enfileirada.", "session_id": session_id}


@router.get("/{session_id}/feedback")
async def get_feedback(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna o feedback gerado. Pode retornar 202 se ainda estiver sendo processado."""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    if not session.feedback_text:
        raise HTTPException(
            status_code=202,
            detail="Feedback ainda não disponível. Tente novamente em instantes.",
        )

    return {
        "session_id": session_id,
        "status": session.status,
        "feedback_text": session.feedback_text,
    }
