"""Tables for ingested records and the batches they arrived in.

Rejections are stored, not just counted. A rejected record is the only evidence
of what a caller actually sent, and discarding it means the answer to "why is
this row missing" is a number.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime
from sqlmodel import JSON, Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class IngestionBatch(SQLModel, table=True):
    """One submission, whatever became of the records inside it."""

    __tablename__ = "ingestion_batch"

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)
    received_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    accepted_count: int = 0
    rejected_count: int = 0


class IngestedRecord(SQLModel, table=True):
    """One record that passed validation, as stored after normalization."""

    __tablename__ = "ingested_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="ingestion_batch.id", index=True)
    external_id: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class RejectedRecord(SQLModel, table=True):
    """One record that did not pass, kept alongside the reason it did not."""

    __tablename__ = "rejected_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: int = Field(foreign_key="ingestion_batch.id", index=True)
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
