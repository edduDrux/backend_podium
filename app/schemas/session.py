from datetime import datetime

from pydantic import BaseModel

from app.core.enums import SessionStatus


class SessionCreate(BaseModel):
    document_id: int
    profile_id: int


class SessionOut(BaseModel):
    id: int
    user_id: int | None = None
    document_id: int | None
    profile_id: int | None
    status: SessionStatus
    feedback_text: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
