# Status

What works, and what is deliberately missing. Kept out of `README.md` because
it changes on a different clock than the rest of it.

Two features working end to end, behind API-key authentication. `personal/` runs
agent turns against durably stored sessions, each owned by the principal that
created it. `ingestion/` takes batches of records through a handler chain and
records what happened to every one of them.

Memory has two proposers and one reviewer. A `remember` tool lets the model
suggest a fact mid-turn; a deferred job reads the transcript afterwards and
suggests more, reading forward from a watermark so its cost tracks new turns
rather than conversation length. Neither writes memory — both write proposals,
which reach no model until a person activates one, at a scope that person
chooses. Extraction is off by default (`BACTERIA_MEMORY_EXTRACTION_ENABLED`); it
is a second model call on every turn. See
[ADR 0002](adr/0002-the-memory-graph-is-postgres-tables.md), whose first
phase this is.

Deliberately absent, each recorded in the code at the place it would be filled
rather than only here:

| Missing | Why it is missing |
|---|---|
| Tools over HTTP | Approval has nobody to ask until a run can pause and resume. Passing no tool registry is the only option that neither silently approves everything nor pretends to gate. |
| A way to ask how a deferred job went | The job id is real and queryable by hand, but no route reports it, so `:defer` is fire-and-forget today. |
| Which memories a turn actually carried | `run_meta` records *how many* reached the prompt, not which. Recording the keys is a change inside `bacteria.agent`, against a decision `_run_meta` states on purpose, so it needs a record of its own rather than a route. |
| Retries on ingestion jobs | Ingestion is not idempotent — duplicates are only caught within a batch — so a retried job would store everything twice. Needs the cross-batch decision first. |
| Key scopes | Every key grants identity and therefore everything; there is no read-only key to hand a script. Browser sessions expire, keys still do not — [ADR 0005](adr/0005-a-browser-holds-a-session-not-a-key.md) explains why the asymmetry is deliberate. |
| Ending every session for a principal | Revoking a key does not close the sessions it opened, which outlive it by up to twelve hours. `revoke-sessions <principal>` is the missing verb. |
| Tenancy for ingested records | Submitting requires authentication, but a batch is not owned by its submitter. Urgent the moment a read route exists. |
| Cross-batch duplicates | A repeated `external_id` in a later batch is stored twice. Needs someone to choose between "update" and "reject". |
| A ceiling on pending proposals | Each extraction run is capped, and the total is not. A long conversation accumulates suggestions until a person drains them, which costs nothing in the prompt and everything in the review surface. |
| Review across sessions | Proposals are listed one conversation at a time, so answering "what is waiting anywhere" means already knowing every session id. The nudge tells you a count for the session you are in and nothing about the rest. |
| Retrieval over the graph | Nodes, edges, contradictions and conclusions exist and are visible ([ADR 0006](adr/0006-the-memory-graph-is-an-assertion-log.md)); nothing yet *retrieves* over them, so the graph does not affect what a model is told. That needs anchor resolution, vectors and the agent-side seam in [its ADR 0024](../backend/agent/docs/adr/0024-memory-candidates-are-supplied-not-read-whole.md), and it is where ADR 0006's kill criterion gets settled. |
| A graph review surface in the console | The write verbs exist as routes — retract, confirm, rename, link, reject ([ADR 0009](adr/0009-the-graph-is-correctable.md)) — and the console draws the graph but does not yet drive them. Read shipped before write deliberately: a destructive route should not exist before there is a way to see what it would destroy. |
| Audio | Planned as speech-to-text → the existing turn → text-to-speech, which needs no change to the agent. |

What is planned, in what order, and why, is in
[`docs/guides/migration.md`](guides/migration.md).
