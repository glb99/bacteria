"""Running one ingestion, from raw records to a stored batch.

Thin by design: assemble the pipeline, hand it a batch, return what came back.
The decisions live in `pipeline.py`; the writing lives in `repository.py`.

Not built:
    Background execution. This runs inline, so a caller waits for the whole
    batch — see the note on batch size in `views.py`. The event loop is no
    longer blocked for its duration, now that the chain and the repository are
    async, but a caller holding a connection open for a large batch is still the
    wrong shape. Anything large belongs in a worker; the stub for one is in
    `fastpaip.entrypoints.queue_worker`, and what it is waiting on is recorded
    there.

    Rejection of an id that already exists in the database. The pipeline rejects
    duplicates *within* a batch only. Across batches, a repeated external_id is
    stored twice, because choosing between "update the existing row" and "reject
    the new one" is a policy decision nobody has made — and picking one silently
    here would make it very hard to notice later.
"""

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.ingestion.pipeline import Batch, build_pipeline
from fastpaip.ingestion.repository import IngestionRepository


async def ingest(session: AsyncSession, source: str, records: list[dict[str, Any]]) -> Batch:
    """Validate, normalize, and store a batch of records."""
    pipeline = build_pipeline(persist=IngestionRepository(session).persist)
    return await pipeline.handle(Batch(source=source, raw=records))
