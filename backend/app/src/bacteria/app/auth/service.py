"""Issuing and revoking credentials.

Deliberately not reachable over HTTP. Key issuance is the one operation that
cannot require a key without a bootstrapping problem — the first one has to come
from somewhere — and an endpoint that mints credentials is the single most
valuable thing on the service to compromise. It is an operator action, run from
`bacteria.app.entrypoints.cli`.
"""

from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth import keys
from bacteria.app.auth.models import ApiKey
from bacteria.app.auth.repository import ApiKeyRepository


async def issue_key(session: AsyncSession, principal_id: str, label: str) -> str:
    """Create a key for ``principal_id`` and return it in plaintext, once.

    Returns:
        The full token. This is the only moment it exists in readable form — the
        store keeps a hash — so a caller that discards it has to issue another.
    """
    generated = keys.generate()
    await ApiKeyRepository(session).create(generated, principal_id=principal_id, label=label)
    return generated.token


async def revoke_key(session: AsyncSession, key_id: str) -> Optional[ApiKey]:
    """Make a key unusable, keeping the record of it.

    Returns:
        The key, or ``None`` if no such id. Revoking an already-revoked key is a
        no-op and returns it unchanged — an operator revoking twice in a panic
        should not get an error.
    """
    return await ApiKeyRepository(session).revoke(key_id)
