"""Cross-cutting infrastructure: the contracts and structures features share.

Owns the shapes that let features be composed without knowing about each other
— repository protocols, the handler chain, the adapter that bridges plain
functions into it — plus the process-wide concerns every feature needs and none
should configure for itself: settings, database session factory, logging.

Must not contain business logic. A rule of thumb: nothing here should name a
domain concept. The moment something in this package knows what an "ingestion
job" or an "audio session" is, it belongs in that feature instead.

Nothing here imports a feature package. The dependency runs one way, and that
is what keeps `core` reusable rather than a second name for "miscellaneous".
"""
