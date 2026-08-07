# fastpaip

An HTTP service built around a small AI agent — conversations that survive a
restart, and a bulk import pipeline — as a uv workspace of two packages.

| Package | What it is |
|---|---|
| [`packages/bacteria`](packages/bacteria) | The agent. Layered by ownership boundary, self-contained, independently runnable and testable. |
| [`packages/fastpaip`](packages/fastpaip) | The application that hosts it — HTTP API, persistence, credentials, features. |

The split is enforced by packaging rather than by discipline: the application
depends on the agent, and the agent knows nothing about the application. It has
no database, no web framework, and no configuration of its own. What connects
them is a protocol the agent declares and the application implements.

---

## Quickstart

Needs Python 3.13+, [uv](https://docs.astral.sh/uv/), and
[just](https://just.systems/). An `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` in
`.env` is required for anything that calls a model.

```bash
just install && just migrate && just test
```

Issue yourself a credential — an operator command, not an endpoint:

```bash
uv run fastpaip-admin issue-key acme-corp --label "local dev"
```

It prints the key once. Only a hash is stored, so it cannot be shown again.

```bash
just serve
```

Then have a conversation:

```bash
curl -sX POST localhost:8000/chat/sessions -H "Authorization: Bearer $FASTPAIP_KEY"
```

```bash
curl -sX POST localhost:8000/chat/sessions/$SESSION/turns -H "Authorization: Bearer $FASTPAIP_KEY" -H 'Content-Type: application/json' -d '{"text":"hello"}'
```

`just --list` shows the rest. Interactive API docs are at `/docs` while the
server runs.

---

## API

Every route except `/health` requires `Authorization: Bearer <key>`. Anything
wrong with the credential — missing, malformed, unknown, wrong secret,
revoked — returns the same `401`, because telling them apart tells an attacker
which half of a guess was right.

| | | |
|---|---|---|
| `GET` | `/health` | Liveness. Does not touch the database, so a database outage cannot cause a restart loop. |
| `POST` | `/chat/sessions` | Open a conversation. Takes no body — the owner is the authenticated caller and cannot be named by the client. |
| `POST` | `/chat/sessions/{id}/turns` | `{"text": "..."}` → `{"run_id", "reply"}`. Runs one agent turn. |
| `GET` | `/chat/sessions/{id}/transcript` | Everything that happened in the conversation, in order. |
| `POST` | `/ingestion/batches` | `{"source", "records": [...]}` → what happened to every record. |

A session that does not exist and one belonging to someone else both return
`404`. A `403` would confirm the session exists, which turns a session id into
an oracle for enumeration.

### Ingestion in one example

```json
POST /ingestion/batches
{"source": "salesforce-nightly",
 "records": [{"external_id": "c-1", "name": "Ada Lovelace", "seats": 12},
             {"name": "no id"}]}
```

```json
201
{"batch_id": 1, "accepted": 1,
 "rejected": [{"payload": {"name": "no id"},
               "reason": "missing required field(s): external_id"}]}
```

A record needs an `external_id` and a `name`; every other key is stored exactly
as it arrived and never inspected, so this fits contacts, products, devices, or
documents equally and knows about none of them. Nothing is dropped silently —
every record becomes either a row or a stored rejection carrying the reason and
the payload as it was sent.

---

## Layout

```
packages/
  bacteria/           the agent — see its own README and docs/adr/
  fastpaip/
    src/fastpaip/
      auth/           API keys and principals — who is calling
      core/           protocols, handlers, adapters, settings, db — cross-cutting
      chat/           conversations with the agent, durably stored
      ingestion/      validate → normalize → persist, built from core.handlers
      entrypoints/    asgi · cli · worker — configuration only, no logic
    migrations/       alembic; the schema lives here, not in the app
    tests/
docs/
  ARCHITECTURE.md     sequence diagrams of each path through the system
  MIGRATION.md        the plan this structure came from, and what is left of it
```

Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). A chat turn drawn end
to end touches nearly every layer, and the conventions below are visible in it
as structure rather than as claims.

---

## Conventions worth knowing before changing things

**Authentication and authorization are separate, and stay separate.** `auth/`
answers *who is calling* and nothing else. Whether that caller may have a
particular resource is decided next to the resource — `chat/access.py` — because
only the owning feature knows what owning one means. Collapsing them is how a
service ends up treating "you know the id" as "you may read it".

**The schema belongs to Alembic.** Nothing creates tables at startup — not the
server, not the admin CLI. A process that builds its own schema starts happily
against a database missing a column and fails later at the query, which is worse
than refusing to start. A test replays every migration and asserts no diff
against the models, so a model changed without a migration fails where it is
cheap to fix.

**Entrypoints hold configuration and nothing else.** They are omitted from
coverage for that reason. If an entrypoint ever looks like it deserves a test,
that is the signal it holds logic belonging to a feature.

**The application never imports `bacteria.interfaces`.** That package is the
agent's own composition root, for running it standalone. The application
composes what it needs in `entrypoints/`. Two composition roots is correct —
they compose different processes — and this rule is what stops them becoming one
tangle.

**The agent is excluded from coverage.** Its suite is architectural fitness
functions rather than line coverage, and the unevenness is deliberate — see
[ADR 0013](packages/bacteria/docs/adr/0013-test-load-bearing-invariants-only.md).
Measuring it produces a number whose only use is tempting someone to write the
tests that record exists to decline.

**I/O is awaited; computation is not.** In the agent, `async def` means "this
reaches outside the process". In the application the same rule holds down to the
database driver, which is `aiosqlite` in development and expects `asyncpg` in
production.

---

## Development

```bash
just test            # both suites; test-agent and test-app run them separately
just cov             # application coverage, entrypoints omitted
just lint            # ruff check + format
just typing          # ty
just check-all       # all of the above
```

```bash
just makemigration "add whatever"   # generate from model changes — read it before committing
just migrate                        # apply
just db-version                     # what the database is at
```

```bash
just agent           # run the agent standalone in a terminal
just serve           # migrate, then run the web service
```

---

## Status

Two features working end to end, behind API-key authentication. `chat/` runs
agent turns against durably stored sessions, each owned by the principal that
created it. `ingestion/` takes batches of records through a handler chain and
records what happened to every one of them.

Deliberately absent, each recorded in the code at the place it would be filled
rather than only here:

| Missing | Why it is missing |
|---|---|
| Tools over HTTP | Approval has nobody to ask until a run can pause and resume. Passing no tool registry is the only option that neither silently approves everything nor pretends to gate. |
| Background workers | Ingestion runs in the request, so batches cap at 500. The open question is which broker, and whether jobs survive a restart. |
| Key scopes and expiry | Every key grants identity and therefore everything; there is no read-only key to hand a script. |
| Tenancy for ingested records | Submitting requires authentication, but a batch is not owned by its submitter. Urgent the moment a read route exists. |
| Cross-batch duplicates | A repeated `external_id` in a later batch is stored twice. Needs someone to choose between "update" and "reject". |
| Audio | Planned as speech-to-text → the existing turn → text-to-speech, which needs no change to the agent. |

What is planned, in what order, and why, is in
[`docs/MIGRATION.md`](docs/MIGRATION.md).

## License

See [LICENSE](LICENSE).
