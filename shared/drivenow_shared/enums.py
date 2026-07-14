"""Shared domain enums used across DriveNow services."""

from enum import Enum


class CarStatus(str, Enum):
    """Fleet car lifecycle status."""

    AVAILABLE = "available"
    IN_USE = "in_use"
    UNDER_MAINTENANCE = "under_maintenance"


class DomainEventType(str, Enum):
    """Domain event type names published by services."""

    CAR_CREATED = "car.created"
    CAR_UPDATED = "car.updated"
    CAR_STATUS_CHANGED = "car.status_changed"
    CAR_DELETED = "car.deleted"
    RENTAL_CREATED = "rental.created"
    RENTAL_ENDED = "rental.ended"
