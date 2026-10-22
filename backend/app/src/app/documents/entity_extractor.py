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


class SendsForDetections(Protocol):
    async def send(
        self,
        page: bytes,
        prompt: str,
    ) -> Detections: ...


class ExtractEntities(Protocol):
    """Recognize the entities on one single-page PDF."""

    async def __call__(
        self,
        model_client: SendsForDetections,
        page: bytes,
        prompt: str,
    ) -> Detections:
        """Return the boxes found on ``page``."""
        ...


async def extract_entities(
    model_client: SendsForDetections,
    page: bytes,
    prompt: str,
) -> Detections:
    """Send one single-page PDF to the model and return its boxes."""
    return await model_client.send(page, prompt)
