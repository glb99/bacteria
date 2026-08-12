"""Turning a request's credential into a principal, or refusing it.

The one place authentication happens. A route depends on
:data:`CurrentPrincipal` and receives an identity that has already been proven;
there is no way to reach a route with an unverified one, because the dependency
raises before the handler is called.
"""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bacteria.app.auth import keys
from bacteria.app.auth.principal import Principal
from bacteria.app.auth.repository import ApiKeyRepository
from bacteria.app.core.dependencies import DbSession

logger = logging.getLogger(__name__)

_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or missing credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
"""One response for every way authentication can fail.

Missing header, malformed token, unknown key id, wrong secret, revoked key — all
identical to the client. Distinguishing them tells an attacker which half of a
guess was right, and turns "find a valid key" into two much easier searches.
The distinction is kept in the log, where the operator can see it and the client
cannot.
"""


async def current_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_scheme)] = None,
) -> Principal:
    """Authenticate the request, or refuse it.

    Raises:
        HTTPException: 401, for every failure mode. See ``_UNAUTHENTICATED``.
    """
    if credentials is None or not credentials.credentials:
        logger.info("auth failed: no credentials presented")
        raise _UNAUTHENTICATED

    parsed = keys.split(credentials.credentials)
    if parsed is None:
        logger.info("auth failed: malformed token")
        raise _UNAUTHENTICATED

    key_id, secret = parsed
    row = await ApiKeyRepository(db).get_by_key_id(key_id)
    if row is None:
        logger.info("auth failed: unknown key id %s", key_id)
        raise _UNAUTHENTICATED

    # Verify before checking revocation, so that a revoked key and a wrong
    # secret cost the same work. Reversing these would let an attacker learn
    # that a key id exists and is revoked without knowing its secret.
    if not keys.matches(secret, row.secret_hash):
        logger.info("auth failed: bad secret for key id %s", key_id)
        raise _UNAUTHENTICATED

    if not row.is_active:
        logger.info("auth failed: revoked key id %s", key_id)
        raise _UNAUTHENTICATED

    return Principal(id=row.principal_id, label=row.label)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
"""The authenticated caller. Depending on this is what makes a route non-public."""
