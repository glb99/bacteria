"""Writing a completed batch to the database.

One method, called once per batch, inside a single transaction: a batch is
either recorded whole or not at all. Committing per record would leave a
half-ingested batch behind on failure, with no way to tell which half.
"""

from sqlmodel import Session as DbSession

from fastpaip.ingestion.models import IngestedRecord, IngestionBatch, RejectedRecord
from fastpaip.ingestion.pipeline import Batch


class IngestionRepository:
    """Persists batches, their accepted records, and their rejections.

    Args:
        session: Injected, so transaction scope belongs to the caller.
    """

    def __init__(self, session: DbSession) -> None:
        self._db = session

    def persist(self, batch: Batch) -> Batch:
        """Store the whole batch and stamp it with its id.

        Rejections are written too. They are the only record of what a caller
        actually sent that did not make it, and a count alone cannot answer
        "which ones, and why".

        Returns:
            The same batch, with ``batch_id`` set — the pipeline threads the
            object onward rather than replacing it.
        """
        row = IngestionBatch(
            source=batch.source,
            accepted_count=len(batch.accepted),
            rejected_count=len(batch.rejected),
        )
        self._db.add(row)
        self._db.flush()  # assigns row.id without ending the transaction

        for record in batch.accepted:
            self._db.add(
                IngestedRecord(
                    batch_id=row.id, external_id=record["external_id"], payload=record
                )
            )
        for rejection in batch.rejected:
            self._db.add(
                RejectedRecord(
                    batch_id=row.id, reason=rejection.reason, payload=rejection.payload
                )
            )

        self._db.commit()
        batch.batch_id = row.id
        return batch
