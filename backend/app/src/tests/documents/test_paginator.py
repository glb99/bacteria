from collections.abc import Iterator
from io import BytesIO

from ingestion.paginator import Paginate, paginate
from pypdf import PdfReader, PdfWriter


def _pdf_with_page_widths(*widths: float) -> bytes:
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=72)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _width(page: bytes) -> float:
    reader = PdfReader(BytesIO(page))
    box = reader.pages[0].mediabox
    return float(box.width)


def test_paginate_yields_one_single_page_pdf_per_page() -> None:
    pages = list(paginate(_pdf_with_page_widths(72, 144)))

    assert len(pages) == 2
    assert [_width(page) for page in pages] == [72.0, 144.0]
    assert all(len(PdfReader(BytesIO(page)).pages) == 1 for page in pages)


def test_paginate_is_an_iterator() -> None:
    result = paginate(_pdf_with_page_widths(72))

    assert isinstance(result, Iterator)
    assert len(PdfReader(BytesIO(next(result))).pages) == 1


def test_paginate_satisfies_the_protocol() -> None:
    split: Paginate = paginate

    assert len(list(split(_pdf_with_page_widths(72)))) == 1
