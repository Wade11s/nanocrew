"""Tests for the event bus system."""

import pytest
import asyncio

from nanocrew.utils.events import EventBus, Event


@pytest.mark.asyncio
async def test_subscribe_and_receive():
    """Test subscribing and receiving an event."""
    bus = EventBus()
    received = []

    async def handler(event: Event[str]):
        received.append(event.data)

    await bus.subscribe("test.event", handler)
    await bus.publish(Event(name="test.event", data="hello"))

    # Allow async handlers to complete
    await asyncio.sleep(0.01)

    assert len(received) == 1
    assert received[0] == "hello"


@pytest.mark.asyncio
async def test_multiple_subscribers():
    """Test that multiple subscribers all receive the event."""
    bus = EventBus()
    received = []

    async def handler1(event: Event[str]):
        received.append("handler1")

    async def handler2(event: Event[str]):
        received.append("handler2")

    await bus.subscribe("test.event", handler1)
    await bus.subscribe("test.event", handler2)
    await bus.publish(Event(name="test.event", data="hello"))

    await asyncio.sleep(0.01)

    assert len(received) == 2
    assert "handler1" in received
    assert "handler2" in received


@pytest.mark.asyncio
async def test_unsubscribe():
    """Test unsubscribing from events."""
    bus = EventBus()
    received = []

    async def handler(event: Event[str]):
        received.append(event.data)

    await bus.subscribe("test.event", handler)
    await bus.publish(Event(name="test.event", data="first"))
    await asyncio.sleep(0.01)

    assert len(received) == 1

    await bus.unsubscribe("test.event", handler)
    await bus.publish(Event(name="test.event", data="second"))
    await asyncio.sleep(0.01)

    # Should not have received second event
    assert len(received) == 1


@pytest.mark.asyncio
async def test_error_isolation():
    """Test that one handler's error doesn't affect others."""
    bus = EventBus()
    received = []

    async def failing_handler(event: Event[str]):
        raise ValueError("Intentional error")

    async def working_handler(event: Event[str]):
        received.append(event.data)

    await bus.subscribe("test.event", failing_handler)
    await bus.subscribe("test.event", working_handler)

    # Should not raise
    await bus.publish(Event(name="test.event", data="test"))
    await asyncio.sleep(0.01)

    # Working handler should still have received the event
    assert len(received) == 1


@pytest.mark.asyncio
async def test_parallel_execution():
    """Test that handlers execute in parallel (not sequentially)."""
    bus = EventBus()
    started = []
    completed = []

    async def slow_handler(event: Event[str]):
        started.append("slow")
        await asyncio.sleep(0.05)
        completed.append("slow")

    async def fast_handler(event: Event[str]):
        started.append("fast")
        await asyncio.sleep(0.01)
        completed.append("fast")

    await bus.subscribe("test.event", slow_handler)
    await bus.subscribe("test.event", fast_handler)

    await bus.publish(Event(name="test.event", data="test"))
    await asyncio.sleep(0.005)  # Wait for both to start

    # Both should have started (parallel execution)
    assert "slow" in started
    assert "fast" in started

    await asyncio.sleep(0.1)  # Wait for both to complete
    assert "slow" in completed
    assert "fast" in completed


@pytest.mark.asyncio
async def test_typed_event_data():
    """Test that event data preserves type information."""
    bus = EventBus()

    class TestData:
        def __init__(self, value: int):
            self.value = value

    received = []

    async def handler(event: Event[TestData]):
        received.append(event.data.value)

    await bus.subscribe("test.event", handler)
    await bus.publish(Event(name="test.event", data=TestData(42)))

    await asyncio.sleep(0.01)

    assert received[0] == 42
