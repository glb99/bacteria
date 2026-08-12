"""Validation boundary for structured model output.

Schema validity is shape, not truth. A model asked for ``{"order_id": str,
"amount_cents": int}`` will reliably produce something matching that shape and
can still produce the wrong order and the wrong amount. This module enforces
the shape so that the rest of the application can reason about *types* without
also having to guess at parse failures — it does not, and cannot, establish
that the values are correct.

The distinction matters at the call site: passing validation is permission to
read the fields, not permission to act on them. Anything with a real side
effect still goes through :mod:`bacteria.agent.tools.execution` and its approval
gate.

Not built:
    Nothing calls this yet. It is the enforcement point for the day a tool or
    workflow needs typed arguments back from the model rather than prose, and
    is kept because the alternative — parsing model JSON ad hoc at each call
    site — is how "it validated" quietly starts meaning "it parsed".
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from bacteria.agent.model.errors import ContractError

T = TypeVar("T", bound=BaseModel)


class OutputValidationError(ContractError):
    """Model output did not match the expected shape.

    Subclasses :class:`~bacteria.agent.model.errors.ContractError` so that callers
    catching contract failures catch this too, while callers that specifically
    care about response shape — as opposed to a malformed *request* — can
    distinguish the two.
    """


def validate_output(raw: dict[str, Any], schema: type[T]) -> T:
    """Parse model output against ``schema``, or fail loudly.

    Args:
        raw: Decoded model output. Untrusted.
        schema: The pydantic model the output must satisfy.

    Returns:
        The validated instance. Type-correct, not necessarily true.

    Raises:
        OutputValidationError: Output did not match ``schema``. Deliberately
            not a silent coercion or a ``None`` return — a caller that forgets
            to check a ``None`` gets a confusing failure much later, whereas an
            exception fails at the boundary that detected the problem.
    """
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise OutputValidationError(str(exc)) from exc
