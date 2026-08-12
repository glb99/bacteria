"""Generating and verifying API keys.

A key looks like ``fp_<key_id>_<secret>``. The two parts do different jobs and
that is the point: ``key_id`` is stored in the clear and indexed, so a lookup is
one row rather than a scan of every key in the table; ``secret`` is never
stored, only its hash.

**Why SHA-256 and not bcrypt or argon2.** Those exist to make *guessing* slow,
which matters for passwords because humans choose them from a small space. These
keys are 256 bits from ``secrets.token_urlsafe``; there is no dictionary to run
and no amount of slowness that helps. A slow hash here would only make every
authenticated request slower. This reasoning does not transfer to passwords —
if this application ever stores one, it needs a real password hash.

Not built:
    Expiry. A key is valid until explicitly revoked. Rotation is possible —
    issue a new key, revoke the old — but nothing forces or reminds. Expiry
    means a column and a check; the reason it is absent is that automatic expiry
    without a rotation story locks people out rather than making them safer.

    Scopes. Every key grants the same thing: proof of identity. There is no
    read-only key, no per-feature key, and no way to issue a narrow credential
    to a script. That is a real limitation the moment a third party gets a key.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

PREFIX = "fp"
_SEPARATOR = "_"


@dataclass(frozen=True)
class GeneratedKey:
    """A freshly issued key, in the only moment its secret exists in plaintext.

    Attributes:
        token: The full key. Shown to the operator once and never recoverable —
            the store keeps a hash. If it is lost, issue another.
        key_id: The public half, safe to log and to store as-is.
        secret_hash: What actually gets persisted.
    """

    token: str
    key_id: str
    secret_hash: str


def generate() -> GeneratedKey:
    """Mint a new key.

    ``token_urlsafe(32)`` is 256 bits from the OS CSPRNG. ``token_hex(8)`` is
    plenty for the id, which needs to be unique rather than unguessable.
    """
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return GeneratedKey(
        token=f"{PREFIX}{_SEPARATOR}{key_id}{_SEPARATOR}{secret}",
        key_id=key_id,
        secret_hash=hash_secret(secret),
    )


def hash_secret(secret: str) -> str:
    """Hash a key's secret half for storage."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def split(token: str) -> tuple[str, str] | None:
    """Parse a presented token into ``(key_id, secret)``.

    Returns:
        ``None`` for anything malformed. A caller must treat that exactly like a
        wrong key — reporting "malformed" separately tells an attacker which of
        their guesses had the right shape.
    """
    parts = token.split(_SEPARATOR, 2)
    if len(parts) != 3 or parts[0] != PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def matches(secret: str, expected_hash: str) -> bool:
    """Whether ``secret`` hashes to ``expected_hash``.

    ``compare_digest`` rather than ``==``. A plain comparison returns as soon as
    two bytes differ, so how long it takes leaks how much of the value was
    right, and that is enough to reconstruct a secret one byte at a time. The
    values here are hashes rather than the secret itself, which makes the attack
    far less useful — but "less useful" is not a reason to hand it over.
    """
    return hmac.compare_digest(hash_secret(secret), expected_hash)
