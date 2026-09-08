"""Where work enters the system.

Owns two things: receiving an event from outside, and composing the concrete
objects that will handle it. The second is the less obvious one and the more
important — this is the only layer that names a specific model provider, a
specific tool set, or a specific approval mechanism. Everything below receives
those as arguments, which is why no other module needs to read configuration.

Must not: contain agent logic. An interface that starts deciding what to say,
which tool to prefer, or when to retry has become a second runtime, and adding
a channel then means reimplementing the agent instead of adding a file.
"""
