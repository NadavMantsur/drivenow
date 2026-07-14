import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response as StarletteResponse

REQUEST_COUNT = Counter(
    "drivenow_http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "drivenow_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "method", "endpoint"],
)
ONGOING_RENTALS = Gauge(
    "drivenow_rentals_ongoing",
    "Number of ongoing rentals",
)


def set_ongoing_rentals(count: int) -> None:
    ONGOING_RENTALS.set(count)


def metrics_response() -> StarletteResponse:
    return StarletteResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def endpoint_label(request: Request) -> str:
    """Low-cardinality route template (e.g. /rentals/{rental_id}/end), not the raw URL path."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "unmatched"


def install_metrics_middleware(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        endpoint = endpoint_label(request)
        REQUEST_LATENCY.labels(service_name, request.method, endpoint).observe(elapsed)
        REQUEST_COUNT.labels(
            service_name,
            request.method,
            endpoint,
            str(response.status_code),
        ).inc()
        return response
