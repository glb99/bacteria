"""Invariant tests for output validation: shape is enforced, truth is not claimed."""

import pytest
from pydantic import BaseModel

from bacteria.model.output import OutputValidationError, validate_output


class RefundArgs(BaseModel):
    order_id: str
    amount_cents: int


def test_valid_output_passes():
    result = validate_output({"order_id": "o1", "amount_cents": 500}, RefundArgs)
    assert result.order_id == "o1"
    assert result.amount_cents == 500


def test_shape_mismatch_is_rejected_not_silently_coerced_into_garbage():
    with pytest.raises(OutputValidationError):
        validate_output({"order_id": "o1", "amount_cents": "not-a-number"}, RefundArgs)


def test_missing_field_is_rejected():
    with pytest.raises(OutputValidationError):
        validate_output({"order_id": "o1"}, RefundArgs)
