# Architecture Decision Records

One record per decision, in [Michael Nygard's
format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions):
**Status**, **Context**, **Decision**, **Consequences**. Numbered, immutable,
and never deleted — a decision that stops being true gets a new record that
supersedes it, because the reasoning behind a reversal is worth as much as the
reasoning behind the original.

These answer *why*. What the code does is in the docstrings; how it fits
together is in [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions in this repository | Accepted |
| [0002](0002-organize-by-ownership-boundary.md) | Organize the system by ownership boundary, not by feature | Accepted |
| [0003](0003-in-memory-state.md) | Keep all state in memory; defer persistence and durable execution | Accepted |
| [0004](0004-single-commit-path.md) | Route every state change through a single commit path | Accepted |
| [0005](0005-narrow-model-protocol.md) | Depend on a narrow protocol, not a provider abstraction layer | Accepted |
| [0006](0006-anthropic-block-shapes-as-internal-format.md) | Use Anthropic block shapes as the internal message format | Accepted |
| [0007](0007-tool-calls-are-proposals.md) | Treat tool calls as proposals and isolate execution in one module | Accepted |
| [0008](0008-approval-at-the-side-effect.md) | Ask for approval at the side effect, and default to denied | Accepted |
| [0009](0009-local-tools-not-mcp.md) | Use local tools instead of MCP | Accepted |
| [0010](0010-bounded-context-window.md) | Assemble context as a bounded recent-message window | Accepted |
| [0011](0011-single-round-tool-loop.md) | Run one round of tool execution per turn | Accepted |
| [0012](0012-commit-evidence-on-failure.md) | Commit evidence even when a run fails | Accepted |
| [0013](0013-test-load-bearing-invariants-only.md) | Test load-bearing invariants only | Accepted |
| [0014](0014-async-at-the-io-boundaries.md) | Make the I/O boundaries async; keep the pure layers synchronous | Accepted |
| [0015](0015-session-store-behind-a-protocol.md) | Put the session store behind a protocol the host implements | Accepted |
| [0016](0016-memory-is-written-by-the-owner-not-the-model.md) | Memory is written by the session's owner, not by the model, and is bounded | Accepted; the "no tool" part superseded by 0017 |
| [0017](0017-memory-is-proposed-and-confirmed.md) | Separate proposing a memory from activating one | Accepted |
| [0018](0018-transcript-items-carry-their-run-id.md) | Stamp every transcript item with the id of the run that wrote it | Accepted |
| [0019](0019-a-run-records-how-it-was-configured.md) | Record how each run was configured, as evidence rather than a runs table | Accepted |

## Writing a new one

Copy the four headings from any existing record. Keep it to one decision — a
record covering three is three records that cannot be superseded independently.

Write the **Context** as it was at the time, in present tense, without the
benefit of hindsight. A future reader needs to know what was and was not known
when the call was made; that is what makes it possible to tell a decision that
has aged badly from one that was wrong to begin with.

Write the **Consequences** honestly, including the ones you dislike. A record
listing only benefits is marketing, and it is worthless six months later when
someone is deciding whether to reverse it.
