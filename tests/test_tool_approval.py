"""Invariant tests for the approval gate: what counts as consent."""

from bacteria.tools.approval import cli_approve, describe_tool_call


def test_describe_tool_call_names_the_action_and_its_arguments():
    """The prompt must show the arguments, not just the tool name.

    "Approve send_email?" and "approve send_email to this address?" are
    different questions, and only the second one can be answered correctly.
    """
    description = describe_tool_call({"id": "t1", "name": "send_email", "input": {"to": "a@b.com"}})

    assert "send_email" in description
    assert "a@b.com" in description


def test_cli_approve_accepts_an_explicit_yes():
    approved = cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "y")
    assert approved is True


def test_cli_approve_rejects_by_default_on_ambiguous_input():
    """Ambiguity denies. Only an explicit yes is consent.

    A stray newline, a piped EOF, or a hedged "sure" must not authorize a side
    effect. Denial is recoverable by asking again; approval is not.
    """
    assert cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "") is False
    assert cli_approve({"name": "echo", "input": {}}, input_fn=lambda _prompt: "sure") is False
