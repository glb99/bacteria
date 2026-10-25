---
date: 2026-10-25
status: gaps
question: "Can we use Logfire as the observability backend instead of the console?"
adr: ""
---

# Can we use Logfire as the observability backend instead of the console?

## Why this session

Understand whether and how Logfire should replace the current console span exporter for runtime traces.

## Starting model

The person believes Logfire will provide “a celarer way to see the traces, with minimum configuration.” They have decided to switch now. Their constraints are “simplicity and mantaining the code decoupled from the concrete backend.” They would reject the approach if it requires “Having to couple my codebase a lot with it, instead of opentelemetry.”

| Prompt | Answer |
| --- | --- |
| What do you currently believe about using Logfire here? | “I will provide a celarer way to see the traces, with minimum configuration.” |
| Which decision would this understanding change? | “I have decided switchig now.” |
| Which constraint will you not trade away? | “simplicity and mantaining the code decoupled from the concrete backend.” |
| What observation would show that belief is wrong? | “Having to couple my codebase a lot with it, instead of opentelemetry.” |

## Evidence

- The current observability setup creates a `TracerProvider` and attaches `BatchSpanProcessor(ConsoleSpanExporter())` in `backend/app/src/app/observability/__init__.py`. Runtime instrumentation uses the OpenTelemetry API via `get_tracer()`.
- The current `backend/app/pyproject.toml` already declares OpenTelemetry API/SDK dependencies; it does not declare Logfire.
- Official Logfire getting-started guide (`https://pydantic.dev/docs/logfire/get-started/first-trace/`) says Logfire is built on OpenTelemetry, supports standard OpenTelemetry, uses `logfire.configure()` to connect an app, and supports authentication or a `LOGFIRE_TOKEN` write token. It also states integrations are optional package extras.
- Official Logfire configuration guide (`https://pydantic.dev/docs/logfire/reference/configuration/`) documents environment-based setup including `LOGFIRE_TOKEN`, `LOGFIRE_SERVICE_NAME`, `LOGFIRE_ENVIRONMENT`, `LOGFIRE_SEND_TO_LOGFIRE`, and `LOGFIRE_CONSOLE`; it says `logfire.configure()` still needs to be called when configuring through environment variables.
- Official Logfire concepts guide (`https://pydantic.dev/docs/logfire/get-started/concepts/`) describes traces as trees of nested spans and Logfire as built on OpenTelemetry.
- Prior session [2026-10-25-entire-runtime-observability.md](2026-10-25-entire-runtime-observability.md): the runtime now creates OTel spans for major workflow operations and captures prompt/context/tool payloads and base64 page images in span attributes. The previous design intentionally retained OTel API usage in application instrumentation and left exporter selection open.

## Inferences

- The requested switch appears feasible without coupling agent/runtime code to Logfire-specific APIs: retain OpenTelemetry span creation and replace provider/exporter initialization in the observability bootstrap with Logfire configuration. This follows from the current OTel API-based instrumentation and Logfire's official description as built on and compatible with OTel.
- Minimal setup likely consists of adding the `logfire` package, calling `logfire.configure()` from the existing setup function, and supplying a write token through environment configuration (or completing Logfire CLI authentication for local development). This follows from the official getting-started and configuration guides.
- Disable Logfire's console output if the intent is to replace console export entirely, and verify the resulting provider/export pipeline to avoid duplicate console plus Logfire output. This follows from the documented `LOGFIRE_CONSOLE` setting and the existing console exporter.
- Because the current trace captures full prompts, tool data, and image bytes, sending it to Logfire would transmit potentially sensitive, high-volume payloads to a hosted backend. This follows from the prior runtime-observability implementation and Logfire's hosted project/write-token setup; data-handling expectations and account policy must be checked before real payloads are sent.

## Shared model

Proposed model, pending confirmation: Use Logfire as the trace backend while keeping OpenTelemetry as the code-facing instrumentation API. The likely change is isolated to observability setup and dependencies/configuration; the runtime's OTel spans should remain vendor-neutral. Logfire access is configured outside source code, and console export should be disabled if Logfire replaces it. Full payload traces will be sent to the configured Logfire project, so data handling is part of the decision.

## Gaps

- Whether a Logfire project/token is available and configured for the intended environment.
- Whether the user accepts sending the already-captured prompts, tool inputs/outputs, and page-image bytes to the hosted Logfire service.
- Exact Logfire package/API version and provider lifecycle behavior should be verified in an implementation before reporting a working switch.
- Whether local development should send telemetry to Logfire, remain console-only, or support both is undecided.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| How should the code stay portable? | Continue using OpenTelemetry APIs in runtime code and confine Logfire configuration to observability bootstrap. | Restatement left blank; their explicit decision keeps runtime on OpenTelemetry APIs. | Partial |
| What does a complete replacement require? | Configure Logfire and turn off the console exporter, with credentials supplied outside source code. | Chose Logfire backend and console export disabled. | Yes |
| What is your decision given the data flow? | Decide whether the full runtime payloads may be sent to the hosted Logfire project. | Explicitly accepted all current payloads being sent to Logfire. | Yes |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the person has decided to switch from console traces to Logfire for clearer viewing with minimum configuration. They require simplicity and continued decoupling from the backend: “simplicity and mantaining the code decoupled from the concrete backend.” They would consider the choice wrong if it couples code to Logfire rather than OpenTelemetry: “Having to couple my codebase a lot with it, instead of opentelemetry.”

Considered options: (1) keep console export; (2) configure Logfire as the backend while retaining OpenTelemetry APIs in runtime code; (3) use Logfire-specific span calls throughout the runtime. The person chose option 2 because they want simpler, clearer trace viewing while keeping application code decoupled from the backend.

Consequences: likely a dependency and bootstrap change, with `LOGFIRE_TOKEN` or local CLI authentication; no Logfire-specific calls should be needed in runtime code. Console output should be disabled for a true replacement. Traces already contain complete user/model/tool payloads and binary page images, so sending them to hosted Logfire transmits this data and may increase volume. The person explicitly accepts sending all current payloads to Logfire.

Confirmation: the person chose “Switch to Logfire as the backend, retain OpenTelemetry APIs in runtime code, configure Logfire in bootstrap, and disable console export,” and accepted sending the current full payloads. The restatement prompt was left blank, so complete alignment is not recorded.

More Information in the person's words: “I will provide a celarer way to see the traces, with minimum configuration”; “simplicity and mantaining the code decoupled from the concrete backend”; “Having to couple my codebase a lot with it, instead of opentelemetry.”

Open questions: credential/project availability, local development export behavior, and verified package/provider lifecycle. No ADR is named.
