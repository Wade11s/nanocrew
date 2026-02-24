"""Lightweight async event bus for in-process communication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

from loguru import logger

T = TypeVar("T")


@dataclass
class Event(Generic[T]):
    """Event data structure."""

    name: str
    data: T


Handler = Callable[[Event[T]], Awaitable[None]]


class EventBus:
    """Lightweight in-memory event bus with async handler support.

    Features:
    - Parallel handler execution (handlers don't block each other)
    - Error isolation (one handler failure doesn't affect others)
    - Subscribe/unsubscribe lifecycle management
    - Zero external dependencies
    """

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._subscribers: dict[str, list[Handler]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, event_name: str, handler: Handler) -> None:
        """Subscribe a handler to an event.

        Args:
            event_name: The event to subscribe to
            handler: Async callback that receives the event
        """
        async with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            self._subscribers[event_name].append(handler)
            logger.debug(f"EventBus: Handler subscribed to '{event_name}'")

    async def unsubscribe(self, event_name: str, handler: Handler) -> None:
        """Unsubscribe a handler from an event.

        Args:
            event_name: The event to unsubscribe from
            handler: The handler to remove
        """
        async with self._lock:
            if event_name in self._subscribers:
                self._subscribers[event_name] = [
                    h for h in self._subscribers[event_name] if h != handler
                ]
                if not self._subscribers[event_name]:
                    del self._subscribers[event_name]
            logger.debug(f"EventBus: Handler unsubscribed from '{event_name}'")

    async def publish(self, event: Event[Any]) -> None:
        """Publish an event to all subscribers.

        Handlers are executed in parallel. Exceptions in one handler
        don't affect other handlers.

        Args:
            event: The event to publish
        """
        handlers: list[Handler] = []
        async with self._lock:
            handlers = self._subscribers.get(event.name, []).copy()

        if not handlers:
            return

        # Execute all handlers in parallel with error isolation
        results = await asyncio.gather(
            *[self._safe_call(handler, event) for handler in handlers],
            return_exceptions=True,
        )

        # Log any failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                handler_name = getattr(handlers[i], "__name__", str(handlers[i]))
                logger.error(
                    f"EventBus: Handler '{handler_name}' failed for event "
                    f"'{event.name}': {result}"
                )

    async def _safe_call(self, handler: Handler, event: Event[Any]) -> None:
        """Safely call a handler, catching all exceptions.

        Args:
            handler: The handler to call
            event: The event to pass to the handler
        """
        await handler(event)


# Global event bus instance
# Use dependency injection in tests, this for production
event_bus = EventBus()
