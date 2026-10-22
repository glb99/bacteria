import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langfuse import Langfuse


_otlp_headers: dict | None = None
_otlp_base_endpoint: str | None = None  # base URL without /v1/traces, used by CLI subprocess


class LangfuseAgentSpan:
    def __init__(self, span, generation) -> None:
        self._span = span
        self._generation = generation

    def finish(self, output: str, usage: dict, metadata: dict) -> None:
        if self._generation:
            try:
                self._generation.update(
                    output=output,
                    usage_details={
                        "input": usage.get("input_tokens", 0),
                        "output": usage.get("output_tokens", 0),
                    },
                    metadata=metadata,
                )
                self._generation.end()
            except Exception:
                pass
        if self._span:
            try:
                self._span.update(output=output)
                self._span.end()
            except Exception:
                pass


class LangfuseAgentTracer:
    def __init__(self, client: "Langfuse", model: str) -> None:
        self._client = client
        self._model = model

    def start(self, name: str, input: str, metadata: dict) -> LangfuseAgentSpan:
        # Outer span = trace root with job metadata.
        # Inner generation = the actual LLM call — Langfuse uses this to render
        # Input/Output fields and cost in the UI. Without it, those fields show null.
        span = self._client.start_observation(
            name=name,
            as_type="span",
            input=input,
            metadata=metadata,
        )
        generation = span.start_observation(
            name="claude_agent",
            as_type="generation",
            model=self._model,
            input=input,
        )
        return LangfuseAgentSpan(span=span, generation=generation)

    def get_subprocess_env(self) -> dict[str, str]:
        if not _otlp_base_endpoint:
            return {}
        headers_str = ",".join(f"{k}={v}" for k, v in (_otlp_headers or {}).items())
        env = {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_EXPORTER_OTLP_ENDPOINT": _otlp_base_endpoint,
            "OTEL_EXPORTER_OTLP_HEADERS": headers_str,
            "OTEL_LOG_USER_PROMPTS": "1",
            "OTEL_LOG_TOOL_DETAILS": "1",
        }
        # Inject W3C traceparent so CLI spans can be correlated if the CLI ever
        # supports context propagation (currently ignored by the Bun binary).
        try:
            from opentelemetry.propagate import inject as otel_inject
            carrier: dict[str, str] = {}
            otel_inject(carrier)
            if traceparent := carrier.get("traceparent"):
                env["TRACEPARENT"] = traceparent
        except Exception:
            pass
        return env


def setup_langfuse(
    secret_key: str,
    public_key: str,
    otlp_endpoint: str,
    host: str,
    model: str,
) -> LangfuseAgentTracer:
    global _otlp_headers, _otlp_base_endpoint
    from langfuse import Langfuse
    from bacteria.observability.tracing import add_otlp_exporter

    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    _otlp_headers = {
        "Authorization": f"Basic {token}",
        "x-langfuse-ingestion-version": "4",
    }
    # The Python OTel exporter takes the full /v1/traces URL, but the CLI subprocess
    # follows the OTel spec and appends /v1/traces automatically — strip it here.
    _otlp_base_endpoint = otlp_endpoint.removesuffix("/v1/traces")

    add_otlp_exporter(endpoint=otlp_endpoint, headers=_otlp_headers)

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    return LangfuseAgentTracer(client=client, model=model)
