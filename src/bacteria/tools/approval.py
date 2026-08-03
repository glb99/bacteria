"""Approval boundary — Part 7 (Execution Surfaces, Identity, and Approval
Boundaries).

The one piece of Part 7 built for real at our current scale. Confirms that
a specific tool call should execute *now* — deliberately not the same thing
as authorization (identity/policy — no multi-tenant/OAuth/service-account
surface exists in this project to model) or sandboxing (blast-radius
containment — also deferred). Both stay documented-only in
docs/SYSTEM_DESIGN.md until there's a concrete need for them.

Placed at the point of the actual side effect (`bacteria.tools.execution`),
not at task start — the article's point that a vague, early "can I do this
task?" approval means nothing by the time the real action happens ten steps
later.
"""

from __future__ import annotations

from typing import Any, Callable


def describe_tool_call(tool_call: dict[str, Any]) -> str:
    """The article's 'good approval text' shape: name what happens and with
    what arguments, not a vague blanket ask."""
    return f"{tool_call['name']}({tool_call['input']!r})"


def cli_approve(tool_call: dict[str, Any], input_fn: Callable[[str], str] = input) -> bool:
    """Ask the local user directly. Anything other than an explicit y/yes is
    a rejection — approval defaults to denied, not allowed, on ambiguous
    input."""
    answer = input_fn(f"Approve tool call {describe_tool_call(tool_call)}? [y/N] ")
    return answer.strip().lower() in ("y", "yes")
