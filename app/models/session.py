from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("simulation_profiles.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="READY")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
