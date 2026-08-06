"""The contracts features are written against, rather than against each other.

Structural, not nominal: a class satisfies anything here by having the methods.
There is no base class to inherit and nothing to register, so a repository backed
by SQLModel, by an HTTP call, or by a dict in a test are interchangeable without
any of them knowing this module exists.

The repository protocols are deliberately one method each. A repository declares
the two or three it actually offers and no more, so a caller needing only reads
cannot be handed something that also deletes.

Two things were here and were removed, because both undid that:

- ``CRUDRepository``, a composite of all four. Recombining them defeats the
  split in a single line, and most repositories genuinely do not want all four —
  bacteria's ``SessionStore`` is the sharp case, where an ``update`` method
  would be a second write path through a store whose entire design rests on
  having exactly one.
- ``Repository``, an empty base marker. Under structural typing a marker adds no
  constraint a checker can enforce and no capability a caller can rely on, so it
  reads as documentation while behaving as nothing.

Note what these protocols do *not* say: whether a method is a coroutine. A
synchronous implementation and an async one both satisfy them structurally, and
only the caller's ``await`` tells the difference. Pick one convention per
application and hold to it.
"""

from typing import Any, Optional, Protocol, TypeVar

DataType = TypeVar("DataType")
CreateModelType = TypeVar("CreateModelType")
IdType = TypeVar("IdType")


class CanRead(Protocol[DataType, IdType]):
    """Reads one entity by identity."""

    def get_by_id(self, id: IdType) -> Optional[DataType]:
        """Return the entity, or ``None`` when there is no such id.

        ``None`` rather than an exception: "not found" is an ordinary answer to
        a lookup. A caller that wants it to be exceptional can say so at the
        call site far more cheaply than one that wants the reverse.
        """
        ...


class CanCreate(Protocol[DataType, CreateModelType]):
    """Creates an entity from a payload that is not one yet.

    ``CreateModelType`` is separate from ``DataType`` deliberately: what a caller
    supplies has no identity, and what comes back does. Collapsing them means
    either inventing an id before the store assigns one, or making the id
    optional forever on a type that always has one after creation.
    """

    def create(self, data: CreateModelType) -> DataType:
        """Persist ``data`` and return the created entity, identity included."""
        ...


class CanUpdate(Protocol[DataType]):
    """Writes back an entity that already exists."""

    def update(self, entity: DataType) -> DataType:
        """Persist changes to ``entity`` and return the stored result."""
        ...


class CanDelete(Protocol[IdType]):
    """Removes an entity by identity."""

    def delete(self, id: IdType) -> None:
        """Remove the entity.

        Deleting an absent id is a no-op rather than an error: the caller wanted
        it gone, and it is.
        """
        ...


class Processable(Protocol[DataType]):
    """One step of business logic, plus whether it applies to this data.

    Implementations are hosted by :class:`fastpaip.core.handlers.StepHandler`,
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
