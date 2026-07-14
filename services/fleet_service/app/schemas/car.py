from pydantic import BaseModel, ConfigDict, Field, model_validator

from drivenow_shared.enums import CarStatus


class CarCreate(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1900, le=2100)


class CarDetailsUpdate(BaseModel):
    """Update model and/or year only (not status)."""

    model: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"model": "Corolla Hybrid", "year": 2025},
        }
    )

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "CarDetailsUpdate":
        if self.model is None and self.year is None:
            raise ValueError("Provide at least one of model or year to update")
        return self


class CarStatusUpdate(BaseModel):
    """Update car status. Optional expected_status enables compare-and-set (used by rental)."""

    status: CarStatus
    expected_status: CarStatus | None = Field(
        default=None,
        description="Optional CAS: only apply if the car currently has this status.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "under_maintenance"},
        }
    )


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    year: int
    status: CarStatus


class CarActionResponse(BaseModel):
    message: str
    car: CarRead


class MessageResponse(BaseModel):
    message: str
