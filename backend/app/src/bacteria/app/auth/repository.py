"""Storing and finding API keys."""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth.keys import GeneratedKey
from bacteria.app.auth.models import ApiKey


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
