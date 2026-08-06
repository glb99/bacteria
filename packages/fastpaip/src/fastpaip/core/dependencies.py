"""What FastAPI injects into a request, and where each thing comes from.

Thin on purpose. A dependency here resolves a collaborator and returns it; if
one starts making decisions, those decisions belong to a feature's service layer
where they can be tested without a request.
"""

from typing import Annotated

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.core.db import session_scope
from fastpaip.core.settings import Settings, get_settings

DbSession = Annotated[AsyncSession, Depends(session_scope)]
"""A database session scoped to one request.

Named ``DbSession`` rather than ``Session`` because "session" already means two
other things here — the identity of a conversation, and the row storing it. The
alias is what keeps ``chat`` readable.
"""

AppSettings = Annotated[Settings, Depends(get_settings)]
"""The process-wide settings, as a dependency so a test can override them."""
