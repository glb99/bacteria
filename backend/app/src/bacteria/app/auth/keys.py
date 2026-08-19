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
"""The prefix on an API key, minted by the operator CLI and never expiring."""

SESSION_PREFIX = "bs"
"""The prefix on a browser session token, exchanged for a key and expiring.

Separate from :data:`PREFIX` so that :func:`split` rejects a credential of the
wrong kind outright -- a session token presented as ``Authorization: Bearer``
parses to ``None`` and is refused by the same path as any malformed value.

**This is a second line, not the mechanism**, and the distinction was learned by
deleting the prefix check and finding every test still green. What actually
keeps the two apart is that they are two tables: a session id looked up in
``api_key`` is simply not there. The prefix makes that failure happen one step
earlier, with a log line that says which mistake was made rather than "unknown
key id" -- and it is what would still hold if the two id spaces ever collided,
since both are :func:`secrets.token_hex` over the same width.

Tested directly in `test_auth.py` for that reason. Routed through HTTP it is
unfalsifiable: the tables refuse first either way.
"""

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


def generate(prefix: str = PREFIX) -> GeneratedKey:
    """Mint a new credential.

    ``token_urlsafe(32)`` is 256 bits from the OS CSPRNG. ``token_hex(8)`` is
    plenty for the id, which needs to be unique rather than unguessable.

    Args:
        prefix: Which kind of credential. Defaults to an API key;
            :data:`SESSION_PREFIX` mints a browser session token.

            Parameterised rather than copied into a second module, so that both
            credentials get the same entropy, the same hash, and the same
            constant-time comparison. A session token is weaker than a key by
            *lifetime*, which is a column, and must not also be weaker by
            construction.
    """
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    return GeneratedKey(
        token=f"{prefix}{_SEPARATOR}{key_id}{_SEPARATOR}{secret}",
        key_id=key_id,
        secret_hash=hash_secret(secret),
    )


def hash_secret(secret: str) -> str:
    """Hash a key's secret half for storage."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def split(token: str, prefix: str = PREFIX) -> tuple[str, str] | None:
    """Parse a presented token of the given kind into ``(key_id, secret)``.

    Args:
        token: Whatever the client sent.
        prefix: The kind of credential this call is willing to accept. A token
            of the *other* kind returns ``None`` here, which is what stops a
            session cookie from working as a bearer key and back again.

    Returns:
        ``None`` for anything malformed, including a well-formed credential of
        the wrong kind. A caller must treat that exactly like a wrong key —
        reporting "malformed" separately tells an attacker which of their
        guesses had the right shape.
    """
    parts = token.split(_SEPARATOR, 2)
    if len(parts) != 3 or parts[0] != prefix or not parts[1] or not parts[2]:
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
