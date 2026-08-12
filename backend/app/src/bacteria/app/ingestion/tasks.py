"""Ingestion as a background job.

The task is a thin shell: it opens a session and calls the same
:func:`bacteria.app.ingestion.service.ingest` the inline route uses. Both paths run
identical code, which is the only way "we moved ingestion to a worker" can avoid
becoming "we now have two ingestion implementations that drift".

The records travel in the job's arguments, which bounds a batch by what is
reasonable to store as JSON in a row rather than by what a caller will wait for.
That is a much larger bound, not an absent one — a genuinely huge import wants
the payload in object storage and a reference in the job, and that is not built.
"""

import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.core.db import get_engine
from bacteria.app.core.jobs import get_app
from bacteria.app.ingestion.service import ingest

logger = logging.getLogger(__name__)


@get_app().task(name="ingest_batch", queue="ingestion")
async def ingest_batch(source: str, records: list[dict[str, Any]]) -> dict[str, int]:
    """Validate, normalize, and store a batch, away from any request.

    Returns a summary rather than the batch: a task's return value is stored in
    the jobs table, and putting every accepted record there would duplicate the
    whole import into a second place that nothing reads.

    Retries are deliberately not configured. Ingestion is not idempotent — the
    pipeline only detects duplicates *within* a batch, so a retried job stores
    every record a second time. Making this retryable means deciding what a
    repeated ``external_id`` across batches should do, which nobody has.
    """
    async with AsyncSession(get_engine()) as session:
        batch = await ingest(session, source=source, records=records)

    logger.info(
        "ingested batch",
        extra={
            "batch_id": batch.batch_id,
            "source": source,
            "accepted": len(batch.accepted),
            "rejected": len(batch.rejected),
        },
    )
    return {
        "batch_id": batch.batch_id or 0,
        "accepted": len(batch.accepted),
        "rejected": len(batch.rejected),
    }
