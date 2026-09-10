import pytest

from bacteria.agent.context.assembly import assemble_context
from bacteria.agent.session.model import SessionState, TranscriptItem


def test_context_assembly_returns_expected_messages():
    """Assembled context should include the new user message and recent history."""
    state = SessionState(
        session=None,  # Not needed for this test
        transcript=[
            TranscriptItem(kind="message", payload={
                           "role": "user", "text": "Hello"}),
            TranscriptItem(kind="message", payload={
                           "role": "assistant", "text": "Hi there!"}),
            TranscriptItem(kind="message", payload={
                           "role": "user", "text": "How are you?"}),
        ]

    )
    user_text = "What's the weather like?"
    window_size = 2

    assembled_context = assemble_context(state, user_text, window_size)

    expected_messages = [
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
        {"role": "user", "content": user_text},
    ]

    assert len(assembled_context.messages) == window_size + 1, (
        "expected window_size prior messages plus the new user message"
    )
    assert assembled_context.messages[:-1] == expected_messages[:-1], (
        "expected the most recent window_size messages from the transcript, oldest first"
    )
    assert assembled_context.messages[-1] == {"role": "user", "content": user_text}, (
        "expected the new user message appended last"
    )
    assert assembled_context.messages == expected_messages, (
        "expected windowed history followed by the new user message"
    )
