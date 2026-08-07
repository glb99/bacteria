# fastpaip

An AI application built around a small agent, as a uv workspace of two packages:

| Package | What it is |
|---|---|
| [`packages/bacteria`](packages/bacteria) | The agent. Layered by ownership boundary, self-contained, independently runnable and testable. |
| [`packages/fastpaip`](packages/fastpaip) | The application that hosts it — HTTP API, workers, and the features built on top. |

The split is enforced by packaging rather than by discipline: the application
depends on the agent, and the agent knows nothing about the application. It has
no database, no web framework, and no configuration of its own.

## Quickstart

Requires Python 3.13+, [uv](https://docs.astral.sh/uv/), and
[just](https://just.systems/).

```bash
just install
```

```bash
just migrate
```

```bash
just test
```

Talk to the agent in a terminal — needs an API key in `.env`:

```bash
just agent
```

Run the web service:

```bash
just serve
```

`just --list` shows the rest.

## Layout

```
packages/
  bacteria/           the agent — see its own README
  fastpaip/
    src/fastpaip/
      auth/           API keys and principals — who is calling
      core/           protocols, handlers, adapters, settings, db — cross-cutting
      chat/           conversations with the agent, durably stored
      ingestion/      validate → normalize → persist, built from core.handlers
      entrypoints/    asgi · cli · worker — configuration only, no logic
    tests/
docs/
  ARCHITECTURE.md     sequence diagrams of each path through the system
  MIGRATION.md        the plan this structure came from, and what is left of it
```

Start with [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — a chat turn drawn
end to end touches nearly every layer, and the boundaries below are visible in
it.

## Conventions worth knowing before changing things

**Entrypoints hold configuration and nothing else.** They are omitted from
coverage for that reason. If an entrypoint ever contains something worth
testing, that is the signal it holds logic that belongs in a feature module.

**The agent is excluded from coverage.** Its suite is architectural fitness
functions rather than line coverage, and the unevenness is deliberate — see
[ADR 0013](packages/bacteria/docs/adr/0013-test-load-bearing-invariants-only.md).
Measuring it produces a number whose only use is tempting someone to write the
tests that record exists to decline. The application is measured; the agent is
not.

**Authentication and authorization are separate, and stay separate.** `auth/`
answers *who is calling* and nothing else. Whether that caller may have a
particular resource is decided next to the resource — `chat/access.py` — because
only the owning feature knows what owning one means. This is the same
distinction the agent is built around, and collapsing it is how a service ends
up treating "you know the id" as "you may read it".

**The application never imports `bacteria.interfaces`.** That package is the
agent's own composition root, for running it standalone. The application
composes what it needs in `entrypoints/`. Two composition roots is correct here
— they compose different processes — and this rule is what keeps them from
becoming one tangled one.

## Status

Two features working end to end, behind API-key authentication. `chat/` runs
agent turns against durably stored sessions, each owned by the principal that
created it; `ingestion/` takes batches of records through a handler chain and
records what happened to every one of them.

Keys are issued by an operator command, not an endpoint:

```bash
uv run fastpaip-admin issue-key acme-corp --label "acme production"
```

The schema belongs to Alembic. Nothing creates tables on startup — not the
server, not the admin CLI — because a process that builds its own schema starts
happily against a database missing a column and fails later at the query. A test
asserts the migrations and the models describe the same thing, so a model
changed without a migration fails where it is cheap to fix.

Deliberately absent, each recorded where it would be filled: background workers,
key scopes and expiry, tenancy for ingested records, tools over HTTP (approval
has nobody to ask until a run can pause), and audio. What is planned and why is in
[`docs/MIGRATION.md`](docs/MIGRATION.md).

## License

See [LICENSE](LICENSE).
