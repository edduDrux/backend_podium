from datetime import datetime
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    content_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
