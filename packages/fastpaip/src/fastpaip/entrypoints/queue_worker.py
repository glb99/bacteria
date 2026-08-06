"""Background worker entrypoint.

Not built:
    All of it. Ingestion currently runs inline in the request that submits it,
    which bounds a batch to what a caller is willing to wait for and blocks the
    event loop while it runs.

    What goes here: a loop that consumes ingestion jobs from a broker and calls
    `fastpaip.ingestion.service.ingest`. What it is waiting on is a decision
    rather than code — which broker, and whether jobs need to be durable across
    a worker restart. Both are infrastructure commitments, and picking one to
    make this file non-empty would be choosing the least considered part of the
    system by accident.

    Until then this module exists as the named place for it, so that the absence
    is visible rather than merely true.
"""
