"""Fixtures shared across the suite, and what this suite is for.

Auto-discovered by pytest; never imported directly.

**Why there are so few tests.** These are architectural fitness functions —
executable checks that a structural property still holds — not line coverage.
The bar for adding one is: *would its silent violation cause a real bug?* A
handler reaching the model, a retry repeating a side effect, a rejection that
did not actually stop anything, a failed run leaving no evidence. Those get a
test that fails when the property breaks.

Design *rationale* does not. "We chose a narrow protocol over a provider
abstraction layer" is a real decision with nothing to assert about it; tests
written to cover that kind of claim end up asserting implementation detail,
which makes refactoring expensive and protects nothing. Rationale lives in the
docstring of whatever it explains.

Two consequences worth knowing before judging this suite:

- Coverage is uneven **by design** — thorough where a break would hurt, thin
  where it would not. That looks like negligence on a coverage report, and a
  percentage gate would reward writing exactly the tests this project has
  decided not to write. Do not add one without reversing this decision
  deliberately.
- Bugs in non-invariant code will not be caught here. Accepted: the alternative
  is a suite large enough that nobody reads a failure carefully.

**Mocks are not sufficient for anything touching a provider API.** Gemini
requires an opaque ``thought_signature`` echoed back on the turn after a tool
call. Every mocked test passed while every live multi-turn tool call failed.
Run it for real before believing a provider integration works.

Test docstrings state the invariant *and* the consequence of breaking it. They
are documentation as much as verification, so keep them that way.
"""

import pytest

from bacteria.agent.model.protocol import ModelResponse


class FakeModelClient:
    """A model client that satisfies the protocol and calls no API.

    Used wherever a test needs *a* model client but is not testing one — the
    runtime tests, mainly. Counts its calls, because "how many times was the
    model called" is itself an invariant worth asserting.
    """

    def __init__(self, text: str = "hi there") -> None:
        self.calls = 0
        self._text = text

    async def send(self, messages, **kwargs) -> ModelResponse:
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
