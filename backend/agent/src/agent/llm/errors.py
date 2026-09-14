"""Failure taxonomy for the model layer, split by what actually broke.

A single ``ModelCallFailed`` exception would be easier to write and useless to
act on: the caller could not tell a rate limit (wait and retry) from a blown
context window (reshape the request) from a missing API key (stop and tell the
operator). Retry policy is decided by the class of the exception raised here,
so the split is load-bearing rather than cosmetic. Working alongside it is
also the rule that keeps retrying safe at all: model clients cannot execute
anything, so there is no side effect in this layer for a second attempt to
duplicate (:mod:`bacteria.agent.tools.execution` is the only place a handler runs).

The three-way asset/serving/contract split describes ways a *well-formed,
authorized attempt* to reach a model can fail. :class:`CredentialsError` sits
outside it deliberately: there, no attempt was ever authorized to begin with.

Invariant: exactly one of these classes is retryable — :class:`ServingError`.
Every model client classifies raw SDK exceptions into this taxonomy and retries
on that class alone. Adding a retryable category means revisiting every client.
"""


class ModelLayerError(Exception):
    """Base for every failure originating in the model layer.

    Callers that do not care which component broke can catch this; callers
    deciding whether to retry must catch the subclasses.
    """


class AssetError(ModelLayerError):
    """The request cannot succeed in its current shape.

    Context window exceeded, unsupported modality, output length overrun.
    Not retryable as-is — the request has to change first, which is a decision
    for the caller, not this layer.
    """


class ServingError(ModelLayerError):
    """Transient failure delivering the request: rate limit, timeout, overload.

    The only retryable category. Retries re-send a byte-identical request, so
    a retry can never produce a side effect the first attempt did not.
    """


class ContractError(ModelLayerError):
    """The request or the response did not match what the API expects.

    An integration bug. Retrying an unchanged malformed request just spends
    quota to fail identically, so this is never retried. Also the fallback
    classification for unrecognized exceptions: an unknown failure is treated
    as a bug in this code until proven otherwise, which is the safe default
    because it does not retry.
    """


class CredentialsError(ModelLayerError):
    """Credentials could not be resolved locally, or were rejected remotely.

    Held apart from the asset/serving/contract split above because those all
    describe a well-formed attempt failing, whereas this means the attempt was
    never authorized at all. Not retryable — no amount of backoff produces an
    API key.

    Worth knowing when adding a provider: SDKs disagree on *when* this
    surfaces. The Anthropic SDK fails lazily, on the first request, with a bare
    ``TypeError`` raised before any network call. The Gemini SDK fails eagerly,
    at client construction, with a bare ``ValueError``. Both are unremarkable
    built-in exception types, so a client that only classifies its SDK's own
    error hierarchy will let this failure escape untyped. Both cases are
    handled explicitly; a third provider will need the same check.
    """
