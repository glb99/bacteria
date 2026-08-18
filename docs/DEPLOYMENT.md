# Deployment — FastAPI Cloud

The target is [FastAPI Cloud](https://fastapicloud.com), deployed by
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) on every push
to `main`.

**Read [ADR 0001](adr/0001-run-the-worker-in-the-api-process.md) first if you are
changing anything here.** This platform runs one process and this service is two,
and the way that is resolved gives up a property the code otherwise protects.

---

## The shape of it

| | |
|---|---|
| Build root | The **repository root**, not `backend/app` — set in *both* the workflow's `Deploy` step and the dashboard. See [§1](#1-the-application). |
| Entrypoint | `bacteria.app.entrypoints.asgi:app`, from `[tool.fastapi]` in the **root** `pyproject.toml` |
| Schema | Applied by the workflow, before the deploy. Nothing creates or upgrades it at startup. |
| Worker | **In-process**, via `BACTERIA_RUN_WORKER_IN_API=true`. There is nowhere else to put it. |

---

## One-time setup

### 1. The application

Create an app in FastAPI Cloud and leave its
[Application Directory](https://fastapicloud.com/docs/builds-and-deployments/application-directory/)
at the **repository root**.

**Two settings choose the build root, and the workflow is the one that wins.**
`fastapi deploy` packages *its own working directory* and uploads that, so the
`Deploy` step in [`deploy.yml`](../.github/workflows/deploy.yml) decides what the
platform ever sees. It must run from the repository root — with no
`working-directory:` — and the dashboard setting has to agree with it. Changing
only the dashboard changes nothing, because the root is never uploaded for it to
point at.

**Neither may be `backend/app`, which is the obvious answer and fails.** The
deployed application is that package, so pointing at it reads as correct —
but the build runs `uv` from whatever directory it is given, and `bacteria-app`
declares `bacteria-agent = { workspace = true }`. A workspace member does not
build without the root that declares `members = ["backend/*"]`.

Rooted at `backend/app`, the build fails three ways at once and none of the
messages names the cause:

```
error: Failed to parse entry: `bacteria-agent`
  Caused by: `bacteria-agent` references a workspace in `tool.uv.sources`, but is
  not a workspace member
```

```
Using CPython 3.14.6          # no .python-version in that directory
/tmp/install_dependencies.sh: cd: can't cd to backend/app
```

The [`Dockerfile`](../Dockerfile) has always had the right shape and is the thing
to compare against: it copies `backend/`, `pyproject.toml` and `uv.lock`, then
runs `uv sync --package bacteria-app`.

**The root depends on `bacteria-app`, and that line is load-bearing.** The
builder runs a plain `uv sync`, which installs a virtual root's `dependencies`
and its groups and nothing else. Every command here names the package it wants —
the Dockerfile, this workflow, the Justfile — so deleting that dependency leaves
all of them green and produces an image with the entire toolchain and no
`bacteria` in it. It fails at import, as `No module named 'bacteria'`, well past
the point anything looks like it could still fail. A test in
`backend/app/tests/test_entrypoints.py` holds it in place.

### 2. The database

Attach Postgres through the
[Neon](https://fastapicloud.com/docs/integrations/neon-integration/) or
[Supabase](https://fastapicloud.com/docs/integrations/supabase-integration/)
integration, or bring your own.

**The integration sets a bare `DATABASE_URL`, which this application does not
read.** `Settings` takes `BACTERIA_`-prefixed variables only, and ignores
unprefixed ones — the prefix is what makes `BACTERIA_DATABSE_URL` a startup
failure instead of a service quietly running on the default. So copy the
connection string into a `BACTERIA_DATABASE_URL` secret by hand.

Two things about that string:

- It must name an **async driver**: `postgresql+psycopg://…`. A synchronous URL
  fails at engine creation rather than at first query, which is where you want
  it. Providers hand out `postgresql://…`, so this usually needs editing.
- **Do not strip `+psycopg` to "make it synchronous".** That is psycopg 3's
  dialect and serves both modes; stripping it routes the URL to psycopg2, which
  is not installed.

If the provider rotates the URL, this copy does not follow. That is the cost of
keeping one prefix rule; the alternative was a second name for one setting.

**On Supabase, take the session pooler and not the transaction pooler.** The
dashboard offers both under one heading and the difference is not cosmetic:

- **Transaction pooler** (port `6543`) hands out a connection per transaction, so
  it does not carry `LISTEN`/`NOTIFY` and breaks the prepared statements psycopg
  makes on its own after a query repeats. The queue is
  [`PsycopgConnector`](../backend/app/src/bacteria/app/core/jobs.py), which uses
  that notification to pick a job up promptly. It also polls, so the honest
  symptom is latency and intermittent statement errors rather than silence —
  which means **"jobs do eventually run" does not clear the pooler**. Session
  mode avoids the question instead of surviving it.
- **Session pooler** (port `5432`) holds the connection for the session and is
  reachable over IPv4. The *direct* connection is IPv6-only on current Supabase
  projects, and GitHub-hosted runners are IPv4-only — so the migration step in
  the workflow cannot reach it either.

One URL serves both halves of the application: `core/jobs.py` strips `+psycopg`
for psycopg's own parser, so there is no second variable to keep in step.

### 3. Environment variables

In the FastAPI Cloud dashboard:

| Variable | Value | |
|---|---|---|
| `BACTERIA_DATABASE_URL` | the connection string | **secret** |
| `BACTERIA_RUN_WORKER_IN_API` | `true` | required here, and only here. Defaults to `false` |
| `BACTERIA_MEMORY_EXTRACTION_ENABLED` | `true` | defaults to `false`, so without it no turn ever enqueues and no proposal is ever produced |
| `BACTERIA_MODEL_PROVIDER` | `anthropic` or `gemini` | |
| `BACTERIA_LOG_LEVEL` | `INFO` | |
| `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` | provider credential | **secret**, unprefixed — the SDKs read these exact names |
| `BACTERIA_WORKER_CONCURRENCY` | `4` | optional; competes with request handling on one loop |
| `BACTERIA_LOGFIRE_TOKEN` | Logfire write token | **secret**; optional — absent means the process prints spans instead of exporting them |
| `BACTERIA_LOGFIRE_ENVIRONMENT` | `production` | defaults to `local`, which is what makes one Logfire project serve both |

Use a **separate write token for this deployment from the one on a laptop**, against
the same project. Same destination, and either can be revoked without disturbing
the other — which matters because the laptop's is the one that leaks.

Anything starting with `BACTERIA_` that is not a setting **fails startup on
purpose**. A typo is a refusal to boot, not a service running on defaults.

The other direction — a setting's name *without* the prefix, such as
`RUN_WORKER_IN_API` — is **warned** about rather than refused, because
`DATABASE_URL` legitimately belongs to the integration. Read that warning: the
missing prefix is silent otherwise, and cost an afternoon of production
diagnosis once.

### 4. CI secrets

```bash
uv run fastapi login
uv run fastapi cloud setup-ci --secrets-only --app-id <your-app-id>
```

With the GitHub CLI authenticated this writes `FASTAPI_CLOUD_TOKEN` and
`FASTAPI_CLOUD_APP_ID` itself; otherwise it prints them for
**Settings → Secrets and variables → Actions**.

**Until all three exist the workflow skips, on purpose.** It reports a notice and
a job summary naming what is missing, rather than failing — a `main` that is red
because a dashboard is half-configured teaches everyone to ignore the red. It
does not report success for a deploy that did not happen either.

Add `BACTERIA_DATABASE_URL` there too — the workflow migrates before deploying,
so the runner needs it. Put all three in a `production` environment, which is
what the workflow's `environment:` names.

Set one **variable** as well, under *Variables* rather than *Secrets*:

| Variable | Value |
|---|---|
| `SMOKE_BASE_URL` | the deployed URL, e.g. `https://<app>.fastapicloud.dev` |

It drives the post-deploy check in [§6](#6-check-that-deferred-work-is-actually-running),
which is skipped with a notice while it is unset rather than failing the deploy.
A variable and not a secret because a public URL is not one, and a masked value
is unreadable in exactly the log you would be reading to find out which host
failed. It is deliberately not `BACTERIA_`-prefixed: anything with that prefix
that is not a setting refuses to boot, and that step runs `bacteria-admin`.

**The database has to be reachable from a GitHub-hosted runner.** Neon and
Supabase are. One inside a private network is not, and the migration step would
have to move somewhere that can reach it.

### 5. Issue a credential

Every route except `/health` needs `Authorization: Bearer <key>`, and keys come
from an operator command rather than an endpoint — minting one over HTTP needs a
credential, and the first has nowhere to come from.

```bash
BACTERIA_DATABASE_URL='postgresql+psycopg://…' uv run bacteria-admin issue-key acme --label production
```

Printed once. Only a hash is stored.

### 6. Check that deferred work is actually running

**The workflow now does this for you**, once `SMOKE_BASE_URL` is set: after every
deploy it runs `scripts/smoke.py --deployed`, which asserts the app serves,
refuses unauthenticated callers, and — the part that matters — that a deferred
job reaches a worker within a minute. It bills no vendor, because it proves the
queue with an ingestion job rather than a turn.

What follows is how to check it by hand, which is still what you want when that
step fails and you need to know which half is wrong.

The conversation works long before the queue does, so this needs checking
deliberately rather than being noticed. Exactly one of these appears at boot,
and it says which branch the lifespan took:

| Line | Level | Means |
|---|---|---|
| `running the job worker inside the API process` | WARNING | the worker started — expected here, and [ADR 0001](adr/0001-run-the-worker-in-the-api-process.md)'s tradeoff said out loud |
| `memory extraction is enabled and no worker runs in this process` | INFO | it did not |

Then take a turn containing a fact worth remembering and look at what the
proposals carry:

```sql
select source, count(*) from chat_memory_proposal group by source;
```

**`source` is what makes this answerable**, and reading the count alone will
mislead you. There are two proposers and only one of them uses the queue:

- `model` — the `remember` tool, written inline inside the turn's own
  transaction. It works whether or not a worker exists, so its rows prove
  nothing about deferred execution.
- `extractor` — the background job. These rows, and only these, mean the whole
  path is alive.

An empty queue after a `"hello"` turn is correct behaviour rather than a fault:
the extractor proposes what it finds, and there was nothing there.

---

## What you are giving up

Stated here as well as in the ADR, because this is the page someone reads before
deciding.

- **A worker failure can take the API with it.** One process, one loop, one pool.
- **Scaling the API scales workers,** and the reverse. `BACTERIA_WORKER_CONCURRENCY`
  is the only dial.
- **A blocking job would stall requests.** Today's task is safe — synchronous
  handler steps run in a worker thread — but nothing enforces that for the next
  one.

Leave `BACTERIA_RUN_WORKER_IN_API` **unset** anywhere you can run two processes.
`just stack` does, and so does any host with a worker service.

---

## Where this sends data

Two places, and both are worth knowing before the first deploy.

- **The model provider**, for every turn and every extraction — the conversation
  itself.
- **Logfire**, when a token is set: timings, SQL shapes, model name, token counts,
  job names. **Not conversation text.** The provider instrumentation elides message
  content, which was checked rather than assumed — a span carrying a system prompt
  with a name in it recorded `content: <elided>`. It is a default and can be turned
  off, so it stays a property to keep rather than one you are given.

Instrumentation is OpenTelemetry and Logfire is one OTLP endpoint, so
`OTEL_EXPORTER_OTLP_ENDPOINT` redirects everything to a collector you host, with no
code change. A local Jaeger — `docker run -d -p 16686:16686 -p 4318:4318
jaegertracing/all-in-one` — receives the same spans, including the model call, and
is the way to look at a trace with nothing leaving the machine. It takes traces but
not metrics, and its all-in-one storage is in memory, so it is a debugging tool
rather than a second deployment. See
[ADR 0003](adr/0003-observability-is-opentelemetry-exported-to-logfire.md).

## Still missing

Not oversights; each is recorded where it would be filled.

| | |
|---|---|
| No route reports a deferred job's outcome | `:defer` is fire-and-forget. The job id is real and queryable by hand. |
| No retries on ingestion jobs | Ingestion is not idempotent across batches, so a retry would store everything twice. |
| No durable execution | A job interrupted mid-run is not resumed. |
| No rollback | Redeploy the previous commit. Migrations are not reversed automatically, and `just rollback` is a local command against a URL you supply. |
| No agent turn is verified anywhere automatic | A turn needs a model provider, and the options are billing a vendor from CI or a test-only seam in production code. Still checked by hand. |

---

## Running it somewhere else

The [`Dockerfile`](../Dockerfile) builds one image that runs all three processes,
and [`compose.app.yml`](../compose.app.yml) runs them as three services with
migrations gated ahead of both. That path keeps the process separation this one
gives up, and is what to reach for if the worker ever needs its own failure
domain.
