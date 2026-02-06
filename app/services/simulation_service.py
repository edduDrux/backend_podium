from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.session import Session


async def generate_question_stub(db: AsyncSession, session_id: int, segment_text: str) -> dict:
    session = await db.get(Session, session_id)

    doc = None
    if session and session.document_id is not None:
        doc = await db.get(Document, session.document_id)

    evidence_chunk_ids: list[int] = []
    evidence_point = "algum ponto relevante do documento"

    if session and doc:
        tsv = func.to_tsvector("portuguese", DocumentChunk.content)
        tsq = func.plainto_tsquery("portuguese", segment_text)
        rank = func.ts_rank_cd(tsv, tsq)

        stmt = (
            select(DocumentChunk, rank.label("rank"))
            .where(DocumentChunk.document_id == session.document_id)
            .where(tsv.op("@@")(tsq))
            .order_by(desc(rank))
            .limit(5)
        )
        result = await db.execute(stmt)
        rows = result.all()

        if rows:
            chunks = [chunk for (chunk, _rank) in rows]
            evidence_chunk_ids = [c.id for c in chunks]
            snippet = chunks[0].content.strip().replace("\n", " ")
            evidence_point = snippet[:120].rstrip() + ("..." if len(snippet) > 120 else "")

    topic = segment_text.strip().replace("\n", " ")[:80].rstrip()
    if not topic:
        topic = "esse ponto"

    question_text = f"Explique melhor: {topic}. Como isso se relaciona com {evidence_point}?"

    return {
        "question_text": question_text,
        "intent": "general",
        "difficulty": 3,
        "evidence_chunk_ids": evidence_chunk_ids,
    }
