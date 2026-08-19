"""Turning a request's credential into a principal, or refusing it.

The one place authentication happens. A route depends on
:data:`CurrentPrincipal` and receives an identity that has already been proven;
there is no way to reach a route with an unverified one, because the dependency
raises before the handler is called.

**Two credentials reach this module, and only one of them can be minted here.**
An API key is issued by the operator CLI and never expires; a browser session is
*exchanged* for one and expires on its own. `POST /auth/session` performs that
exchange by calling :func:`principal_for_key` below, so the verification a route
depends on and the verification the exchange performs are the same code rather
than two implementations that agree until one of them learns something. See
[ADR 0005](../../../../../docs/adr/0005-a-browser-holds-a-session-not-a-key.md).
"""

import logging
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bacteria.app.auth import keys
from bacteria.app.auth.principal import Principal
from bacteria.app.auth.repository import ApiKeyRepository, BrowserSessionRepository
from bacteria.app.core.dependencies import DbSession

logger = logging.getLogger(__name__)

_scheme = HTTPBearer(auto_error=False)

COOKIE_NAME = "bacteria_session"
"""The cookie a browser presents instead of a key.

Named here rather than in the view that sets it, because three places have to
agree on it: the exchange that sets it, the logout that clears it, and this
module, which reads it. A cookie name that drifts fails as "you are not logged
in", which is the least informative symptom available.
"""


UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
"""One response for every way authentication can fail.

Missing header, malformed token, unknown key id, wrong secret, revoked key,
expired session, revoked session, a session token sent as a bearer key — all
identical to the client. Distinguishing them tells an attacker which half of a
guess was right, and turns "find a valid key" into two much easier searches.
The distinction is kept in the log, where the operator can see it and the client
cannot.

**This got harder to hold when the cookie arrived**, and it is the property most
worth protecting here: two credentials means twice as many failure modes, and
any one of them answering differently reintroduces the oracle for all of them.
"""


async def principal_for_key(db: DbSession, token: str) -> Principal | None:
    """Verify an API key. ``None`` for every failure, which the caller must not distinguish.

    Also called by `POST /auth/session`, which is why it returns rather than
    raises: the exchange refuses with the same 401, but it is a view's job to
    say so, not this function's.
    """
    parsed = keys.split(token, keys.PREFIX)
    if parsed is None:
        logger.info("auth failed: malformed token")
        return None

    key_id, secret = parsed
    row = await ApiKeyRepository(db).get_by_key_id(key_id)
    if row is None:
        logger.info("auth failed: unknown key id %s", key_id)
        return None

    # Verify before checking revocation, so that a revoked key and a wrong
    # secret cost the same work. Reversing these would let an attacker learn
    # that a key id exists and is revoked without knowing its secret.
    if not keys.matches(secret, row.secret_hash):
        logger.info("auth failed: bad secret for key id %s", key_id)
        return None

    if not row.is_active:
        logger.info("auth failed: revoked key id %s", key_id)
        return None

    return Principal(id=row.principal_id, label=row.label)


async def principal_for_session(db: DbSession, token: str) -> Principal | None:
    """Verify a browser session cookie. ``None`` for every failure.

    The same order as :func:`principal_for_key`, and for the same reason: the
    secret is checked before the row's validity, so that an expired session and
    a forged one cost the same work.

    ``label`` comes from the principal id rather than from a key. A session is
    not issued against any particular key — see
    :class:`~bacteria.app.auth.models.BrowserSession` — so there is no label to
    inherit, and inventing one would put a value into :class:`Principal` that
    nothing chose. It is documented as never being used for access decisions,
    which is what makes that safe.
    """
    parsed = keys.split(token, keys.SESSION_PREFIX)
    if parsed is None:
        logger.info("auth failed: cookie is not a session token")
        return None

    session_id, secret = parsed
    row = await BrowserSessionRepository(db).get(session_id)
    if row is None:
        logger.info("auth failed: unknown session %s", session_id)
        return None

    if not keys.matches(secret, row.secret_hash):
        logger.info("auth failed: bad secret for session %s", session_id)
        return None

    if not row.is_active:
        logger.info("auth failed: expired or revoked session %s", session_id)
        return None

    return Principal(id=row.principal_id, label=row.principal_id)


async def current_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)] = None,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Principal:
    """Authenticate the request by key or by session, or refuse it.

    The bearer header is tried first, so a request carrying one behaves exactly
    as it did before sessions existed — a client that presents a key does not
    silently start depending on a cookie its browser happened to keep.

    Presenting both is not an error and resolves to the key. There is no case
    where a caller sends a bearer token meaning "but use the cookie instead",
    and refusing the combination would break a console tab open beside a
    terminal doing `curl` against the same origin.

    Raises:
        HTTPException: 401, for every failure mode. See ``UNAUTHENTICATED``.
    """
    if credentials is not None and credentials.credentials:
        principal = await principal_for_key(db, credentials.credentials)
        if principal is not None:
            return principal
        raise UNAUTHENTICATED

    if session_cookie:
        principal = await principal_for_session(db, session_cookie)
        if principal is not None:
            return principal
        raise UNAUTHENTICATED

    logger.info("auth failed: no credentials presented")
    raise UNAUTHENTICATED


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
"""The authenticated caller. Depending on this is what makes a route non-public."""
