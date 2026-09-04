# Documentation conventions

Repo-wide. These began as the agent package's rules and were made general when
the documentation moved into one tree; `backend/agent/CLAUDE.md` still states
them for readers who arrive inside that package with nothing else loaded.

## Where each kind of knowledge goes

| Kind | Home |
|---|---|
| How to run it | [`README.md`](../../README.md) |
| How it fits together | [`docs/architecture/`](../architecture/README.md) |
| Why a decision was made | [`docs/adr/NNNN-*.md`](../adr/README.md) |
| What broke before, and why the rule exists | [`docs/guides/traps.md`](traps.md) |
| Where the idea came from | [`docs/research/`](../research/README.md) |
| **What a thing does** | **its docstring** |

Do not restate one in another. Cross-reference instead. The one that matters
most is the last row: detail lives next to the code, not in a file that drifts
from it.

## Docstrings are the reference

Reading a module should tell you what it owns, what it refuses to do, and what
is missing — without a second file open.

PEP 257 shape: a one-line summary in the imperative, a blank line, then the
body. Google-style `Args:` / `Returns:` / `Raises:` sections **only where they
carry information the signature does not**. Type hints already state the types;
restating them is noise.

Document the non-obvious: invariants, side effects, why a default is what it is,
what a caller will get wrong.

Two things are worth writing down explicitly, because they are what a reader
cannot recover from the code:

- **Why, not what.** `# increment the counter` is worthless. "Bound as a default
  argument, because a bare closure would capture the loop variable" is not.
- **The rejected alternative.** When a plausible simpler approach was tried and
  failed, say so. Someone will otherwise try it again.

Comments inside a function explain a decision at that line. If a comment is
explaining *what* the code does, rewrite the code instead.

## Package docstrings

Every feature package's `__init__.py` states three things, in this order:

1. what the package owns — the tables, the routes, the concepts;
2. what it refuses to do, and which boundary that protects;
3. the ADR that decided it, by number.

That makes a package self-describing on open, which is the whole point of
keeping the reference in the code. A package whose `__init__.py` is empty is
one that has to be reconstructed by reading every module in it.

## The two markers

Grep-discoverable, and load-bearing for anyone — human or agent — arriving
without context. Originally an agent-package convention; useful anywhere.

**`Not built:`** — a deliberate gap, documented at the exact place it would be
filled. Every block names *what* is missing, *why*, and *where it goes*. Never
add a gap without all three.

**`Invariant:`** — a property that is enforced and tested. Breaking one is a
bug, not a design change.

```bash
grep -rn "Not built:" backend/
grep -rn "Invariant:" backend/
```

Keeping these accurate matters more than keeping them tidy. A `Not built:` block
that is now built, or an `Invariant:` with no test behind it, is worse than no
marker at all.

## Test docstrings

State the invariant *and the consequence of breaking it*. A test whose name and
body say the same thing twice is missing the point.

## Decision records

Any decision that constrains future work, that a reasonable engineer would make
differently, or that is a deliberate omission which will look like a bug, gets
an ADR. Nygard format — Status, Context, Decision, Consequences. Library choices
and formatting conventions do not qualify.

Records are immutable **in substance**. Supersede with a new record; do not edit
an old one to change what it decided, what it considered, or what it cost. The
Consequences section must include the ones you dislike, or the record is useless
to whoever later considers reversing it.

The line to hold: if an edit would change what a reader concludes, it is a new
record. If it only changes what they have to translate — a rename, a moved path
— it is an edit, recorded in the commit that makes it.

## Style of prose

Comments and docs explain *why*, never *what*. Where a plausible simpler
approach was tried and failed, say so — otherwise it gets tried again. Several
docstrings here record exactly that; keep them accurate rather than tidy.
