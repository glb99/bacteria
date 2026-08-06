"""
Provides adapter classes to bridge different interfaces within the framework.

This module is central to connecting the functional-style business logic with
the object-oriented structure of the handlers, following the Adapter design pattern.
"""

from dataclasses import dataclass
from typing import Callable, Any, Generic
from .protocols import DataType


@dataclass
class FunctionalProcessor(Generic[DataType]):
    """
    An adapter that makes standalone functions compatible with the `Processable` protocol.

    This dataclass acts as a bridge, taking pure `can_handle` and `process`
    functions and wrapping them in a single object that the `StepHandler`
    can work with. This allows the core business logic to remain fully decoupled
    from the framework.
    """

    can_handle: Callable[[DataType], bool]
    process: Callable[[DataType], Any]
