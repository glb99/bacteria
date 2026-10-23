from bacteria.observability.logging import setup_logging

_tracer = None


def setup_observability():
    global _tracer
    from bacteria.settings import get_settings
    obs = get_settings().observability

    setup_logging(level=obs.log_level, fmt=obs.log_format)

    from bacteria.observability.tracing import instrument_app, setup_tracing
    setup_tracing(otlp_endpoint=obs.otel_endpoint,
                  console=obs.otel_console, service_name=obs.service_name)

    if app is not None:
        instrument_app(app)


def get_tracer():
    return _tracer
