"""Golden page-text evals for the ingestion pipeline.

One entry is a single PDF page and the text that page should produce. The
eval sends that page to a page extractor and compares the returned text with
the expected text. It does not read a database row and it does not retrieve.

The strings must be equal. What counts as a match is still an open decision,
so every difference is a miss.
"""

from dataclasses import dataclass
from pathlib import Path

from ingestion.page import PageExtractor


@dataclass(frozen=True)
class GoldenPage:
    """A fixed page and the text the pipeline must return for it."""

    name: str
    page: bytes
    expected_text: str


@dataclass(frozen=True)
class PageMiss:
    """One golden page whose returned text was not the expected text."""

    name: str
    expected_text: str
    returned_text: str


class EmptyGoldenSet(Exception):
    """The eval ran with no pages, so it cannot detect a broken pipeline."""

    def __init__(self) -> None:
        super().__init__("golden set has no pages")


class GoldenSetMiss(Exception):
    """At least one page returned text other than its expected text."""

    def __init__(self, misses: tuple[PageMiss, ...]) -> None:
        self.misses = misses
        lines = [f"{len(misses)} golden page(s) missed:"]
        for miss in misses:
            lines.append(
                f"{miss.name}: expected {miss.expected_text!r}, "
                f"returned {miss.returned_text!r}"
            )
        super().__init__("\n".join(lines))


def load_golden_set(directory: Path) -> tuple[GoldenPage, ...]:
    """Load each child directory that holds `page.pdf` and `expected.txt`."""
    if not directory.is_dir():
        raise EmptyGoldenSet
    pages: list[GoldenPage] = []
    for child in sorted(path for path in directory.iterdir() if path.is_dir()):
        page_path = child / "page.pdf"
        expected_path = child / "expected.txt"
        if not page_path.is_file() or not expected_path.is_file():
            continue
        pages.append(
            GoldenPage(
                name=child.name,
                page=page_path.read_bytes(),
                expected_text=expected_path.read_text(encoding="utf-8"),
            )
        )
    if not pages:
        raise EmptyGoldenSet
    return tuple(pages)


def evaluate(extractor: PageExtractor, pages: tuple[GoldenPage, ...]) -> None:
    """Fail when the set is empty or any page's returned text differs."""
    if not pages:
        raise EmptyGoldenSet
    misses: list[PageMiss] = []
    for golden in pages:
        returned = extractor.extract_page(golden.page)
        if returned != golden.expected_text:
            misses.append(
                PageMiss(
                    name=golden.name,
                    expected_text=golden.expected_text,
                    returned_text=returned,
                )
            )
    if misses:
        raise GoldenSetMiss(tuple(misses))
