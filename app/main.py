from fastapi import FastAPI

import app.models  # garante import dos models
from app.api.routes.documents import router as documents_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.websocket import router as websocket_router
from app.api.routes.auth import router as auth_router


app = FastAPI(title="Podium Backend")


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(profiles_router)
app.include_router(sessions_router)
app.include_router(websocket_router)
