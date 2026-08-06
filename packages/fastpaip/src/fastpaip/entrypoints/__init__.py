"""How the application is started, and nothing else.

Each module here is one way in — ASGI, a queue worker, a command — and its whole
job is composition: read configuration, construct concrete implementations, wire
them together, hand off. Every decision that belongs to a *deployment* rather
than to the code lives here, which is what keeps the packages below free of
global configuration.

Must not contain logic. These modules are omitted from coverage on that basis,
so a bug written here is a bug nothing measures. If an entrypoint starts to look
like it deserves a test, that is the signal it holds logic belonging to a
feature — move the logic, not the test.

This is also the only place an event loop is started. `bacteria` deliberately
starts none of its own so that it can be hosted; undoing that here, by starting
one somewhere further in, would take the choice away from whatever hosts *this*.

Note there are two composition roots in this repository, and that is correct:
`bacteria.interfaces` composes the agent for running standalone, and this
package composes the application. They compose different processes. The rule
that keeps them from becoming one tangle is that the application never imports
`bacteria.interfaces`.
"""
