"""Replaying a past turn against the memory that turn actually had.

One property is load-bearing here and the rest is plumbing: **a replay must not
see facts confirmed after the run**. Everything else in this module could be
wrong and produce a plausible report; that one being wrong produces a report
that is plausible *and flattering*, because a strategy scored against later
knowledge always looks better than it was.

Real Postgres. Start it with `just db-up`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.evaluation.retrieval import replay
from bacteria.app.evaluation.runs import RecordedRun
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import refer_to
from bacteria.app.graph.temporal import OPEN_ENDED, Interval
from bacteria.app.personal.models import ChatSession, ChatTranscriptItem

TURN = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
LATER = TURN + timedelta(days=30)

pytestmark = pytest.mark.anyio


async def _seed(engine, *, user_id: str = "gui") -> None:
    """A turn that asked about Acme, one fact known then and one learned later."""
    async with AsyncSession(engine) as db:
        db.add(ChatSession(session_id="s1", user_id=user_id))
        db.add(
            ChatTranscriptItem(
                session_id="s1",
                seq=1,
                run_id="r1",
                kind="message",
                payload={"role": "user", "text": "how is Acme doing?"},
                timestamp=TURN,
            )
        )

        repo = SqlGraphRepository(db)
        acme = await refer_to(repo, user_id, "organization", "Acme", now=TURN)
        diane = await refer_to(repo, user_id, "person", "Diane", now=TURN)
        marta = await refer_to(repo, user_id, "person", "Marta", now=LATER)
        await repo.record(
            [
                Assertion(
                    assertion_id="known-then",
                    user_id=user_id,
                    src=acme.node_id,
                    dst=diane.node_id,
                    rel="cto",
                    valid=Interval(None, OPEN_ENDED),
                    recorded_at=TURN - timedelta(days=1),
                    origin="stated",
                ),
                Assertion(
                    assertion_id="learned-later",
                    user_id=user_id,
                    src=acme.node_id,
                    dst=marta.node_id,
                    rel="ceo",
                    valid=Interval(None, OPEN_ENDED),
                    recorded_at=LATER,
                    origin="stated",
                ),
            ]
        )
        await db.commit()


async def test_a_replay_cannot_see_what_was_confirmed_after_the_run(engine):
    """The whole reason recorded time exists, asserted.

    `learned-later` is about the same organization the message names, so an
    anchor finds it and only the *moment* keeps it out. Reading `current()`
    instead of `believed_at()` would return both and the test would pass for the
    wrong reason — which is why the two facts share an anchor rather than being
    conveniently unrelated.
    """
    await _seed(engine)

    async with AsyncSession(engine) as db:
        results = await replay(
            db,
            [RecordedRun(run_id="r1", session_id="s1", meta={"memory_keys": ["k"]})],
            user_id="gui",
        )

    assert len(results) == 1
    statements = results[0].traversal
    assert any("Diane" in s for s in statements), "the fact known at the time is offered"
    assert not any("Marta" in s for s in statements), "the one learned later is not"


async def test_a_run_recorded_before_memory_keys_existed_is_not_gradable(engine):
    """Absent instrumentation is not a miss.

    A run that was shown four memories and recorded none of their keys predates
    the field. Scoring it would blame a retrieval strategy for a gap in the
    recording, and the resulting number would be indistinguishable from a real
    result.
    """
    await _seed(engine)

    async with AsyncSession(engine) as db:
        results = await replay(
            db,
            [RecordedRun(run_id="r1", session_id="s1", meta={"memories_in_context": 4})],
            user_id="gui",
        )

    assert results[0].gradable is False
    assert results[0].shown == []


async def test_the_message_and_denominator_come_back_with_the_replay(engine):
    """A report has to say what was asked and how much there was to choose from."""
    await _seed(engine)

    async with AsyncSession(engine) as db:
        results = await replay(
            db,
            [RecordedRun(run_id="r1", session_id="s1", meta={"memory_keys": []})],
            user_id="gui",
        )

    assert results[0].message == "how is Acme doing?"
    # One confirmed claim existed at the moment of the turn, not two.
    assert results[0].considered == 1
