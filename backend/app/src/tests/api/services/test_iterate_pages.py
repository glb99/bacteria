from app.api.services.document_service import iterate_pages


def test_iterate_pages_yields_pages_in_order() -> None:
    def paginate(doc: bytes):
        assert doc == b"stored-pdf"
        yield b"page-1"
        yield b"page-2"

    assert list(iterate_pages(paginate, b"stored-pdf")) == [b"page-1", b"page-2"]


def test_iterate_pages_pulls_one_page_at_a_time() -> None:
    pulled: list[str] = []

    def paginate(doc: bytes):
        assert doc == b"stored-pdf"
        pulled.append("first")
        yield b"one"
        pulled.append("second")
        yield b"two"

    pages = iterate_pages(paginate, b"stored-pdf")

    assert pulled == []
    assert next(pages) == b"one"
    assert pulled == ["first"]
    assert next(pages) == b"two"
    assert pulled == ["first", "second"]
