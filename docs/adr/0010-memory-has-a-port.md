# 0010 — Memory has a port, so the graph can back it without replacing anything

## Status

Proposed — 2026-08-25.

Step two of the four-step order for making the graph what backs memory. [ADR 0008](0008-preferences-are-assertions.md) did step one: the graph can hold a preference and project it as keyed memory. Nothing calls it.

**Changes no behaviour.** The seam is introduced with one implementation behind it — the tables that back memory today — and the graph's implementation lands beside it as a configuration choice. Requires no migration.

## Context

Two memories exist and neither knows about the other. Two extractors read the same transcript. ADR 0024's retrieval — the graph deciding which memories surface — has no join to make, because a key/value entry is about nothing while a graph narrows by relationship.

The agreed destination is that `MemoryEntry` stays as the agent's contract and the graph becomes what backs it. That is a *protocol* boundary rather than a table boundary, and it matters: `bacteria.agent` carries real semver because things implement its protocols, so dropping tables is an application change while changing `MemoryEntry` is a major version bump invalidating five records.

### The step this record replaces

The plan said: **a graph-backed `SessionRepository`, protocol unchanged, both implementations runnable side by side** — and called that the honest way to settle 0006's kill criterion. One protocol, two backings, compared.

**There is no second implementation to write.** `SqlSessionRepository` is 760 lines and memory is about half of it. The rest is `create_session`, `list_sessions`, `get_state`'s transcript half, `commit` and `extraction_progress` — sessions, conversation, and an extraction watermark. **None of that is memory and none of it moves to the graph**, which holds no transcripts and never will.

So a "graph-backed repository" would be a class that delegates most of its surface to the SQL one and overrides five methods. That is one implementation with a swappable part, described as two implementations of a protocol — and building it that way would make the comparison worse, because the two objects would differ in places that have nothing to do with the question.

## Decision

### 1. A `MemoryStore` port, narrower than `SessionRepository`

A protocol in `app/chat/` covering exactly what varies:

```python
class MemoryStore(Protocol):
    async def entries(self, session_id: str, user_id: str) -> MemoryView: ...
    async def remember(self, session_id: str, user_id: str, key: str,
                       entry: MemoryEntry, scope: MemoryScope) -> None: ...
    async def forget(self, session_id: str, user_id: str, key: str,
                     scope: MemoryScope) -> None: ...
    async def propose(self, session_id: str, source: str, key: str,
                      entry: MemoryEntry) -> None: ...
    async def activate(self, session_id: str, user_id: str, source: str,
                       key: str, scope: MemoryScope) -> None: ...
    async def reject(self, session_id: str, source: str, key: str) -> None: ...
```

`MemoryView` is the three collections `SessionState` already declares — `memory`, `user_memory`, `proposals` — returned together because `get_state` needs all three and two round trips would let them disagree.

**What is deliberately not on it**: sessions, the transcript, `commit`, `extraction_progress`, `known_keys` and `count_proposals`. Those are identical under either backing, and a port that included them would be asking two implementations to agree about things nobody is questioning.

### 2. `SqlSessionRepository` composes one, and stops implementing it

The memory methods become delegation. The class keeps its protocol conformance — callers, routes and the agent see nothing — and stops being where memory is *decided*.

This is the whole of the change in the first version: a move, not a rewrite, with the existing SQL behaviour lifted into `TableMemoryStore` unchanged.

### 3. The graph's implementation is a second class, not a second repository

`GraphMemoryStore` reads through 0008's `preferences_for` and writes assertions:

| method | graph |
|---|---|
| `entries` | stated preferences → `memory` / `user_memory`; inferred ones → `proposals` |
| `remember` | append an assertion with `origin="stated"` |
| `propose` | append with `origin="inferred"` |
| `activate` | append the same triple with `origin="stated"` |
| `reject` / `forget` | retract |

Every one of those already exists. **This record adds an interface and a caller, not a mechanism.**

### 4. Selected by configuration, defaulting to the tables

One setting, defaulting to what runs today. The graph's store is opt-in until it has been compared, and the comparison is the point.

**Not a per-request choice and not a fallback chain.** A store that silently fell back would make "which memory answered" unanswerable exactly when a discrepancy appeared, which is the question the whole exercise exists to ask.

### 5. The structural guarantee has to be restated, because it moves

The agent's ADR 0017 rests on something sharp: *two tables let each primary key state its own rule, and make "reaches the model" a question of which table a row is in rather than of a column someone must remember to filter on.*

Under `TableMemoryStore` that is unchanged. Under `GraphMemoryStore` it becomes `origin = "stated"` — a **column someone must remember to filter on**, which is exactly the trade 0017 warned against.

So the filter lives in **one function**, `preferences_for`, which is the only thing that reads assertions on behalf of a prompt. Not a discipline spread across a store: a single named place, with a test asserting that an `inferred` preference never appears in a `MemoryView`. That is weaker than two tables and it is the strongest thing available once one store holds both, and saying so plainly is better than discovering it later.

## Consequences

**The kill criterion becomes measurable rather than arguable.** 0006 asks whether the graph beats recency, and it was going to be answered by swapping a large object with many differences. It is now answered by swapping the source of a keyed lookup with everything around it held fixed — the difference between a comparison and an anecdote.

**The transition carries one implementation of everything not in question.** That is the objection the plan recorded and could not price: two full repositories means keeping two things correct for as long as the transition lasts.

**`chat/` still owns memory tables**, and this record does not change that. It changes where the decision to use them is made.

**A discrepancy is now observable.** With both stores present, the same question can be asked of each. Nothing here builds that, and it is the obvious next thing.

### The one to dislike

**This is a refactor of shipped, working code for the benefit of an experiment that may fail.** If the graph loses its kill criterion, the port stays behind as a seam nobody needed, in a class that was coherent before.

The defence is that the seam is small, mechanical, and would be wanted anyway the first time memory needs a second backing for any reason. It is not the defence that the experiment will succeed.

## Alternatives rejected

**A graph-backed `SessionRepository`**, as originally planned. There is no second implementation of the other 380 lines, so it would be delegation dressed as substitution — and the two objects would differ in places irrelevant to the question, which is how a comparison becomes an anecdote.

**Dual-write to both stores.** Tempting, because it would let a discrepancy be observed without choosing. It doubles every write path, makes failure modes conditional on which write failed, and turns "which is right" into a question with two wrong answers rather than a comparison.

**Wait for retrieval.** The graph cannot influence what a model is told until something reads it, so retrieval and this are often confused for one another. They are separable: this decides *where a keyed memory comes from*, and retrieval decides *which memories are worth surfacing*. Doing retrieval first means building ranking over a store nothing yet reads.

## Not built

**The comparison itself** — running both stores against the same question and reporting where they differ. It is what makes the kill criterion answerable and it needs the port to exist first.

**Preference extraction.** Nothing writes a preference to the graph yet; 0008 made it representable and the extractor does not propose one. `GraphMemoryStore` would therefore start empty, which is honest and will look broken.

**Steps three and four** — retiring the transcript memory extractor, and dropping the tables. Both wait on the comparison.
