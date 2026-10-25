---
date: 2026-10-25
status: gaps
question: "How could we add observability to the entire runtime?"
adr: ""
---

# How could we add observability to the entire runtime?

## Why this session

Understand the current runtime boundary and determine what observability across it should mean before choosing an implementation approach.

## Starting model

The person wants visibility into “the model calls, the context assembly, the retreving, the tool calls...”. Follow-up answers clarified the first-step scope and debugging goal; the falsifier prompt remains unanswered.

| Prompt | Answer |
| --- | --- |
| What do you currently believe about observability across the entire runtime? | “the model calls, the context assembly, the retreving, the tool calls...” |
| Which decision would this understanding change? | They want to add runtime details to the current observability traces. |
| Which constraint will you not trade away? | Keep the first step as simple as possible. |
| What observation would show that belief is wrong? | Not supplied. |

## Evidence

- `backend/app/src/app/agent/runtime.py`: `run_turn` creates a run ID, loads session state, selects retrieved documents, assembles context, sends one initial model request, executes tool calls and sends follow-up model requests for up to `MAX_TOOL_ROUNDS` (3), then commits the user and assistant transcript items. Tool calls are executed sequentially in `_execute_tool_calls`.
- `backend/app/src/app/agent/model.py`: the runtime depends on the `SendsToAgent` protocol, whose `send` method is the model-call seam.
- `backend/app/src/app/agent/retriever.py` and `backend/app/src/app/agent/context.py`: retrieval is a synchronous `select` call that returns page bytes; context assembly combines recent message history, user text, and any retrieved page images.
- `backend/app/src/app/agent/tools.py`: `execute_tool_call` resolves a registered tool and runs its handler, which may be synchronous or asynchronous; it returns a `ToolResult`.
- `backend/app/src/app/agent/session.py`: `TranscriptItem` has an optional `run_id`; the current runtime's user and assistant commits do not pass one.
- `backend/app/src/app/cli/cli.py`: the CLI is the only current caller of `run_turn` found under `backend/app/src`. It wraps the turn in `agent.run_turn`, adds `session.id`, raw `input.text`, and (after the call returns) `run.id`. It calls `setup_observability()` at CLI startup.
- `backend/app/src/app/observability/__init__.py`: the current provider adds a `BatchSpanProcessor(ConsoleSpanExporter())`; `setup_observability(app=None)` ignores its `app` argument and only initializes tracing.
- `backend/app/src/app/main.py`: the FastAPI app does not call `setup_observability` or activate the installed OpenTelemetry instrumentors. It initializes Sentry tracing only when the DSN exists and the environment is not development.
- `backend/app/pyproject.toml`: OpenTelemetry API, SDK, OTLP HTTP exporter, and FastAPI, HTTPX, and SQLAlchemy instrumentation packages are dependencies. Package presence alone does not activate these instrumentors.
- `ai/sessions/2026-10-23-opentelemetry-basics.md`: the preceding session confirms the CLI's basic tracing setup and one-span-per-turn implementation, and records that detailed retrieval, model, and tool spans need deeper instrumentation.
- Interview confirmation: the requested first step is trace-only, adding details to the existing traces. The person wants full payload capture, including prompt/history and retrieved page images, to debug whether context assembly contains the correct documents.
- Implementation: `backend/app/src/app/agent/runtime.py` now emits a correlated `agent.runtime` span and child spans for session load, retrieval, context assembly, each model request, each tool execution, and transcript commits. It records full serialized payloads, encoding page bytes as base64, and propagates `run_id` to the committed user/assistant transcript items.
- Implementation: `backend/app/src/app/agent/retriever.py` adds optional retrieval provenance (`document_id`, `page_index`, score, and bytes) while keeping `select()` returning the same `list[bytes]` shape. The runtime uses provenance when available and retains a generic fallback for other retriever implementations.
- Validation: the focused runtime/retrieval/context test set passed (7 tests); Ruff passed for changed files when ignoring the existing `B905` finding in the retriever's cosine helper; mypy passed for the runtime and retriever modules.

## Inferences

- A useful first full-runtime trace can be rooted in `run_turn`, then create child spans for session loading, retrieval, context assembly, each model request, each tool execution, and transcript commits. These are the operation boundaries visible in `runtime.py` and its protocols.
- Keeping the root span in the runtime rather than only in the CLI would cover any future caller of `run_turn`; currently the CLI is its only caller. This follows from the call-site search and the runtime's interface-agnostic dependencies.
- The application `run_id` and OpenTelemetry trace/span IDs serve different purposes: the runtime creates the former, while the current CLI creates the outer span. Establish the run ID at the root span and propagate it consistently if traces and transcript records should be joined. This follows from `runtime.py`, `cli.py`, and `session.py`.
- Trace-only phase instrumentation is the simplest first increment matching the person's stated preference; metrics and logs can remain out of scope initially. This follows from their preference to add runtime details to current traces and keep the first step simple.
- The implemented trace makes the requested payloads inspectable by serializing them as span attributes and encoding image bytes as base64. This follows from the current changes in `runtime.py`.
- Adding retrieval provenance without changing the existing `select()` return shape preserves existing retriever callers while allowing this runtime to identify selected pages. This follows from the optional metadata method in `retriever.py` and its compatibility test.
- Metrics can complement traces with aggregate turn/model/tool durations, counts, errors, and token usage, while structured logs can carry trace/run correlation for error details. The visible runtime phases provide the candidate measurements; availability of token usage from the current model response is not established by the normalized response type.
- Setup and export need to be consistent across application entry points. The CLI has an OpenTelemetry provider; the FastAPI app does not invoke that setup, and installed instrumentors are not automatically active. This follows from `cli.py`, `main.py`, `observability/__init__.py`, and `pyproject.toml`.

## Shared model

Confirmed and implemented model: “Entire runtime” means adding trace details for the major workflow boundaries (state load, retrieval, context assembly, each model request, tool executions, and persistence) to the existing per-turn trace. The first step is trace-only. Full payloads are captured on spans, with page images encoded as base64; retrieval spans include document ID, page index, score, and bytes. A trace describes one execution path; a run ID is the application's identifier for that turn, not an OpenTelemetry trace ID.

## Gaps

- The person has not supplied an observation that would falsify their starting model.
- The telemetry backend/exporter and deployment entry points to support are not chosen. In particular, the API currently does not call the agent runtime.
- Whether Google GenAI requests or the retriever's embedding request receive automatic spans from installed instrumentation was not checked.
- The normalized `ModelResponse` does not expose token counts; the available source of usage metrics and whether the provider returns usage data are unchecked.
- The requested full payload includes user content and page-image bytes; destination, retention, size handling, access controls, and whether image content should be stored inline or via a trace-linked artifact remain undecided.
- Full payloads, including user content and page-image bytes, are now inline span attributes. The configured console exporter prints these large and potentially sensitive values; a production exporter, retention policy, access controls, and payload redaction policy remain undecided.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| What counts as full-runtime observability? | Add runtime details for major phases to the existing per-turn traces. | “I want to add to my current observability traces, info about what happens during the runtime.” | Yes |
| What is the first implementation scope? | Keep phase one trace-only and simple. | “At first I want it to be as simple as possible”; selected trace-only. Implemented. | Yes |
| What payload scope supports the debugging goal? | Capture full text/history and retrieved page images, alongside document provenance. | Selected literal all payloads; wants to debug whether context assembly takes the correct documents. Implemented with base64 page bytes. | Yes |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context: the person wants to debug whether context assembly includes the correct documents. The CLI currently creates one OpenTelemetry span around the turn, but the runtime's internal steps have no spans, the CLI exports raw input text, and the FastAPI app does not use this OpenTelemetry setup. The API does not currently call the runtime.

Drivers in the person's words: “At first I want it to be as simple as possible, as a way of debugging if the context assembler is taking the correct documents, etc”; “I want to add to my current observability traces, info about what happens during the runtime.”

Considered options: (1) retain only the current interface-level span; (2) add custom phase spans and payload details inside the runtime trace; (3) add provider/framework auto-instrumentation as well where it covers actual calls. The person chose option 2, with trace-only instrumentation and literal full payloads (including page-image bytes), because they want runtime detail for debugging document/context selection while keeping the first step simple. Implemented custom spans and payload attributes in `runtime.py`, optional document provenance in `retriever.py`, and run ID propagation to transcript items.

Consequences: phase spans expose durations/outcomes and show runtime progression; retrieval spans identify selected document/page/score. Payloads are inline span attributes, with page bytes base64-encoded. This keeps phase one simple but can make trace exports very large and include sensitive content. The exporter, retention, access controls, payload redaction, and runtime/API setup remain undecided.

Confirmation: the person restated the shared model as wanting to add runtime information to current traces, chose trace-only for phase one, and explicitly chose literal all-payload capture. The resulting tests verify a correlated runtime trace, phase spans, full payload capture, image encoding, retrieval provenance, multiple model requests, and persisted run IDs.

More Information in the person's words: “At first I want it to be as simple as possible, as a way of debugging if the context assembler is taking the correct documents, etc.”

Open questions: where full payloads should be exported and retained, and what access controls/redaction should apply; whether the FastAPI entry point needs setup before it invokes the runtime; whether automatic provider instrumentation is useful. No ADR is named.
