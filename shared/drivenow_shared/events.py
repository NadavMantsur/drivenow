"""Domain event payload contracts (Phase 2 will publish these via RabbitMQ)."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from drivenow_shared.enums import DomainEventType


class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: DomainEventType
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
