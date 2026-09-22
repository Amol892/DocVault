from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ActivityLogOut(BaseModel):
    id: str
    actor_id: str
    actor_name: str
    action: str
    target_type: str | None
    target_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
