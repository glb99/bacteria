"""The last piece of ADR 0006's bet: does asking the graph beat asking recency.

Not the kill criterion — that runs on the eval harness over recorded runs. This
checks the mechanism the criterion will measure: a message names something, the
graph says what it knows about that thing, and only what a person confirmed comes
back.

Real Postgres.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.chat.graph_candidates import GraphCandidateSupplier
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import confirm, observe
from bacteria.app.graph.temporal import OPEN_ENDED, Interval

USER = "candidates"
NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)
LATER = datetime(2026, 5, 11, tzinfo=timezone.utc)
"""A confirmation is later than the claim, because a person reads before agreeing.

Not decoration: at one instant there is one belief about a claim, so confirming
at ``NOW`` collides with the claim itself on the log's uniqueness rule."""


async def _fact(repo, assertion_id: str, src: str, rel: str, dst: str, *, confirmed: bool):
    source = await repo.mint_node(
        USER, "organization" if rel != "mother" else "person", src, now=NOW
    )
    target = await repo.mint_node(USER, "person", dst, now=NOW)
    claim = Assertion(
        assertion_id=assertion_id,
        user_id=USER,
        src=source.node_id,
        rel=rel,
        dst=target.node_id,
        valid=Interval(None, OPEN_ENDED),
        recorded_at=NOW,
        attrs={"reason": f"the transcript mentioned {dst}"},
    )
    await observe(repo, [claim], now=NOW)
    if confirmed:
        await confirm(repo, claim, assertion_id=f"{assertion_id}-ok", now=LATER)
    return source, target


@pytest.fixture(name="repo")
async def _repo(engine):
    async with AsyncSession(engine) as session:
        yield SqlGraphRepository(session)
        await session.commit()


async def _supplier(engine):
    return AsyncSession(engine)


async def test_a_message_naming_a_thing_gets_what_the_graph_knows_about_it(engine):
    """The whole mechanism, in one turn."""
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=True)
        await db.commit()

        supplied = await GraphCandidateSupplier(db, USER).candidates("s1", "how is Acme doing?", 8)

    assert [e.value for e in supplied.user.values()] == ["Diane is the CTO of Acme"]


async def test_an_unconfirmed_fact_is_never_a_candidate(engine):
    """The rule the whole record rests on, checked at the surface that would break it.

    A supplier is where unreviewed model output would reach a system prompt if it
    ever could, and it looks like plumbing rather than like a write.
    """
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=False)
        await db.commit()

        supplied = await GraphCandidateSupplier(db, USER).candidates("s1", "how is Acme doing?", 8)

    assert supplied.user == {}
    assert supplied.considered == 0


async def test_considered_counts_everything_confirmed_not_everything_returned(engine):
    """ADR 0022's invariant. A memory the owner kept must not vanish silently."""
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=True)
        await _fact(repo, "a2", "Globex", "ceo", "Marta", confirmed=True)
        await db.commit()

        supplied = await GraphCandidateSupplier(db, USER).candidates("s1", "tell me about Acme", 8)

    assert len(supplied.user) == 1, "narrowed to what the message named"
    assert supplied.considered == 2, "and says what it narrowed from"


async def test_a_message_naming_nothing_falls_back_to_everything(engine):
    """No anchor is no opinion, and the alternatives are both worse.

    Returning nothing would hide memories a person kept behind a message that
    happened to name nobody; having an opinion without evidence would be
    inventing one.
    """
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=True)
        await db.commit()

        supplied = await GraphCandidateSupplier(db, USER).candidates("s1", "hello there", 8)

    assert len(supplied.user) == 1


async def test_a_two_letter_label_is_not_an_anchor(engine):
    """An anchor that matches everything narrows nothing and costs a hop."""
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await repo.mint_node(USER, "person", "Al", now=NOW)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=True)
        await db.commit()

        supplier = GraphCandidateSupplier(db, USER)
        anchors = await supplier._anchors(SqlGraphRepository(db), "shall we talk")

    assert anchors == []


async def test_candidates_arrive_in_the_user_scope(engine):
    """A confirmed fact is about the person's world, not about one conversation.

    In the session scope it would win precedence over a preference stated in this
    very conversation, which is backwards.
    """
    async with AsyncSession(engine) as db:
        repo = SqlGraphRepository(db)
        await _fact(repo, "a1", "Acme", "cto", "Diane", confirmed=True)
        await db.commit()

        supplied = await GraphCandidateSupplier(db, USER).candidates("s1", "about Acme", 8)

    assert supplied.session == {}
    assert supplied.user != {}
