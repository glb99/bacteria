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


async def principal_is_known(session: AsyncSession, principal_id: str) -> bool:
    """Whether ``principal_id`` has ever held a key.

    **Not an authorization check, and must not be used as one.** It says a
    credential was issued to this principal at some point, not that the caller
    holds it — every route proves that with :data:`CurrentPrincipal` instead.

    [ADR 0004](../../../../../docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md)
    names this function as the one most likely to be misused that way, and this
    docstring as the only thing preventing it.

    It exists for the operator CLI, where the principal is *typed* rather than
    proven. ``chat_session.user_id`` has no foreign key, deliberately, so a
    mistyped principal creates a perfectly valid session owned by nobody: no
    key resolves to it, so no HTTP caller can ever read it back, and nothing
    reports the mistake. This is the check that would have caught the typo.

    Returns:
        Whether any key exists for the principal, revoked ones included.
    """
    return await ApiKeyRepository(session).has_principal(principal_id)


async def list_keys(session: AsyncSession, principal_id: Optional[str] = None) -> list[ApiKey]:
    """Every issued key, or one principal's, for an operator to read.

    **Also not an authorization check**, and less obviously so than
    :func:`principal_is_known` — this one returns rows, and rows look like
    facts a caller may act on. Nothing here decides access; it exists so that a
    person can answer "which principals are there" without opening a database
    client, which is what the CLI otherwise sent them to do.

    That gap was found by hitting it. ``bacteria-admin chat`` refuses an unknown
    principal and tells the operator to check the spelling — against nothing,
    because no command listed what the spellings were.

    Returns:
        Rows including revoked keys, oldest first within each principal.
    """
    return await ApiKeyRepository(session).list_keys(principal_id)


async def revoke_key(session: AsyncSession, key_id: str) -> Optional[ApiKey]:
    """Make a key unusable, keeping the record of it.

    Returns:
        The key, or ``None`` if no such id. Revoking an already-revoked key is a
        no-op and returns it unchanged — an operator revoking twice in a panic
        should not get an error.
    """
    return await ApiKeyRepository(session).revoke(key_id)
