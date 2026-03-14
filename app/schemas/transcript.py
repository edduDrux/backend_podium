from datetime import datetime

from pydantic import BaseModel, Field


class SegmentIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    start_ms: int | None = None
    end_ms: int | None = None


class SegmentOut(BaseModel):
    id: int
    session_id: int
    text: str
    start_ms: int | None
    end_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
