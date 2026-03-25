"""Shared SSE keepalive helper for LlamaIndex workflow streaming."""

import asyncio
from typing import AsyncGenerator, Tuple, Any


async def stream_with_keepalive(
    handler, keepalive_interval: float = 5.0
) -> AsyncGenerator[Tuple[str, Any], None]:
    """Yield (kind, item) tuples from a LlamaIndex workflow handler.

    Emits ("keepalive", None) every keepalive_interval seconds when the
    workflow is silent (e.g. waiting for an LLM response).

    Kinds: "event" (progress event), "result" (dict), "error" (Exception), "keepalive"
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def _collect():
        try:
            async for ev in handler.stream_events():
                await queue.put(("event", ev))
            result = await handler
            await queue.put(("result", result))
        except Exception as exc:
            await queue.put(("error", exc))
        finally:
            await queue.put(("done", None))

    task = asyncio.create_task(_collect())
    try:
        getter = asyncio.ensure_future(queue.get())
        while True:
            done, _ = await asyncio.wait({getter}, timeout=keepalive_interval)
            if not done:
                yield ("keepalive", None)
                continue
            kind, item = getter.result()
            if kind == "done":
                getter.cancel()
                break
            getter = asyncio.ensure_future(queue.get())
            yield (kind, item)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
