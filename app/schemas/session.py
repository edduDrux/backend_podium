from datetime import datetime

from pydantic import BaseModel


class SessionCreate(BaseModel):
    document_id: int
    profile_id: int


class SessionOut(BaseModel):
    id: int
    document_id: int | None
    profile_id: int | None
    status: str
    feedback_text: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
