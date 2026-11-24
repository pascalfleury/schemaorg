"""Floating task that discovers and runs the schema.org unittest suite."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import io
import logging
import math
from pathlib import Path
from typing import Any
import unittest

from schemaorg.executor import TaskExecutor, shard_sequence
from schemaorg.progress import ProgressReporter

_SHARD_SIZE: int = 6


@dataclass(frozen=True)
class TestSuiteSummary:
    """Structured summary returned by RunUnitTestsTask."""

    total_run: int
    failure_count: int
    error_count: int
    skipped_count: int
    expected_failure_count: int
    unexpected_success_count: int
    failures: tuple[tuple[str, str], ...]
    errors: tuple[tuple[str, str], ...]

    @property
    def ok(self) -> bool:
        return (
            self.failure_count == 0
            and self.error_count == 0
            and self.unexpected_success_count == 0
        )


@dataclass(frozen=True)
class _ShardOutcome:
    total_run: int
    test_ids: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]
    errors: tuple[tuple[str, str], ...]
    skipped_count: int
    expected_failure_count: int
    unexpected_success_ids: tuple[str, ...]


class _CollectingTestResult(unittest.TestResult):
    """Collects picklable outcomes and buffers stdio/logs for passing tests."""

    def __init__(self) -> None:
        super().__init__()
        self.buffer = True
        self.test_ids: list[str] = []
        self._log_buffer: io.StringIO = io.StringIO()
        self._saved_root_handlers: list[logging.Handler] = []

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        self.test_ids.append(test.id())
        self._log_buffer = io.StringIO()
        root = logging.getLogger()
        self._saved_root_handlers = list(root.handlers)
        handler = logging.StreamHandler(self._log_buffer)
        handler.setLevel(root.level)
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        root.handlers = [handler]

    def stopTest(self, test: unittest.TestCase) -> None:
        logging.getLogger().handlers = self._saved_root_handlers
        # Traceback already embeds captured stdout/stderr; suppress duplicate mirror.
        self._mirrorOutput = False
        super().stopTest(test)

    def _append_captured_logs(
        self, entries: list[tuple[unittest.TestCase, str]]
    ) -> None:
        logs = self._log_buffer.getvalue()
        if logs and entries:
            case, tb = entries[-1]
            if not logs.endswith("\n"):
                logs += "\n"
            entries[-1] = (case, f"{tb}\nCaptured logs:\n{logs}")

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        super().addError(test, err)
        self._append_captured_logs(self.errors)

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self._append_captured_logs(self.failures)


def _iter_cases(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
        else:
            yield item


def _build_shards(suite: unittest.TestSuite) -> list[unittest.TestSuite]:
    by_class: dict[type[unittest.TestCase], list[unittest.TestCase]] = {}
    for case in _iter_cases(suite):
        by_class.setdefault(type(case), []).append(case)

    shards: list[unittest.TestSuite] = []
    for cases in by_class.values():
        shard_count = max(1, math.ceil(len(cases) / _SHARD_SIZE))
        for group in shard_sequence(cases, shard_count):
            shards.append(unittest.TestSuite(group))
    return shards


def _run_shard(shard: unittest.TestSuite) -> _ShardOutcome:
    result = _CollectingTestResult()
    result.startTestRun()
    try:
        shard.run(result)
    finally:
        result.stopTestRun()
    return _ShardOutcome(
        total_run=result.testsRun,
        test_ids=tuple(result.test_ids),
        failures=tuple((t.id(), tb) for t, tb in result.failures),
        errors=tuple((t.id(), tb) for t, tb in result.errors),
        skipped_count=len(result.skipped),
        expected_failure_count=len(result.expectedFailures),
        unexpected_success_ids=tuple(
            t.id() for t in result.unexpectedSuccesses
        ),
    )


class RunUnitTestsTask:
    """Discovers and executes unittest cases in a given directory via TaskExecutor."""

    def __init__(
        self,
        tests_dir: Path,
        skip_basics: bool,
        progress: ProgressReporter,
        executor: TaskExecutor,
    ) -> None:
        self.tests_dir: Path = tests_dir
        self.skip_basics: bool = skip_basics
        self.progress: ProgressReporter = progress
        self.executor: TaskExecutor = executor

    def run(self) -> TestSuiteSummary:
        pattern = "*graphs*.py" if self.skip_basics else "test*.py"
        # Pass top_level_dir=tests_dir so two distinct tests_dir paths in one
        # process do not collide unless module basenames overlap.
        suite = unittest.loader.TestLoader().discover(
            start_dir=str(self.tests_dir),
            pattern=pattern,
            top_level_dir=str(self.tests_dir),
        )
        total = suite.countTestCases()
        shards = _build_shards(suite)

        total_run = 0
        skipped_count = 0
        expected_failure_count = 0
        unexpected_success_count = 0
        failures: list[tuple[str, str]] = []
        errors: list[tuple[str, str]] = []

        with self.progress.task(
            "Running unit tests",
            total=total,
            unit="tests",
        ) as p:
            for outcome in self.executor.map(_run_shard, shards):
                total_run += outcome.total_run
                skipped_count += outcome.skipped_count
                expected_failure_count += outcome.expected_failure_count
                unexpected_success_count += len(outcome.unexpected_success_ids)
                for test_id, tb in outcome.errors:
                    errors.append((test_id, tb))
                    p.log(f"ERROR in {test_id}:\n{tb}", logging.ERROR)
                for test_id, tb in outcome.failures:
                    failures.append((test_id, tb))
                    p.log(f"FAIL in {test_id}:\n{tb}", logging.ERROR)
                for test_id in outcome.unexpected_success_ids:
                    p.log(f"UNEXPECTED SUCCESS in {test_id}", logging.ERROR)
                if outcome.test_ids:
                    p.step(outcome.test_ids[-1])
                p.advance(outcome.total_run)

        return TestSuiteSummary(
            total_run=total_run,
            failure_count=len(failures),
            error_count=len(errors),
            skipped_count=skipped_count,
            expected_failure_count=expected_failure_count,
            unexpected_success_count=unexpected_success_count,
            failures=tuple(failures),
            errors=tuple(errors),
        )
