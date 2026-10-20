"""Embed one recognized entity."""

from typing import Any, Protocol

from agent.errors import CredentialsError
from agent.model import _AUTH_HINTS
from google import genai


class Embed(Protocol):
    """Return one vector for the UTF-8 text of one entity."""

    def __call__(self, entity: bytes) -> list[float]:
        """Embed ``entity``, which is UTF-8 text."""
        ...


class GeminiEmbedder:
    """Embeds entity text with a Gemini embedding model.

    ``entity`` is the UTF-8 text of one recognized entity. A diagram with no
    text has nothing to embed here.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-embedding-001",
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            try:
                self._client = genai.Client(api_key=api_key)
            except ValueError as exc:
                if any(hint in str(exc).lower() for hint in _AUTH_HINTS):
                    raise CredentialsError(str(exc)) from exc
                raise
        self.model = model

    def __call__(self, entity: bytes) -> list[float]:
        response = self._client.models.embed_content(
            model=self.model,
            contents=entity.decode("utf-8"),
        )
        return list(response.embeddings[0].values)
