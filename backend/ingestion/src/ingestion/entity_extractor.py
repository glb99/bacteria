from dataclasses import dataclass
from pathlib import Path
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
    """One diagram box. Edges are 0-1000 relative to the image."""

    label: str
    ymin: int = Field(
        description="Top edge, 0 at the top of the image, 1000 at the bottom.")
    xmin: int = Field(
        description="Left edge, 0 at the left, 1000 at the right.")
    ymax: int
    xmax: int


class Detections(BaseModel):
    boxes: list[Box]


class SendsMultimodalContent(Protocol):
    async def send(
        self,
        image: bytes,
        prompt: str,
    ) -> Detections: ...


def load_image_as_bytes(path: Path) -> bytes:
    return path.read_bytes()


class GeminiMultimodalClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash",
        max_retries: int = 2,
        backoff_seconds: float = 1.0,
    ) -> None:
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
        image: bytes,
        prompt: str,
    ) -> Detections:
        """
        Sends the image and prompt to the Gemini model and returns the extracted boxes.

        Args:
            image (bytes): The image data in bytes.
            prompt (str): The prompt to guide the model's response.
        """
        response = self._client.models.generate_content(
            model=self.model,
            contents=[
                genai.types.Part.from_bytes(data=image, mime_type="image/png"),
                prompt,
            ],
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Detections,
            ),
        )
        return response.output[0].content


class ExtractEntities(Protocol):
    """A protocol for a function that formats text."""

    def __call__(self, model_client: SendsMultimodalContent, image_path: Path, prompt: str) -> str:
        ...


def extract_entities(model_client: SendsMultimodalContent, image_path: Path, prompt: str) -> Detections:
    """
    Extracts entities from the given image using a simple rule-based approach.

    Args:
        image_path (Path): The path to the image from which to extract entities.
        prompt (str): The prompt to guide the model's response.

    Returns:
        Detections: A list of extracted entities.
    """
    image_bytes = load_image_as_bytes(image_path)
    return model_client.send(image_bytes, prompt)
