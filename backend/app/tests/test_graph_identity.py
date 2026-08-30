"""Which node a name resolves to, and which mistake is the unrecoverable one.

The asymmetry these tests protect: **splitting one person across two nodes is
fixable** — assert a link and both keep their observations — while **collapsing
two people into one node is not**, because their assertions are already
interleaved under a single id and nothing records which belonged to whom.

So the matching here is deliberately dull, and the tests that matter most are
the ones asserting it *declines* to match. A future change that makes resolution
cleverer should make these fail rather than pass more often.

Real Postgres for the repository half; `normalize` is pure and tested directly.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.graph.identity import normalize
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import refer_to
from bacteria.app.personal.catalogue import VOCABULARY

NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)
LATER = datetime(2026, 5, 25, tzinfo=timezone.utc)


@pytest.fixture(name="repo")
async def _repo(engine):
    async with AsyncSession(engine) as session:
        yield SqlGraphRepository(session, vocabulary=VOCABULARY)
        await session.commit()


def test_normalization_folds_only_what_is_certainly_the_same_name():
    """Case, whitespace and Unicode composition — and nothing that guesses.

    Composition matters more than it looks: the same name arrives composed from
    one source and decomposed from another, so "José" typed two ways would
    otherwise become two nodes that read identically on screen and cannot be
    told apart by eye.
    """
    assert normalize("  Diane  ") == normalize("diane")
    assert normalize("DIANE") == normalize("Diane")
    assert normalize("José") == normalize("José")


def test_normalization_refuses_to_guess():
    """A nickname, an initial and a fuller name are three different names.

    Each of these is a merge someone might want, and each is a merge that is
    wrong often enough to lose data permanently when it fires on two people. The
    right place to propose them is entity resolution with a confidence and a
    person to accept it — not a string function nothing reviews.
    """
    assert normalize("Diane") != normalize("Diana")
    assert normalize("Diane Mercer") != normalize("D. Mercer")
    assert normalize("Diane") != normalize("Diane Mercer")


async def test_the_same_name_resolves_to_the_same_node(repo):
    """Second mention must not create a second node, or every fact is orphaned.

    Without this, a conversation mentioning someone twice produces two nodes with
    one assertion each, and no constraint could ever see a conflict because no
    two claims would share a subject.
    """
    first = await refer_to(repo, "u1", "person", "Diane", now=NOW)
    again = await refer_to(repo, "u1", "person", "  diane ", now=LATER)

    assert again.node_id == first.node_id


async def test_a_repeat_mention_moves_last_seen(repo):
    """Recorded time, not a claim: it says when we last heard, not what is true."""
    node = await refer_to(repo, "u1", "person", "Diane", now=NOW)
    assert node.first_seen == node.last_seen == NOW

    again = await refer_to(repo, "u1", "person", "Diane", now=LATER)

    assert again.first_seen == NOW
    assert again.last_seen == LATER


async def test_different_kinds_with_one_name_stay_apart(repo):
    """A company and a person may share a name and are not the same thing.

    Common enough to be worth a test rather than a comment — someone's employer
    and someone's surname collide constantly.
    """
    person = await refer_to(repo, "u1", "person", "Acme", now=NOW)
    org = await refer_to(repo, "u1", "organization", "Acme", now=NOW)

    assert person.node_id != org.node_id


async def test_two_people_never_share_a_node(repo):
    """The same name in two graphs is two things, and the key already says so.

    Ownership is part of the node key rather than a filter, so this cannot be
    got wrong by forgetting a `WHERE` — but it is the failure that would be
    worst here, since a shared node id would interleave two people's assertions
    permanently.
    """
    mine = await refer_to(repo, "u1", "person", "Diane", now=NOW)
    theirs = await refer_to(repo, "u2", "person", "Diane", now=NOW)

    assert mine.node_id != theirs.node_id


async def test_node_ids_say_nothing_about_the_label(repo):
    """Opaque on purpose: a label-derived id encodes a fact that can be corrected.

    If the id contained the name, fixing a misspelling would either leave the id
    lying about what it names or require rewriting every assertion referencing
    it — which is the one thing a node id must never need.
    """
    node = await refer_to(repo, "u1", "person", "Diane Mercer", now=NOW)

    assert "diane" not in node.node_id.lower()
    assert "mercer" not in node.node_id.lower()


async def test_the_owner_resolves_to_one_node_however_it_is_spelled(repo):
    """ "self", "Self" and "SELF" are the same person: the one whose graph it is.

    A transcript rarely names the speaker, so an extractor left to itself invents
    a label and invents a different one next week. Three nodes for the graph's
    owner, none of them connected, is the failure this reserves against.
    """
    first = await refer_to(repo, "u1", "person", "self", now=NOW)
    shouted = await refer_to(repo, "u1", "person", "SELF", now=LATER)

    assert shouted.node_id == first.node_id


async def test_the_owner_node_id_is_derived_rather_than_allocated(repo):
    """Two concurrent first mentions must not produce two owners.

    An allocated id would let both mint before either could look the other up,
    splitting the owner's own assertions across a pair of nodes with nothing
    recording that they are one person. Derived from the user id, that race has
    nowhere to happen.
    """
    from bacteria.app.graph.identity import owner_node_id

    node = await refer_to(repo, "u1", "person", "self", now=NOW)

    assert node.node_id == owner_node_id("u1")
    assert owner_node_id("u1") != owner_node_id("u2")


async def test_two_owners_are_different_people(repo):
    """The reserved label must not collapse two graphs into one node."""
    mine = await refer_to(repo, "u1", "person", "self", now=NOW)
    theirs = await refer_to(repo, "u2", "person", "self", now=NOW)

    assert mine.node_id != theirs.node_id


async def test_a_person_actually_called_self_gets_an_ordinary_node(repo):
    """The reservation is on the label, so only a *person* named self collides.

    An organization called "Self" resolves lexically like anything else, because
    the owner is reserved for `kind="person"` alone. A person genuinely called
    that is the case this cannot serve, and is rare enough to accept.
    """
    from bacteria.app.graph.identity import owner_node_id

    org = await refer_to(repo, "u1", "organization", "Self", now=NOW)

    assert org.node_id != owner_node_id("u1")
