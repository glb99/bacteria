import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ingestion.embedder import Embed


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


@dataclass(frozen=True)
class StoredEntity:
    """One recognized region and the page image file that holds it."""

    document_id: str
    page_index: int
    vector: list[float]
    image_path: str


class EmbeddingPageRetriever:
    """Score stored entities against the question and return the page images.

    Entity scores on the same page are added. ``limit`` is the most pages
    returned. Zero returns none.
    """

    # TODO: I don't like having o import Embed from Ingestion package
    def __init__(self, embed: Embed, entities: list[StoredEntity]) -> None:
        self._embed = embed
        self._entities = entities

    def select(self, query: str, limit: int) -> list[bytes]:
        if limit <= 0 or not self._entities:
            return []
        query_vector = self._embed(query.encode())
        scores: dict[tuple[str, int], float] = {}
        paths: dict[tuple[str, int], str] = {}
        for entity in self._entities:
            key = (entity.document_id, entity.page_index)
            scores[key] = scores.get(key, 0.0) + \
                _cosine(query_vector, entity.vector)
            paths[key] = entity.image_path
        ranked = sorted(scores, key=lambda key: (-scores[key], key))
        pages: list[bytes] = []
        for key in ranked:
            if len(pages) == limit:
                break
            image_path = paths[key]
            if not image_path:
                continue
            image_file = Path(image_path)
            if not image_file.is_file():
                continue
            image = image_file.read_bytes()
            if image:
                pages.append(image)
        return pages


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return product / (left_norm * right_norm)
