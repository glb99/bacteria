"""What happens when two requests touch one session at the same time.

The rest of the suite drives the repository one call at a time, which is the
shape a CLI has and not the shape a web application has. Two HTTP requests for
the same session is a browser with two tabs, so everything here is ordinary
traffic rather than an adversarial case.

Each task gets its own ``AsyncSession``, because that is what a request gets.
Sharing one across concurrent tasks would be a different bug, and a much easier
one to notice.
"""

import asyncio

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.agent.session.store import TranscriptItem
from bacteria.app.chat.models import ChatTranscriptItem
from bacteria.app.chat.repository import SqlSessionRepository


def message(text: str) -> TranscriptItem:
    return TranscriptItem(kind="message", payload={"role": "user", "text": text})


async def test_concurrent_commits_produce_distinct_positions(engine):
    """`seq` must order the transcript, which requires it to be unique.

    `commit` reads the current maximum and writes one past it. Two commits that
    read before either writes both see the same maximum and claim the same
    position, so the column that exists to order the record stops ordering it —
    and silently, since the ordering still *looks* fine on read.

    Reproduced at five concurrent writers, where every one of them claimed
    position 0. This is the transcript, which every other guarantee here treats
    as authoritative: ADR 0012's evidence is only useful if you can tell what
    happened before what.
    """
    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session(user_id="racer")

    async def write(text: str) -> None:
        async with AsyncSession(engine) as db:
            await SqlSessionRepository(db).commit(
                session.session_id, new_transcript_items=[message(text)]
            )

    await asyncio.gather(*(write(f"m{i}") for i in range(5)))

    async with AsyncSession(engine) as db:
        rows = (
            await db.exec(
                select(ChatTranscriptItem).where(
                    ChatTranscriptItem.session_id == session.session_id
                )
            )
        ).all()

    positions = sorted(row.seq for row in rows)
    assert len(rows) == 5, "a commit was lost entirely"
    assert positions == [0, 1, 2, 3, 4], f"positions collided: {positions}"


async def test_no_commit_is_lost_when_they_overlap(engine):
    """Serializing writers must not drop one.

    The obvious fix for the test above is a lock, and the obvious way to get a
    lock wrong is to let a blocked writer give up quietly. Every message sent
    has to be in the record afterwards.
    """
    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session(user_id="racer")

    async def write(text: str) -> None:
        async with AsyncSession(engine) as db:
            await SqlSessionRepository(db).commit(
                session.session_id, new_transcript_items=[message(text)]
            )

    sent = [f"m{i}" for i in range(8)]
    await asyncio.gather(*(write(text) for text in sent))

    async with AsyncSession(engine) as db:
        state = await SqlSessionRepository(db).get_state(session.session_id)

    assert sorted(item.payload["text"] for item in state.transcript) == sorted(sent)


async def test_a_multi_item_commit_stays_contiguous(engine):
    """One commit's items must not be interleaved with another's.

    A turn writes the user message and the reply together, and they are ordered
    relative to each other. If a concurrent commit could take a position in
    between, a transcript would show someone else's message inside a single
    exchange.
    """
    async with AsyncSession(engine) as db:
        session = await SqlSessionRepository(db).create_session(user_id="racer")

    async def write_pair(tag: str) -> None:
        async with AsyncSession(engine) as db:
            await SqlSessionRepository(db).commit(
                session.session_id,
                new_transcript_items=[message(f"{tag}-a"), message(f"{tag}-b")],
            )

    await asyncio.gather(*(write_pair(t) for t in ("x", "y", "z")))

    async with AsyncSession(engine) as db:
        state = await SqlSessionRepository(db).get_state(session.session_id)

    texts = [item.payload["text"] for item in state.transcript]
    for tag in ("x", "y", "z"):
        assert texts.index(f"{tag}-b") == texts.index(f"{tag}-a") + 1, texts
