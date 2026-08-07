"""HTTP surface for submitting records."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fastpaip.auth.dependencies import CurrentPrincipal
from fastpaip.core.dependencies import DbSession
from fastpaip.ingestion.tasks import ingest_batch
from fastpaip.ingestion.service import ingest

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

MAX_RECORDS_PER_BATCH = 500
"""Bounded because ingestion runs inline, in the request that submits it.

Not a business rule — a consequence of there being no worker yet. A caller with
more than this to send has to page, and when background execution exists this
limit is the thing to remove first. See the gap in `fastpaip.ingestion.service`.
"""


class Submission(BaseModel):
    source: str = Field(min_length=1)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_RECORDS_PER_BATCH)


class RejectionOut(BaseModel):
    payload: dict[str, Any]
    reason: str


class BatchResult(BaseModel):
    batch_id: int | None
    accepted: int
    rejected: list[RejectionOut]


class BatchQueued(BaseModel):
    job_id: int


@router.post("/batches", response_model=BatchResult, status_code=201)
async def submit_batch(
    body: Submission, principal: CurrentPrincipal, db: DbSession
) -> BatchResult:
    """Ingest a batch now, and report exactly what happened to every record.

    Runs inline, so the caller waits and learns the outcome. That is the right
    shape for a batch small enough to wait for; anything larger belongs on
    ``/batches:defer``, which answers immediately and reports nothing.

    Rejections are returned in full rather than counted. A caller that sent 50
    records and is told 42 were accepted has no way to find the eight, and the
    reason is the only part that lets them fix it.

    Requires an authenticated caller. Note what is *not* here: a batch is not
    owned by the principal that submitted it, so any authenticated caller
    could read another's records once a read route exists. That is tolerable
    while every key belongs to one operator and is the first thing to fix if
    that changes -- see the tenancy gap in `fastpaip.ingestion`.

    A batch where nothing passes validation is still a 201, and still gets a
    batch row: the submission was received and recorded, and "your records were
    all invalid" is an outcome of a successful request rather than a failure of
    it. That batch is the one whose stored rejections matter most, so it is
    emphatically not the case that nothing is written.
    """
    batch = await ingest(session=db, source=body.source, records=body.records)

    return BatchResult(
        batch_id=batch.batch_id,
        accepted=len(batch.accepted),
        rejected=[RejectionOut(payload=r.payload, reason=r.reason) for r in batch.rejected],
    )


@router.post("/batches:defer", response_model=BatchQueued, status_code=202)
async def defer_batch(
    body: Submission, principal: CurrentPrincipal, db: DbSession
) -> BatchQueued:
    """Hand the batch to a worker and answer immediately.

    ``202``, not ``201``: nothing has been ingested yet, and saying otherwise
    would make a caller believe a batch row exists that does not. The response
    carries a job id and no outcome, because there is no outcome yet.

    The job is enqueued **inside this request's transaction**, so it commits
    with everything else the request did or not at all. That is the whole
    reason the queue lives in Postgres — with a broker there is a window where
    the request succeeds and the work silently never happens.

    Not built:
        Any way to ask how the job went. The job id is real and can be looked
        up in the jobs table by hand, but there is no route for it, so a caller
        that wants the outcome has to poll the batch instead -- and cannot,
        because no read route exists either. Deferred ingestion is genuinely
        fire-and-forget today, and that is the first thing to fix if anything
        depends on the result.
    """
    job_id = await ingest_batch.defer_async(source=body.source, records=body.records)
    return BatchQueued(job_id=job_id)
