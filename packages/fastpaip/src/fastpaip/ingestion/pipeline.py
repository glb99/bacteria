"""The ingestion pipeline: what the steps are, and what flows between them.

Each step is a pure function pair — ``can_handle`` and ``process`` — wrapped by
:class:`~fastpaip.core.adapters.FunctionalProcessor` and hosted by a
:class:`~fastpaip.core.handlers.StepHandler`. None of them import each other or
know the order; :func:`build_pipeline` is the only place the order exists.

The unit flowing through is a whole :class:`Batch`, not one record. Per-record
chaining reads more elegantly and is wrong here: persisting would then be one
write per record, and a step could not say "nothing valid survived, skip me" —
which is exactly what ``can_handle`` is for.

:class:`Batch` is mutated in place and also returned. Returning it is what the
handler contract expects; mutating it is what keeps a rejection recorded even if
a later step raises, so a partial failure still explains itself.
"""

from dataclasses import dataclass, field
from typing import Any

from fastpaip.core.adapters import FunctionalProcessor
from fastpaip.core.handlers import Handler, StepHandler

REQUIRED_FIELDS = ("external_id", "name")


@dataclass(frozen=True)
class Rejection:
    """One record that will not be stored, and why."""

    payload: dict[str, Any]
    reason: str


@dataclass
class Batch:
    """One submission as it moves through the pipeline.

    Attributes:
        source: Where these records came from. Recorded rather than inferred,
            because "which upload produced this row" is the first question asked
            when one looks wrong.
        raw: What arrived, untouched. Kept after validation so a rejection can
            quote the original rather than a half-normalized version of it.
        accepted: Records that passed, as they will be stored.
        rejected: Records that did not, each with a reason.
        batch_id: Set by the persist step. ``None`` until then.
    """

    source: str
    raw: list[dict[str, Any]]
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    batch_id: int | None = None


def _is_blank(value: Any) -> bool:
    """Whether a required field is effectively absent.

    ``None`` is checked before stringifying, and that is the whole reason this
    is a function. ``str(None)`` is ``"None"`` — five non-blank characters — so
    a JSON ``null`` id used to pass validation and be stored under the literal
    id ``"None"``, where two of them would then collide with each other and
    with any record genuinely named that.

    Not ``not value``: ``0`` is a perfectly good external id, and a falsy check
    would reject it. Only absent, null, and whitespace count as blank.

    Everything else is coerced, and that stays deliberately loose: an integer id
    becomes its digits, which is what a caller means. The cost is that nonsense
    types are coerced too — ``False`` becomes the id ``"False"`` — so this
    validates presence rather than type. Restricting to str and int would catch
    that, and would also reject a UUID object or anything else with a sensible
    ``__str__``, which is why it has not been done.
    """
    return value is None or not str(value).strip()


def _validate(batch: Batch) -> Batch:
    """Partition raw records into accepted and rejected.

    Every record ends up in exactly one of the two lists. That total is what
    lets a caller reconcile what it sent against what happened, and it is the
    property most easily lost by a `continue` in the wrong place.
    """
    seen: set[str] = set()
    for record in batch.raw:
        missing = [f for f in REQUIRED_FIELDS if _is_blank(record.get(f))]
        if missing:
            batch.rejected.append(
                Rejection(payload=record, reason=f"missing required field(s): {', '.join(missing)}")
            )
            continue

        external_id = str(record["external_id"]).strip()
        if external_id in seen:
            # Within-batch duplicates only. A record already in the database
            # from an earlier batch is not this step's business — deciding
            # between "update" and "reject" is a policy question, and the
            # honest answer today is that neither has been chosen.
            batch.rejected.append(
                Rejection(payload=record, reason=f"duplicate external_id in batch: {external_id}")
            )
            continue

        seen.add(external_id)
        batch.accepted.append(record)
    return batch


def _normalize(batch: Batch) -> Batch:
    """Clean accepted records into the shape that gets stored.

    Only the two required fields are touched, and that limit is deliberate.
    Every other key is passed through exactly as it arrived, because this
    pipeline does not know what a record represents and should not act as
    though it does.

    An earlier version also lowercased ``email``. It was removed: it was the one
    domain assumption in a module built to have none, and it was inherited from
    a leftover ``UserCreate`` model rather than chosen. It was also worse than
    doing nothing — a caller whose field is ``contact_email`` or ``work_email``
    got no normalization at all, so the behaviour was inconsistent rather than
    merely absent, and no rule could be stated about which fields were cleaned.
    If per-field rules are wanted later, they belong in an argument to
    :func:`build_pipeline`, supplied by whoever knows the domain.

    Runs after validation, never before: normalizing first would mean a
    rejection quotes a record the caller never sent, which makes the reason
    harder to act on than no reason at all.
    """
    batch.accepted = [
        {
            **record,
            "external_id": str(record["external_id"]).strip(),
            "name": str(record["name"]).strip(),
        }
        for record in batch.accepted
    ]
    return batch


def build_pipeline(persist) -> Handler[Batch]:
    """Assemble the chain and return its head.

    The one place the order of steps exists. ``persist`` is passed in rather
    than imported so that this module needs no database — the pipeline's logic
    can be exercised, and read, without one.

    Args:
        persist: Called with a batch that has anything worth recording —
            accepted records, rejections, or both — and expected to set
            ``batch_id``. Skipped only when a batch is entirely empty, which is
            why it is a step with a ``can_handle`` rather than an ``if`` at the
            end of this function.
    """
    validate = StepHandler(
        FunctionalProcessor(can_handle=lambda batch: bool(batch.raw), process=_validate)
    )
    normalize = StepHandler(
        FunctionalProcessor(can_handle=lambda batch: bool(batch.accepted), process=_normalize)
    )
    persist_step = StepHandler(
        FunctionalProcessor(
            # Rejections count as something to store, not just acceptances. A
            # batch where nothing passed validation is exactly the one whose
            # evidence matters most, and gating this on `accepted` alone threw
            # it away -- reporting the reasons in the response and keeping none
            # of them.
            can_handle=lambda batch: bool(batch.accepted or batch.rejected),
            process=persist,
        )
    )

    validate.set_next(normalize).set_next(persist_step)
    return validate
