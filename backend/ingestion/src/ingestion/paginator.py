"""Split one stored PDF into single-page PDFs."""

from collections.abc import Iterator
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader, PdfWriter


class Paginate(Protocol):
    """Yield each page of a PDF as the bytes of a one-page PDF."""

    def __call__(self, doc: bytes) -> Iterator[bytes]:
        """Yield one single-page PDF per page, in page order."""
        ...


def paginate(doc: bytes) -> Iterator[bytes]:
    """Yield each page of ``doc`` as its own single-page PDF."""
    reader = PdfReader(BytesIO(doc))
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        buffer = BytesIO()
        writer.write(buffer)
        yield buffer.getvalue()
