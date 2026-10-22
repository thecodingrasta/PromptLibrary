"""Abstract base class for sync providers."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable


class SyncProvider(ABC):
    """Base class for all sync providers."""

    @abstractmethod
    async def push(self, content: bytes, filename: str) -> None:
        """Push content to the remote storage."""
        ...

    @abstractmethod
    async def pull(self, filename: str) -> bytes:
        """Pull content from remote storage."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the connection to the provider works."""
        ...


async def blocking_operation[Result](operation: Callable[[], Result]) -> Result:
    """Retain the caller's locks until an uncancellable worker has finished its IO."""
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Cancelling to_thread does not stop its thread. Releasing the transfer lock
        # early would allow a second upload to race the first file replacement.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
