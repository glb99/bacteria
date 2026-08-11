# 0021 — Memory is scoped to a session or to a user, and the human picks

## Status

Accepted — 2026-08-11

## Context

Memory is session-scoped, and it is session-scoped for a reason that has
expired. The Part 5 record says so plainly: *"built for real, but in-memory and
session-scoped (no persistence backend exists yet, same constraint as Parts
3/4)."* The scope followed from the storage. There is now Postgres, a
`user_id` on every session, and authenticated principals.

The consequence is worse than a missing feature. Within one conversation, memory
is largely *redundant with the transcript window* — a preference stated three
turns ago is already in the last twenty messages. Memory earns its keep by
outliving the conversation that produced it, and today it cannot: every route is
`/sessions/{id}/memory`, and a user's second session starts blank.

Part 5's fourth failure mode is "missing scope": an item entering the prompt with
no owner boundary turns personalization into leakage. This project has exactly
one scope, implicit in which table row holds the entry, and no way to express
another.

## Decision

Memory is scoped. `MemoryScope` is `"session"` or `"user"`.

**Two collections, not a `scope` field.** `SessionState` gains `user_memory`
alongside `memory`. This follows [ADR 0017](0017-memory-is-proposed-and-confirmed.md):
which collection an entry is in *is* the fact about it, and an attribute could
disagree with the container holding it. The two are keyed the same way — by
`key` — but keyed *within different things*, a session and a user, which is the
distinction a single dict would erase.

**Session overrides user on the same key.** The narrower scope wins. A
preference stated in this conversation is more current than a standing one, and
the alternative — showing the model both — hands it a contradiction and no rule
for resolving it.

**The model cannot choose scope.** `propose` is unchanged and proposals stay
session-scoped; `activate` gains a `scope` argument. So the human confirming a
suggestion decides not only *whether* it persists but *how far*. This is the
same boundary ADR 0017 drew, one level finer: a model that could mark its own
suggestion user-scoped would be deciding that something it wrote applies to every
future conversation that person has, which is precisely the escalation
confirmation exists to prevent.

**The owner writes either scope directly**, via `remember(..., scope=...)` and
`forget(..., scope=...)`. They are the human that confirmation exists to insert,
so requiring them to confirm their own write would be ceremony — unchanged from
ADR 0016.

Storage is a second table keyed by `(user_id, key)`. The in-memory store keeps
user memory outside its per-session dict, because the semantics are the point:
two sessions belonging to one person must see the same user memory, and a store
that modelled it per-session would satisfy every signature while implementing
the old behaviour.

## Consequences

Memory now does the thing it exists for. A fact kept in one conversation is
available in the next, which is what makes it memory rather than a slower way of
reading the transcript.

The leakage surface is real and new. Reaching user memory requires: an
authenticated principal, who owns the session, whose `user_id` selects the rows.
Every link in that chain already existed; this is the first feature that depends
on all of them at once, which is why the conformance suite gets a test that two
users' sessions cannot see each other's memory rather than trusting the join.

`SessionRepository` grows argument surface on three methods rather than growing
new ones. That is deliberate — `remember_user` and `forget_user` would be a
second write path per scope, and the count of *paths* is what ADR 0015 was
protecting, not the count of parameters.

Existing memories stay session-scoped. There is no backfill, because nothing
recorded whether a fact was meant to outlive its conversation and guessing would
promote things nobody chose to promote.

Not decided here: expiry. A user-scoped memory now lasts indefinitely across
every future conversation, which makes the absence of a TTL matter more than it
did when the blast radius was one session. Also unbuilt: any indication of scope
or age in what the model is shown, so a standing preference and one stated this
morning still render identically.
