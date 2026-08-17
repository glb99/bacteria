# 0003 — Instrument with OpenTelemetry, export to Logfire, and keep both out of the agent

## Status

Accepted — 2026-08-17.

Drafted before the deployment it exists for, then accepted after a spike, and the
spike is the part worth recording. **Four of the decisions below came out of
running it rather than out of writing it**, which is a poor ratio for a record
that was supposed to be cheap to reason about in advance:

- **FastAPI is instrumented at module scope**, not from the lifespan. Starlette
  builds its middleware stack on the first call it receives and the lifespan *is*
  one, so instrumenting there adds middleware to a stack already built — silently,
  with the server working perfectly and producing no request spans at all. There is
  no later hook: production imports `app` rather than calling `main`.
- **Only the configured provider is instrumented.** Calling every provider's
  instrumentation unconditionally raised at startup, because each needs its own
  optional dependency. Two entrypoint tests caught it.
- **The test suite patches instrumentation out.** The lifespan is an entrypoint the
  tests drive on purpose, so without it every `TestClient` acquired an exporter —
  which this record forbids in the next paragraph but the code did anyway.
- **The admin CLI is instrumented silently.** Its stdout is where a person reads
  what a model said; nine query spans printed between a question and its answer made
  the conversation unreadable within minutes of it being wired.

Three claims were checked rather than argued. Request, query, job and model spans
appear on one timeline. Token counts and model latency arrive — closing the gap
[the agent's ADR 0019](../../backend/agent/docs/adr/0019-a-run-records-how-it-was-configured.md)
named. And conversation text does not leave the process: a span carrying a system
prompt with a name in it recorded `content: <elided>`.

One claim is false as built and known to be. See the first consequence.

## Context

The service is about to be deployed, and three questions it cannot currently
answer become operational rather than academic.

**The first is one this repository already wrote down as unanswerable.**
[ADR 0001](0001-run-the-worker-in-the-api-process.md) folded the job worker into
the API process because the platform runs one, and listed what that gives up:

> A blocking job stalls requests. […] A future task that blocks the loop directly
> would degrade the API, **and nothing here would attribute the latency to the
> job.**

That was written when the queue had one task and it was rarely enqueued. ADR 0002
put an extraction job on *every turn*, so the worker now has steady work
competing with request handling on one event loop and one connection pool. The
cost 0001 accepted has grown, and nothing measures it.

**The second is the agent's own list of gaps.**
[The agent's ADR 0019](../../backend/agent/docs/adr/0019-a-run-records-how-it-was-configured.md)
made a run explicable — which model answered, which tools were exposed, how much
was in context, what the outcome was — and closed by naming what it still does
not record:

> Still unrecorded: **latency and token cost**, the prompt or tool-schema
> version, the approval decision on calls that *succeeded* […], and the identity
> the run acted under.

ADR 0002 then roughly doubled per-turn model spend. A record that cannot say what
a turn cost is a poor place from which to judge whether the second call earns its
keep, which is a question this project has explicitly deferred to evidence.

**The third is that a deployment is opaque in a way local runs are not.**
`docs/DEPLOYMENT.md` lists "no smoke check against the deployed app" among what is
missing: a deploy that boots into a broken state looks exactly like one that
worked.

### What is already here, and must not be duplicated

This is the part that decides between candidates, so it comes before any of them.

- **Evidence has a home, and it is the transcript.** The agent's ADR 0019 put
  `run_meta` in the transcript rather than a `runs` table, on the grounds that
  [ADR 0004](../../backend/agent/docs/adr/0004-single-commit-path.md) has one
  commit path and [ADR 0012](../../backend/agent/docs/adr/0012-commit-evidence-on-failure.md)
  depends on that single write surviving a failure. Anything that makes a
  *second* system the place you go to find out what a run did puts the record of
  a turn somewhere that can fail independently of the turn.
- **Evaluation is already designed.**
  [ADR 0020](../../backend/agent/docs/adr/0020-deterministic-evals-over-recorded-runs.md)
  chose deterministic checks over recorded runs, and `bacteria.app.evaluation`
  implements them. It also declined to encode a policy nobody has chosen, twice
  and on purpose.
- **The agent is vendorable, and a fitness test enforces the boundary.**
  `bacteria.agent` reaches outside itself only through protocols it declares, and
  `test_package_boundaries.py` fails the build when a layer below `interfaces/`
  reads configuration. Its records travel into hosts that never agreed to this
  application's vendors.
- **The deployment target runs one process.** The same constraint that eliminated
  every dedicated graph database in ADR 0002.
- **This repository is Apache-2.0.**
- **Transcripts carry an unsolved retention question.** ADR 0012 flagged it, ADR
  0019 noted the record now names the model and tools a deployment has, and
  [ADR 0020](../../backend/agent/docs/adr/0020-deterministic-evals-over-recorded-runs.md)
  did not settle it. Sending conversation contents to a third party is a decision
  taken on top of a question still open.

### What was evaluated

**Logfire** — Pydantic's, built on OpenTelemetry, with first-class instrumentation
for FastAPI, SQLAlchemy and psycopg, which is this application's whole stack. It
consolidated Pydantic's AI Gateway in early 2026, so token and cost accounting
arrives with it rather than as a second vendor. The SDK is open source; the
backend is a hosted service with a free tier.

**Opik** — the best-principled option in the field and the closest match to this
repository's license: Apache-2.0 with no feature restrictions when self-hosted,
including tracing, datasets, evaluations and prompt management. It is eliminated
by hosting rather than by design, exactly as Apache AGE was in ADR 0002. Its
self-hosted build is Postgres **and ClickHouse** behind a Helm chart — a second
datastore and a second thing to operate, on a platform that hosts one process.
Its SaaS avoids that and in doing so discards the Apache-2.0 property that was
the reason to prefer it.

**LangSmith** — proprietary, with no self-hosting outside its own plans, and its
ergonomics assume LangChain or LangGraph. This project wrote its own runtime and
keeps a deliberately narrow model protocol
([ADR 0005](../../backend/agent/docs/adr/0005-narrow-model-protocol.md)) with two
hand-written clients. Adopting it would mean re-litigating settled decisions to
get value out of it.

**Structured logs and nothing else** — the honest minimum, and the strongest
rejected alternative. See below.

## Decision

**Instrument with OpenTelemetry. Export to Logfire.** The distinction is the
decision: the API is vendor-neutral and the backend is an OTLP endpoint, so
outgrowing Logfire means re-pointing an exporter rather than removing
instrumentation. This is the same reasoning ADR 0002 used to prefer ordinary
tables over an extension — choose the thing that does not foreclose the next
move.

**Nothing is instrumented inside `bacteria.agent`.** Not a decorator, not an
import, not an optional extra. Instrumentation lives in the application's
`entrypoints/` — which is where configuration belongs and why it is omitted from
coverage — and in `core/`, which holds nothing that names a domain concept.
`@traceable`-style decorators on `Runtime` are how these SDKs want to be used and
are precisely what the vendorable boundary forbids. A host embedding this agent
picks its own observability or none.

**Observability is operational, not evidentiary.** `run_meta` in the transcript
stays the authoritative record of what a run did, and every deterministic eval
keeps reading it. Spans are for latency, contention and cost — questions about
*the system* rather than about a run. Nothing may become answerable only by
querying a vendor, because the answer would then be outside the single commit
path ADR 0004 protects and would disappear with a subscription.

**Instrument three things first, chosen because each answers a question already
written down as unanswerable:**

1. FastAPI request spans.
2. psycopg query spans.
3. The procrastinate worker — job pickup, duration, and queue latency.

Together those answer ADR 0001's "nothing here would attribute the latency to the
job", which is the reason this is being done before the deployment rather than
after.

**Message bodies are not exported by default.** Spans carry counts, durations,
token totals, model identity and outcome — everything ADR 0019 listed as missing
— and not prompts or completions. Turning capture on is a separate decision that
belongs to whoever settles the retention question, not a default that settles it
by accident.

**A failure to export must never fail a request.** The exporter is batched and
out of band, and no code path may await it. An observability vendor being down is
not an outage of this service.

**`BACTERIA_LOGFIRE_TOKEN`, absent by default**, and absence means local console
output rather than a startup failure. This is the one place the `BACTERIA_`
prefix rule's "a typo refuses to boot" behaviour would be actively wrong: a
development machine with no token is the normal case, not a misconfiguration.

## Consequences

**The trace does not cross the whole stack, and cannot as built.** It reaches
HTTP, every SQL statement, each job, and the model call. Everything between — the
context that was assembled, the tools that were exposed, the approval that was or
was not asked for — is a gap between two database queries. That is the direct cost
of the boundary above, and the `Not built:` block in
:mod:`bacteria.app.core.observability` names the only way to close it. Anyone
reading a trace here should know what is missing from it.

**Spans and `run_meta` describe the same turn and share no identifier.** Given a
slow span there is no way to reach the run that produced it, and given a bad run no
way to reach its latency. The two records were built years apart by the same
reasoning and never joined; a root span per turn carrying `session_id` and `run_id`
is the fix, and it is not in this record because it was not built.

The loop-contention cost ADR 0001 accepted becomes visible, on the same timeline
as the requests it competes with, which is the only way the two can be compared
at all.

ADR 0019's latency and token-cost gap closes without a second write on the commit
path, and without the `runs` table that record declined to add.

**A second vendor, and a third-party dependency in the request path.** Batched
and out of band, but present — an SDK that starts a background exporter, holds a
queue, and has its own failure modes. `just check-all` gains a dependency it did
not need, and CI installs it.

**Two places now describe one turn.** `run_meta` says what the run did; a span
says how long it took. They can disagree — through a dropped span, a sampled
trace, or an exporter that quietly stopped — and the transcript is the one to
believe. That precedence is stated here and enforced by nothing.

**Instrumentation in `entrypoints/` is instrumentation nothing tests.** That
directory is omitted from coverage on the grounds that it holds configuration and
no logic, which is exactly why it is the right home — and it means a broken
exporter setup is found by looking at a dashboard rather than by a failing test.
The mitigation is that it cannot break a request; the cost is that it can be
silently absent.

**Deployment gains a required secret and a place data goes.** `DEPLOYMENT.md`
grows a row, and the answer to "where does this service send data" grows an
entry.

### The one to dislike

**The single question that justified this could be answered with three timers.**
Whether the in-process worker starves request handling is measurable with
`time.perf_counter` around the handler and the job, logged at `INFO`, in about
twenty lines and with no vendor, no dependency, and no data leaving the process.
That would answer ADR 0001's open question completely.

What it would not do is answer the next question, or the one after, without
another twenty lines each — and the honest version of this record is that it buys
a general capability on the strength of one specific need, at a moment when the
service has one user. If the deployment turns out to be quiet, this will have been
machinery bought for a graph nobody looked at.

## Alternatives rejected

**Opik.** Better licensed and genuinely open, and it fails the constraint that
eliminated four graph databases in ADR 0002: a second datastore to operate beside
a deployment that runs one process. Revisit if this ever runs its own
infrastructure, at which point the OTel instrumentation this record specifies is
what would be re-pointed at it — which is most of the argument for choosing the
neutral API.

**A self-hosted collector instead of Logfire.** Tried, and it works: with
`OTEL_EXPORTER_OTLP_ENDPOINT` set, a local Jaeger received every span including the
model call, with no code change and nothing leaving the machine. It is declined as
the *deployment's* backend for the reason above — there is nowhere on this platform
to run it, and its all-in-one storage is in memory — and kept as the documented
local option, which costs nothing precisely because neither backend appears in the
code. What would actually be lost is querying: "what did every turn cost this week"
is SQL in Logfire and not really answerable in Jaeger, and cost is the specific gap
ADR 0019 named.

**LangSmith.** Proprietary, not self-hostable, and shaped for a framework this
project deliberately does not use.

**Structured logging only, no vendor.** Cheapest, and it keeps every byte inside
the process. It is declined because the question that matters — whether a job and
a request contended — is a question about *two things at once*, and correlating
them across log lines by hand is the work a trace exists to have already done.
This is the alternative to return to if the consequences above start being paid
without the dashboard being read.

**Instrument the agent and let hosts opt out.** It is where the interesting spans
are — a model call, a tool execution, an assembly. It is rejected because
`bacteria.agent` is vendorable and this would put an application's vendor choice
inside it, which the package boundary test exists to prevent. If agent-level
spans are ever wanted, the shape is the one ADR 0024 used for retrieval: a
protocol the agent declares and the host implements, with a no-op default — a
separate record, not a widened import list.
