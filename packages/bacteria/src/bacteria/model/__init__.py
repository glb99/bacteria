"""Talking to a language model, and nothing else.

Owns three concerns that are worth naming separately even though one hosted API
call covers all of them:

- **asset** — which model, with what capabilities and limits.
- **serving** — how the request is delivered, queued, and retried. Mostly the
  provider's problem here; this layer only handles retry and backoff.
- **contract** — the request and response shapes, and what happens when they
  are not what was expected.

Splitting them shows up concretely in :mod:`bacteria.model.errors`, where the
failure taxonomy follows those lines so that retry policy can be decided from
the exception class alone.

Must not: execute anything. A model asking for a tool is a proposal, and this
layer's only job with it is to report it accurately. No module here imports
:mod:`bacteria.tools`, which is what makes that a structural guarantee rather
than a rule someone has to remember.

Start at :mod:`bacteria.model.protocol` — it defines the contract both clients
implement and every caller uses.
"""
