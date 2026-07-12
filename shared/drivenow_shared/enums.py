"""Shared domain enums used across DriveNow services."""

from enum import Enum


class CarStatus(str, Enum):
    AVAILABLE = "available"
    IN_USE = "in_use"
    UNDER_MAINTENANCE = "under_maintenance"


class DomainEventType(str, Enum):
    CAR_CREATED = "car.created"
    CAR_UPDATED = "car.updated"
    CAR_STATUS_CHANGED = "car.status_changed"
    RENTAL_CREATED = "rental.created"
    RENTAL_ENDED = "rental.ended"
