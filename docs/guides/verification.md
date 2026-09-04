# Verification

**Passing tests are not evidence that something works.** This has been true
repeatedly here, not theoretically:

- A mocked Gemini test passed while every live tool call failed.
- The async refactor was green while the loop was still being blocked; a
  heartbeat measurement showed otherwise.
- The queue's tests passed before the app could enqueue anything at all.

Exercise the real path. Start the server on a socket, run the worker, issue a
key through the CLI, make the request.

`just smoke` now does exactly that, as `scripts/smoke.py`, and is run by CI. It
issues a credential through the admin CLI, drives a real server and a real
worker over HTTP, and asserts the things a test cannot reach — most importantly
that a deferred job is picked up by a worker in another process, which no test
run can show because there is no worker in one.

**A one-off verification script still belongs in a scratchpad rather than here.**
The distinction is whether it is a gate. `scripts/smoke.py` is kept because it
runs on every pull request and fails them; a script written to answer one
question, once, is not that, and adding it to the repository leaves behind
something nobody maintains and nobody trusts.

Two narrower modes exist alongside it, and both cover something the plain run
cannot:

- `just smoke --in-process-worker` runs the topology a deployment actually uses
  — one process, worker inside the API behind `BACTERIA_RUN_WORKER_IN_API`
  (ADR 0001). Everything else here runs the two-process shape, so that flag was
  load-bearing in production and exercised nowhere. It failed exactly that way
  once: the variable never reached the process, the service conversed normally,
  nothing drained the queue, and it was found by hand days later. Note that a
  local `.env` setting the flag makes the *plain* run a hybrid.
- `just stack-smoke` builds the Docker image and runs the same checks against
  the containers, including that the console is served from the image. The
  platform's builder never reads the Dockerfile, so that is a second packaging
  path, and it is the exit route off FastAPI Cloud.

What `just smoke` deliberately does not cover: an agent turn. That needs a model
provider, and the options are billing a vendor from CI or putting a test-only
seam into production code. The turn is still verified by hand.

**Prove a new guard can fail.** The migration drift test was checked by adding
a field without a migration and watching it break. A guard nobody has seen fail
is a guard nobody has tested.

