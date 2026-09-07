from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


TranscriptItemKind = Literal["message", "tool_call", "run_error", "run_meta"]
"""The kinds of event a transcript can hold, and the payload each carries.

- ``message`` — ``{"role": "user" | "assistant", "text": str}``
- ``tool_call`` — ``{"name": str, "input": dict, "status": "executed" | "failed"}``
  plus ``"output"`` when executed, or ``"error"`` when failed. One item covers
  the whole attempt: a separate ``tool_result`` kind would let a call exist in
  the record with no visible outcome, which is the exact gap the item is here
  to close.
- ``run_error`` — ``{"error": str}``. A run that failed part-way, recorded so
  the failure leaves evidence rather than only an exception.
- ``run_meta`` — how the run was configured, not what it said: ``{"model":
  str | None, "tools_exposed": list[str], "messages_in_context": int,
  "memories_in_context": int, "tool_calls_proposed": int, "outcome":
  "completed" | "failed"}``. Exactly one per run, appended last.

  This is the only item that describes the run rather than belonging to the
  conversation, which is what makes a transcript reconstructable instead of
  merely readable: two runs producing identical text may have been shown
  different memories, offered different tools, or answered by different
  models, and without this nothing distinguishes them. See
  [ADR 0019](../../docs/adr/0019-a-run-records-how-it-was-configured.md).

Kept as a closed ``Literal`` so that adding a kind is a typed change that
surfaces every reader needing to handle it.
"""


@dataclass(frozen=True)
class Session:
    """Identity of one conversation.

    ``session_id`` is generated here and never derived from ``user_id``: one
    user holds many sessions, and knowing who someone is says nothing about
    which of their conversations an event belongs to. Keeping the two separate
    also keeps identity from drifting into an implicit authorization check —
    "this session exists" must never come to mean "this action is allowed".
    """

    session_id: str
    user_id: str
    created_at: datetime


@dataclass(frozen=True)
class TranscriptItem:
    """One immutable entry in the durable record.

    Frozen because the transcript is append-only: correcting history means
    appending a correction, not editing what was already recorded.

    Attributes:
        run_id: Which run wrote this, or ``None``. A field rather than a
            ``payload`` key because ``payload`` differs per ``kind`` and this
            does not, and because "everything from run X" should be an index
            scan rather than a reach into JSON.

            Optional because not every write is a run — a working-state-only
            commit is not one, and rows written before the field existed have
            no run to name. Neither gets a fabricated id. What that costs is
            that a producer forgetting to set it fails silently, so the
            runtime's obligation to stamp every item it commits is asserted by
            a test rather than by this type. See
            [ADR 0018](../../docs/adr/0018-transcript-items-carry-their-run-id.md).
    """

    kind: TranscriptItemKind
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str | None = None


MemoryScope = Literal["session", "user"]
"""How far a memory reaches.

``session`` lasts as long as the conversation. ``user`` outlives it and is
visible in every session that person opens, which is what makes memory more than
a slower way of reading the transcript.

A closed ``Literal`` rather than a free string: a typo'd scope would otherwise
create a third, silent category that nothing renders and nothing can delete. See
[ADR 0021](../../docs/adr/0021-memory-is-scoped-to-a-session-or-a-user.md).
"""

SESSION_SCOPE: MemoryScope = "session"
USER_SCOPE: MemoryScope = "user"

OWNER = "owner"
"""The source of a memory written by the person who owns the session.

Their writes are active immediately, because the human confirmation every other
source has to wait for *is* them ([ADR 0017](../../docs/adr/0017-memory-is-proposed-and-confirmed.md)).
"""


@dataclass(frozen=True)
class MemoryEntry:
    """One preserved fact, or one proposal that it should become preserved.

    ``reason`` is required, not optional. A memory with no recorded reason
    cannot be reviewed later — there is no way to judge whether it is still
    worth keeping, so it is kept forever by default. Requiring provenance at
    write time is what makes expiry a decision someone can actually make.

    ``source`` says who proposed it — :data:`OWNER`, a model, or a named job.
    It survives activation rather than being discarded once the entry is live,
    because "the extractor has been noisy" is a question someone will ask and
    an activated memory that forgot where it came from cannot answer it.

    There is deliberately no ``status`` field. Whether an entry is proposed or
    active is expressed by *which collection it is in* on
    :class:`SessionState`, not by an attribute that could disagree with its
    container. ADR 0017 as drafted named a status field; making the two
    collections key differently is what forced the change, and the redundancy
    it removes is the kind this package treats as a defect.
    """

    value: Any
    reason: str
    source: str = OWNER
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    """Everything the store holds for one session.

    Mutable, unlike the items inside it, because ``commit`` mutates it in
    place. Callers never receive this object — only deep copies of it.

    ``memory`` and ``proposals`` are separate collections with *different keys*,
    and that difference is the whole mechanism of ADR 0017:

    - ``memory`` is keyed by ``key`` alone. At most one active fact may claim a
      key, which is what keeps the model's view unambiguous.
    - ``proposals`` is keyed by ``(source, key)``. Two proposers may both
      suggest ``tone`` and both survive, because collapsing them is a judgement
      only a human can make — the same rule the ingestion pipeline applies to
      duplicate records, and for the same reason.

    Only ``memory`` reaches a model. A proposal is inert until something
    activates it.

    ``user_memory`` is the same idea one scope out: entries belonging to the
    person rather than to this conversation, carried into every session they
    open. Kept as a separate collection for the reason above — which collection
    an entry is in *is* its scope, where an attribute could disagree with the
    container holding it. Both are keyed by ``key``, but keyed within different
    things, and a single dict would erase exactly that.

    Assembly merges the two with session winning on a shared key; see
    :func:`~bacteria.agent.context.assembly.assemble_context`.
    """

    session: Session
    transcript: list[TranscriptItem] = field(default_factory=list)
    working_state: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, MemoryEntry] = field(default_factory=dict)
    user_memory: dict[str, MemoryEntry] = field(default_factory=dict)
    proposals: dict[tuple[str, str], MemoryEntry] = field(default_factory=dict)
