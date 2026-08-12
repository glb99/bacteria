"""Persistence for the entities in :mod:`bacteria.app.models`.

Temporarily at the top level, alongside the models it stores; both move to the
feature that owns accounts when one exists.

This module had no imports at all — it referenced ``Session``, ``User``,
``UserCreate``, ``UserId`` and ``Optional`` from nowhere. Worth knowing how that
survived: on Python 3.13 and earlier it raised ``NameError`` the moment the
module was imported, but PEP 649 defers annotation evaluation from 3.14 onward,
so it began importing cleanly and failing at the first *call* instead.
"""

from typing import Optional

from sqlmodel import Session

from bacteria.app.models import User, UserCreate, UserId


class UserRepository:
    """Stores users in a SQLModel session.

    Satisfies ``CanRead``, ``CanCreate``, ``CanUpdate`` and ``CanDelete`` from
    :mod:`bacteria.app.core.protocols` structurally — it inherits nothing and
    registers nothing. It happens to offer all four; callers should still depend
    on only the ones they use.

    The session is injected rather than created here. A repository that opened
    its own connection would decide transaction scope on the caller's behalf,
    and transaction scope belongs to whoever knows what a unit of work is.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, id: UserId) -> Optional[User]:
        return self.session.get(User, id)

    def create(self, data: UserCreate) -> User:
        # model_validate converts the UserCreate payload into a User table
        # entity — the point at which an unidentified payload becomes a row.
        db_user = User.model_validate(data)

        self.session.add(db_user)
        self.session.commit()
        self.session.refresh(db_user)
        return db_user

    def update(self, entity: User) -> User:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def delete(self, id: UserId) -> None:
        user = self.get_by_id(id)
        if user:
            self.session.delete(user)
            self.session.commit()
