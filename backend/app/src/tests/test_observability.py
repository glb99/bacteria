import re

import logfire

from app.observability import setup_observability, setup_tracing


def test_setup_tracing_configures_logfire_without_console(monkeypatch) -> None:
    calls = []

    def configure(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("app.observability.logfire.configure", configure)

    setup_tracing(service_name="test-service")

    assert len(calls) == 1
    assert {key: value for key, value in calls[0].items() if key != "scrubbing"} == {
        "service_name": "test-service",
        "send_to_logfire": True,
        "console": False,
    }
    scrubbing = calls[0]["scrubbing"]
    assert isinstance(scrubbing, logfire.ScrubbingOptions)
    assert scrubbing.callback is not None
    callback = calls[0]["scrubbing"].callback
    session_match = re.search("session", "session.id")
    api_key_match = re.search("api_key", "api_key")
    assert session_match is not None
    assert api_key_match is not None
    assert (
        callback(
            logfire.ScrubMatch(
                path=("attributes", "session.id"),
                value="session-123",
                pattern_match=session_match,
            )
        )
        == "session-123"
    )
    assert (
        callback(
            logfire.ScrubMatch(
                path=("attributes", "api_key"),
                value="secret-value",
                pattern_match=api_key_match,
            )
        )
        is None
    )


def test_setup_observability_configures_logfire(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.observability.logfire.configure", lambda **kwargs: calls.append(kwargs)
    )

    setup_observability()

    assert len(calls) == 1
    assert {key: value for key, value in calls[0].items() if key != "scrubbing"} == {
        "service_name": "bacteria",
        "send_to_logfire": True,
        "console": False,
    }
    scrubbing = calls[0]["scrubbing"]
    assert isinstance(scrubbing, logfire.ScrubbingOptions)
    assert scrubbing.callback is not None
