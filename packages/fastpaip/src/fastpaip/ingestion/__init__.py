"""Taking records from outside and turning them into rows we trust.

Owns the pipeline — validate, normalize, persist — and the tables it writes to.
The pipeline is assembled from `core.handlers`, which is what this feature
exists to demonstrate as much as to do: each step is a plain function that knows
nothing about the steps around it, and the order lives in one place.

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
