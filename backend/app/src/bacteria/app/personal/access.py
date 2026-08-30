"""Whether this principal may have this session.

Separate from :mod:`bacteria.app.auth`, and deliberately. That package answers "who
is calling"; this one answers "may they have this", and only ``chat`` knows what
owning a session means. Merging them would put an access decision in a module
with no idea what it is deciding about.

The split is recorded in
[ADR 0004](../../../../../docs/adr/0004-authentication-is-shared-authorization-lives-next-to-the-resource.md).
That record also says what it costs: an ownership rule per feature, forgotten
silently, with nothing in the build to notice. Ingestion has not written one.

This is the distinction the agent's own design is built around — a session
identifies an interaction, and identifying it is not permission to read it. The
application had the first half and none of the second: any caller who knew or
guessed a session id could read its entire transcript.
"""

import logging

from fastapi import HTTPException, status

from bacteria.agent.session.store import SessionState, UnknownSessionError
from bacteria.app.auth.principal import Principal
from bacteria.app.personal.repository import SqlSessionRepository

logger = logging.getLogger(__name__)

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such session")
"""404 for "does not exist" *and* for "not yours".

A 403 would confirm the session exists, which turns a session id into an oracle:
someone enumerating ids learns which are real without ever reading one. The
distinction is kept in the log rather than in the response.
"""


async def load_owned_session(
    repository: SqlSessionRepository, principal: Principal, session_id: str
) -> SessionState:
    """Load a session, or refuse if it is not this principal's.

    Every route that touches a session goes through here rather than calling the
    repository directly. One function is something a reviewer can check; an
    ownership comparison repeated in each handler is one that will eventually be
    written without.

    Raises:
        HTTPException: 404, whether the session is absent or belongs to someone
            else.
    """
    try:
        state = await repository.get_state(session_id)
    except UnknownSessionError:
        raise _NOT_FOUND from None

    if state.session.user_id != principal.id:
        logger.warning(
            "access denied: principal %s requested session %s owned by %s",
            principal.id,
            session_id,
            state.session.user_id,
        )
        raise _NOT_FOUND

    return state
