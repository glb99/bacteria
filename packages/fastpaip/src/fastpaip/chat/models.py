"""Tables behind the agent's session state.

Three tables, not one, mirroring the split the agent insists on: transcript,
working state, and memory have different lifecycles, and a single JSON blob per
session would merge them back together in storage even while the code kept them
apart. Transcript is append-only rows; memory is keyed rows that are overwritten
and deleted; working state is per-session scratch and lives on the session row.

Payloads are stored as JSON columns rather than modelled further. A transcript
item's payload shape depends on its ``kind`` and is the agent's business, not
this schema's — normalizing it here would mean this application had opinions
about what a tool call looks like, and would need a migration every time the
agent gained a new kind of event.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime
from sqlmodel import JSON, Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# SQLite drops timezone information on the way in and hands back naive
# datetimes, which then compare as if they were local time. Storing with an
# explicit timezone-aware column keeps round trips honest on backends that
# support it; see `_as_utc` in repository.py for the read side.
def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)


class ChatSession(SQLModel, table=True):
    """One conversation. The row the other two tables hang off.

    ``user_id`` is a plain column and not a foreign key: the agent's notion of a
    user is "whoever owns this session", and binding it to an accounts table
    would make the agent's storage depend on a feature it knows nothing about.
    """

    __tablename__ = "chat_session"

    session_id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    working_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ChatTranscriptItem(SQLModel, table=True):
    """One entry in the durable record. Append-only.

    ``seq`` orders the transcript explicitly rather than relying on ``id`` or on
    ``timestamp``. Autoincrement ordering is an implementation detail that a
    different backend may not preserve, and two items committed in the same turn
    can share a timestamp to the microsecond.
    """

    __tablename__ = "chat_transcript_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chat_session.session_id", index=True)
    seq: int = Field(index=True)
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())


class ChatMemoryEntry(SQLModel, table=True):
    """One deliberately preserved fact, keyed within its session.

    ``value`` is wrapped in a JSON object rather than stored bare, because a
    memory's value may be any JSON type — including ``null``, a string, or a
    number — and a bare JSON column cannot distinguish "stored null" from "no
    row" on every backend.
    """

    __tablename__ = "chat_memory_entry"

    session_id: str = Field(foreign_key="chat_session.session_id", primary_key=True)
    key: str = Field(primary_key=True)
    value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
