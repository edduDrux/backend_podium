from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProfileOut(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    config: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
