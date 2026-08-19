"""Tests for authentication: what counts as proof of identity.

The failures here are the expensive kind — a wrong answer means an unauthorized
caller is treated as an authorized one — so these lean toward asserting refusals
rather than successes.
"""

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.auth import keys
from bacteria.app.auth.models import ApiKey
from bacteria.app.auth.service import issue_key, list_keys, principal_is_known, revoke_key


@pytest.fixture(name="db")
async def _db(engine):
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


async def test_an_unknown_principal_is_not_known(db):
    """The typo guard. Without it, `chat alicce` silently creates an orphan.

    `chat_session.user_id` has no foreign key, deliberately, so a mistyped
    principal produces a valid session that no key resolves to — unreadable
    over HTTP forever, and reported by nothing. The operator CLI refuses on
    this answer, which is the only thing standing between a slip and a row
    nobody can reach.
    """
    await issue_key(db, principal_id="alice", label="demo")

    assert await principal_is_known(db, "alicce") is False


async def test_a_principal_holding_a_key_is_known(db):
    """The other half: issuing a key must be enough to then use the CLI.

    A guard that refuses everything would pass the test above and make the
    command unusable.
    """
    await issue_key(db, principal_id="alice", label="demo")

    assert await principal_is_known(db, "alice") is True


async def test_a_principal_whose_only_key_was_revoked_is_still_known(db):
    """Revocation must not lock an operator out of their own sessions.

    Rotation revokes the old key before or after minting the new one, and a
    check that counted only live keys would refuse in the window between —
    turning routine hygiene into "your sessions are unreachable". The principal
    is real whether or not any credential currently works; whether a *caller*
    may act as it is a different question, answered by the auth dependency.
    """
    token = await issue_key(db, principal_id="alice", label="demo")
    key_id, _secret = keys.split(token)
    await revoke_key(db, key_id=key_id)

    assert await principal_is_known(db, "alice") is True


async def test_a_revoked_key_is_still_listed(db):
    """A listing that hid revoked keys would answer the operator's question wrongly.

    "There is no key" and "the key you had was revoked" are different answers to
    "why did this stop working", and only one of them is fixed by issuing a new
    one. Hiding the row would also contradict `principal_is_known`, which counts
    a revoked key as proof the principal is real — so the two would disagree
    about whether a principal exists.
    """
    token = await issue_key(db, principal_id="alice", label="demo")
    key_id, _secret = keys.split(token)
    await revoke_key(db, key_id=key_id)

    listed = await list_keys(db)

    assert [row.key_id for row in listed] == [key_id]
    assert listed[0].is_active is False


async def test_one_principals_keys_are_listed_together(db):
    """Grouping by principal is what makes rotation legible.

    Sorted by issue date alone, a principal holding three keys has them
    scattered among everyone else's — and a principal holding several is exactly
    the case worth looking at, because it is either mid-rotation or has keys
    nobody has revoked.
    """
    await issue_key(db, principal_id="bob", label="first")
    await issue_key(db, principal_id="alice", label="first")
    await issue_key(db, principal_id="bob", label="second")

    listed = await list_keys(db)

    assert [row.principal_id for row in listed] == ["alice", "bob", "bob"]
    assert [row.label for row in listed] == ["first", "first", "second"]


async def test_the_listing_can_be_narrowed_to_one_principal(db):
    """Without a filter the answer is unreadable on any database that has run smoke.

    `just smoke` issues four keys per run and revokes one, so a working
    repository accumulates dozens of `smoke-*` rows — thirty-one on the machine
    this was written on, of which three were a person's. An operator looking for
    their own key should not have to read past them.
    """
    await issue_key(db, principal_id="alice", label="demo")
    await issue_key(db, principal_id="bob", label="demo")

    listed = await list_keys(db, "alice")

    assert [row.principal_id for row in listed] == ["alice"]


async def test_listing_an_unknown_principal_is_empty_rather_than_an_error(db):
    """Asking about a principal that does not exist is the normal case here.

    This command exists because someone mistyped a principal, so being asked
    about one that was never issued a key is the reason it was written rather
    than a misuse of it. Raising would make the CLI report a traceback for the
    question it is there to answer.
    """
    await issue_key(db, principal_id="alice", label="demo")

    assert await list_keys(db, "alicce") == []
