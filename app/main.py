from fastapi import FastAPI

from app.core.database import Base, engine
import app.models  # garante import dos models
from app.api.routes.documents import router as documents_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.websocket import router as websocket_router


app = FastAPI(title="Podium Backend (MVP)")


@app.on_event("startup")
async def on_startup():
    # MVP: cria tabelas automaticamente (mais tarde a gente troca por Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(documents_router)
app.include_router(profiles_router)
app.include_router(sessions_router)
# WebSocket sem prefixo extra para manter padrão /sessions/{session_id}/live
app.include_router(websocket_router)
