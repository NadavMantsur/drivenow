from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.core.database import engine
from app.core.metrics import metrics_response

router = APIRouter(tags=["ops"])


def database_ready() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/health")
def health() -> dict[str, str]:
    if not database_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "ok", "service": "rental-service"}


@router.get("/metrics")
def metrics():
    return metrics_response()
