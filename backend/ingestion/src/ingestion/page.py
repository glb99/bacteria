"""The pipeline's contract for one PDF page."""

from typing import Protocol


class PageExtractor(Protocol):
    """The visual call for one PDF page. Returns the text that page produced."""

    def extract_page(self, page: bytes) -> str:
        """Return the text extracted from one PDF page."""
