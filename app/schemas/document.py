from datetime import datetime

from pydantic import BaseModel

from app.core.enums import DocumentStatus


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    status: DocumentStatus
    created_at: datetime

    model_config = {"from_attributes": True}
