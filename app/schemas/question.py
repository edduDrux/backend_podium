from datetime import datetime

from pydantic import BaseModel


class QuestionOut(BaseModel):
    id: int
    session_id: int
    question_text: str
    intent: str
    difficulty: int
    evidence_chunk_ids: list[int]
    created_at: datetime

    model_config = {"from_attributes": True}
