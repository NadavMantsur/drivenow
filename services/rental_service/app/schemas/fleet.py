from pydantic import BaseModel, ConfigDict

from drivenow_shared.enums import CarStatus


class FleetCar(BaseModel):
    """Car payload returned by fleet-service HTTP APIs."""

    model_config = ConfigDict(extra="ignore")

    id: int
    model: str
    year: int
    status: CarStatus
