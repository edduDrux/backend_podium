from datetime import datetime

from pydantic import BaseModel


class SessionCreate(BaseModel):
    document_id: int
    profile_id: int


class SessionOut(BaseModel):
    id: int
    document_id: int
    profile_id: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
