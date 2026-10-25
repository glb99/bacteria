

from app.agent.retriever import EmbeddingPageRetriever, StoredEntity


def test_select_returns_the_highest_scoring_page_image(tmp_path) -> None:
    best = tmp_path / "best.png"
    other = tmp_path / "other.png"
    best.write_bytes(b"best-page")
    other.write_bytes(b"other-page")
    entities = [
        StoredEntity("doc", 0, [1.0, 0.0], str(other)),
        StoredEntity("doc", 1, [0.0, 1.0], str(best)),
        StoredEntity("doc", 1, [0.0, 1.0], str(best)),
    ]

    pages = EmbeddingPageRetriever(
        embed=lambda text: [0.0, 1.0], entities=entities
    ).select("diagram", limit=1)

    assert pages == [b"best-page"]


def test_select_with_limit_zero_returns_nothing(tmp_path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"page")
    retriever = EmbeddingPageRetriever(
        embed=lambda text: [1.0],
        entities=[StoredEntity("doc", 0, [1.0], str(image))],
    )

    assert retriever.select("question", limit=0) == []


def test_select_skips_an_entity_with_no_page_image(tmp_path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"page")
    entities = [
        StoredEntity("doc", 0, [0.0, 1.0], ""),
        StoredEntity("doc", 1, [1.0, 0.0], str(image)),
    ]

    pages = EmbeddingPageRetriever(
        embed=lambda text: [0.0, 1.0], entities=entities
    ).select("diagram", limit=1)

    assert pages == [b"page"]


def test_select_with_metadata_returns_page_provenance_and_score(tmp_path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"page")
    retriever = EmbeddingPageRetriever(
        embed=lambda text: [0.0, 1.0],
        entities=[StoredEntity("document-1", 3, [0.0, 1.0], str(image))],
    )

    pages = retriever.select_with_metadata("diagram", limit=1)

    assert len(pages) == 1
    assert pages[0].document_id == "document-1"
    assert pages[0].page_index == 3
    assert pages[0].score == 1.0
    assert pages[0].content == b"page"
