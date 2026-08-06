# bacteria — working in this repository

## What this is

A small AI agent built as reusable infrastructure: the layered skeleton and the
ownership boundaries you would want in place before an agent grows, kept
deliberately minimal so the boundaries stay visible.

Read first, in order:

1. `src/bacteria/__init__.py` — the layer map and the distinctions that matter.
2. `docs/ARCHITECTURE.md` — request path, ownership, invariants, gaps.
3. `docs/adr/` — why any particular thing is the way it is.

## Commands

```bash
uv sync --extra dev      # install
uv run pytest            # test
uv run bacteria          # interactive CLI (needs a key in .env)
```

Provider selection is `MODEL_PROVIDER` (`anthropic` by default, or `gemini`),
with the matching `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` in `.env`.

## The two markers

Grep-discoverable conventions. Both are load-bearing for anyone — human or
agent — arriving without context.

**`Not built:`** — a deliberate gap, documented at the exact place it would be
filled. Every block names *what* is missing, *why*, and *where it goes*. Never
add a gap without all three.

```bash
grep -rn "Not built:" src/
```

**`Invariant:`** — a property that is enforced and tested. Breaking one is a
bug, not a design change.

```bash
grep -rn "Invariant:" src/
```

Keeping these accurate matters more than keeping them tidy. A `Not built:` block
that is now built, or an `Invariant:` with no test behind it, is worse than no
marker at all.

## Documentation conventions

**Docstrings are the reference.** Detail lives next to the code, not in a doc
that drifts from it. Reading a module should tell you what it owns, what it
refuses to do, and what is missing — without a second file open.

PEP 257 shape: a one-line summary, a blank line, then the body. Google-style
`Args:` / `Returns:` / `Raises:` sections **only where they carry information the
signature does not**. Type hints already state the types; restating them is
noise. Document the non-obvious: invariants, side effects, why a default is what
it is, what a caller will get wrong.

Two things worth writing down explicitly, because they are what a reader cannot
recover from the code:

- **Why, not what.** `# increment the counter` is worthless. "Bound as a default
  argument, because a bare closure would capture the loop variable" is not.
- **The rejected alternative.** When a plausible simpler approach was tried and
  failed, say so. Someone will otherwise try it again.

Comments inside a function explain a decision at that line. If a comment is
explaining *what* the code does, rewrite the code instead.

**Where each kind of knowledge goes:**

| Kind | Home |
|---|---|
| How to run it | `README.md` |
| How it fits together | `docs/ARCHITECTURE.md` |
| Why a decision was made | `docs/adr/NNNN-*.md` |
| What a thing does | Its docstring |

Do not restate one in another. Cross-reference instead.

## Decision records

Any decision that constrains future work, that a reasonable engineer would make
differently, or that is a deliberate omission which will look like a bug, gets an
ADR. Nygard format — Status, Context, Decision, Consequences.

Records are immutable. Supersede with a new record; do not edit an old one. The
Consequences section must include the ones you dislike, or the record is useless
to whoever later considers reversing it.

Library choices and formatting conventions do not qualify.

## Testing

The bar for a test is: **would its silent violation cause a real bug?** If yes,
it is a load-bearing invariant and gets a test that fails when the invariant
breaks. If it is a judgment call with no runtime behavior — "we chose X over Y
because Y was premature" — it gets an ADR and no test.

Small and deliberate per module. There is no coverage gate, on purpose; see
[ADR 0013](docs/adr/0013-test-load-bearing-invariants-only.md).

Test docstrings state the invariant *and the consequence of breaking it*. They
are documentation as much as verification.

Mocks are not sufficient verification for anything touching a provider API.
Gemini's `thought_signature` requirement passed every mocked test and failed
every live multi-turn tool call. Run it for real before believing it works.

## Boundaries not to erode

These are the point of the project. Each is easy to break in a way that still
passes the tests and still runs.

- **The runtime orchestrates and implements nothing.** It decides *when* each
  layer acts, never *how*. Formatting a prompt inline or appending to the
  transcript directly is always briefly easier and is always wrong here.
- **The model layer cannot execute.** `model/` imports no tool module, no
  filesystem, no subprocess. That is what makes retries provably side-effect
  free.
- **Only `session/` writes state.** Everything else proposes.
- **`tools/` keeps three questions in three modules** — what exists, whether it
  may run, running it. Merging any two makes a control invisible.
- **`interfaces/` owns composition, and nothing below it reads configuration.**

## Working style

Discuss before implementing when a change touches a boundary above, or adds a
`Not built:` gap — those are design decisions, and they get recorded rather than
inferred. Small internal changes do not need that ceremony.

When something needs a hook into a layer that does not exist yet, build the
smallest possible stub and mark it `Not built:` with what it is waiting on. Do
not design the absent layer speculatively in order to support a stub.

`articles/` and `pdfs/` are archived background reading that informed the
original design. They are not part of this system's documentation, nothing
depends on them, and they should not be cited from code or docs.
