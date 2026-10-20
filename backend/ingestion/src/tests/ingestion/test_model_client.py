import asyncio
from types import SimpleNamespace

from google.genai import types
from ingestion.entity_extractor import Detections, GeminiMultimodalClient


class _Models:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def generate_content(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(parsed={"boxes": []})


class _Client:
    def __init__(self) -> None:
        self.models = _Models()


def test_send_returns_parsed_detections() -> None:
    client = _Client()
    sender = GeminiMultimodalClient(client=client)

    found = asyncio.run(sender.send(b"%PDF", "boxes"))

    assert found == Detections(boxes=[])
    contents = client.models.kwargs["contents"]
    assert contents[0].inline_data.mime_type == "application/pdf"
    assert client.models.kwargs["config"].response_schema is Detections
    assert isinstance(contents[0], types.Part)
