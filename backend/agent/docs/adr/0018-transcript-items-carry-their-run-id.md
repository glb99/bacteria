# 0018 — Transcript items carry the id of the run that wrote them

## Status

Accepted — 2026-08-11

## Context

`run_turn` generates a `run_id`, threads it through the step tracker as a key
prefix, returns it on `RunResult`, and stores it nowhere. The application hands
it back to HTTP callers in the turn response. There is nothing to look it up
against.

That was harmless while state was in-memory and a process held one session for
one turn: the transcript *was* the run. It stopped being harmless when the store
became Postgres and one session began accumulating many turns from many
requests.

The failure it leaves open is the one [ADR
0012](0012-commit-evidence-on-failure.md) half-solved. A failed turn now commits
its evidence — the user's message and a `run_error` — and re-raises. The caller
sees a 500 and retries. The transcript then holds the abandoned attempt and the
successful one as a single undifferentiated stream, ordered correctly and
attributable to nothing. Evidence was preserved; the boundary between one
attempt and the next was not, which is most of what makes evidence readable.

Part 8's first checklist item is "every meaningful run has a trace ID and a
session ID — a user-visible outcome must map back to the run that produced it."
Session identity is solid here: it is the foreign key on every row, and `seq`
orders the transcript under a unique constraint. Run identity is generated and
discarded.

## Decision

`TranscriptItem` gains `run_id: str | None`. `Runtime` sets it at every point it
constructs evidence. The SQL store persists it as an indexed column.

**A field, not a payload key.** `payload` has a different shape per `kind` —
that is what makes it a payload. `run_id` is the same for every kind, which is
what makes it a field. It also means "everything from run X" is an index scan
rather than a reach into JSON.

**Nullable, and not stamped by `commit`.** Stamping in the store was the
tempting option: `commit` is the single write path ([ADR
0004](0004-single-commit-path.md)), so a stamp there could not be bypassed and
the invariant would be structural rather than remembered. It was rejected
because it makes the store hold a concept it has no other use for, and because a
`commit` carrying items from two runs — which nothing does today and the
protocol permits — would have to lie about one of them. The runtime knows which
run it is in; the store does not, and should not have to be told in order to
append a row.

Nullable is therefore the honest type: rows written before this change have no
run, and a working-state-only commit is not a run. Neither gets a fabricated id.

**The cost of that choice is paid by a test.** Optional means a missed
construction site is silent, so the invariant — every item a run commits carries
that run's id, on the success path and the failure path both — is asserted
directly rather than left to review.

## Consequences

A run is reconstructable from storage. The `run_id` in a turn response now
selects the rows that response was produced from, which is what makes a bug
report and a transcript the same object.

Retries stop being ambiguous. Two attempts at the same message are two runs, and
the abandoned one is identifiable rather than inferred from a `run_error` sitting
next to it.

The nullable column is a permanent asymmetry: existing rows will read `null`
forever, and code reading it must handle that. Backfilling was not attempted
because the information does not exist — no run id was ever written down.

This closes checklist item 1 and nothing else. The run's model and provider, the
assembled context, the tools exposed, the approval decision, and latency remain
unrecorded, so a `run_id` groups the evidence without explaining how the run was
configured. The API does not expose `run_id` on the transcript route and there
is no route that takes one. Both are additive once something needs them.
