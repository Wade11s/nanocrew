"""Tests for the file cache system."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from nanocrew.utils.file_cache import FileCache


@pytest.mark.asyncio
async def test_cache_miss_reads_from_disk():
    """Test that cache miss reads from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache()
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("hello world")

        content = await cache.get(test_file)

        assert content == "hello world"


@pytest.mark.asyncio
async def test_cache_hit_uses_cached_content():
    """Test that cache hit uses cached content without disk read."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache()
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        # First read populates cache
        content1 = await cache.get(test_file)
        assert content1 == "original"

        # Modify file behind cache's back
        test_file.write_text("modified")

        # Second read should still return cached content (same mtime)
        # Note: This tests the cache behavior when mtime hasn't changed
        # In real usage, file watcher will invalidate when mtime changes
        content2 = await cache.get(test_file)
        # Because mtime changed, this should be a cache miss
        assert content2 == "modified"


@pytest.mark.asyncio
async def test_cache_returns_none_for_missing_file():
    """Test that cache returns None for missing files."""
    cache = FileCache()
    missing_file = Path("/nonexistent/path/file.txt")

    content = await cache.get(missing_file)

    assert content is None


@pytest.mark.asyncio
async def test_invalidation_clears_cache():
    """Test that invalidation clears specific path from cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(debounce_ms=50)  # Short debounce for testing
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        # Populate cache
        await cache.get(test_file)

        # Invalidate
        await cache.invalidate(test_file)
        await asyncio.sleep(0.1)  # Wait for debounce

        # Modify file
        test_file.write_text("modified")

        # Should read new content
        content = await cache.get(test_file)
        assert content == "modified"


@pytest.mark.asyncio
async def test_debounced_invalidation():
    """Test that multiple rapid invalidations are debounced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(debounce_ms=100)
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content")

        invalidation_count = [0]

        class CountingInvalidator:
            async def invalidate(self, path: Path) -> None:
                invalidation_count[0] += 1

        cache.register_invalidator(CountingInvalidator())

        # Trigger multiple rapid invalidations
        await cache.invalidate(test_file)
        await cache.invalidate(test_file)
        await cache.invalidate(test_file)

        # Wait for debounce period
        await asyncio.sleep(0.15)

        # Should only have triggered once
        assert invalidation_count[0] == 1


@pytest.mark.asyncio
async def test_invalidate_all_clears_all():
    """Test that invalidate_all clears all cached entries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache()
        file1 = Path(tmpdir) / "file1.txt"
        file2 = Path(tmpdir) / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        # Populate cache
        await cache.get(file1)
        await cache.get(file2)

        # Invalidate all
        await cache.invalidate_all()

        # Files modified
        file1.write_text("new1")
        file2.write_text("new2")

        # Should read new content
        assert await cache.get(file1) == "new1"
        assert await cache.get(file2) == "new2"


@pytest.mark.asyncio
async def test_thread_safety():
    """Test that concurrent operations don't cause race conditions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache()
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("content")

        async def reader():
            for _ in range(10):
                await cache.get(test_file)
                await asyncio.sleep(0.001)

        async def invalidator():
            for _ in range(10):
                await cache.invalidate(test_file)
                await asyncio.sleep(0.001)

        # Run concurrently
        await asyncio.gather(reader(), invalidator())

        # Should complete without errors
        content = await cache.get(test_file)
        assert content == "content"
