"""The contracts features are written against, rather than against each other.

Structural, not nominal: a class satisfies anything here by having the methods.
There is no base class to inherit and nothing to register, so a processor backed
by a pure function, by an HTTP call, or by a dict in a test are interchangeable
without any of them knowing this module exists.

**The four CRUD repository protocols were here and are gone, and that is the
finding rather than a tidy-up.** ``CanRead``, ``CanCreate``, ``CanUpdate`` and
``CanDelete`` were one method each, segregated so that a caller needing only
reads could not be handed something that also deletes -- which is a good rule
and was still the wrong shape here. Every repository this application actually
grew declined it:

- ``ApiKeyRepository`` has ``get_by_key_id``, a three-argument ``create``, and
  ``revoke`` rather than ``delete`` -- because revocation is a timestamp, so
  that "this key was valid until Tuesday" stays answerable.
- ``SqlSessionRepository`` has ``create_session`` / ``get_state`` / ``commit`` /
  ``remember`` / ``forget``, and no ``update`` at all: an update method is a
  second write path through a store whose entire design rests on having exactly
  one. `bacteria.agent.session.protocol` argues this at length and is the
  protocol that has two implementations and fifty conformance tests.
- ``IngestionRepository`` has ``persist``.

So they had exactly one implementer ever -- a ``UserRepository`` that came from
the project template, that no router ever mounted, and that was deleted with the
``user`` table in migration ``a3f81c60b204``. Nothing was ever *written against*
them either: no signature anywhere annotated one. That is the line worth keeping,
because it is what separates a seam from a shape nobody chose --
``SessionRepository`` had no implementation for a while too, and was real the
whole time, because ``Runtime`` was written against it.

Two earlier removals made the same point one step less far, and are worth
keeping for the same reason:

- ``CRUDRepository``, a composite of all four. Recombining them defeats the
  split in a single line.
- ``Repository``, an empty base marker. Under structural typing a marker adds no
  constraint a checker can enforce and no capability a caller can rely on, so it
  reads as documentation while behaving as nothing.

Note what the protocol below does *not* say: whether a method is a coroutine. A
synchronous implementation and an async one both satisfy it structurally, and
only the caller's ``await`` tells the difference. Pick one convention per
application and hold to it.
"""

from typing import Any, Protocol, TypeVar

DataType = TypeVar("DataType")


class Processable(Protocol[DataType]):
    """One step of business logic, plus whether it applies to this data.

    Implementations are hosted by :class:`bacteria.app.core.handlers.StepHandler`,
    which is what links them into a chain. Separating the question ("does this
    apply?") from the work ("do it") is what lets a pipeline be assembled from
    steps that know nothing about which other steps exist.

    Either method may be written synchronously or as a coroutine. The handler
    awaits a coroutine and runs a plain function in a worker thread, so a pure
    transformation stays a plain function and a step that touches a database
    does not have to pretend it does not.

    Known limitation, worth understanding before depending on it: ``can_handle``
    returns a bare ``bool``, so a step that declines cannot say *why*. The
    handler logs that a skip happened and which processor skipped, which is
    enough to see it and not enough to explain it. Carrying the reason means
    returning something richer than a bool from every processor — a change worth
    making deliberately rather than discovering halfway through an incident.
    """

    def can_handle(self, data: DataType) -> bool:
        """Whether this step applies to ``data``. Must not mutate anything."""
        ...

    def process(self, data: DataType) -> Any:
        """Do the work, and return what should be passed onward."""
        ...
