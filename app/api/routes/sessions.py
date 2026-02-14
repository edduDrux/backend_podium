from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document
from app.models.profile import SimulationProfile
from app.models.session import Session
from app.schemas.session import SessionCreate, SessionOut


router = APIRouter(prefix="/sessions", tags=["sessions"])


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
