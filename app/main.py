from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.models  # garante import dos models
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.profiles import router as profiles_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.websocket import router as websocket_router
from app.core.logging import setup_logging
from app.services.redis_service import close_redis

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_redis()


app = FastAPI(title="Podium Backend", lifespan=lifespan)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("podium").error(f"Erro não tratado em {request.url}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(profiles_router)
app.include_router(sessions_router)
app.include_router(websocket_router)
