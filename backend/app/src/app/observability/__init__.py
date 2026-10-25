import logfire
from opentelemetry import trace


def _scrub_sensitive_attributes(match: logfire.ScrubMatch) -> object | None:
    if match.path == ("attributes", "session.id"):
        return match.value
    return None


def setup_tracing(service_name: str = "bacteria") -> None:
    logfire.configure(
        service_name=service_name,
        send_to_logfire=True,
        console=False,
        scrubbing=logfire.ScrubbingOptions(callback=_scrub_sensitive_attributes),
    )


def setup_observability() -> None:
    setup_tracing()


def get_tracer(name: str = "bacteria") -> trace.Tracer:
    return trace.get_tracer(name)
