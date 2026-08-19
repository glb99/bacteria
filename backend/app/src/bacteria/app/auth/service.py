"""Issuing and revoking credentials.

**Key issuance is deliberately not reachable over HTTP.** It is the one
operation that cannot require a key without a bootstrapping problem — the first
one has to come from somewhere — and an endpoint that mints credentials is the
single most valuable thing on the service to compromise. It is an operator
action, run from `bacteria.app.entrypoints.cli`.

**Browser sessions are, and that is not the same claim.** `POST /auth/session`
does not mint a credential from nothing: it takes a key the caller already
holds, proves it, and hands back something strictly weaker — no ability to
issue, a twelve-hour life, and revocable on its own. Compromising that endpoint
gets an attacker exactly what presenting the key they already had would have.
The bootstrapping argument is untouched, because the bootstrap still happens at
`bacteria-admin issue-key`. See
[ADR 0005](../../../../../docs/adr/0005-a-browser-holds-a-session-not-a-key.md).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth import keys
from bacteria.app.auth.models import SESSION_LIFETIME, ApiKey, BrowserSession
from bacteria.app.auth.repository import ApiKeyRepository, BrowserSessionRepository


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


async def open_browser_session(session: AsyncSession, principal_id: str) -> tuple[str, datetime]:
    """Open a session for a principal whose key has *already* been verified.

    **Takes a principal id, not a key**, and the signature is the guard. A
    function here that accepted a token would be one that could be called
    without checking it; the caller proves the key through
    :func:`~bacteria.app.auth.dependencies.principal_for_key` and passes what
    that returned, so "was this verified" is answered by the type rather than by
    reading the call site.

    Returns:
        The token, in the only moment it exists in readable form, and when it
        expires. The expiry is returned rather than recomputed by the caller so
        that the cookie's ``max-age`` and the row cannot disagree — a cookie
        outliving its row is a confusing 401 and a row outliving its cookie is a
        session nothing can reach.
    """
    generated = keys.generate(keys.SESSION_PREFIX)
    expires_at = datetime.now(timezone.utc) + SESSION_LIFETIME
    await BrowserSessionRepository(session).create(
        generated, principal_id=principal_id, expires_at=expires_at
    )
    return generated.token, expires_at


async def close_browser_session(session: AsyncSession, token: str) -> Optional[BrowserSession]:
    """End the session a cookie names, if it names a real one.

    Not behind :data:`CurrentPrincipal`, on purpose: logging out is not an
    action anyone needs permission for, and requiring a *valid* session to end
    one would refuse exactly the person whose session has gone wrong — an
    expired cookie could then never be cleared server-side.

    **The secret is still checked**, and that is not the same thing as requiring
    a live session. Revoking on the session id alone would make logout an
    unauthenticated write against any id an attacker could name, and ids are not
    secret — this module's own failure logs print them. Sixty-four bits makes
    guessing impractical rather than impossible, and "impractical" is a poor
    reason to accept a write nobody proved they were entitled to.

    Returns:
        The session, or ``None`` if the cookie was malformed, unknown, or not
        backed by the right secret. The caller reports success either way — see
        the view.
    """
    parsed = keys.split(token, keys.SESSION_PREFIX)
    if parsed is None:
        return None

    session_id, secret = parsed
    repository = BrowserSessionRepository(session)
    row = await repository.get(session_id)
    if row is None or not keys.matches(secret, row.secret_hash):
        return None

    return await repository.revoke(session_id)
