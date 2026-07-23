"""Shared test fixtures. Auto-discovered by pytest for every file under tests/."""

import pytest

from bacteria.model.client import ModelResponse


class FakeModelClient:
    """A minimal stand-in satisfying the same shape ModelClient.send() has,
    without touching the real Anthropic SDK. Used wherever a test needs a
    model client but isn't testing ModelClient itself."""

    def __init__(self, text: str = "hi there") -> None:
        self.calls = 0
        self._text = text

    def send(self, messages, **kwargs) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text=self._text, tool_calls=[], stop_reason="end_turn", raw=None)


@pytest.fixture(name="make_fake_model_client")
def _make_fake_model_client():
    """Factory fixture — tests that need a custom response text call this
    instead of importing FakeModelClient directly.

    Defining function is underscore-prefixed with the fixture name set
    explicitly, so accidentally referencing the raw function instead of
    requesting the fixture (forgetting the test-parameter dependency) is
    visibly wrong rather than silently passing the wrong object.
    """

    def _make(text: str = "hi there") -> FakeModelClient:
        return FakeModelClient(text=text)

    return _make
