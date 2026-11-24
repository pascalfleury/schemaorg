from __future__ import annotations

import contextlib
import io
import logging
import sys
import unittest

from schemaorg.executor import (
    ProcessTaskExecutor,
    SequentialExecutor,
    TaskExecutor,
    ThreadTaskExecutor,
    default_worker_count,
    shard_sequence,
)


class TestTaskExecutors(unittest.TestCase):
    def _executors(self) -> tuple[TaskExecutor, ...]:
        return (
            SequentialExecutor(),
            ThreadTaskExecutor(max_workers=2),
            ProcessTaskExecutor(max_workers=2),
        )

    def test_map_runs_closures_across_all_executors(self) -> None:
        factor = 3
        for executor in self._executors():
            with self.subTest(executor=type(executor).__name__):
                results = list(executor.map(lambda x: x * factor, [1, 2, 3, 4]))
                self.assertEqual(sorted(results), [3, 6, 9, 12])

    def test_run_all_preserves_subtask_order_across_all_executors(self) -> None:
        prefix = "item-"
        for executor in self._executors():
            with self.subTest(executor=type(executor).__name__):
                results = executor.run_all([
                    lambda: f"{prefix}a",
                    lambda: f"{prefix}b",
                    lambda: f"{prefix}c",
                ])
                self.assertEqual(results, ["item-a", "item-b", "item-c"])

    def test_worker_exceptions_propagate(self) -> None:
        def boom(val: int) -> int:
            if val == 2:
                raise ValueError("bad value")
            return val

        for executor in self._executors():
            with self.subTest(executor=type(executor).__name__):
                with self.assertRaises((ValueError, RuntimeError)):
                    list(executor.map(boom, [1, 2, 3]))

    def test_invalid_worker_counts_raise(self) -> None:
        self.assertGreaterEqual(default_worker_count(), 1)
        with self.assertRaises(ValueError):
            ThreadTaskExecutor(max_workers=0)
        with self.assertRaises(ValueError):
            ProcessTaskExecutor(max_workers=0)

    def test_shard_sequence_balances_items(self) -> None:
        self.assertEqual(shard_sequence([], 4), [])
        self.assertEqual(
            shard_sequence([1, 2, 3, 4, 5], 3),
            [(1, 2), (3, 4), (5,)],
        )
        self.assertEqual(shard_sequence([1, 2], 5), [(1,), (2,)])
        with self.assertRaises(ValueError):
            shard_sequence([1], 0)

    def test_process_executor_replays_worker_logs_and_stdio_in_parent(
        self,
    ) -> None:
        logger = logging.getLogger("test.executor.replay")

        def emit(val: int) -> int:
            if val == 0:
                logger.warning("warn-%d", val)
            elif val == 1:
                print(f"out-{val}")
                print(f"err-{val}", file=sys.stderr)
            return val

        out_buf = io.StringIO()
        err_buf = io.StringIO()
        executor = ProcessTaskExecutor(max_workers=2)
        with (
            self.assertLogs(None, level=logging.WARNING) as captured,
            contextlib.redirect_stdout(out_buf),
            contextlib.redirect_stderr(err_buf),
        ):
            results = list(executor.map(emit, [0, 1]))

        self.assertEqual(sorted(results), [0, 1])
        self.assertIn("WARNING:test.executor.replay:warn-0", captured.output)
        self.assertEqual(out_buf.getvalue().strip(), "out-1")
        self.assertEqual(err_buf.getvalue().strip(), "err-1")


if __name__ == "__main__":
    unittest.main()
