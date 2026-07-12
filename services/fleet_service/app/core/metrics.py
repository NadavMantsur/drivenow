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
AVAILABLE_CARS = Gauge(
    "drivenow_cars_available",
    "Number of cars with available status",
)


def set_available_cars(count: int) -> None:
    AVAILABLE_CARS.set(count)


def metrics_response() -> StarletteResponse:
    return StarletteResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def install_metrics_middleware(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        endpoint = request.url.path
        REQUEST_LATENCY.labels(service_name, request.method, endpoint).observe(elapsed)
        REQUEST_COUNT.labels(
            service_name,
            request.method,
            endpoint,
            str(response.status_code),
        ).inc()
        return response
