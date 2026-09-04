"""The owner's own ontology, and the conversation it is learned from.

Owns two things that turned out to be one feature. First, hosting the agent:
the session tables, the durable ``SessionRepository`` the agent's runtime is
handed, and the ``/chat`` routes that start a session and advance a turn.
Second, the *personal* ontology — the claims a person makes about their own
life — which is extracted from those conversations, held in the shared
assertion log under its own ``ontology`` partition, and reviewed through the
``/graph`` routes.

They live together because the extraction is not a separate pipeline reading
somebody else's data: a turn produces a transcript, the transcript produces
candidate claims, and the same owner reviews them. Splitting the package would
put a queue between two halves of one act.

Contrast :mod:`~bacteria.app.architecture`, which shares the assertion table
and inverts the trust model — that one derives claims from source code and
requires a human to accept each; this one auto-commits what the extractor
believes and lets the owner retract. Two ontologies, one log, opposite
defaults. See ADR 0006 for the log and ADR 0007 for the relation catalogue.

Must not: reach into ``bacteria.agent.interfaces``. That package is the agent's
own composition root, for running it standalone. Composition for *this* process
happens in ``bacteria.app.entrypoints``. The direction of dependency is the
point — this package imports ``bacteria.agent``; the agent imports nothing from
here and does not know this application exists.
"""
