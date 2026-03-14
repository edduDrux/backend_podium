from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.profile import SimulationProfile
from app.schemas.profile import ProfileOut


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    stmt = select(SimulationProfile).order_by(SimulationProfile.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    profile = await db.get(SimulationProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil de simulação não encontrado.")
    return profile
