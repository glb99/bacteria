"""Asking a human whether a specific action should happen, right now.

Approval is one of three controls that are easy to collapse into each other and
should not be:

- **authorization** — is this principal permitted this capability at all? Policy,
  evaluated against identity. Not built; there is one local user and no policy
  to evaluate.
- **approval** — should this particular call, with these arguments, run now?
  A judgment about one action. This module.
- **isolation** — if it runs and goes wrong, how far does the damage reach?
  Containment, independent of whether it was allowed. Not built; see
  :mod:`bacteria.agent.tools.execution`.

Two properties make approval real rather than ceremonial, and both are here:

*Placement.* The prompt happens at the side effect, inside the execution path,
not at the start of a task. "May I help with your files?" answered ten steps
before a deletion is not consent to that deletion — by then the user has agreed
to something they could not have seen.

*Default.* Ambiguity denies. Anything that is not an explicit yes is a no, so a
stray keystroke, an empty line, or a piped EOF cannot become permission.

Not built:
    Non-interactive approval. :func:`cli_approve` blocks on stdin, so it cannot
    be used by a server, a scheduled run, or any surface without a human
    present. The *shape* for one now exists —
    :data:`bacteria.agent.tools.execution.Approve` accepts a coroutine function, so a
    gate that persists the question and awaits an answer arriving minutes later
    is expressible. What is missing is everything behind it: pausing a run,
    notifying someone, and resuming on their answer all need durable run state,
    which does not exist. Until then this module holds the interactive
    implementation only.

    Remembered decisions. Every call is asked about individually; there is no
    "always allow this tool". Adding one means deciding what the grant is scoped
    to, and a grant scoped too broadly is the failure mode approval exists to
    prevent.
"""

from __future__ import annotations

from typing import Callable

from bacteria.agent.model.protocol import ToolCall


def describe_tool_call(tool_call: ToolCall) -> str:
    """Render a pending call as text someone can actually decide on.

    Names the tool *and* its arguments. The arguments are the part that
    matters: "run add_note?" and "run add_note with this text?" are different
    questions, and only the second can be answered correctly.

    Returns:
        A one-line description, argument values included verbatim.
    """
    return f"{tool_call['name']}({tool_call['input']!r})"


def cli_approve(tool_call: ToolCall, input_fn: Callable[[str], str] = input) -> bool:
    """Ask the local user to approve one tool call.

    Written synchronously even though the caller is async, and deliberately so:
    :func:`bacteria.agent.tools.execution.execute_tool_call` runs a synchronous gate
    in a worker thread, which is exactly right for a blocking terminal read.
    Making this a coroutine that awaited stdin would be more machinery for the
    same behavior.

    Args:
        tool_call: The pending call, described to the user in full.
        input_fn: Injected so tests can drive the prompt without a terminal.

    Returns:
        ``True`` only for an explicit ``y`` or ``yes``. Everything else —
        blank input, ``sure``, a typo, an accidental newline — is a rejection.
        Denial is the safe failure: a wrongly refused call is retried by asking
        again, while a wrongly approved one has already happened.
    """
    answer = input_fn(f"Approve tool call {describe_tool_call(tool_call)}? [y/N] ")
    return answer.strip().lower() in ("y", "yes")
