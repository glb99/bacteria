"""
Defines the core, abstract interfaces (Protocols) for the shared framework.

This module contains the contracts that connect the framework's structural components
to the application's business logic and persistence layers. Using Protocols enables
a decoupled, pluggable architecture based on structural typing ("duck typing").
"""

from typing import Protocol, Any, TypeVar, Generic, Optional

# ==============================================================================
# 1. Generic Type Variables
# ==============================================================================
# These allow our protocols to be flexible and work with any data type.

DataType = TypeVar("DataType")
CreateModelType = TypeVar("CreateModelType")
IdType = TypeVar("IdType")


# ==============================================================================
# 2. Base Repository Protocol (Marker Interface)
# ==============================================================================
class Repository(Protocol):
    """A base marker protocol for all repository interfaces."""

    pass


# ==============================================================================
# 3. Granular, Composable Repository Protocols (Interface Segregation)
# ==============================================================================
# These small, single-method protocols define the most basic persistence behaviors.


class CanRead(Repository, Protocol[DataType, IdType]):
    """An interface for a repository that can read data."""

    def get_by_id(self, id: IdType) -> Optional[DataType]:
        """Retrieves an entity by its unique identifier."""
        ...


class CanCreate(Repository, Protocol[DataType, CreateModelType]):
    """An interface for a repository that can create data."""

    def create(self, data: CreateModelType) -> DataType:
        """Creates a new entity in the repository."""
        ...


class CanUpdate(Repository, Protocol[DataType]):
    """An interface for a repository that can update data."""

    def update(self, entity: DataType) -> DataType:
        """Updates an existing entity."""
        ...


class CanDelete(Repository, Protocol[IdType]):
    """An interface for a repository that can delete data."""

    def delete(self, id: IdType) -> None:
        """Deletes an entity by its unique identifier."""
        ...


# --- Composite Protocol for full CRUD functionality ---
class CRUDRepository(
    CanRead[DataType, IdType],
    CanCreate[DataType, CreateModelType],
    CanUpdate[DataType],
    CanDelete[IdType],
    Protocol,
):
    """A composite interface for a repository with full CRUD capabilities."""

    pass


# ==============================================================================
# 4. Protocol for Business Logic Components
# ==============================================================================


class Processable(Protocol[DataType]):
    """
    A protocol defining the contract for any business logic "processor".

    Any object that implements `can_handle` and `process` methods with matching
    signatures is considered a valid `Processable` component, allowing for
    flexible integration with the framework's handlers.
    """

    def can_handle(self, data: DataType) -> bool:
        """
        Determines if the component is capable of processing the given data.

        Args:
            data: The input data to be evaluated.

        Returns:
            True if the component can process the data, False otherwise.
        """
        ...

    def process(self, data: DataType) -> Any:
        """
        Executes the core business logic on the given data.

        Args:
            data: The input data to be processed.

        Returns:
            The result of the processing.
        """
        ...
