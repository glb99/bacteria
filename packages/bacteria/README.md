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

---

## Status

Working and exercised end to end against live APIs. Two model providers
(Anthropic, Gemini), one tool, an interactive approval gate, and 61 tests
covering the load-bearing invariants.

Runnable on its own (`uv run bacteria`) and embeddable in a host application —
both are supported and neither is the "real" one. In this workspace it is
embedded by [`fastpaip`](../fastpaip), which supplies a database-backed session
store; the agent itself has never learned what a database is.

The layers that touch the outside world are async; the ones that only compute
are not — `async def` here means *this reaches outside the process*. Tools and
approval gates may be written either way, and a synchronous one is run in a
worker thread rather than on the event loop. See
[ADR 0014](docs/adr/0014-async-at-the-io-boundaries.md).

It is also **deliberately incomplete**: no durable execution, no retrieval, no
sandboxing, no multi-round tool loop. Those absences are decisions with recorded
reasoning, not a backlog — see [Deliberate gaps](#deliberate-gaps).

---

## Quickstart

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
```

Put a key in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Then talk to it:

```bash
uv run bacteria
```

To use Gemini instead, set `GEMINI_API_KEY` and `MODEL_PROVIDER=gemini`. Nothing
else changes — that swap is the point of the model layer's design.

```bash
uv run pytest
```

---

## Embedding it

The CLI is one entry point, not the interface. A host application constructs the
pieces itself and calls one method:

```python
from bacteria.model.client import ModelClient
from bacteria.runtime.runtime import Runtime
from bacteria.session.store import SessionStore

store = SessionStore()
runtime = Runtime(model_client=ModelClient(), session_store=store)

session = await store.create_session(user_id="whoever-you-call-this")
result = await runtime.run_turn(session.session_id, "hello")

result.response.text            # the reply
result.committed_state.transcript  # what is now on the record
```

Add capabilities by registering tools and supplying a gate. Both are checked in
that order — resolve, approve, then run — so a refusal means nothing happened
rather than something happened and was reported as refused:

```python
from bacteria.tools.registry import ToolDefinition, ToolRegistry

tools = ToolRegistry()
tools.register(ToolDefinition(
    name="add_note",
    description="Save a note",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    handler=lambda payload: f"saved: {payload['text']}",   # sync or async
))

async def approve(tool_call) -> bool:
    return tool_call["name"] == "add_note"

result = await runtime.run_turn(
    session.session_id, "note that the kettle is broken",
    tool_registry=tools, approve=approve,
)
```

Omitting `tool_registry` means the model is told of no tools and cannot propose
any. Omitting `approve` allows everything, which is only appropriate when no
registered tool has a side effect worth stopping.

### Supplying your own storage

`Runtime` is typed against
[`SessionRepository`](src/bacteria/session/protocol.py), not against the
in-memory class. A durable store is a second implementation of five methods —
`create_session`, `get_state`, `commit`, `remember`, `forget` — and no caller
here changes. The dependency runs outward: this package declares the shape,
whoever hosts it implements it, and nothing here imports an ORM.
See [ADR 0015](docs/adr/0015-session-store-behind-a-protocol.md).

Four guarantees an implementation must provide that no type checker can enforce,
and that callers depend on:

- `get_state` returns a **detached copy** — a caller mutating what it read
  changes nothing. Returning a live ORM row satisfies the protocol and breaks
  the system.
- `commit` **appends** transcript items and **merges** working state; it never
  replaces either.
- `remember` overwrites by key; `forget` on an absent key is a no-op.
- An unknown `session_id` raises `UnknownSessionError` rather than creating one.

`fastpaip` implements this against SQLModel and runs a conformance suite over
both implementations, which is the shape that catches the ones above.

### Adding a provider

Implement one method — `async send(messages, **kwargs) -> ModelResponse` — per
[`model/protocol.py`](src/bacteria/model/protocol.py). Budget for translation,
not just a signature: the runtime speaks Anthropic's block shapes, so a
non-Anthropic client converts in both directions. Read
[`model/gemini_client.py`](src/bacteria/model/gemini_client.py) first to see how
much that actually is, and [ADR 0006](docs/adr/0006-anthropic-block-shapes-as-internal-format.md)
for why the internal format is not neutral.

---

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

---

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

---

## Deliberate gaps

The authoritative list is in the code, next to where each gap would be filled.
Eleven modules carry one, each naming what is missing, why, and where it goes:

```bash
grep -rn "Not built:" src/
```

(That prints thirteen lines — two of them are `__init__.py` describing the
convention rather than declaring a gap.)

The largest:

| Gap | Consequence today | Where it lands |
|---|---|---|
| Persistence *here* | This store is a dict and vanishes on exit | `session/store.py` — but the seam is built: implement `SessionRepository` in your host |
| Durable execution | A crash mid-turn loses the turn | `runtime/runtime.py` — needs persistence first |
| Isolation | A tool runs with full process privileges | `tools/execution.py` — wraps the handler call |
| Retrieval | No external evidence, ever | `context/assembly.py` — an added section |
| Identity & policy | Approval exists; authorization does not | `tools/approval.py` |
| Non-interactive approval | `cli_approve` reads stdin, so no server can use it | `tools/approval.py` — the *shape* allows an async gate; pausing a run does not exist |
| Multi-round tool loops | One round per turn, no more | `runtime/runtime.py` |
| Streaming | `send()` blocks until the full response arrives | `model/protocol.py` — a second method, not a wider `send` |

The companion marker flags what is load-bearing — properties with tests, where a
break is a bug rather than a design change:

```bash
grep -rn "Invariant:" src/
```

---

## Testing philosophy

Tests here are [architectural fitness
functions](https://www.thoughtworks.com/insights/books/building-evolutionary-architectures):
executable checks that a structural property still holds. The bar for adding one
is that its silent violation would cause a real incident — a retry re-running a
side effect, a handler reaching the model, a failed run leaving no evidence.

Design *rationale* gets an ADR, not a test. There is no coverage gate, because a
percentage target rewards writing the tests this project has decided not to
write. See [ADR 0013](docs/adr/0013-test-load-bearing-invariants-only.md).

**Mocks are not sufficient for anything touching a provider API.** Gemini
requires an opaque `thought_signature` echoed back on the turn after a tool call.
Every mocked test passed while every live multi-turn tool call failed. Run it for
real before believing a provider integration works.

---

## Layout

```
src/bacteria/
  interfaces/   entry points and composition
  runtime/      turn sequencing and step discipline
  context/      working-set assembly
  model/        protocol + one client per provider
  session/      protocol + the in-memory store
  tools/        registry, approval, execution, and one example tool
tests/          invariant tests, one file per module
docs/
  ARCHITECTURE.md
  adr/          numbered decision records
articles/       archived research notes; not part of the system's docs
```

## License

Not currently licensed for redistribution.
