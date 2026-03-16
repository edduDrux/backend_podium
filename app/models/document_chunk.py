from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_chunk_document_index", "document_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
    )

    chunk_index: Mapped[int] = mapped_column(Integer)  # ordem do chunk no doc
    content: Mapped[str] = mapped_column(Text)

    # Embedding gerado via OpenAI text-embedding-3-small (1536 dims)
    # Armazenado como JSON (lista de floats) — compatível com SQLite e PostgreSQL
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
