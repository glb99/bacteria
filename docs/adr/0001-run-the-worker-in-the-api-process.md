# 0001 — Run the job worker inside the API process on single-process platforms

## Status

Accepted. Supersedes nothing; the separation it relaxes was stated in a
docstring rather than a record, which is part of why this exists.

## Context

The deployment target is [FastAPI Cloud](https://fastapicloud.com). It runs one
ASGI application per app. This service is two processes: `bacteria-serve` and
`bacteria-worker`.

The worker is not optional decoration. `POST /ingestion/batches:defer` enqueues
a job inside the request's transaction and answers `202` — the whole reason the
queue lives in Postgres rather than a broker is that the job and the data change
it justifies commit together or not at all (`core/jobs.py`). With no worker
anywhere, that route accepts work and nothing ever performs it. The row sits in
`procrastinate_jobs` forever, the caller has been told `202`, and no route
reports otherwise because none exists.

`entrypoints/queue_worker.py` states the case for two processes: they fail
differently, they scale differently, and a slow import or a saturating job must
not be able to make the API unresponsive. That reasoning is sound and this
record does not dispute it.

Four options were considered.

1. **Two processes, as designed.** Not available on this platform.
2. **A second platform for the worker** — a VM or container host running
   `bacteria-worker` against the same Postgres. Keeps the separation and the
   feature, and costs a second thing to operate, pay for, and monitor, for a
   study project whose queue currently has one task.
3. **Disable `:defer`** — return `501` when no worker is configured. Honest, and
   it removes a working feature from the deployment that most needs it, because
   inline ingestion is capped at 500 records precisely because it blocks a
   request.
4. **Run the worker in the API process**, started from the ASGI lifespan.

## Decision

Option 4, behind `BACTERIA_RUN_WORKER_IN_API`, **defaulting to false**.

When set, the lifespan starts `App.run_worker_async` as a named
`asyncio.Task` alongside the server, and cancels and awaits it on shutdown.

The default is the decision as much as the mechanism is. Anywhere two processes
are possible — `just stack`, Docker Compose, any host with a worker service —
the separation stands and this flag stays off. Turning it on by default would
spread a platform's constraint to deployments that do not have it, and would
give a host already running `bacteria-worker` two workers competing for one
queue with nothing anywhere saying so.

The comparison that decides this is not *in-process worker versus separate
worker*. On this platform it is *in-process worker versus no worker*, and a
degraded separation beats a route that lies.

## Consequences

**A worker failure can now take the API with it.** They share a process, an
event loop, and a connection pool. This is the property `queue_worker.py` was
protecting, and it is genuinely given up — not mitigated, not worked around.

**Scaling the API scales workers.** There is no way to add queue capacity
without adding request capacity, or the reverse. `worker_concurrency` is the
only dial, and it competes with request handling on one loop.

**A blocking job stalls requests.** The handler chain runs synchronous steps in
a worker thread (`core/handlers.py`), so the current task is safe. A future task
that blocks the loop directly would degrade the API, and nothing here would
attribute the latency to the job.

**Shutdown is now something that can be got wrong.** An abandoned worker task
leaves its job marked `doing`: invisible to the next worker, not reported as
failed, and the row looks busy forever. The cancel-and-await is asserted by
`test_the_in_api_worker_is_awaited_on_shutdown_not_abandoned`, which was
verified by deleting the cancel and watching it fail. Its first version checked
`done()` and passed either way, because the pool closes on the way out and an
abandoned worker dies on its own; it checks `cancelled()` now.

**Two deployment shapes exist to reason about.** "Does this deployment run a
worker, and where" is now a question with two answers rather than one. The flag
logs a warning at startup so a running process says which shape it is.

**What this does not buy.** It is still not durable execution. A job interrupted
mid-run is not resumed, retries are still absent from ingestion because
ingestion is not idempotent, and there is still no route reporting a job's
outcome. Those are unchanged and recorded where they would be filled.
