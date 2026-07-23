"""Structured output validation — Part 2 decision: schema validity is shape,
not truth. Anything the model produces gets validated here before the rest
of the app trusts it; this module is the boundary, not the model's own
schema-following behavior.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from bacteria.model.errors import ContractError

T = TypeVar("T", bound=BaseModel)


class OutputValidationError(ContractError):
    """Model output didn't match the expected shape. Distinct from a
    ContractError about the request — this one is about the response."""


def validate_output(raw: dict[str, Any], schema: type[T]) -> T:
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise OutputValidationError(str(exc)) from exc
