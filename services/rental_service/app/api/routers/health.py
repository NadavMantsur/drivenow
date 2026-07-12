from fastapi import APIRouter

from app.core.metrics import metrics_response

router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rental-service"}


@router.get("/metrics")
def metrics():
    return metrics_response()
