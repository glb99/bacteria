"""Render one single-page PDF as a PNG."""

from io import BytesIO

import pypdfium2 as pdfium


def render_page_image(page: bytes) -> bytes:
    """Return a PNG for a one-page PDF."""
    document = pdfium.PdfDocument(page)
    try:
        bitmap = document[0].render(scale=2)
        image = bitmap.to_pil()
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        document.close()
