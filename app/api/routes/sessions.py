from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.question import Question
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.schemas.question import QuestionOut
from app.schemas.transcript import SegmentIn, SegmentOut
from app.workers.tasks import generate_question_for_segment


router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/{session_id}/segments", response_model=SegmentOut)
async def create_segment(
    session_id: int,
    payload: SegmentIn,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    segment = TranscriptSegment(
        session_id=session_id,
        text=payload.text,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
    )
    db.add(segment)

    if session.status == "READY":
        session.status = "RUNNING"

    await db.commit()
    await db.refresh(segment)

    generate_question_for_segment.delay(session_id, segment.id)

    return segment


@router.get("/{session_id}/segments", response_model=list[SegmentOut])
async def list_segments(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    stmt = (
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{session_id}/questions", response_model=list[QuestionOut])
async def list_questions(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    stmt = (
        select(Question)
        .where(Question.session_id == session_id)
        .order_by(Question.id.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
@router.post("", response_model=SessionOut)
async def create_session(payload: SessionCreate, db: AsyncSession = Depends(get_db)):
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

    session = Session(document_id=payload.document_id, profile_id=payload.profile_id, status="READY")
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return session


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return session
