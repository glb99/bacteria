"""HTTP surface for submitting records."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fastpaip.core.dependencies import DbSession
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


@router.post("/batches", response_model=BatchResult, status_code=201)
async def submit_batch(body: Submission, db: DbSession) -> BatchResult:
    """Ingest a batch and report exactly what happened to every record.

    Rejections are returned in full rather than counted. A caller that sent 50
    records and is told 42 were accepted has no way to find the eight, and the
    reason is the only part that lets them fix it.

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
