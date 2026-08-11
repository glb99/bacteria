"""The stored half of an API key.

The secret is not here. Only its hash is, which is what makes a leaked database
dump an inconvenience rather than a set of working credentials.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column(nullable: bool = False) -> Column:
    return Column(DateTime(timezone=True), nullable=nullable)


class ApiKey(SQLModel, table=True):
    """One issued credential, and the principal it authenticates.

    ``principal_id`` is separate from ``key_id`` so that a principal can hold
    several keys and rotate between them. Tying ownership to the key instead
    would mean revoking a key orphaned everything created with it.
    """

    __tablename__ = "api_key"

    key_id: str = Field(primary_key=True)
    secret_hash: str
    principal_id: str = Field(index=True)
    label: str
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    revoked_at: Optional[datetime] = Field(default=None, sa_column=_tz_column(nullable=True))

    @property
    def is_active(self) -> bool:
        """Whether this key may still authenticate.

        Revocation is a timestamp rather than a deleted row, so that "this key
        was valid until Tuesday" stays answerable. A deleted key leaves an
        authenticated action in the logs with nothing behind it.
        """
        return self.revoked_at is None
