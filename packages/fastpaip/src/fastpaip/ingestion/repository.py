"""Writing a completed batch to the database.

One method, called once per batch, inside a single transaction: a batch is
either recorded whole or not at all. Committing per record would leave a
half-ingested batch behind on failure, with no way to tell which half.

``persist`` is a coroutine, which is only possible because the handler chain
awaits its steps. While the chain was synchronous this method had to be too, and
ingestion could not be made non-blocking by any change confined to this file.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.ingestion.models import IngestedRecord, IngestionBatch, RejectedRecord
from fastpaip.ingestion.pipeline import Batch


class IngestionRepository:
    """Persists batches, their accepted records, and their rejections.

    Args:
        session: Injected, so transaction scope belongs to the caller.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def persist(self, batch: Batch) -> Batch:
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
        await self._db.flush()  # assigns row.id without ending the transaction

        # Read the id now, not after the commit below. A session expires its
        # objects on commit, so a later `row.id` would trigger a reload — which
        # is IO, attempted outside an await, and fails as MissingGreenlet rather
        # than as anything that names the real problem.
        batch_id = row.id
        if batch_id is None:
            # `flush` is what assigns it, so this cannot happen — and it is
            # checked rather than suppressed because the failure it would
            # otherwise produce is silent: every child row below would take a
            # null foreign key, and a batch's records would be orphaned from the
            # batch with nothing raising. The type says Optional because
            # SQLModel's autoincrement primary key is unset before insert.
            raise RuntimeError("ingestion batch has no id after flush")

        for record in batch.accepted:
            self._db.add(
                IngestedRecord(batch_id=batch_id, external_id=record["external_id"], payload=record)
            )
        for rejection in batch.rejected:
            self._db.add(
                RejectedRecord(
                    batch_id=batch_id,
                    source_index=rejection.index,
                    reason=rejection.reason,
                    payload=rejection.payload,
                )
            )

        await self._db.commit()
        batch.batch_id = batch_id
        return batch
