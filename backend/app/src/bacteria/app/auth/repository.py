"""Storing and finding the two credentials: API keys and browser sessions."""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth.keys import GeneratedKey
from bacteria.app.auth.models import ApiKey, BrowserSession


class ApiKeyRepository:
    """Persists issued keys and resolves a presented one."""

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(self, generated: GeneratedKey, principal_id: str, label: str) -> ApiKey:
        """Store a newly issued key. Only its hash is written."""
        row = ApiKey(
            key_id=generated.key_id,
            secret_hash=generated.secret_hash,
            principal_id=principal_id,
            label=label,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def get_by_key_id(self, key_id: str) -> Optional[ApiKey]:
        """Find a key by its public half.

        Returns the row whether or not it is revoked. The caller checks, because
        "no such key" and "revoked key" must produce the same answer to a client
        and are worth telling apart in a log.
        """
        return await self._db.get(ApiKey, key_id)

    async def has_principal(self, principal_id: str) -> bool:
        """Whether any key has ever been issued to ``principal_id``.

        Revoked keys count, and that is the point rather than an oversight. The
        question is "is this a real principal or a mistyped one", and a
        principal whose only key was revoked is still real — excluding those
        would turn ordinary key rotation into a lockout.

        Selects one key id rather than counting: nothing needs the number, and
        ``limit(1)`` stops at the first row of a principal holding many.
        """
        found = await self._db.exec(
            select(ApiKey.key_id).where(ApiKey.principal_id == principal_id).limit(1)
        )
        return found.first() is not None

    async def list_keys(self, principal_id: Optional[str] = None) -> list[ApiKey]:
        """Every key issued, or one principal's, grouped by principal.

        Revoked keys are included, for the reason :attr:`ApiKey.is_active`
        gives: the row is kept so that "this key was valid until Tuesday" stays
        answerable, and hiding them here would leave an operator unable to tell
        a principal whose key was revoked from one that never existed at all —
        which is precisely the distinction :meth:`has_principal` is built on.

        Ordered by principal and then by issue date, rather than by date alone.
        The question this answers is "who exists and what do they hold", and a
        principal's keys sitting next to each other is what makes rotation
        legible; sorting by time scatters them for exactly the principals that
        hold more than one, which are the ones worth looking at.

        Returns whole rows rather than a projection. The caller decides what to
        show, and one of the columns — ``secret_hash`` — is the one thing that
        must not be shown, which is a rule about output and is stated where the
        output is written.
        """
        # `col()` rather than the bare attributes: at class level those are
        # `InstrumentedAttribute`, and only this wrapper tells a type checker so
        # -- `where()` above infers it from the comparison and `order_by()` has
        # nothing to infer from.
        statement = select(ApiKey).order_by(col(ApiKey.principal_id), col(ApiKey.created_at))
        if principal_id is not None:
            statement = statement.where(ApiKey.principal_id == principal_id)
        found = await self._db.exec(statement)
        return list(found.all())

    async def revoke(self, key_id: str) -> Optional[ApiKey]:
        """Mark a key unusable, keeping the row."""
        row = await self._db.get(ApiKey, key_id)
        if row is None or row.revoked_at is not None:
            return row
        row.revoked_at = datetime.now(timezone.utc)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row


class BrowserSessionRepository:
    """Persists browser sessions and resolves a presented cookie.

    A second class rather than more methods on :class:`ApiKeyRepository`. They
    answer the same shape of question about different tables, and a repository
    that owns two is one that has to be told which every call — see ADR 0005 for
    why the tables are separate to begin with.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def create(
        self, generated: GeneratedKey, principal_id: str, expires_at: datetime
    ) -> BrowserSession:
        """Open a session. Only the secret's hash is written."""
        row = BrowserSession(
            session_id=generated.key_id,
            secret_hash=generated.secret_hash,
            principal_id=principal_id,
            expires_at=expires_at,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def get(self, session_id: str) -> Optional[BrowserSession]:
        """Find a session by its public half, expired and revoked ones included.

        The caller checks :attr:`BrowserSession.is_active`, for the reason
        :meth:`ApiKeyRepository.get_by_key_id` gives: "no such session" and
        "expired session" must look identical to a client and are worth telling
        apart in a log.
        """
        return await self._db.get(BrowserSession, session_id)

    async def revoke(self, session_id: str) -> Optional[BrowserSession]:
        """End a session now, keeping the row.

        Logging out revokes rather than deletes, matching ``api_key`` — an
        authenticated action in the log should still have something behind it.
        Revoking an already-revoked or expired session is a no-op: a person
        clicking log out twice, or on a session that had already lapsed, has not
        made a mistake worth an error.
        """
        row = await self._db.get(BrowserSession, session_id)
        if row is None or row.revoked_at is not None:
            return row
        row.revoked_at = datetime.now(timezone.utc)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row
