from dotenv import load_dotenv

from app.cli.cli import build_document_retriever


def test_retriever_retrieves_correct_page() -> None:
    load_dotenv()
    document_retriever = build_document_retriever()

    retrieved_pages = document_retriever.select_with_metadata(
        query="what Scaled Dot-Product Attention is?", limit=1
    )

    assert retrieved_pages
    assert retrieved_pages[0].page_index == 3
