"""Taking records from outside and turning them into rows we trust.

Owns the pipeline — validate, normalize, persist — and the tables it writes to.
The pipeline is assembled from `core.handlers`, which is what this feature
exists to demonstrate as much as to do: each step is a plain function that knows
nothing about the steps around it, and the order lives in one place.

Domain-neutral, and held that way deliberately. A record needs an
``external_id`` and a ``name``; every other key is stored exactly as it arrived
and is never inspected. So this fits contacts, products, devices, or documents
equally, and knows about none of them. The one exception — ``email`` being
lowercased — was removed once it was noticed, because a single special-cased
field made the behaviour inconsistent rather than merely limited.

If a caller needs per-field rules, they belong in an argument to
``build_pipeline``, supplied by whoever knows what the records mean. Worth
building when there are two callers wanting different rules, and not before.

Not built:
    Tenancy. Submitting requires authentication, but a batch is not owned by
    the principal that submitted it, and no read route exists that would
    enforce it if it were. Safe while every key belongs to one operator, and
    the first thing to fix when that stops being true.

Must not: reject silently. Every record that does not make it into the database
leaves a recorded reason. A batch that reports "42 accepted" out of 50 and
cannot say what happened to the other eight is worse than one that fails
outright, because it looks like it worked.
"""
