from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def setup_tracing(service_name: str = "bacteria"):
    resource = Resource(attributes={"service.name": service_name})
    provider = TracerProvider(resource=resource)

    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


def setup_observability(app=None):

    setup_tracing()


def get_tracer(name: str = "bacteria"):
    return trace.get_tracer(name)
