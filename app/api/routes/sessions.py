from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.session import Session
from app.models.transcript import TranscriptSegment
from app.schemas.transcript import SegmentIn, SegmentOut


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
