"""Tests for authentication: what counts as proof of identity.

The failures here are the expensive kind — a wrong answer means an unauthorized
caller is treated as an authorized one — so these lean toward asserting refusals
rather than successes.
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastpaip.auth import keys
from fastpaip.auth.models import ApiKey
from fastpaip.auth.service import issue_key, revoke_key


@pytest.fixture(name="db")
async def _db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session


def test_a_generated_key_is_not_recoverable_from_what_is_stored():
    """The secret must not be derivable from the stored hash.

    This is the whole reason for hashing: a leaked database should be an
    inconvenience, not a set of working credentials.
    """
    generated = keys.generate()

    _key_id, secret = keys.split(generated.token)
    assert secret not in generated.secret_hash
    assert generated.token not in generated.secret_hash


def test_two_keys_are_never_the_same():
    assert keys.generate().token != keys.generate().token


def test_a_wrong_secret_does_not_match():
    generated = keys.generate()

    assert not keys.matches("not-the-secret", generated.secret_hash)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "fp_only-one-part",
        "wrongprefix_abc_def",
        "fp__missing-key-id",
        "fp_abc_",
    ],
)
def test_malformed_tokens_are_refused_rather_than_parsed(token):
    """Anything not exactly the right shape is rejected, with no partial credit.

    A parser that accepted some of these would hand the verifier an empty secret
    or an empty key id, and the interesting question becomes whether anything
    downstream treats those as matching.
    """
    assert keys.split(token) is None


async def test_only_a_hash_reaches_the_database(db):
    """The plaintext secret must never be written.

    Asserted against the stored row rather than the code path, because this is
    the property someone reading a database dump actually cares about.
    """
    token = await issue_key(db, principal_id="acme", label="demo")

    row = (await db.exec(select(ApiKey))).one()
    _key_id, secret = keys.split(token)
    assert row.secret_hash != secret
    assert secret not in row.secret_hash
    assert keys.matches(secret, row.secret_hash)


async def test_revocation_keeps_the_record(db):
    """A revoked key is marked, not deleted.

    Deleting the row would leave every authenticated action it took in the logs
    with nothing behind it, and "was this key valid last Tuesday" unanswerable.
    """
    token = await issue_key(db, principal_id="acme", label="demo")
    key_id, _secret = keys.split(token)

    await revoke_key(db, key_id=key_id)

    row = (await db.exec(select(ApiKey))).one()
    assert row.revoked_at is not None
    assert not row.is_active
    assert row.principal_id == "acme"


async def test_revoking_an_unknown_key_is_reported_not_raised(db):
    assert await revoke_key(db, key_id="does-not-exist") is None


async def test_revoking_twice_is_a_no_op(db):
    """An operator revoking twice in a panic should not get an error."""
    token = await issue_key(db, principal_id="acme", label="demo")
    key_id, _secret = keys.split(token)

    first = await revoke_key(db, key_id=key_id)
    second = await revoke_key(db, key_id=key_id)

    assert second is not None
    assert second.revoked_at == first.revoked_at


async def test_a_principal_can_hold_several_keys(db):
    """Rotation must be possible without orphaning what the old key created.

    Ownership is by principal, not by key, so issuing a replacement and revoking
    the original leaves every session intact.
    """
    first = await issue_key(db, principal_id="acme", label="old")
    second = await issue_key(db, principal_id="acme", label="new")

    rows = (await db.exec(select(ApiKey))).all()
    assert len(rows) == 2
    assert {r.principal_id for r in rows} == {"acme"}
    assert first != second
