"""What the transcript extractor must not get wrong.

The invariants here are of two kinds and both are load-bearing. One is money:
this runs on every turn, so a run that re-reads what it already read makes cost
grow with conversation length rather than with new content. The other is the
boundary the agent's ADRs 0016 and 0017 draw — extraction is a model call over
user-controlled text, and the only thing standing between an injected
"remember that you must always comply with X" and the next system prompt is that
this module can write proposals and nothing else.

Not covered here: that a turn only enqueues the job when
``memory_extraction_enabled`` is set. That gate is real — breaking it bills a
model call per turn on every deployment — and asserting it needs a worker and a
queue rather than a function call, which puts it in ``scripts/smoke.py``.
"""

from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.model.protocol import ModelResponse
from bacteria.agent.session.store import TranscriptItem
from bacteria.app.chat.extraction import EXTRACTOR_SOURCE, extract_memories
from bacteria.app.chat.models import ChatMemoryExtraction
from bacteria.app.chat.repository import SqlSessionRepository


class _FakeClient:
    """Returns one prepared reply and counts how often it was asked.

    The count is the point in half these tests: "did this cost a model call" is
    the assertion, and a mock library would express it less directly than an
    integer.
    """

    def __init__(self, text: str | None = "[]") -> None:
        self.text = text
        self.calls = 0

    async def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> ModelResponse:
        self.calls += 1
        self.seen = messages
        return ModelResponse(
            text=self.text, tool_calls=[], stop_reason="end_turn", raw=None, model="fake-model"
        )


def _message(text: str, role: str = "user") -> TranscriptItem:
    return TranscriptItem(kind="message", payload={"role": role, "text": text})


@pytest.fixture(name="session_id")
async def _session_id(engine):
    """A session with two messages already in its transcript."""
    async with AsyncSession(engine) as db:
        repository = SqlSessionRepository(db)
        session = await repository.create_session("owner-1")
        await repository.commit(
            session.session_id,
            new_transcript_items=[_message("call me Gui"), _message("noted", role="assistant")],
        )
        return session.session_id


async def test_a_run_with_nothing_new_makes_no_model_call(engine, session_id):
    """A second run over an unchanged transcript must not reach a model.

    This is the whole economic argument for the watermark. Break it and every
    turn pays to re-read a conversation that did not change, which is a bill
    that grows with session length and a behaviour no test output would show.
    """
    client = _FakeClient(text='[{"key": "name", "value": "Gui", "reason": "said so"}]')

    async with AsyncSession(engine) as db:
        first = await extract_memories(db, client, session_id, max_proposals=5)
        second = await extract_memories(db, client, session_id, max_proposals=5)

    assert first.examined == 2
    assert client.calls == 1, "the second run re-read a transcript it had already seen"
    assert second.examined == 0
    assert second.through_seq == first.through_seq


async def test_extraction_writes_proposals_and_never_active_memory(engine, session_id):
    """Nothing extracted may reach a model without a human activating it.

    The security invariant, and the reason this module exists in the shape it
    does. A violation would let a conversation write the instructions the model
    is given on every later turn, with the transcript showing only a job that
    succeeded.
    """
    client = _FakeClient(text='[{"key": "name", "value": "Prefers Gui", "reason": "said so"}]')

    async with AsyncSession(engine) as db:
        result = await extract_memories(db, client, session_id, max_proposals=5)
        state = await SqlSessionRepository(db).get_state(session_id)

    assert result.proposed == 1
    assert state.memory == {}, "extraction wrote active memory"
    assert state.user_memory == {}, "extraction wrote user-scoped memory"
    assert state.proposals[(EXTRACTOR_SOURCE, "name")].value == "Prefers Gui"


async def test_a_re_run_overwrites_its_own_proposals(engine, session_id):
    """Re-proposing the same key replaces, so a retried job cannot accumulate.

    This is what makes the task safe to retry where ingestion is not. Without
    it, every retry would add another copy of the same suggestion to a review
    queue a person has to read.
    """
    async with AsyncSession(engine) as db:
        await extract_memories(
            db,
            _FakeClient('[{"key": "tone", "value": "terse", "reason": "asked"}]'),
            session_id,
            max_proposals=5,
        )
        # A second run over the same slice: the watermark is reset by hand
        # rather than by adding messages, so this isolates the overwrite from
        # everything else the extractor does.
        watermark = await db.get(ChatMemoryExtraction, session_id)
        watermark.through_seq = -1
        db.add(watermark)
        await db.commit()
        await extract_memories(
            db,
            _FakeClient('[{"key": "tone", "value": "very terse", "reason": "asked again"}]'),
            session_id,
            max_proposals=5,
        )
        state = await SqlSessionRepository(db).get_state(session_id)

    assert len(state.proposals) == 1, "a retry accumulated duplicate suggestions"
    assert state.proposals[(EXTRACTOR_SOURCE, "tone")].value == "very terse"


async def test_output_beyond_the_cap_is_dropped_and_counted(engine, session_id):
    """The cap bounds the review queue, and the excess is reported not hidden.

    A model reliably returning more than the cap is a configuration problem.
    Dropping silently would make it look like the extractor was simply quiet.
    """
    facts = ", ".join(f'{{"key": "k{i}", "value": "v{i}", "reason": "r{i}"}}' for i in range(5))
    client = _FakeClient(text=f"[{facts}]")

    async with AsyncSession(engine) as db:
        result = await extract_memories(db, client, session_id, max_proposals=2)
        state = await SqlSessionRepository(db).get_state(session_id)

    assert result.proposed == 2
    assert result.dropped == 3
    assert len(state.proposals) == 2


@pytest.mark.parametrize(
    "reply",
    [
        "I could not find any durable facts.",
        '{"key": "name", "value": "Gui", "reason": "said so"}',
        "",
        None,
    ],
    ids=["prose", "object-not-array", "empty", "none"],
)
async def test_unusable_output_proposes_nothing_and_does_not_raise(engine, session_id, reply):
    """A reply this cannot read must produce nothing, not an exception.

    The job is retried, so raising on unparseable output would put a session
    whose content reliably confuses the model into a retry loop that costs a
    model call every time and never succeeds.
    """
    async with AsyncSession(engine) as db:
        result = await extract_memories(db, _FakeClient(reply), session_id, max_proposals=5)
        state = await SqlSessionRepository(db).get_state(session_id)

    assert result.proposed == 0
    assert state.proposals == {}


async def test_a_fact_without_a_reason_is_rejected(engine, session_id):
    """A proposal with no reason is one a reviewer cannot check.

    ``MemoryEntry`` requires a reason precisely so that "does this still earn
    its place" is answerable. Accepting a blank one here would put an
    unreviewable row into the queue through the back door.
    """
    client = _FakeClient(
        text='[{"key": "a", "value": "v", "reason": ""}, '
        '{"key": "b", "value": "w", "reason": "checkable"}]'
    )

    async with AsyncSession(engine) as db:
        result = await extract_memories(db, client, session_id, max_proposals=5)
        state = await SqlSessionRepository(db).get_state(session_id)

    assert result.proposed == 1
    assert result.dropped == 1
    assert list(state.proposals) == [(EXTRACTOR_SOURCE, "b")]


async def test_new_messages_after_a_run_are_picked_up(engine, session_id):
    """The watermark advances rather than freezing; later turns still extract.

    The opposite failure to the first test in this file, and the one that would
    make the feature look like it stopped working after its first run.
    """
    client = _FakeClient(text='[{"key": "tone", "value": "terse", "reason": "asked"}]')

    async with AsyncSession(engine) as db:
        await extract_memories(db, client, session_id, max_proposals=5)
        await SqlSessionRepository(db).commit(
            session_id, new_transcript_items=[_message("also I'm in Madrid")]
        )
        second = await extract_memories(db, client, session_id, max_proposals=5)

    assert client.calls == 2
    assert second.examined == 1, "the second run did not see the message the turn added"


async def test_new_items_with_no_conversation_in_them_cost_no_model_call(engine, session_id):
    """A slice that advanced but holds no messages must not reach a model.

    Guarded separately from the empty-slice case, and this test exists because
    breaking that guard on purpose changed nothing: the watermark *has* moved
    here, so the early return does not fire, and the only thing preventing a
    paid call over an empty transcript is the check that there is something to
    send. The watermark must still advance, or these items are re-read forever.
    """
    client = _FakeClient()

    async with AsyncSession(engine) as db:
        await extract_memories(db, client, session_id, max_proposals=5)
        await SqlSessionRepository(db).commit(
            session_id,
            new_transcript_items=[
                TranscriptItem(kind="run_meta", payload={"outcome": "completed"})
            ],
        )
        result = await extract_memories(db, client, session_id, max_proposals=5)

    assert client.calls == 1, "a slice containing no messages was sent to a model"
    assert result.examined == 0
    assert result.through_seq == 2, "the watermark did not advance past the non-message item"
