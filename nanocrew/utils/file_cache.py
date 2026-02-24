"""File content cache with mtime-based invalidation and debouncing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from loguru import logger


from typing import runtime_checkable


@runtime_checkable
class CacheInvalidator(Protocol):
    """Protocol for cache invalidation callbacks."""

    async def invalidate(self, path: Path) -> None:
        """Called when a cached file is invalidated.

        Args:
            path: The path that was invalidated
        """
        ...


@dataclass
class CacheEntry:
    """A cached file entry with mtime tracking."""

    mtime: float
    content: str


class FileCache:
    """Thread-safe file content cache with debounced invalidation.

    Features:
    - Mtime-based cache validation (automatic reload if file changes)
    - Debounced invalidation (batch rapid changes)
    - Async-safe with asyncio.Lock
    - Pluggable invalidation callbacks
    """

    def __init__(self, debounce_ms: int = 500) -> None:
        """Initialize the file cache.

        Args:
            debounce_ms: Debounce delay in milliseconds
        """
        self._cache: dict[Path, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._debounce_ms = debounce_ms
        self._pending_invalidations: dict[Path, asyncio.Task] = {}
        self._invalidators: list[CacheInvalidator] = []

    def register_invalidator(self, invalidator: CacheInvalidator) -> None:
        """Register a callback to be called on cache invalidation.

        Args:
            invalidator: The invalidator to register
        """
        self._invalidators.append(invalidator)
        logger.debug(f"FileCache: Registered invalidator {type(invalidator).__name__}")

    def unregister_invalidator(self, invalidator: CacheInvalidator) -> None:
        """Unregister an invalidation callback.

        Args:
            invalidator: The invalidator to unregister
        """
        self._invalidators.remove(invalidator)

    async def get(self, path: Path) -> str | None:
        """Get file content, using cache if valid.

        Args:
            path: Path to the file

        Returns:
            File content, or None if file doesn't exist
        """
        if not path.exists():
            return None

        current_mtime = path.stat().st_mtime

        async with self._lock:
            entry = self._cache.get(path)
            if entry and entry.mtime == current_mtime:
                # Cache hit
                logger.debug(f"FileCache: Hit for {path}")
                return entry.content

        # Cache miss or stale
        try:
            content = path.read_text(encoding="utf-8")
            async with self._lock:
                self._cache[path] = CacheEntry(mtime=current_mtime, content=content)
            logger.debug(f"FileCache: Miss for {path}, loaded from disk")
            return content
        except (OSError, UnicodeDecodeError) as e:
            logger.error(f"FileCache: Failed to read {path}: {e}")
            return None

    async def invalidate(self, path: Path) -> None:
        """Invalidate cache entry with debouncing.

        If invalidate is called multiple times rapidly, only the last
        one will actually execute after the debounce period.

        Args:
            path: Path to invalidate
        """
        # Cancel any pending invalidation for this path
        if path in self._pending_invalidations:
            self._pending_invalidations[path].cancel()
            try:
                await self._pending_invalidations[path]
            except asyncio.CancelledError:
                pass

        # Schedule new debounced invalidation
        async def _do_invalidate() -> None:
            await asyncio.sleep(self._debounce_ms / 1000)

            async with self._lock:
                if path in self._cache:
                    del self._cache[path]
                    logger.debug(f"FileCache: Invalidated {path}")

            # Notify invalidators
            for invalidator in self._invalidators:
                try:
                    await invalidator.invalidate(path)
                except Exception as e:
                    logger.error(f"FileCache: Invalidator failed for {path}: {e}")

            # Clean up pending tracking
            self._pending_invalidations.pop(path, None)

        self._pending_invalidations[path] = asyncio.create_task(_do_invalidate())

    async def invalidate_all(self) -> None:
        """Invalidate all cached entries immediately."""
        async with self._lock:
            paths = list(self._cache.keys())
            self._cache.clear()

        # Cancel all pending invalidations
        for task in self._pending_invalidations.values():
            task.cancel()
        self._pending_invalidations.clear()

        # Notify invalidators
        for path in paths:
            for invalidator in self._invalidators:
                try:
                    await invalidator.invalidate(path)
                except Exception as e:
                    logger.error(f"FileCache: Invalidator failed for {path}: {e}")

        logger.debug(f"FileCache: Invalidated all ({len(paths)} entries)")

    async def clear_pending(self) -> None:
        """Clear all pending invalidations without executing them."""
        for task in self._pending_invalidations.values():
            task.cancel()
        self._pending_invalidations.clear()
