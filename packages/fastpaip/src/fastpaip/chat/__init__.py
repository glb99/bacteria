"""The feature that hosts the agent.

Owns everything needed to run a conversation over HTTP: the tables its state
lives in, the durable ``SessionRepository`` the agent's runtime is handed, and
the routes that start a session and advance a turn.

The direction of dependency is the point. This package imports ``bacteria``;
``bacteria`` imports nothing from here and does not know this application
exists. What connects them is a protocol the agent declares and this package
implements, which is why the agent can be lifted into a different host without
carrying a database with it.

Must not: reach into ``bacteria.interfaces``. That package is the agent's own
composition root, for running it standalone. Composition for *this* process
happens in ``fastpaip.entrypoints``.
"""
