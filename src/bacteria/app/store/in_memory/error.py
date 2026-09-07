class UnknownSessionError(KeyError):
    """The named session does not exist.

    Raised rather than creating the session implicitly: a session id that does
    not resolve usually means a caller lost track of one, and silently
    conjuring an empty session turns that into invisible data loss.
    """


class MemoryRefused(Exception):
    """A store will not hold this key, and that is an answer rather than a fault.

    **The outcome the protocol was missing.** It was written against a store that
    cannot refuse anything — a table takes whatever key it is handed — so
    :meth:`SessionRepository.remember` and :meth:`~SessionRepository.propose`
    returned an entry and had no other ending, and every caller was built on the
    assumption that a write either succeeds or the process is broken.

    A store with a vocabulary breaks that assumption. Raising anything else says
    *this handler is defective*, which is what
    :func:`~bacteria.agent.tools.execution.execute_tool_call` correctly does with
    an exception it does not recognize — and that cost a whole turn for a memory
    nobody asked for. See ADR 0025.

    ``reason`` is written for a model to read. It is not an error message for a
    log: the caller that acts on this is the one deciding what to say next.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"{key!r} refused: {reason}")
        self.key = key
        self.reason = reason