"""
Provides the structural components for the Chain of Responsibility pattern.

This module contains the `Handler` abstract base class, which defines the
stateful "link" in a chain, and the `StepHandler`, a concrete implementation
that executes a business logic step.
"""

from abc import ABC, abstractmethod
from typing import Generic
from .protocols import Processable, DataType


class Handler(Generic[DataType], ABC):
    """

    An abstract base class representing a single link in a Chain of Responsibility.

    Each handler holds a reference to the next handler in the chain and defines
    the contract for passing data down the chain. This class is stateful,
    as its primary role is to manage the structure of the pipeline.
    """

    _next_handler: "Handler[DataType] | None" = None

    def set_next(self, handler: "Handler[DataType]") -> "Handler[DataType]":
        """
        Sets the next handler in the chain.

        This method allows for fluent chaining of handlers.

        Args:
            handler: The next handler instance in the chain.

        Returns:
            The `handler` that was passed in, to allow for chaining calls
            (e.g., handler1.set_next(handler2).set_next(handler3)).
        """
        self._next_handler = handler
        return handler

    @abstractmethod
    def handle(self, data: DataType) -> DataType:
        """
        Handles the data and passes it to the next handler in the chain.

        Subclasses should implement their specific logic and then call
        super().handle() to ensure the data continues down the chain.

        Args:
            data: The data being passed through the pipeline.

        Returns:
            The data after it has been processed by the entire subsequent chain.
        """
        if self._next_handler:
            return self._next_handler.handle(data)
        return data


class StepHandler(Handler[DataType]):
    """
    A concrete `Handler` that executes a business logic step via a `Processable`.

    This class acts as a host for a `Processable` component (the processor),
    bridging the structural framework with the functional business logic.
    """

    def __init__(self, processor: Processable[DataType]):
        """
        Initializes the StepHandler with a specific processor.

        Args:
            processor: A component that fulfills the `Processable` protocol.
        """
        self._processor = processor

    def handle(self, data: DataType) -> DataType:
        """
        Executes the processor if it can handle the data, then passes to the next link.

        This implementation first checks `processor.can_handle()`. If true, it
        runs `processor.process()`. Regardless of the outcome, it then passes
        the data (original or processed) down the chain.

        Args:
            data: The data being passed through the pipeline.

        Returns:
            The data after it has been processed by this step and the rest of the chain.
        """
        processed_data = data
        if self._processor.can_handle(data):
            print(
                f"✅ Handler executing processor: {self._processor.__class__.__name__}"
            )
            processed_data = self._processor.process(data)
        else:
            print(
                f"➖ Handler skipping processor: {self._processor.__class__.__name__}"
            )

        return super().handle(processed_data)
