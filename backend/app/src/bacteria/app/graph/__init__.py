"""The memory graph: what this system believes, and when it believed it.

Owns the assertion log, the conclusions drawn from it, and — later — the review
surface where a person contests both. A feature of its own rather than part of
``chat``, because ``chat`` owns a conversation and this owns a model of the
world that outlives every conversation it was learned in. See ADR 0006.

The distinction that shapes everything here is between an **assertion** and a
**projection**. An assertion is a claim someone or something made, with two time
axes: when it was true in the world, and when this system came to believe it.
Nothing edits one. A projection — the current graph, an embedding, a derived
property — is folded from assertions and may be thrown away and rebuilt, because
its inputs are kept. The rule for deciding which a new thing is: *could it be
regenerated deterministically from what we keep?* A model call or a human
decision in its history means no, and means durable.

Must not: write text a model will read. This package may decide *which* already
confirmed memories are surfaced and may propose new ones for a person to accept,
which is the boundary the agent's ADR 0024 draws and ADR 0017 exists to hold. An
index ranks; it does not speak.

Not built:
    Everything past the schema. The projection fold, constraint evaluation, the
    staleness walk, entity resolution, the review routes and the retrieval
    supplier are all specified in ADR 0006 and none of them exist yet. The
    schema is first because it is the part that is expensive to change once
    there are rows, and because nothing else can be written against a shape that
    is still moving.
"""
