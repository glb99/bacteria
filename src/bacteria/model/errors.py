"""Error taxonomy for the model layer — Part 2 decision: split error handling
by which of the three model-layer components failed (asset / serving /
contract), so retries and logging are diagnosable per the layer that broke.
"""


class ModelLayerError(Exception):
    """Base for all model-layer failures."""


class AssetError(ModelLayerError):
    """Request can't succeed as shaped: context window exceeded, unsupported
    modality, output too long. Not retryable as-is — requires reshaping the
    request."""


class ServingError(ModelLayerError):
    """Transient delivery failure: rate limit, timeout, overload. Retryable
    with backoff."""


class ContractError(ModelLayerError):
    """Malformed request or unexpected response shape — an integration bug,
    not retryable blindly."""


class CredentialsError(ModelLayerError):
    """Credentials could not be resolved or were rejected. Distinct from the
    asset/serving/contract three-way split above: those all describe ways a
    *well-formed attempt* to reach the model can fail, whereas this means we
    were never authorized to make the attempt at all. Not retryable — no
    amount of backoff fixes a missing or invalid API key."""
