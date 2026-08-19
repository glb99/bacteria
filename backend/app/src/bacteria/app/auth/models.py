"""The stored halves of the two credentials this service accepts.

Neither secret is here. Only their hashes are, which is what makes a leaked
database dump an inconvenience rather than a set of working credentials.

The two tables are deliberately not one. They share four columns and differ in
the thing that matters: a key is valid until revoked, a browser session is valid
until it expires. Merging them would mean a nullable ``expires_at`` and a rule,
written nowhere the database can enforce it, that one kind of row must have it
and the other must not. See
[ADR 0005](../../../../../docs/adr/0005-a-browser-holds-a-session-not-a-key.md).
"""

from datetime import datetime, timedelta, timezone
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


SESSION_LIFETIME = timedelta(hours=12)
"""How long a browser session lasts before it must be established again.

A working day, chosen so that a console left open through one is not
interrupted and one left open overnight is. There is no refresh: the exchange
costs pasting a key that the operator already has, and a session that renews
itself for as long as a tab stays open is not really expiring.

A constant rather than a setting. Nothing has needed a different value, and this
repository's own rule about that is
[ADR 0004](../../../../../docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md)'s
on scopes: a knob nobody has needed is a knob nobody has tested.
"""


class BrowserSession(SQLModel, table=True):
    """One browser's proof of identity, exchanged for a key and expiring.

    **Expiry is the whole reason this is not an ``ApiKey`` row.** A key lives in
    an operator's password manager and is revoked deliberately; this lives in a
    cookie on a machine that might be a shared laptop, and the mitigation for
    that is that it stops working on its own. `keys.py` records "Not built:
    Expiry" for keys and explains why — automatic expiry with no rotation story
    locks people out. The reasoning inverts here: nothing is locked out by a
    session ending, because establishing another costs one paste.

    ``principal_id`` is copied rather than joined to the key that established
    it. Revoking that key must not retroactively orphan the sessions it opened —
    the same reason `ApiKey` separates ``principal_id`` from ``key_id`` — and a
    session outliving its parent key by up to its lifetime is the accepted cost,
    stated here because it is the kind of thing that reads as an oversight.
    """

    __tablename__ = "browser_session"

    session_id: str = Field(primary_key=True)
    secret_hash: str
    principal_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_tz_column())
    expires_at: datetime = Field(sa_column=_tz_column())
    revoked_at: Optional[datetime] = Field(default=None, sa_column=_tz_column(nullable=True))

    @property
    def is_active(self) -> bool:
        """Whether this session may still authenticate.

        Two ways to be inactive and both are checked here rather than at the
        call site, because a caller that remembered one and forgot the other
        would accept an expired session forever and nothing would look wrong.

        ``expires_at`` is compared against an aware ``utcnow``. The column is
        ``DateTime(timezone=True)`` for the reason `conftest` gives at length:
        under SQLite this comparison raised ``TypeError`` on naive values, which
        is precisely why there is no SQLite here any more.
        """
        return self.revoked_at is None and self.expires_at > _utcnow()
