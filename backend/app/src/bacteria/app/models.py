"""Persistent entities.

Temporarily at the top level. These belong to whichever feature owns accounts,
and move there when one exists — see docs/guides/migration.md.
"""

from typing import Optional

from sqlmodel import Field, SQLModel

UserId = int


class UserCreate(SQLModel):
    """What a caller supplies to create a user: no identity yet.

    Separate from :class:`User` because the two are genuinely different shapes —
    see ``CanCreate`` in :mod:`bacteria.app.core.protocols`. It is also the request
    body, which means it defines what a client is permitted to set: anything
    absent here cannot be set from outside, and ``id`` being absent is what stops
    a client from choosing its own primary key.
    """

    name: str = Field(min_length=1, max_length=100)
    email: str


class User(UserCreate, table=True):
    """A stored user: everything in :class:`UserCreate`, plus identity."""

    id: Optional[UserId] = Field(default=None, primary_key=True)
