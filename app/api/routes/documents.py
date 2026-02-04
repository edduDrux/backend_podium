from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func, desc
from app.models.document_chunk import DocumentChunk
from app.schemas.chunk import DocumentChunkOut, ChunkSearchHit


from app.workers.tasks import extract_document_text
from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.services.storage_service import save_upload
from fastapi import Query



router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    # MVP: só PDF por enquanto
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="No MVP, envie apenas PDF (application/pdf).")

    storage_path = await save_upload(file)

    doc = Document(
        filename=file.filename,
        content_type=file.content_type,
        storage_path=storage_path,
        status="QUEUED",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # dispara job assíncrono
    extract_document_text.delay(doc.id)

    return doc



@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return doc


@router.get("/{document_id}/text", response_class=PlainTextResponse)
async def get_document_text(document_id: int, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if not doc.extracted_text:
        raise HTTPException(status_code=409, detail=f"Sem texto ainda. Status atual: {doc.status}")
    return doc.extracted_text


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkOut])
async def list_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if doc.status not in ("CHUNKED", "READY"):
        raise HTTPException(status_code=409, detail=f"Documento ainda não está pronto. Status: {doc.status}")

    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/{document_id}/search", response_model=list[ChunkSearchHit])
async def search_chunks(
    document_id: int,
    q: str = Query(..., min_length=2, max_length=200),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    if doc.status not in ("CHUNKED", "READY"):
        raise HTTPException(status_code=409, detail=f"Documento ainda não está pronto. Status: {doc.status}")

    # Full Text Search no Postgres
    tsv = func.to_tsvector("portuguese", DocumentChunk.content)
    tsq = func.plainto_tsquery("portuguese", q)
    rank = func.ts_rank_cd(tsv, tsq)

stmt = (
    select(DocumentChunk, rank.label("rank"))
    .where(DocumentChunk.document_id == document_id)
    .where(tsv.op("@@")(tsq))
    .order_by(desc("rank"))
    .limit(limit)
)

    res = await db.execute(stmt)
    rows = res.all()

    return [{"rank": float(r), "chunk": c} for (c, r) in rows]
