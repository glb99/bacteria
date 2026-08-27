"""Keyed memory, backed by the assertion graph instead of by two tables.

The second implementation of :class:`~bacteria.app.chat.memory.MemoryStore`, and
the reason the port exists. Everything it needs was built by ADR 0008 — a
preference is a functional relation from the owner to a value node, so the
relation name *is* the key — and by ADR 0009, which gave the graph a way to be
told it is wrong. This adds a caller, not a mechanism.

**Whether a claim may be spoken is one column here, not two tables**, and that is
the trade ADR 0010 §5 records rather than hides. The agent's ADR 0017 rests on
*"reaches the model" being a question of which table a row is in* — a guarantee
you cannot forget. One log holding both proposals and memories cannot have it. So
the filter lives in exactly one function,
:func:`~bacteria.app.graph.service.preferences_for`, which is the only thing in
the system that reads assertions on behalf of a prompt, and
:func:`~bacteria.app.graph.service.proposals_from` is deliberately a separate
function rather than a flag on it.

Not built:
    A name. ``user_name`` is the one key the tables hold that this store cannot,
    because ADR 0007 §9 stopped the extractor emitting name-claims and a name is
    not a preference relation. The obvious repair — emit the owner node's label —
    is unsafe: a label has no ``origin``, so it would reach a prompt without
    passing the one filter that decides what may be spoken. What it wants is to
    be a *claim* in the shape ADR 0008 built, which is a change to that record
    rather than to this module.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from bacteria.agent.session.store import (
    OWNER,
    SESSION_SCOPE,
    USER_SCOPE,
    MemoryEntry,
    MemoryScope,
)
from bacteria.app.chat.memory import MemoryView
from bacteria.app.graph.catalogue import is_canonical
from bacteria.app.graph.catalogue import preferences as preference_relations
from bacteria.app.graph.log import Assertion
from bacteria.app.graph.repository import SqlGraphRepository
from bacteria.app.graph.service import (
    Preference,
    owner,
    preferences_for,
    proposals_from,
    refer_to,
    retract,
)
from bacteria.app.graph.temporal import OPEN_ENDED, Interval


class UnknownPreferenceError(KeyError):
    """A key the catalogue has no relation for.

    **The substantive difference between the two stores**, and it is refused
    rather than absorbed. A table takes any key; the graph takes the ones its
    vocabulary knows, because a claim under an unratified relation cannot be
    projected — no relation means no key means nothing to return. Writing it
    anyway would make ``remember`` a call that reports success and loses the
    fact, which is worse than a refusal a caller can see.

    That the vocabulary gates what may be remembered is ADR 0008's design rather
    than an accident: it is what stops the model making its own proposals
    speakable. The cost lands here, on a person naming a key nobody seeded.
    """

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _entry(preference: Preference) -> MemoryEntry:
    return MemoryEntry(
        value=preference.value,
        reason=preference.reason,
        source=preference.source,
        created_at=preference.recorded_at,
    )


class GraphMemoryStore:
    """Memory as a projection of the assertion log."""

    def __init__(self, db: Any) -> None:
        self._repository = SqlGraphRepository(db)
        self._db = db

    async def entries(self, session_id: str, user_id: str) -> MemoryView:
        """The three collections, from one log rather than three tables.

        Scope decides which of the two speakable collections a preference lands
        in, where the tables decide it by which table the row is in. That is the
        weaker arrangement and the one this store is here to be compared against.
        """
        spoken = await preferences_for(self._repository, user_id, session_id=session_id)
        proposed = await proposals_from(self._repository, user_id, session_id=session_id)

        return MemoryView(
            memory={p.key: _entry(p) for p in spoken if p.scope == "session"},
            user_memory={p.key: _entry(p) for p in spoken if p.scope == "user"},
            proposals={(p.source, p.key): _entry(p) for p in proposed},
        )

    async def remember(
        self,
        session_id: str,
        user_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str = OWNER,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry:
        """Record a preference the owner stated.

        ``origin="stated"``, which is what makes it speakable. Nothing else in
        the system writes that value: an extractor's claims are always
        ``inferred``, which is how *memory is written by the owner, not the
        model* survives a store where the model does most of the writing.
        """
        claim = await self._write(
            session_id, user_id, key, value, reason, source, scope, origin="stated"
        )
        await self._db.commit()
        return _memory_entry(value, reason, source, claim.recorded_at)

    async def propose(
        self,
        session_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        prompt_version: Optional[str] = None,
    ) -> None:
        """Suggest a preference. Reaches no prompt until somebody states it."""
        session = await self._session_owner(session_id)
        await self._write(
            session_id,
            session,
            key,
            value,
            reason,
            source,
            SESSION_SCOPE,
            origin="inferred",
            prompt_version=prompt_version,
        )
        await self._db.commit()

    async def activate(
        self,
        session_id: str,
        user_id: str,
        source: str,
        key: str,
        scope: MemoryScope = SESSION_SCOPE,
    ) -> MemoryEntry:
        """Ratify a proposal by **stating** it, which appends rather than moves.

        The proposal stays exactly where it was. Ratification is not a property
        of a claim that gets flipped — it is the owner making the claim, and the
        log records events. The two rows differ in ``origin``, which is why that
        field is in the repeat key while ``trust`` is not.

        Raises:
            KeyError: No such proposal, matching the table store rather than
                conjuring a memory from nothing.
        """
        proposed = await proposals_from(self._repository, user_id, session_id=session_id)
        match = next((p for p in proposed if p.key == key), None)
        if match is None:
            raise KeyError((source, key))

        claim = await self._write(
            session_id,
            user_id,
            key,
            match.value,
            match.reason,
            match.source,
            scope,
            origin="stated",
        )
        await self._db.commit()
        return _memory_entry(match.value, match.reason, match.source, claim.recorded_at)

    async def forget(
        self, session_id: str, user_id: str, key: str, scope: MemoryScope = SESSION_SCOPE
    ) -> None:
        """Stop believing the stated preference for a key."""
        await self._close(user_id, key, session_id=session_id, origin="stated")

    async def reject(self, session_id: str, source: str, key: str) -> None:
        """Discard a proposal, by retracting the claim that carried it."""
        session_owner = await self._session_owner(session_id)
        await self._close(session_owner, key, session_id=session_id, origin="inferred")

    async def _write(
        self,
        session_id: str,
        user_id: str,
        key: str,
        value: Any,
        reason: str,
        source: str,
        scope: MemoryScope,
        *,
        origin: str,
        prompt_version: Optional[str] = None,
    ) -> Assertion:
        if not is_canonical(key) or key not in {r.name for r in preference_relations()}:
            raise UnknownPreferenceError(key)

        now = datetime.now(timezone.utc)
        me = await owner(self._repository, user_id, now=now)
        # The value is a node whose label *is* the value -- ADR 0008's `value`
        # kind, and the reason a preference is a relation like any other rather
        # than a property table evidence could never cite.
        held = await refer_to(self._repository, user_id, "value", str(value), now=now)

        attrs: dict[str, Any] = {"reason": reason, "source": source}
        if prompt_version is not None:
            attrs["prompt_version"] = prompt_version

        claim = Assertion(
            assertion_id=_assertion_id(user_id, key, held.node_id, origin, now),
            user_id=user_id,
            src=me.node_id,
            rel=key,
            dst=held.node_id,
            # Open-ended: a preference is asserted to hold now, which is what
            # makes two of them collide rather than sit undecidable.
            valid=Interval(None, OPEN_ENDED),
            recorded_at=now,
            origin=origin,  # ty: ignore[invalid-argument-type]
            scope="user" if scope == USER_SCOPE else "session",
            trust="user" if origin == "stated" else "third-party",
            session_id=session_id,
            attrs=attrs,
        )
        await self._repository.record([claim])
        return claim

    async def _close(self, user_id: str, key: str, *, session_id: str, origin: str) -> None:
        now = datetime.now(timezone.utc)
        me = await owner(self._repository, user_id, now=now)
        for claim in await self._repository.current(user_id):
            if claim.rel != key or claim.src != me.node_id or claim.origin != origin:
                continue
            if claim.scope == "session" and claim.session_id != session_id:
                continue
            await retract(self._repository, claim, now=now)
        await self._db.commit()

    async def _session_owner(self, session_id: str) -> str:
        from bacteria.app.chat.models import ChatSession

        row = await self._db.get(ChatSession, session_id)
        if row is None:
            raise KeyError(session_id)
        return str(row.user_id)


def _memory_entry(value: Any, reason: str, source: str, at: datetime) -> MemoryEntry:
    return MemoryEntry(value=value, reason=reason, source=source, created_at=at)


def _assertion_id(user_id: str, key: str, value_id: str, origin: str, now: datetime) -> str:
    import hashlib

    material = f"{user_id}\x00{key}\x00{value_id}\x00{origin}\x00{now.isoformat()}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]
