"""The two routes a browser needs, and the only routes `auth/` has.

Establishing and ending a session. Nothing here issues a key, lists one, or
revokes one — those stay operator commands for the reason
`bacteria.app.auth.service` gives at the top.

**These are the only paths that answer without `CurrentPrincipal`, apart from
`/health`.** That is what a credential-establishing route is, and it is also
why the enumeration in `test_personal_access.py` keeps its exemptions as a named
constant: adding one has to be a thing somebody wrote down.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status
from pydantic import BaseModel, Field

from bacteria.app.auth.dependencies import COOKIE_NAME, UNAUTHENTICATED, principal_for_key
from bacteria.app.auth.service import close_browser_session, open_browser_session
from bacteria.app.core.dependencies import DbSession

router = APIRouter(prefix="/auth", tags=["auth"])


class KeyExchange(BaseModel):
    """The one thing the browser sends, once."""

    key: str = Field(min_length=1, description="An API key issued by `bacteria-admin issue-key`.")


class SessionOpened(BaseModel):
    """What the console needs to render itself, and nothing more.

    **The token is not here.** It goes back in a ``Set-Cookie`` header marked
    ``HttpOnly``, so no script on the page can read it — which is the entire
    point of the exchange, and would be undone by also putting it in a JSON body
    that `fetch` hands straight to JavaScript.

    ``principal_id`` is not a secret: it is what the operator typed at
    `issue-key`, it is already in every session row, and the console shows it so
    a person can tell which identity a tab is acting as.
    """

    principal_id: str
    expires_at: datetime


@router.post("/session", response_model=SessionOpened)
async def open_session(body: KeyExchange, response: Response, db: DbSession) -> SessionOpened:
    """Trade an API key for a session cookie.

    Verified through the same :func:`principal_for_key` every route depends on,
    rather than a second implementation. Two verifications that agree today are
    two that can disagree after one of them learns something, and the one that
    forgets to check revocation is the one that matters.

    Raises:
        HTTPException: 401, identical to every other authentication failure. A
            distinct "bad key" here would make this endpoint an oracle for
            testing keys, which is worse than elsewhere: it is unauthenticated
            and it takes the key in a body rather than a header.
    """
    principal = await principal_for_key(db, body.key)
    if principal is None:
        raise UNAUTHENTICATED

    token, expires_at = await open_browser_session(db, principal.id)

    response.set_cookie(
        COOKIE_NAME,
        token,
        # `httponly` is the reason this route exists at all: a key in
        # `localStorage` or in a JS variable is readable by any script that gets
        # onto the page, and this is not.
        httponly=True,
        # `secure` even though local development is plain HTTP. Browsers treat
        # `localhost` as a secure context by exception, so this costs nothing
        # there -- and making it conditional would mean a setting whose wrong
        # value is a credential sent in clear text.
        secure=True,
        # `strict`, not `lax`. Every route behind this cookie is either a read
        # of somebody's conversation or a write to their memory, and none of
        # them should happen because a link was followed from somewhere else.
        # This is what stands in for a CSRF token while the console is served
        # from the same origin as the API; a separate origin needs more.
        samesite="strict",
        path="/",
        # Matched to the row rather than computed here, so the cookie and the
        # session cannot disagree about when it ends.
        max_age=int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds()),
    )
    return SessionOpened(principal_id=principal.id, expires_at=expires_at)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
    response: Response,
    db: DbSession,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> None:
    """End the session and clear the cookie. 204 whether or not there was one.

    Idempotent, and answering the same way for "logged out" and "was not logged
    in" is deliberate: the difference is of no use to the caller and telling
    them turns this into a way to test whether a session id is live.

    The cookie is cleared even when the token was unusable. Otherwise a browser
    holding an expired or forged cookie would keep presenting it forever, and
    the person's only fix would be clearing site data by hand.
    """
    if session_cookie:
        await close_browser_session(db, session_cookie)

    # Same attributes as when it was set. A browser matches on name, path and
    # domain, so a delete that omits `path` silently fails to clear a cookie
    # that was set with one -- leaving a logged-out tab still sending it.
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=True, samesite="strict")


__all__ = ["router"]
