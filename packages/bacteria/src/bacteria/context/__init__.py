"""Choosing what the model is shown on a given turn.

Owns the working set: the bounded selection of history, memory, and (eventually)
retrieved evidence that goes into one request. Assembling context is a policy
decision — what is relevant, what fits, what is worth its cost — which is why it
is a layer rather than a formatting step inside the runtime.

Must not: be confused with the transcript. The transcript is the complete record
and lives in :mod:`bacteria.session`; context is a small, disposable view built
fresh each turn. An agent that sends its whole transcript has not chosen a
context strategy, it has skipped the question.
"""
