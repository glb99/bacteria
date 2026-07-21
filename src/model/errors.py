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
