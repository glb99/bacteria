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
      core/           protocols, handlers, adapters — cross-cutting infrastructure
      entrypoints/    asgi · cli · worker — configuration only, no logic
    tests/
docs/
  MIGRATION.md        the plan this structure came from, and what is left of it
```

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

**The application never imports `bacteria.interfaces`.** That package is the
agent's own composition root, for running it standalone. The application
composes what it needs in `entrypoints/`. Two composition roots is correct here
— they compose different processes — and this rule is what keeps them from
becoming one tangled one.

## Status

Skeleton. The agent works end to end; the application is a health endpoint and
a set of empty modules waiting for their first feature. What is planned, in what
order, and why, is in [`docs/MIGRATION.md`](docs/MIGRATION.md).

## License

See [LICENSE](LICENSE).
