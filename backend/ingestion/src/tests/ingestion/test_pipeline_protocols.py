import asyncio
from dataclasses import dataclass

from ingestion.embedder import Embed, GeminiEmbedder
from ingestion.entity_extractor import Detections, ExtractEntities, extract_entities


@dataclass
class _Sent:
    page: bytes
    prompt: str


class _RecordsPage:
    def __init__(self) -> None:
        self.sent: _Sent | None = None

    async def send(self, page: bytes, prompt: str) -> Detections:
        self.sent = _Sent(page=page, prompt=prompt)
        return Detections(boxes=[])


class _Embedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _EmbedResponse:
    def __init__(self, values: list[float]) -> None:
        self.embeddings = [_Embedding(values)]


class _Models:
    def __init__(self) -> None:
        self.model: str | None = None
        self.contents: str | None = None

    def embed_content(self, model: str, contents: str) -> _EmbedResponse:
        self.model = model
        self.contents = contents
        return _EmbedResponse([0.25, 0.5])


class _Client:
    def __init__(self) -> None:
        self.models = _Models()


def test_extract_entities_sends_the_page_bytes() -> None:
    client = _RecordsPage()

    found = asyncio.run(extract_entities(client, b"%PDF-1", "boxes"))

    assert found.boxes == []
    assert client.sent == _Sent(page=b"%PDF-1", prompt="boxes")


def test_extract_entities_satisfies_the_protocol() -> None:
    recognize: ExtractEntities = extract_entities

    assert recognize is extract_entities


def test_embedder_sends_the_entity_text() -> None:
    client = _Client()
    embedder = GeminiEmbedder(client=client)

    vector = embedder(b"diagram label")

    assert vector == [0.25, 0.5]
    assert client.models.model == "gemini-embedding-001"
    assert client.models.contents == "diagram label"


def test_embedder_satisfies_the_protocol() -> None:
    embed: Embed = GeminiEmbedder(client=_Client())

    assert embed(b"a") == [0.25, 0.5]
