from datetime import datetime

from pydantic import BaseModel, field_validator

from app.core.enums import QuestionIntent


class QuestionOut(BaseModel):
    id: int
    session_id: int
    question_text: str
    intent: str
    difficulty: int
    evidence_chunk_ids: list[int]
    created_at: datetime

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: int) -> int:
        if not (1 <= v <= 5):
            raise ValueError("difficulty deve estar entre 1 e 5")
        return v

    model_config = {"from_attributes": True}
