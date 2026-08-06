"""Fixtures shared across the suite. Auto-discovered by pytest; never imported."""

import pytest

from bacteria.model.protocol import ModelResponse


class FakeModelClient:
    """A model client that satisfies the protocol and calls no API.

    Used wherever a test needs *a* model client but is not testing one — the
    runtime tests, mainly. Counts its calls, because "how many times was the
    model called" is itself an invariant worth asserting.
    """

    def __init__(self, text: str = "hi there") -> None:
        self.calls = 0
        self._text = text

    def send(self, messages, **kwargs) -> ModelResponse:
        self.calls += 1
        return ModelResponse(text=self._text, tool_calls=[], stop_reason="end_turn", raw=None)


@pytest.fixture(name="make_fake_model_client")
def _make_fake_model_client():
    """Factory for :class:`FakeModelClient`, so tests can set the reply text.

    The defining function is underscore-prefixed with the fixture name given
    explicitly. A test that forgets to declare the fixture as a parameter and
    reaches for the module-level name instead then gets an obvious failure
    rather than silently closing over the wrong object.
    """

    def _make(text: str = "hi there") -> FakeModelClient:
        return FakeModelClient(text=text)

    return _make
