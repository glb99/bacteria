from io import BytesIO

from ingestion.page_image import render_page_image
from pypdf import PdfWriter


def test_render_page_image_returns_a_png() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = BytesIO()
    writer.write(buffer)

    image = render_page_image(buffer.getvalue())

    assert image.startswith(b"\x89PNG")
