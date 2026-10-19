from typing import Protocol


class Embed(Protocol):

    def __call__(entity: bytes):
