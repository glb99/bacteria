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
- Implementation: `backend/app/src/app/observability/__init__.py` now calls `logfire.configure(service_name=..., send_to_logfire=True, console=False)`. Runtime tracing continues to use `opentelemetry.trace`; Logfire-specific code is isolated to bootstrap.
- Implementation: `backend/app/pyproject.toml` declares Logfire and `uv.lock` resolves it to 5.3.0.
- Validation: tests assert Logfire is configured for hosted sending and console output is disabled, and the existing runtime trace test passes. Ruff, mypy, and `uv lock --check` pass. No Logfire token was available, so delivery to a real Logfire project was not exercised.
- Follow-up investigation: installed Logfire 5.3.0's `ScrubbingOptions` supports a callback receiving a `ScrubMatch` with `path`, `value`, and matched regex; returning a non-`None` value replaces the scrubbed value, while returning `None` retains default redaction. The default regex list includes `session`. The scrubber checks `session.id` as an attribute key and produces the observed path `("attributes", "session.id")`.
- Implementation: `backend/app/src/app/observability/__init__.py` now uses a `ScrubbingOptions` callback that returns the original value only for the exact path `("attributes", "session.id")`, returning `None` for all other matches so Logfire applies its default redaction.
- Validation: `backend/app/src/tests/test_observability.py` verifies the exact-path exception preserves the session ID and that another sensitive key still follows the default redaction path. Focused tests and mypy pass.

## Inferences

- The requested switch appears feasible without coupling agent/runtime code to Logfire-specific APIs: retain OpenTelemetry span creation and replace provider/exporter initialization in the observability bootstrap with Logfire configuration. This follows from the current OTel API-based instrumentation and Logfire's official description as built on and compatible with OTel.
- Minimal setup likely consists of adding the `logfire` package, calling `logfire.configure()` from the existing setup function, and supplying a write token through environment configuration (or completing Logfire CLI authentication for local development). This follows from the official getting-started and configuration guides.
- Disable Logfire's console output if the intent is to replace console export entirely, and verify the resulting provider/export pipeline to avoid duplicate console plus Logfire output. This follows from the documented `LOGFIRE_CONSOLE` setting and the existing console exporter.
- Because the current trace captures full prompts, tool data, and image bytes, sending it to Logfire would transmit potentially sensitive, high-volume payloads to a hosted backend. This follows from the prior runtime-observability implementation and Logfire's hosted project/write-token setup; data-handling expectations and account policy must be checked before real payloads are sent.
- The implementation meets the stated portability constraint: OpenTelemetry span creation remains unchanged, and only the observability bootstrap configures Logfire. This follows from the current runtime and observability module.
- A narrowly scoped Logfire configuration callback preserves only `session.id` while retaining default scrubbing for other attributes. This follows from the implementation and test in `observability/__init__.py` and `test_observability.py`.

## Shared model

Implemented model: Use Logfire as the trace backend while keeping OpenTelemetry as the code-facing instrumentation API. Logfire is configured only in the observability bootstrap, with console export disabled and hosted sending enabled. Credentials come from Logfire configuration outside source code. Full-payload runtime traces are sent to the configured project; the person explicitly accepted that data flow.

## Gaps

- No Logfire token was available during validation, so real network delivery and visibility in the Logfire UI have not been verified.
- The session's restatement prompt was left blank. The explicit backend choice and payload consent are recorded, but strict alignment confirmation is incomplete.
- Environment-specific token provisioning and Logfire project selection remain deployment configuration responsibilities.
- The session ID is now explicitly permitted in traces. The person accepted this action by asking “do it”.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| How should the code stay portable? | Continue using OpenTelemetry APIs in runtime code and confine Logfire configuration to observability bootstrap. | Restatement left blank; explicit decision keeps runtime on OpenTelemetry APIs. | Partial |
| Can the session ID be kept visible without disabling default scrubbing? | Yes; the callback returns the original value only when `match.path == ("attributes", "session.id")`, and `None` for every other match. | Asked whether changing Logfire configuration can fix the masking, then said “do it”. Implemented. | Yes |
| What does a complete replacement require? | Configure Logfire and turn off the console exporter, with credentials supplied outside source code. | Chose Logfire backend and console export disabled; implemented. | Yes |
| What is your decision given the data flow? | Decide whether the full runtime payloads may be sent to the hosted Logfire project. | Explicitly accepted all current payloads being sent to Logfire. | Yes |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the person has decided to switch from console traces to Logfire for clearer viewing with minimum configuration. They require simplicity and continued decoupling from the backend: “simplicity and mantaining the code decoupled from the concrete backend.” They would consider the choice wrong if it couples code to Logfire rather than OpenTelemetry: “Having to couple my codebase a lot with it, instead of opentelemetry.”

Considered options: (1) keep console export; (2) configure Logfire as the backend while retaining OpenTelemetry APIs in runtime code; (3) use Logfire-specific span calls throughout the runtime. The person chose option 2 because they want simpler, clearer trace viewing while keeping application code decoupled from the backend. Implemented with Logfire 5.3.0, `send_to_logfire=True`, and `console=False`.

Consequences: likely a dependency and bootstrap change, with `LOGFIRE_TOKEN` or local CLI authentication; no Logfire-specific calls should be needed in runtime code. Console output should be disabled for a true replacement. Traces already contain complete user/model/tool payloads and binary page images, so sending them to hosted Logfire transmits this data and may increase volume. The person explicitly accepts sending all current payloads to Logfire.

Confirmation: the person chose “Switch to Logfire as the backend, retain OpenTelemetry APIs in runtime code, configure Logfire in bootstrap, and disable console export,” and accepted sending the current full payloads. The restatement prompt was left blank, and a real Logfire delivery was not tested because no token was available; complete alignment and live delivery remain unverified.

More Information in the person's words: “I will provide a celarer way to see the traces, with minimum configuration”; “simplicity and mantaining the code decoupled from the concrete backend”; “Having to couple my codebase a lot with it, instead of opentelemetry.”

Open questions: provision a Logfire project write token and verify trace arrival in its UI. No ADR is named.

Follow-up on the session-ID scrub: The person asked whether it could be fixed through Logfire configuration, then asked to implement the configuration-based approach. `observability/__init__.py` now preserves only the exact `session.id` attribute path using a Logfire `ScrubbingOptions` callback and leaves all other default scrubbing enabled. The test checks both the session ID exception and default handling for another sensitive attribute.
