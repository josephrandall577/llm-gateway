"""
Proxy API Module Initialization
"""

import asyncio
from collections.abc import Awaitable
from contextlib import suppress
from typing import TypeVar

from starlette.requests import Request


T = TypeVar("T")


async def cancel_on_disconnect(request: Request, operation: Awaitable[T]) -> T:
    """Cancel an operation when its HTTP client disconnects."""
    request_task = asyncio.current_task()
    if request_task is None:
        return await operation

    async def watch_disconnect() -> None:
        while (await request.receive())["type"] != "http.disconnect":
            pass
        request_task.cancel()

    watcher = asyncio.create_task(watch_disconnect())
    try:
        return await operation
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


from app.api.proxy.openai import router as openai_router
from app.api.proxy.anthropic import router as anthropic_router

__all__ = [
    "cancel_on_disconnect",
    "openai_router",
    "anthropic_router",
]
