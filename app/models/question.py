from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    question_text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(40), default="general")
    difficulty: Mapped[int] = mapped_column(Integer, default=3)
    evidence_chunk_ids: Mapped[list[int]] = mapped_column(JSON)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
