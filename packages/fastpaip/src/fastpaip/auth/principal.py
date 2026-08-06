"""The identity a request is acting as."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Whoever is making this request, once their credential has been verified.

    Frozen: a request's identity is established once, at the edge, and nothing
    downstream may adjust it. A mutable principal is one an over-helpful service
    layer can promote.

    Attributes:
        id: Stable identifier. This is what resources are owned by, so it must
            outlive any individual credential — rotating a key must not orphan
            the sessions created with the old one.
        label: Human-readable, for logs and operator commands. Never used for
            access decisions; two principals may share a label.
    """

    id: str
    label: str
