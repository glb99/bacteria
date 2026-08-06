"""What FastAPI injects into a request, and where each thing comes from.

Thin on purpose. A dependency here resolves a collaborator and returns it; if
one starts making decisions, those decisions belong to a feature's service layer
where they can be tested without a request.
"""

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from fastpaip.core.db import session_scope
from fastpaip.core.settings import Settings, get_settings

DbSession = Annotated[Session, Depends(session_scope)]
"""A database session scoped to one request."""

AppSettings = Annotated[Settings, Depends(get_settings)]
"""The process-wide settings, as a dependency so a test can override them."""
