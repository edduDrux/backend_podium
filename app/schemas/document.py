from datetime import datetime

from pydantic import BaseModel

from app.core.enums import DocumentStatus


class DocumentOut(BaseModel):
    id: int
    user_id: int | None = None
    filename: str
    content_type: str
    status: DocumentStatus
    created_at: datetime

    model_config = {"from_attributes": True}
