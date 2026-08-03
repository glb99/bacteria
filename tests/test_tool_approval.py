"""Load-bearing invariant tests for the approval boundary (Part 7 decisions)."""

from bacteria.tools.approval import cli_approve, describe_tool_call


def test_describe_tool_call_names_the_action_and_its_arguments():
    """The article's 'good approval text' requirement — a vague blanket ask
    isn't enough; the description must show what would actually run."""
    description = describe_tool_call({"id": "t1", "name": "send_email", "input": {"to": "a@b.com"}})

    assert "send_email" in description
    assert "a@b.com" in description


def test_cli_approve_accepts_an_explicit_yes():
    approved = cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "y")
    assert approved is True


def test_cli_approve_rejects_by_default_on_ambiguous_input():
    """Approval must default to denied, not allowed — an empty/garbage
    answer must never be treated as consent."""
    assert cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "") is False
    assert cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "sure") is False
