from agent.model import GeminiClient
from google.genai import types


def test_image_block_becomes_an_image_part() -> None:
    content = GeminiClient._to_content(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What does the diagram show?"},
                {"type": "image", "media_type": "image/png", "data": b"page-png"},
            ],
        },
        {},
    )

    assert content.role == "user"
    assert content.parts[0].text == "What does the diagram show?"
    assert isinstance(content.parts[1], types.Part)
    assert content.parts[1].inline_data.mime_type == "image/png"
    assert content.parts[1].inline_data.data == b"page-png"
