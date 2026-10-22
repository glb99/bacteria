import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from bacteria.observability.context import bind_request, clear

_provider = None


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        clear()
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        bind_request(request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response


def setup_tracing(otlp_endpoint: str | None = None, console: bool = True, service_name: str = "bacteria") -> None:
    global _provider

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource(attributes={"service.name": service_name})
    _provider = TracerProvider(resource=resource)

    if console:
        _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))

    trace.set_tracer_provider(_provider)


def add_otlp_exporter(endpoint: str, headers: dict | None = None) -> None:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if _provider is None:
        raise RuntimeError("setup_tracing() must be called before add_otlp_exporter()")

    kwargs = {"endpoint": endpoint}
    if headers:
        kwargs["headers"] = headers
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**kwargs)))


def instrument_app(app) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()


def get_tracer(name: str = "bacteria"):
    from opentelemetry import trace
    return trace.get_tracer(name)
