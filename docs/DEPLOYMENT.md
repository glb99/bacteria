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
| Application directory | `backend/app` |
| Entrypoint | `bacteria.app.entrypoints.asgi:app`, from `[tool.fastapi]` in that package's `pyproject.toml` |
| Schema | Applied by the workflow, before the deploy. Nothing creates or upgrades it at startup. |
| Worker | **In-process**, via `BACTERIA_RUN_WORKER_IN_API=true`. There is nowhere else to put it. |

---

## One-time setup

### 1. The application

Create an app in FastAPI Cloud and set its
[Application Directory](https://fastapicloud.com/docs/builds-and-deployments/application-directory/)
to `backend/app`.

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

### 3. Environment variables

In the FastAPI Cloud dashboard:

| Variable | Value | |
|---|---|---|
| `BACTERIA_DATABASE_URL` | the connection string | **secret** |
| `BACTERIA_RUN_WORKER_IN_API` | `true` | required here, and only here |
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
| No smoke check against the deployed app | CI smoke-tests a local stack. Nothing verifies the deployment after it lands. |

---

## Running it somewhere else

The [`Dockerfile`](../Dockerfile) builds one image that runs all three processes,
and [`compose.app.yml`](../compose.app.yml) runs them as three services with
migrations gated ahead of both. That path keeps the process separation this one
gives up, and is what to reach for if the worker ever needs its own failure
domain.
