"""Tests for UserRepository against a real in-memory database.

SQLite in memory rather than a mocked session: the thing most worth checking
here is that the SQLModel calls are correct, and a mock would assert only that
we called the methods we wrote.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fastpaip.models import UserCreate
from fastpaip.repositories import UserRepository


@pytest.fixture(name="session")
def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_assigns_an_identity_the_caller_did_not_supply(session):
    """UserCreate has no id; User does. Creation is where that gap closes."""
    repo = UserRepository(session)

    user = repo.create(UserCreate(name="Ada", email="ada@example.com"))

    assert user.id is not None
    assert user.name == "Ada"


def test_get_by_id_returns_none_for_a_missing_row(session):
    """Not found is an ordinary answer, not an exception.

    Callers branch on it; if this raised, every lookup would need a try block
    to express "maybe it is not there", which is the common case.
    """
    assert UserRepository(session).get_by_id(9999) is None


def test_delete_removes_the_row(session):
    """The row must actually be gone, not merely committed around.

    Worth asserting rather than assuming: an earlier revision of this method
    committed the session without ever calling `delete`, which leaves a
    perfectly successful-looking no-op.
    """
    repo = UserRepository(session)
    user = repo.create(UserCreate(name="Ada", email="ada@example.com"))

    repo.delete(user.id)

    assert repo.get_by_id(user.id) is None


def test_deleting_an_absent_id_is_a_no_op(session):
    UserRepository(session).delete(9999)


def test_update_persists_a_change(session):
    repo = UserRepository(session)
    user = repo.create(UserCreate(name="Ada", email="ada@example.com"))

    user.name = "Ada Lovelace"
    repo.update(user)

    assert repo.get_by_id(user.id).name == "Ada Lovelace"
