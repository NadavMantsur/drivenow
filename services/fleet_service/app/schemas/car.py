from pydantic import BaseModel, ConfigDict, Field

from drivenow_shared.enums import CarStatus


class CarCreate(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    year: int = Field(ge=1900, le=2100)


class CarUpdate(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=120)
    year: int | None = Field(default=None, ge=1900, le=2100)
    status: CarStatus | None = None
    # When set with status, fleet applies an atomic compare-and-set (concurrency-safe).
    expected_status: CarStatus | None = None


class CarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    year: int
    status: CarStatus
