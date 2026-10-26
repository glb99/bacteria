

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
    ).select_with_metadata("diagram", limit=1)

    assert len(pages) == 1
    assert pages[0].document_id == "doc"
    assert pages[0].page_index == 1
    assert pages[0].content == b"best-page"


def test_select_with_metadata_scores_a_page_by_its_closest_entity(tmp_path) -> None:
    closest = tmp_path / "closest.png"
    crowded = tmp_path / "crowded.png"
    closest.write_bytes(b"closest-page")
    crowded.write_bytes(b"crowded-page")
    moderate = [0.6, 0.8]
    entities = [
        StoredEntity("doc", 0, moderate, str(crowded)),
        StoredEntity("doc", 0, moderate, str(crowded)),
        StoredEntity("doc", 0, moderate, str(crowded)),
        StoredEntity("doc", 1, [1.0, 0.0], str(closest)),
        StoredEntity("doc", 1, moderate, str(closest)),
    ]

    pages = EmbeddingPageRetriever(
        embed=lambda text: [1.0, 0.0], entities=entities
    ).select_with_metadata("diagram", limit=1)

    assert len(pages) == 1
    assert pages[0].document_id == "doc"
    assert pages[0].page_index == 1
    assert pages[0].score == 1.0
    assert pages[0].content == b"closest-page"
