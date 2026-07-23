"""Load-bearing invariant tests for the session store (Part 3 decisions).

Not exhaustive by design — per CLAUDE.md's testing approach, only the
decisions whose violation would cause a real bug get a test here.
"""

import pytest

from bacteria.session.store import SessionStore, TranscriptItem, UnknownSessionError


def test_get_state_returns_a_copy_not_the_authoritative_record():
    """'Model/runtime output is always a proposal, never a direct write' —
    mutating what get_state() returns must not affect the store."""
    store = SessionStore()
    session = store.create_session(user_id="u1")

    state = store.get_state(session.session_id)
    state.working_state["hacked"] = True
    state.transcript.append(TranscriptItem(kind="message", payload={"text": "sneaky"}))

    fresh = store.get_state(session.session_id)
    assert fresh.working_state == {}
    assert fresh.transcript == []


def test_commit_is_the_only_way_state_actually_changes():
    store = SessionStore()
    session = store.create_session(user_id="u1")

    committed = store.commit(
        session.session_id,
        new_transcript_items=[TranscriptItem(kind="message", payload={"text": "hi"})],
        working_state_updates={"step": 1},
    )

    assert len(committed.transcript) == 1
    assert committed.working_state == {"step": 1}
    assert store.get_state(session.session_id).working_state == {"step": 1}


def test_session_identity_is_independent_of_user_identity():
    """'Session identity kept explicit and separate from user identity' —
    the same user must be able to hold multiple distinct sessions."""
    store = SessionStore()
    session_a = store.create_session(user_id="u1")
    session_b = store.create_session(user_id="u1")

    assert session_a.session_id != session_b.session_id
    assert session_a.user_id == session_b.user_id == "u1"


def test_transcript_and_working_state_are_independently_addressable():
    """'Three explicitly separate concerns' — a working-state update must not
    touch the transcript, and vice versa."""
    store = SessionStore()
    session = store.create_session(user_id="u1")

    store.commit(session.session_id, working_state_updates={"a": 1})
    state = store.get_state(session.session_id)
    assert state.transcript == []

    store.commit(
        session.session_id,
        new_transcript_items=[TranscriptItem(kind="message", payload={"text": "hi"})],
    )
    state = store.get_state(session.session_id)
    assert state.working_state == {"a": 1}
    assert len(state.transcript) == 1


def test_unknown_session_is_rejected():
    store = SessionStore()
    with pytest.raises(UnknownSessionError):
        store.get_state("does-not-exist")
