"""Turning a transcript into claims, and refusing the ones that would poison it.

Driven with a fake model client, because the interesting behaviour is what this
module does with a reply rather than what a vendor produces. What is *not*
covered by a fake — whether a real model reliably gets the tense right — is not
coverable here at all and is the thing to check by hand before trusting output.

Real Postgres for the transcript and the graph. Start it with `just db-up`.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from bacteria.app.chat.models import ChatSession, ChatTranscriptItem
from bacteria.app.graph.extraction import (
    PROMPT_VERSION,
    UnknownSessionError,
    extract_assertions,
)
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.temporal import OPEN_ENDED

NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)
LATER = datetime(2026, 5, 11, tzinfo=timezone.utc)
SESSION = "s1"
USER = "u1"


@dataclass
class _Reply:
    text: Optional[str]
    model: str = "fake"


class FakeClient:
    """Returns whatever it was handed, and remembers what it was asked.

    A list of replies rather than one, so a test can drive two runs and give
    different answers — which is how the watermark's behaviour is reachable.
    """

    def __init__(self, *replies: Optional[str]) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []
        self.calls = 0

    async def send(self, messages: list[dict[str, Any]], **kwargs: Any) -> _Reply:
        self.calls += 1
        self.prompts.append(messages[0]["content"])
        return _Reply(self._replies.pop(0) if self._replies else "[]")


def _claim(src: str, rel: str, dst: str, tense: str = "current") -> dict[str, Any]:
    return {
        "src": {"label": src, "kind": "organization"},
        "rel": rel,
        "dst": {"label": dst, "kind": "person"},
        "tense": tense,
        "reason": f"the transcript said {src} {rel} {dst}",
    }


@pytest.fixture(name="db")
async def _db(engine):
    async with AsyncSession(engine) as session:
        session.add(ChatSession(session_id=SESSION, user_id=USER))
        for seq, (role, text) in enumerate(
            [("user", "Diane from Acme is their CTO"), ("assistant", "Noted.")]
        ):
            session.add(
                ChatTranscriptItem(
                    session_id=SESSION,
                    seq=seq,
                    kind="message",
                    payload={"role": role, "text": text},
                )
            )
        await session.commit()
        yield session
        await session.commit()


async def test_a_current_claim_is_recorded_with_an_open_end(db):
    """ "Is their CTO" must end open, or the claim reads as merely undated.

    This is the judgment the extractor exists to make. An open end says the claim
    still holds, which is what makes a second current claim a *conflict* rather
    than an undecidable pair — and that contradiction is the one a person would
    certainly want shown.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))

    result = await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    assert result.recorded == 1
    stored = await SqlGraphRepository(db).current(USER)
    assert stored[0].valid.end == OPEN_ENDED
    assert stored[0].valid.is_open


async def test_a_past_claim_does_not_read_as_still_true(db):
    """ "Used to work there" must not end open.

    ``past`` and ``unknown`` both become an unknown end today, which loses a
    distinction the model was asked for. The loss errs toward under-claiming and
    the answer is kept in ``attrs``, so this asserts the end is not open rather
    than asserting the two tenses differ — because today they do not.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane", tense="past")]))

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    stored = (await SqlGraphRepository(db).current(USER))[0]
    assert not stored.valid.is_open
    assert stored.valid.end is None
    assert stored.attrs is not None and stored.attrs["tense"] == "past"


async def test_a_claim_from_a_mixed_slice_is_not_trusted_as_the_users_own(db):
    """An assistant turn in the slice means the model's words are in the input.

    A claim extracted from those is the model deciding what it knows, and must
    not be able to influence what the model is shown next. The fixture's slice
    contains one user message and one assistant message, which is the ordinary
    case rather than a contrived one.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    assert (await SqlGraphRepository(db).current(USER))[0].trust == "third-party"


async def test_an_unknown_kind_is_dropped_rather_than_accepted(db):
    """The node vocabulary must not widen one plausible answer at a time.

    "human" instead of "person" is exactly the drift that makes a graph
    unusable — three kinds for one thing, and no query meaning what it says.
    """
    unknown_kind = _claim("Acme", "cto", "Diane")
    unknown_kind["dst"] = {"label": "Diane", "kind": "human"}
    client = FakeClient(json.dumps([unknown_kind]))

    result = await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    assert (result.recorded, result.dropped) == (0, 1)
    assert await SqlGraphRepository(db).current(USER) == []


async def test_unusable_output_advances_the_watermark_without_writing(db):
    """A session whose content will not parse must not block extraction forever.

    Raising here would leave the watermark unmoved and the same slice retried on
    every later turn, on a conversation that reliably breaks the extractor — a
    loop that costs a model call each time and never completes.
    """
    client = FakeClient("I'm afraid I can't do that.")

    result = await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    assert result.recorded == 0
    assert result.through_seq == 1
    assert await SqlGraphRepository(db).current(USER) == []


async def test_a_second_run_reads_nothing_new_and_calls_no_model(db):
    """The watermark is what keeps cost proportional to new turns.

    Without the early return a quiet turn still sends the whole slice again,
    which is a bill for re-reading a conversation nobody added to.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))
    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    result = await extract_assertions(db, client, SESSION, max_assertions=5, now=LATER)

    assert client.calls == 1
    assert (result.examined, result.recorded) == (0, 0)


async def test_re_reading_the_same_slice_does_not_duplicate_claims(db):
    """A retried job must rewrite its own claims rather than accumulate copies.

    The watermark advances *after* the write, so a crash between the two means
    the next run extracts the same messages again. The assertion id is derived
    from the claim and the run's timestamp, so a repeat at the same instant is
    the same row.
    """
    payload = json.dumps([_claim("Acme", "cto", "Diane")])
    first = FakeClient(payload)
    await extract_assertions(db, first, SESSION, max_assertions=5, now=NOW)

    # Rewind the watermark by hand: the crash this simulates leaves it unmoved.
    from bacteria.app.graph.models import GraphExtraction

    row = await db.get(GraphExtraction, SESSION)
    assert row is not None
    row.through_seq = -1
    db.add(row)
    await db.flush()

    await extract_assertions(db, FakeClient(payload), SESSION, max_assertions=5, now=NOW)

    assert len(await SqlGraphRepository(db).current(USER)) == 1


async def test_the_cap_drops_the_excess_and_counts_it(db):
    """Silent truncation would make a prompt problem look like a quiet one."""
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane"), _claim("Acme", "ceo", "Bob")]))

    result = await extract_assertions(db, client, SESSION, max_assertions=1, now=NOW)

    assert (result.recorded, result.dropped) == (1, 1)


async def test_what_was_written_records_which_prompt_produced_it(db):
    """ "The extractor went wrong for a fortnight" is only answerable if it does.

    Assertions are written without review, so the retraction query that fixes a
    bad run filters on this — and it cannot be reconstructed after the fact.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    stored = (await SqlGraphRepository(db).current(USER))[0]
    assert stored.attrs is not None
    assert stored.attrs["prompt_version"] == PROMPT_VERSION


async def test_an_absent_session_is_an_error_rather_than_a_quiet_zero(db):
    """A scheduling bug must not look like a conversation nobody spoke in."""
    with pytest.raises(UnknownSessionError):
        await extract_assertions(db, FakeClient(), "no-such-session", max_assertions=5, now=NOW)


async def test_what_was_written_records_which_conversation_it_came_from(db):
    """A claim nobody can trace back to a conversation cannot be judged.

    The column existed, was indexed, and was never written, so every assertion
    from the first fortnight of real use carries a null — provenance that looks
    recorded and is not. Retracting one bad session's output needs it, and so
    does anyone asking why a surprising claim is in their graph.
    """
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    stored = (await SqlGraphRepository(db).current(USER))[0]
    assert stored.session_id == SESSION


async def test_a_claim_restated_in_a_later_run_is_not_recorded_twice(db):
    """Not the retry above: a later run stamps a different recorded time.

    The assertion id is hashed from the claim *and* the run's timestamp, so a
    fact mentioned again next week hashes differently and used to land as a
    second believed row. This is the case that actually filled the log; the retry
    it was designed for never happened.
    """
    payload = json.dumps([_claim("Acme", "cto", "Diane")])
    await extract_assertions(db, FakeClient(payload), SESSION, max_assertions=5, now=NOW)

    for seq, (role, text) in enumerate(
        [("user", "Diane is still their CTO"), ("assistant", "Noted.")], start=2
    ):
        db.add(
            ChatTranscriptItem(
                session_id=SESSION, seq=seq, kind="message", payload={"role": role, "text": text}
            )
        )
    await db.flush()

    result = await extract_assertions(db, FakeClient(payload), SESSION, max_assertions=5, now=LATER)

    assert (result.recorded, result.duplicates) == (0, 1)
    assert len(await SqlGraphRepository(db).current(USER)) == 1


async def test_an_extracted_preference_is_proposed_and_never_spoken(db):
    """The whole containment, in one row.

    Everything the extractor writes is `inferred`, so a preference it hears is a
    proposal and reaches no prompt until a person states it. Without this the
    model would be writing its own memory, which is the one thing the agent's
    ADR 0016 forbids.
    """
    client = FakeClient(
        json.dumps(
            [
                {
                    "src": {"label": "self", "kind": "person"},
                    "rel": "tone",
                    "dst": {"label": "concise", "kind": "value"},
                    "tense": "current",
                    "reason": "they asked for short answers",
                }
            ]
        )
    )

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    claims = [a for a in await SqlGraphRepository(db).current(USER) if a.rel == "tone"]

    assert len(claims) == 1
    assert claims[0].origin == "inferred", "a proposal, not a memory"
    assert claims[0].scope == "session", "it belongs to the conversation it was heard in"


async def test_an_extracted_fact_stays_scoped_to_the_person(db):
    """A fact is about the world and holds wherever they go; a preference is not."""
    client = FakeClient(json.dumps([_claim("Acme", "cto", "Diane")]))

    await extract_assertions(db, client, SESSION, max_assertions=5, now=NOW)

    stored = await SqlGraphRepository(db).current(USER)
    assert stored[0].scope == "user"
