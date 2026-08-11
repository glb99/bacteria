"""Reading finished runs back out of the transcript.

The transcript is an event log, ordered and flat. A *run* is a slice of it —
everything one turn wrote, which since bacteria's ADR 0018 is everything sharing
a ``run_id``, and since ADR 0019 always ends with a ``run_meta`` item describing
how that turn was configured. This module puts the slice back together.

Named ``evaluation`` rather than ``eval`` because the latter is a builtin, and
shadowing it inside a package that will be imported by a command-line tool is a
small trap for no gain.

Kept apart from :mod:`fastpaip.evaluation.checks` on purpose. Loading is the
part that knows about SQL and about how evidence is laid out; a check should
read a plain object and say whether it likes what it sees. That split is what
lets the same checks run against a seeded fixture database and against a
production one without knowing which they were handed.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.chat.models import ChatTranscriptItem


@dataclass(frozen=True)
class RecordedRun:
    """One turn, as it survives in storage.

    Everything here was read back rather than observed happening, which is the
    whole point: a check that could only run while the turn was in flight is a
    test, and this is meant to be pointable at a database nobody was watching.

    Attributes:
        run_id: Groups the evidence. ``None`` is impossible here — runs are
            built by grouping on it — but rows written before ADR 0018 have no
            run and are skipped by the loader rather than collected under a
            fake id.
        meta: The ``run_meta`` payload, or an empty dict when the run has none.
            Empty is itself a finding rather than a reason to skip: a run that
            wrote messages and no description is exactly the regression that
            would make every other check silently pass over it.
        tool_calls: ``tool_call`` payloads in transcript order.
        message_count: How many messages the run committed.
        has_error: Whether a ``run_error`` was recorded.
    """

    run_id: str
    session_id: str
    meta: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    message_count: int = 0
    has_error: bool = False

    @property
    def model(self) -> Optional[str]:
        return self.meta.get("model")

    @property
    def tools_exposed(self) -> list[str]:
        return list(self.meta.get("tools_exposed") or [])

    @property
    def outcome(self) -> Optional[str]:
        return self.meta.get("outcome")

    @property
    def completed(self) -> bool:
        return self.outcome == "completed"


async def load_runs(db: AsyncSession, session_id: Optional[str] = None) -> list[RecordedRun]:
    """Rebuild every run visible in the transcript, oldest first.

    Args:
        session_id: Restrict to one conversation. Omitted, this reads every run
            in the database, which is what a policy check over a deployment
            wants and what a fixture-seeded check gets for free.

    Rows with no ``run_id`` are skipped rather than grouped together. They exist
    — anything written before the column did — and collecting them under a
    single synthetic run would invent a turn that never happened, then report
    findings about it.
    """
    statement = select(ChatTranscriptItem).order_by(
        ChatTranscriptItem.seq  # ty: ignore[invalid-argument-type]
    )
    if session_id is not None:
        statement = statement.where(ChatTranscriptItem.session_id == session_id)

    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in (await db.exec(statement)).all():
        if item.run_id is None:
            continue
        if item.run_id not in grouped:
            grouped[item.run_id] = {
                "session_id": item.session_id,
                "meta": {},
                "tool_calls": [],
                "message_count": 0,
                "has_error": False,
            }
            order.append(item.run_id)

        bucket = grouped[item.run_id]
        if item.kind == "run_meta":
            bucket["meta"] = dict(item.payload)
        elif item.kind == "tool_call":
            bucket["tool_calls"].append(dict(item.payload))
        elif item.kind == "message":
            bucket["message_count"] += 1
        elif item.kind == "run_error":
            bucket["has_error"] = True

    return [RecordedRun(run_id=run_id, **grouped[run_id]) for run_id in order]
