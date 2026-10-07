"""Async executor integration with real deadlines and one explicit insertion callback."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import threading
import time
from collections.abc import Awaitable, Callable

from efficiency_client import LeanAdapter, Observer
from efficiency_workflow import workflow_arguments


class AsyncLeanBinding:
    """Bind an async, cancellation-safe MCP call to the bounded synchronous collector.

    The transport callback must cancel/drain abandoned request IDs (or disconnect)
    on coroutine cancellation. This binding never leaves a blocking RPC running in
    an unbounded worker pool. The only worker runs deterministic collection code.
    register the selected static surface before the task; call insert at the actual
    client boundary. This integration does not install itself in a desktop client.
    """

    def __init__(
        self, call: Callable[[str, dict], Awaitable[dict]], observer: Observer, surface: dict, **budgets
    ) -> None:
        self.call = call
        self.observer = observer
        self.surface = surface
        self.budgets = budgets
        self.active = False

    async def collect(self, arguments: dict, insert: Callable[[str], None] | None = None) -> dict:
        """Collect then insert exactly one text; cancellation never inserts partial old context."""
        if self.active:
            raise ValueError("binding allows one collection at a time")
        if insert is not None and inspect.iscoroutinefunction(insert):
            raise ValueError("insertion callback must be synchronous")
        arguments = workflow_arguments(self.surface, arguments)
        self.active = True
        loop = asyncio.get_running_loop()
        cancelled = threading.Event()
        futures: list[concurrent.futures.Future] = []

        def deadline_call(name: str, args: dict, *, deadline: float, cancelled: Callable[[], bool]) -> dict:
            future = asyncio.run_coroutine_threadsafe(self.call(name, args), loop)
            futures.append(future)
            try:
                while True:
                    if cancelled():
                        raise InterruptedError("collection cancelled")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("MCP collection deadline")
                    try:
                        return future.result(timeout=min(remaining, 0.05))
                    except concurrent.futures.CancelledError as error:
                        raise InterruptedError("MCP request cancelled") from error
                    except concurrent.futures.TimeoutError:
                        if future.done():
                            return future.result()
            finally:
                if not future.done():
                    future.cancel()
                futures.remove(future)

        self.observer.binding_mode = "async_deadline_single_text_v1"
        try:
            adapter = LeanAdapter(
                None,
                self.observer,
                collection_format=self.budgets.get("collection_format", "pcg-lean-collection-2"),
                deadline_call=deadline_call,
                cancelled=cancelled.is_set,
                defer_insertion=True,
                **{k: v for k, v in self.budgets.items() if k != "collection_format"},
            )
            worker = asyncio.create_task(asyncio.to_thread(adapter.collect, arguments))
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                cancelled.set()
                for future in futures:
                    future.cancel()
                await worker
                raise
            if insert is not None:
                try:
                    returned = insert(result["text"])
                    if returned is not None:
                        if inspect.iscoroutine(returned):
                            returned.close()
                        raise TypeError("insertion callback must return None")
                except Exception as error:
                    self.observer.insertion_boundary_complete = False
                    self.observer._event("insertion_failure", error_kind=type(error).__name__)
                    raise
                adapter.commit_insertion()
            else:
                self.observer._event(
                    "collection_prepared",
                    collection_id=self.observer.collection_id,
                    chars=len(result["text"]),
                    insertion_observed=False,
                )
            return result
        finally:
            cancelled.set()
            for future in futures:
                future.cancel()
            self.active = False
