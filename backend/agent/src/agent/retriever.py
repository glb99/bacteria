from typing import Protocol


class RetrievesDocumentPages(Protocol):
    """A rule for picking which memories a turn should see.

    Synchronous, unlike the rest of this package's seams, and deliberately: an
    implementation that needs to await something is querying a store, which is
    the other design named in the module docstring rather than an instance of
    this one.
    """

    def select(self, query: str, limit: int) -> list[bytes]:
        """Choose from ``candidates``.

        Args:
            query: The incoming user message. Unused by recency, and present
                because it is the whole input to any rule that is not recency —
                a protocol that omitted it would have to change shape the first
                time someone ranked against it.
            limit: The most that may be returned. Zero means none; a strategy
                that treats it as "no bound" inverts the strictest request into
                the loosest, which is a bug this module has already had once.
        """
        ...
