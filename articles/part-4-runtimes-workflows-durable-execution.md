# The Agent Stack — Part 4: Runtimes, Workflows, and Durable Execution

- **Author:** Vinoth Govindarajan
- **Source:** https://theagentstack.substack.com/p/the-agent-stack-part-4-runtimes-workflows
- **Published:** 2026-04-20
- **Fetched into this repo:** 2026-07-22

## Thesis

"A loop can answer a turn. A durable workflow can survive time." The runtime bridges model inference and real-world complexity by advancing a run through states, recording progress, and enabling recovery from interruption.

## The runtime's role

The runtime owns *progress*, not ultimate authority. It assembles context, calls the model, interprets output, invokes tools, handles handoffs, pauses for approval, resumes from saved state, and emits evidence of what happened. The control plane (Part 3) establishes permissions/policy; the runtime executes the path forward within those bounds.

## Workflows = the recoverable shape of a run

A workflow specifies possible states, isolation boundaries, wait conditions, and how execution continues after an interruption. It's not the business logic itself — it's the shape that makes the business logic resumable. (LangGraph's checkpoint model, Temporal's event history are cited examples of this pattern, not prescriptions.)

## Durable execution — four concepts that must stay distinct

- **Retry** — re-attempting failed work.
- **Replay** — rebuilding workflow state from history.
- **Resume** — continuing after a wait, crash, or approval.
- **Idempotency** — preventing unintended effects from a repeated operation.

These solve different problems. Conflating them is how you get duplicate side effects or lost state.

## Boundaries that matter (this part's version)

| Not the same as | |
|---|---|
| Checkpointed state | Memory across sessions (checkpoints are workflow-internal recovery data, not the Part 3/5 memory concept) |
| Tool exposure | Execution authority (same capability ≠ execution boundary from Parts 1–2, now at the workflow level) |
| Handoff (to another agent/step) | Authorization (moving execution doesn't move permission) |
| Tracing | Evaluation (same observability ≠ evaluation boundary from Part 1, restated for runtime traces) |

## Failure modes named

1. Retrying partial side effects — repeating a branch push, email, or payment because there was no step boundary.
2. Treating queues as workflows — confusing delivery guarantees (at-least-once, etc.) with actual progress tracking.
3. Treating background execution as durability — running async ≠ being able to replay/recover.
4. Treating approval as modal (a UI popup) instead of tied to a specific pending action and run state.
5. Replaying non-deterministic work that shouldn't be re-run.
6. Letting a handoff silently move authority — the receiving agent/step doesn't automatically inherit permissions.
7. Hiding evidence — not emitting traces that explain decisions and side effects, so failures are undebuggable.

## Builder checklist from the article

1. Define run identity across all execution phases.
2. Record progress persistently, not in process memory.
3. Establish step boundaries around side effects and external calls.
4. Design idempotency before production, not after an incident.
5. Classify wait types explicitly (approval, timer, webhook, etc.).
6. Structure resume events with run identification and state.
7. Attach approvals to specific pending actions, not a generic "confirm" modal.
8. Emit comprehensive traces for debugging and monitoring.

## Series roadmap

Part 5 next: Context, Retrieval, and Memory — what the model should see vs. what the system should preserve across sessions.
