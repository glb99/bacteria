# bacteria

A small AI agent, built as **infrastructure** rather than as a script — and
deliberately kept small enough to read in one sitting.

The whole thing is one turn: text arrives, context is assembled, a model is
called, tools may run, state is committed. That loop would fit in a single
function. It is split into layers instead, because the failures that actually
hurt in agent systems are not algorithmic — they are ownership failures:

- something wrote state that had no business writing state
- a retry re-ran a side effect that had already happened
- a capability the model could *see* quietly became one it could *use*
- a run failed and left no trace of what it had already done

Every layer here exists to make one of those impossible by construction rather
than by discipline. The point is the boundaries, not the feature set.

## Status

Working and exercised end to end against live APIs. Two model providers
(Anthropic, Gemini), one tool, an interactive approval gate, and 57 tests
covering the load-bearing invariants.

It is also **deliberately incomplete**: no persistence, no retrieval, no
sandboxing, no multi-round tool loop. Those absences are decisions with recorded
reasoning, not a backlog — see [Deliberate gaps](#deliberate-gaps).

## Quickstart

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
```

Put a key in `.env` at the repository root:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Then talk to it:

```bash
uv run bacteria
```

To use Gemini instead, set `GEMINI_API_KEY` and `MODEL_PROVIDER=gemini`. Nothing
else changes — that swap is the point of the model layer's design.

Run the tests:

```bash
uv run pytest
```

## Architecture at a glance

A turn flows top to bottom and back:

```
  interfaces/   receives input, composes the system
       │
  runtime/      sequences the turn, delegates every step
       ├──────► context/    chooses what the model sees
       ├──────► model/      calls a provider; proposes, never acts
       ├──────► tools/      describes, gates, and runs capabilities
       └──────► session/    the authoritative record; the only writer
```

| Package | Owns | Must not |
|---|---|---|
| `interfaces` | Receiving work; choosing concrete implementations | Contain agent logic |
| `runtime` | Ordering, step discipline, evidence on failure | Absorb the layers it calls |
| `context` | The bounded working set for one request | Be confused with the transcript |
| `model` | Provider calls, failure classification, retry | Execute anything |
| `tools` | What exists, whether it may run, running it | Merge those three questions |
| `session` | Transcript, working state, memory | Be written to from anywhere else |

Six distinctions the code keeps apart on purpose, each easy to collapse and
expensive to have collapsed:

| | |
|---|---|
| **session ≠ authorization** | "this conversation exists" vs. "this action is permitted" |
| **transcript ≠ context** | everything that happened vs. what this request shows |
| **memory ≠ history** | a fact deliberately kept vs. a turn that occurred |
| **capability ≠ authority** | the model seeing a tool vs. being allowed to use it |
| **approval ≠ isolation** | "should this run" vs. "how bad if it goes wrong" |
| **trace ≠ audit** | how a result was reached vs. who is answerable for it |

## Where the knowledge lives

Four places, each with a different job — roughly the
[Diátaxis](https://diataxis.fr/) split:

| Question | Where |
|---|---|
| *How do I run it?* | This file |
| *How does it fit together?* | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| *Why is it like this?* | [`docs/adr/`](docs/adr/) — one record per decision |
| *What exactly does this do?* | The docstrings. They are the reference. |

Docstrings carry the detail rather than deferring to the docs, so that reading
a module tells you what it owns, what it refuses to do, and what is missing —
without a second file open.

## Deliberate gaps

The authoritative list is in the code, next to where each gap would be filled:

```bash
grep -rn "Not built:" src/
```

Each block names what is missing, why, and where it goes. The largest ones:

| Gap | Consequence today | Where it lands |
|---|---|---|
| Persistence | Everything is lost on exit; no memory across runs | `session/store.py` — a second implementation of the same four methods |
| Durable execution | A crash mid-turn loses the turn | `runtime/runtime.py` — needs persistence first |
| Isolation | A tool runs with full process privileges | `tools/execution.py` — wraps the handler call |
| Retrieval | No external evidence, ever | `context/assembly.py` — an added section |
| Identity & policy | One user, no authorization model | `tools/approval.py` — approval exists, authorization does not |
| Multi-round tool loops | One round per turn, no more | `runtime/runtime.py` |

The companion marker flags what is load-bearing — properties with tests, where a
break is a bug rather than a design change:

```bash
grep -rn "Invariant:" src/
```

## Testing philosophy

Tests here are [architectural fitness
functions](https://www.thoughtworks.com/insights/books/building-evolutionary-architectures):
executable checks that a structural property still holds. The bar for adding one
is that its silent violation would cause a real incident — a retry re-running a
side effect, a handler reaching the model, a failed run leaving no evidence.

Design *rationale* gets an ADR, not a test. There is no coverage gate, because a
percentage target rewards writing the tests this project has decided not to
write. See [ADR 0013](docs/adr/0013-test-load-bearing-invariants-only.md).

## Layout

```
src/bacteria/
  interfaces/   entry points and composition
  runtime/      turn sequencing and step discipline
  context/      working-set assembly
  model/        protocol + one client per provider
  session/      the authoritative store
  tools/        registry, approval, execution, and one example tool
tests/          invariant tests, one file per module
docs/
  ARCHITECTURE.md
  adr/          numbered decision records
articles/       archived research notes; not part of the system's docs
```

## License

Not currently licensed for redistribution.
