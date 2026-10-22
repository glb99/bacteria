from bacteria.observability.logging import setup_logging

_tracer = None


def setup_observability(app=None):
    global _tracer
    from bacteria.settings import get_settings
    obs = get_settings().observability

    setup_logging(level=obs.log_level, fmt=obs.log_format)

    from bacteria.observability.tracing import instrument_app, setup_tracing
    setup_tracing(otlp_endpoint=obs.otel_endpoint, console=obs.otel_console, service_name=obs.service_name)

    if obs.langfuse_secret_key and obs.langfuse_public_key and obs.langfuse_otlp_endpoint:
        from bacteria.observability.langfuse import setup_langfuse
        agent_model = get_settings().agent.model
        # Prefer the explicit host setting. Fall back to stripping the known Langfuse
        # OTLP path suffix for backwards compatibility with existing deployments that
        # only set LANGFUSE_OTLP_ENDPOINT.
        host = obs.langfuse_host or obs.langfuse_otlp_endpoint.removesuffix("/v1/traces").removesuffix("/api/public/otel")
        _tracer = setup_langfuse(
            secret_key=obs.langfuse_secret_key,
            public_key=obs.langfuse_public_key,
            otlp_endpoint=obs.langfuse_otlp_endpoint,
            host=host,
            model=agent_model,
        )

    if app is not None:
        instrument_app(app)


def get_tracer():
    return _tracer
