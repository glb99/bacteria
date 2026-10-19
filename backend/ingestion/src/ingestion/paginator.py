"""The pipeline's contract for one PDF page."""

from typing import Protocol


class Paginate(Protocol):
    """A protocol for a function that formats text."""

    def __call__(self, doc: bytes) -> str:
        ...


def paginate(doc: bytes):
