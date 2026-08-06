"""Invariant tests for the authoritative store: who may write, and what stays apart.

Not exhaustive by design. These cover the properties whose silent violation
would cause a real bug — not every method, and not every branch.
"""

import pytest

from bacteria.session.store import SessionStore, TranscriptItem, UnknownSessionError


def test_get_state_returns_a_copy_not_the_authoritative_record():
    """A caller cannot write to the store by mutating what it read.

    This is what makes "only commit() writes" structural rather than a rule
    everyone has to remember. Without the deep copy, authoritative state could
    be edited from outside the module that owns it — a bug that leaves no
    trace of who changed what.
    """
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
    """One user holds many sessions; session id is never derived from user id.

    Keeping them separate also keeps "this session exists" from drifting into
    an implicit answer to "is this allowed".
    """
    store = SessionStore()
    session_a = store.create_session(user_id="u1")
    session_b = store.create_session(user_id="u1")

    assert session_a.session_id != session_b.session_id
    assert session_a.user_id == session_b.user_id == "u1"


def test_transcript_and_working_state_are_independently_addressable():
    """Writing one kind of state must not disturb another.

    The three-way split is only real if the three are independently writable;
    otherwise it is one blob with three names.
    """
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


def test_memory_writes_are_explicit_and_separate_from_commit():
    """Remembering is a decision, so it needs its own call.

    If working-state updates could reach memory, "stash this for the current
    turn" and "keep this permanently" would be the same operation — and the
    difference between them is the entire reason memory exists separately.
    """
    store = SessionStore()
    session = store.create_session(user_id="u1")

    store.commit(session.session_id, working_state_updates={"scratch": 1})
    state = store.get_state(session.session_id)
    assert state.memory == {}

    store.remember(session.session_id, key="pref", value="concise", reason="user said so")
    state = store.get_state(session.session_id)
    assert state.working_state == {"scratch": 1}
    assert state.memory["pref"].value == "concise"
    assert state.memory["pref"].reason == "user said so"


def test_forget_removes_a_memory_entry():
    """A memory can be removed.

    Without a removal path every memory is permanent by default, which is how
    a stale preference outlives the situation that produced it.
    """
    store = SessionStore()
    session = store.create_session(user_id="u1")
    store.remember(session.session_id, key="pref", value="concise", reason="user said so")

    store.forget(session.session_id, key="pref")

    assert store.get_state(session.session_id).memory == {}
