"""Floating task executors for sequential, multithreaded, and forked execution."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
import concurrent.futures
import multiprocessing
import os
import queue
import threading
import traceback
from typing import Any, Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def default_worker_count() -> int:
    """Return the default concurrency limit for the current host."""
    return max(1, os.cpu_count() or 1)


def shard_sequence(items: Sequence[T], shard_count: int) -> list[tuple[T, ...]]:
    """Partition items into up to shard_count balanced contiguous shards."""
    if shard_count < 1:
        raise ValueError(f"shard_count must be >= 1, got {shard_count}")
    total = len(items)
    if total == 0:
        return []
    count = min(total, shard_count)
    base, extra = divmod(total, count)
    shards: list[tuple[T, ...]] = []
    offset = 0
    for idx in range(count):
        size = base + (1 if idx < extra else 0)
        shards.append(tuple(items[offset : offset + size]))
        offset += size
    return shards


class TaskExecutor(Protocol):
    """Unified execution interface for independent items and subtasks."""

    def map(
        self,
        fn: Callable[[T], R],
        items: Sequence[T],
    ) -> Iterator[R]:
        """Apply fn to each item, yielding results as items complete."""
        ...

    def run_all(
        self,
        subtasks: Sequence[Callable[[], R]],
    ) -> list[R]:
        """Run independent zero-argument subtasks and return results in order."""
        ...


class SequentialExecutor:
    """In-process sequential executor for unit tests and single-worker runs."""

    def map(
        self,
        fn: Callable[[T], R],
        items: Sequence[T],
    ) -> Iterator[R]:
        for item in items:
            yield fn(item)

    def run_all(
        self,
        subtasks: Sequence[Callable[[], R]],
    ) -> list[R]:
        return [subtask() for subtask in subtasks]


class ThreadTaskExecutor:
    """Multithreaded executor for I/O-bound subtasks and shared-memory fan-out."""

    def __init__(self, max_workers: int) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self.max_workers: int = max_workers

    def map(
        self,
        fn: Callable[[T], R],
        items: Sequence[T],
    ) -> Iterator[R]:
        if len(items) <= 1 or self.max_workers <= 1:
            for item in items:
                yield fn(item)
            return

        workers = min(self.max_workers, len(items))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(fn, item) for item in items]
            for future in concurrent.futures.as_completed(futures):
                yield future.result()

    def run_all(
        self,
        subtasks: Sequence[Callable[[], R]],
    ) -> list[R]:
        if len(subtasks) <= 1 or self.max_workers <= 1:
            return [subtask() for subtask in subtasks]

        workers = min(self.max_workers, len(subtasks))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(subtask) for subtask in subtasks]
            return [future.result() for future in futures]


class ProcessTaskExecutor:
    """Fork-based process executor with zero module globals or input pickling.

    Workers inherit lexical closures and read-only parent memory copy-on-write
    across os.fork(); only return values cross the result queue. Falls back to
    ThreadTaskExecutor when fork is unavailable or multiple threads are active.
    """

    def __init__(self, max_workers: int) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self.max_workers: int = max_workers

    def _can_fork(self) -> bool:
        return (
            self.max_workers > 1
            and "fork" in multiprocessing.get_all_start_methods()
            and threading.active_count() == 1
        )

    def _run_indexed(
        self,
        fn: Callable[[T], R],
        items: Sequence[T],
    ) -> Iterator[tuple[int, R]]:
        total = len(items)
        ctx = multiprocessing.get_context("fork")
        worker_count = min(self.max_workers, total)
        counter: Any = ctx.Value("i", 0)
        result_queue: Any = ctx.Queue()

        def _worker() -> None:
            try:
                while True:
                    with counter.get_lock():
                        idx = int(counter.value)
                        counter.value = idx + 1
                    if idx >= total:
                        return
                    try:
                        value = fn(items[idx])
                    except BaseException as exc:  # noqa: BLE001
                        result_queue.put(
                            (idx, False, traceback.format_exc(), str(exc))
                        )
                    else:
                        result_queue.put((idx, True, value, ""))
            finally:
                result_queue.close()
                result_queue.join_thread()

        procs = [ctx.Process(target=_worker) for _ in range(worker_count)]
        for proc in procs:
            proc.start()

        received = 0
        try:
            while received < total:
                try:
                    idx, ok, payload, err_msg = result_queue.get(timeout=0.5)
                except queue.Empty:
                    if not any(proc.is_alive() for proc in procs):
                        raise RuntimeError(
                            "Worker process exited before completing all items "
                            f"({received}/{total} completed)."
                        )
                    continue
                received += 1
                if not ok:
                    raise RuntimeError(
                        f"Worker failed on item {idx}: {err_msg}\n{payload}"
                    )
                yield idx, payload
        finally:
            for proc in procs:
                if proc.is_alive():
                    proc.terminate()
            for proc in procs:
                proc.join()
            result_queue.close()
            result_queue.join_thread()

    def map(
        self,
        fn: Callable[[T], R],
        items: Sequence[T],
    ) -> Iterator[R]:
        if len(items) <= 1 or self.max_workers <= 1:
            for item in items:
                yield fn(item)
            return
        if not self._can_fork():
            yield from ThreadTaskExecutor(self.max_workers).map(fn, items)
            return

        for _, result in self._run_indexed(fn, items):
            yield result

    def run_all(
        self,
        subtasks: Sequence[Callable[[], R]],
    ) -> list[R]:
        if len(subtasks) <= 1 or self.max_workers <= 1:
            return [subtask() for subtask in subtasks]
        if not self._can_fork():
            return ThreadTaskExecutor(self.max_workers).run_all(subtasks)

        ordered: list[Any] = [None] * len(subtasks)
        for idx, result in self._run_indexed(lambda fn: fn(), subtasks):
            ordered[idx] = result
        return ordered
