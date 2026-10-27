from dotenv import find_dotenv, load_dotenv

from app.agent.retriever import EmbeddingPageRetriever, StoredEntity
from app.composition import build_gemini_embedder


def test_retriever_retrieves_correct_page(stored_entities: list[StoredEntity]) -> None:
    load_dotenv(find_dotenv(usecwd=True))
    document_retriever = EmbeddingPageRetriever(
        embed=build_gemini_embedder(),
        entities=stored_entities,
    )

    retrieved_pages = document_retriever.select_with_metadata(
        query="what Scaled Dot-Product Attention is?", limit=1
    )

    assert retrieved_pages
    assert retrieved_pages[0].page_index == 3
