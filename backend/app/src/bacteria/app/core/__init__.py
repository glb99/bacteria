"""Cross-cutting infrastructure: the contracts and structures features share.

Owns the shapes that let features be composed without knowing about each other
— the `Processable` step contract, the handler chain, the adapter that bridges
plain functions into it — plus the process-wide concerns every feature needs and
none should configure for itself: settings, database session factory, logging.

It owns no repository contract, and that is a finding rather than an omission:
the generic CRUD protocols that used to live here were declined by every
repository this application grew, and `core/protocols.py` records which and why.
A repository's contract belongs either to the feature that owns it or, where it
is a genuine seam, to the package whose callers are written against it — which
is `bacteria.agent.session.protocol`, not this one.

Must not contain business logic. A rule of thumb: nothing here should name a
domain concept. The moment something in this package knows what an "ingestion
job" or an "audio session" is, it belongs in that feature instead.

Nothing here imports a feature package. The dependency runs one way, and that
is what keeps `core` reusable rather than a second name for "miscellaneous".
"""
