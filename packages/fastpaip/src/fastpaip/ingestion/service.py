"""Running one ingestion, from raw records to a stored batch.

Thin by design: assemble the pipeline, hand it a batch, return what came back.
The decisions live in `pipeline.py`; the writing lives in `repository.py`.

Not built:
    Background execution. This runs inline, so a caller waits for the whole
    batch and the event loop is blocked for its duration — see the note on batch
    size in `views.py`. Anything large belongs in a worker; the stub for one is
    in `fastpaip.entrypoints.queue_worker`, and what it is waiting on is
    recorded there.

    Rejection of an id that already exists in the database. The pipeline rejects
    duplicates *within* a batch only. Across batches, a repeated external_id is
    stored twice, because choosing between "update the existing row" and "reject
    the new one" is a policy decision nobody has made — and picking one silently
    here would make it very hard to notice later.
"""

from typing import Any

from sqlmodel import Session as DbSession

from fastpaip.ingestion.pipeline import Batch, build_pipeline
from fastpaip.ingestion.repository import IngestionRepository


def ingest(session: DbSession, source: str, records: list[dict[str, Any]]) -> Batch:
    """Validate, normalize, and store a batch of records."""
    pipeline = build_pipeline(persist=IngestionRepository(session).persist)
    return pipeline.handle(Batch(source=source, raw=records))
