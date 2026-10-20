from dataclasses import dataclass
from typing import Protocol

from agent.errors import CredentialsError
from agent.model import _AUTH_HINTS
from google import genai
from pydantic import BaseModel
from sqlmodel import Field


@dataclass
class ModelResponse:
    text: str


class Box(BaseModel):
    """One diagram box. Edges are 0-1000 relative to the page."""

    label: str
    ymin: int = Field(
        description="Top edge, 0 at the top of the page, 1000 at the bottom.")
    xmin: int = Field(
        description="Left edge, 0 at the left, 1000 at the right.")
    ymax: int
    xmax: int


class Detections(BaseModel):
    boxes: list[Box]


ENTITY_PROMPT = (
    "Mark each diagram and each text block on this page. Return one box per region."
)


class SendsMultimodalContent(Protocol):
    async def send(
        self,
        page: bytes,
        prompt: str,
    ) -> Detections: ...


class GeminiMultimodalClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
        client: object | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            self.model = model
            self.max_retries = max_retries
            self.backoff_seconds = backoff_seconds
            return
        try:
            self._client = genai.Client(api_key=api_key)
        except ValueError as exc:
            # This SDK validates credentials eagerly and raises a bare
            # ValueError, where the Anthropic SDK defers to the first request.
            # Without this branch the failure never reaches send()'s handler
            # and escapes the error taxonomy entirely as a raw ValueError.
            if any(hint in str(exc).lower() for hint in _AUTH_HINTS):
                raise CredentialsError(str(exc)) from exc
            raise
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    async def send(
        self,
        page: bytes,
        prompt: str,
    ) -> Detections:
        """Send one single-page PDF and return the boxes on that page."""
        response = self._client.models.generate_content(
            model=self.model,
            contents=[
                genai.types.Part.from_bytes(data=page, mime_type="application/pdf"),
                prompt,
            ],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Detections,
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, Detections):
            return parsed
        return Detections.model_validate(parsed)


class ExtractEntities(Protocol):
    """Recognize the entities on one single-page PDF."""

    async def __call__(
        self,
        model_client: SendsMultimodalContent,
        page: bytes,
        prompt: str,
    ) -> Detections:
        """Return the boxes found on ``page``."""
        ...


async def extract_entities(
    model_client: SendsMultimodalContent,
    page: bytes,
    prompt: str,
) -> Detections:
    """Send one single-page PDF to the model and return its boxes."""
    return await model_client.send(page, prompt)
