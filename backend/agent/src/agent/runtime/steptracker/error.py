class StepAlreadyExecutedError(Exception):
    """A step was about to run a second time within the same run.

    Always a bug in the runtime's own control flow, never something a caller
    can cause. Raised loudly instead of skipping the repeat, because a skipped
    duplicate would return ``None`` where a result was expected and fail
    somewhere less informative.
    """