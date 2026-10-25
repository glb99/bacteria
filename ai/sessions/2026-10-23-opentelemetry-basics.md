---
date: 2026-10-23
status: aligned
question: "How do we start observability with OpenTelemetry, from the basics?"
adr: ""
---

# How do we start observability with OpenTelemetry, from the basics?

## Why this session

The person wants to implement observability with OpenTelemetry, starting from the basics. This overlaps the still-open session [2026-10-19-agent-observability.md](2026-10-19-agent-observability.md), which is about agent traces in the sense of The Agent Stack, Part 8. The decision this understanding would change is still open.

## Starting model

The person is unsure whether observability is wired up.

| Prompt | Answer |
| --- | --- |
| What do you currently believe? | "I’m unsure whether observability is wired up." |
| Which decision would this understanding change? | |
| Which constraint will you not trade away? | |
| What observation would show that belief is wrong? | |

## Evidence

- `backend/app/pyproject.toml` declares the OpenTelemetry API, SDK, OTLP HTTP exporter, and FastAPI, HTTPX, and SQLAlchemy instrumentation packages.
- `backend/app/src/app/observability/__init__.py` defines `setup_tracing`, which creates an SDK `TracerProvider`, sets `service.name`, adds a `BatchSpanProcessor(ConsoleSpanExporter())`, and installs that provider. It defines `setup_observability(app=None)`, but that function ignores `app` and only calls `setup_tracing()`.
- `backend/app/src/app/cli/cli.py` calls `setup_observability()` inside its `main()` entry point, immediately before starting `_run` with `anyio.run`.
- `backend/app/src/app/main.py` does not call `setup_observability` or an OpenTelemetry instrumentor. It initializes Sentry only when `SENTRY_DSN` is set and `FASTAPI_ENV` is not `"development"`, with `enable_tracing=True`.
- `backend/app/src/app/core/config.py` declares `SENTRY_DSN` optional and defaults it to `None`.
- Runtime smoke check: calling `setup_observability()`, creating and ending a span with `get_tracer()`, and flushing the provider printed the span to the console and returned `force_flush: True`.
- Before the change, search of `backend/app/src` found no `start_span`, `start_as_current_span`, or application call to `get_tracer()` outside the observability module.
- `backend/app/src/app/cli/cli.py` has a clear per-turn call to `run_turn(...)` inside its interactive loop. `backend/app/src/app/agent/runtime.py` creates a `run_id` at the start of `run_turn` and performs retrieval, context assembly, model calls, tool rounds, and transcript commits there.
- The person confirmed the shared model: "Yes: setup works, but actual turns need spans." They chose explanation only for now and declined implementation.
- The person then explicitly asked to implement the simplest option: one span per CLI turn.
- `backend/app/src/app/cli/cli.py` now wraps each `run_turn(...)` await in an `agent.run_turn` span, sets `session.id` before the call, and sets `run.id` from the returned result.
- Focused integration check ran the actual CLI `_run()` loop with a fake `run_turn` and an in-memory OpenTelemetry exporter; it verified one `agent.run_turn` span with `session.id="session-123"` and `run.id="run-456"`.
- `uv run --package app ruff check --ignore T201 backend/app/src/app/cli/cli.py` passed. The existing `T201` print rule is ignored for this check because this CLI already uses `print` for its intended terminal interaction.
- [2026-10-19-agent-observability.md](2026-10-19-agent-observability.md) remains `exploring`. Its starting belief is a trace that registers the session id, the run id, and every step. Its interview on decision, constraint, and falsifier is still open. No ADR is named.

## Inferences

- OpenTelemetry is initialized in the CLI entry point, and each CLI agent turn now produces a parent span carrying session and run IDs. This follows from the CLI instrumentation and focused integration check above.
- Adding one parent span around each `await run_turn(...)` is a small, localized change in the CLI loop. Adding spans for retrieval, each model request, tool calls, and persistence would need more instrumentation within `run_turn` and its collaborators. This follows from the visible turn call and implementation phases.
- One span around each turn is a small, localized change; detailed phase spans would require deeper instrumentation. This follows from the per-turn call in `cli.py` and work phases in `runtime.py`.
- The CLI turn span is a parent for any OpenTelemetry spans emitted during the awaited turn, because it is made current across the call. The trace will appear in the configured console exporter after the turn ends.
- Sentry tracing may be enabled for the FastAPI app, but only when its DSN and environment condition are satisfied. This follows from `main.py` and `core/config.py`.
- Having instrumentation packages installed does not, by itself, show that the FastAPI, HTTPX, or SQLAlchemy instrumentors are activated. The current `setup_observability` body does not activate them.

## Shared model

“Set up” is surface-specific here. The CLI initializes a basic OpenTelemetry provider with console span export, and each agent turn is now wrapped in a span annotated with its session ID and run ID. The FastAPI app does not use that OpenTelemetry setup; it has conditional Sentry tracing instead.
## Gaps

- The person has not identified which decision this understanding would change, a constraint to preserve, or an observation that would falsify their belief.
- The integration check used a fake turn result to verify the CLI span boundary and attributes; it did not make a real model call or exercise tool spans. Sentry delivery for FastAPI was not checked.
- The scope relationship with the still-open 2026-10-19 agent-observability session remains unsettled.

## Alignment check

| Question | Answer that matches the shared model | Person's answer | Match |
| --- | --- | --- | --- |
| Is observability wired up? | The CLI initializes OpenTelemetry and each turn now produces a console-exported span with session and run IDs. FastAPI has conditional Sentry tracing and no OpenTelemetry setup call. | "Yes: setup works, but actual turns need spans." | Yes |
| Is adding spans difficult? | One span per turn is a small change; detailed retrieval/model/tool spans require deeper instrumentation. | Chose "Just explaining for now." | Yes |
| What should happen next? | Implement a single span around each CLI turn, adding session and run IDs. | Explicitly asked: "so can we start implementing the simplest?" | Yes |

## Handoff for a human ADR

No ADR is named. The person has not chosen an option.

Context so far, in their words: "I’m unsure whether observability is wired up." The CLI setup emitted a manually created console span in a runtime smoke check. They confirmed that actual CLI turns need spans, then explicitly asked to implement the simplest option. Implemented one `agent.run_turn` span around each `run_turn(...)` await, with `session.id` and the returned `run.id` attributes; an in-memory exporter check verified those span attributes. No ADR is named. A separate session from 2026-10-19 still holds an earlier belief that agent observability means a trace of the session id, the run id, and every step.
