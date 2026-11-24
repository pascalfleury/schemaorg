"""Progress reporting protocol and logger/Rich implementations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
import logging
import threading
import time
from types import TracebackType
from typing import Protocol

from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column

import util.pretty_logger as pretty_logger

_REFRESH_INTERVAL_SECONDS: float = 1.0 / 25.0


class TaskProgress(Protocol):
    """Active handle for one running task."""

    def step(self, label: str) -> None:
        """Update the current sub-step or item label."""
        ...

    def advance(self, n: int) -> None:
        """Increment completed work units by n."""
        ...

    def log(self, message: str, level: int) -> None:
        """Emit a diagnostic log line safely alongside active progress."""
        ...


class ProgressReporter(Protocol):
    """Factory for scoped task progress handles."""

    def task(
        self,
        description: str,
        total: int | None,
        unit: str,
    ) -> AbstractContextManager[TaskProgress]: ...


class _NullTaskProgress:
    def step(self, label: str) -> None:
        pass

    def advance(self, n: int) -> None:
        pass

    def log(self, message: str, level: int) -> None:
        pass


class NullProgressReporter:
    """Silent no-op reporter for unit tests and non-interactive callers."""

    @contextmanager
    def task(
        self,
        description: str,
        total: int | None,
        unit: str,
    ) -> Iterator[TaskProgress]:
        yield _NullTaskProgress()


class _LogTaskProgress:
    def __init__(
        self,
        logger: logging.Logger,
        description: str,
        log_steps: bool,
    ) -> None:
        self.logger = logger
        self.description = description
        self.log_steps = log_steps
        self.completed: int = 0
        self.current_step: str = ""

    def step(self, label: str) -> None:
        self.current_step = label
        if self.log_steps:
            self.logger.info("%s: %s", self.description, label)

    def advance(self, n: int) -> None:
        self.completed += n

    def log(self, message: str, level: int) -> None:
        self.logger.log(level, "%s", message)


class LogProgressReporter:
    """Logger-backed reporter using pretty_logger.BlockLog."""

    def __init__(self, logger: logging.Logger, log_steps: bool) -> None:
        self.logger: logging.Logger = logger
        self.log_steps: bool = log_steps

    @contextmanager
    def task(
        self,
        description: str,
        total: int | None,
        unit: str,
    ) -> Iterator[TaskProgress]:
        handle = _LogTaskProgress(self.logger, description, self.log_steps)
        with pretty_logger.BlockLog(
            logger=self.logger,
            message=description,
            timing=True,
        ) as block:
            yield handle
            if total is not None:
                block.append(f"({handle.completed}/{total} {unit})")
            elif handle.completed:
                block.append(f"({handle.completed} {unit})")


def configure_rich_logging(
    console: Console, level: int = logging.WARNING
) -> None:
    """Route root logging through RichHandler so logs print cleanly above bars."""
    logging.basicConfig(
        level=level,
        format="%(name)s: %(message)s",
        handlers=[
            RichHandler(
                console=console,
                show_time=False,
                show_path=False,
                markup=False,
            )
        ],
        force=True,
    )


class _RichTaskProgress:
    def __init__(
        self,
        reporter: RichProgressReporter,
        task_id: TaskID,
        logger: logging.Logger,
    ) -> None:
        self._reporter: RichProgressReporter = reporter
        self.task_id: TaskID = task_id
        self._logger: logging.Logger = logger
        self.completed: int = 0

    def step(self, label: str) -> None:
        self._reporter._step_task(self.task_id, label)

    def advance(self, n: int) -> None:
        self._reporter._advance_task(self, n)

    def log(self, message: str, level: int) -> None:
        self._logger.log(level, "%s", message)


class RichProgressReporter:
    """Rich-backed reporter stacking active and concurrent tasks cleanly.

    Uses manual throttled refreshes (auto_refresh=False) so no background
    thread is spawned, preserving ProcessTaskExecutor's POSIX fork() safety.
    """

    def __init__(
        self,
        console: Console | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.console: Console = console if console is not None else Console()
        self.logger: logging.Logger = (
            logger if logger is not None else logging.getLogger("schemaorg")
        )
        self._lock: threading.Lock = threading.Lock()
        self._explicit_depth: int = 0
        self._active_tasks: int = 0
        self._started: bool = False
        self._last_refresh: float = 0.0
        self._progress: Progress = Progress(
            SpinnerColumn(finished_text="[green]✓[/green]"),
            TextColumn(
                "[progress.description]{task.description}",
                table_column=Column(
                    no_wrap=True, overflow="ellipsis", max_width=34
                ),
            ),
            BarColumn(
                bar_width=None,
                table_column=Column(min_width=12, ratio=2),
            ),
            MofNCompleteColumn(
                table_column=Column(no_wrap=True, justify="right")
            ),
            TextColumn("{task.fields[unit]}", table_column=Column(no_wrap=True)),
            TimeElapsedColumn(table_column=Column(no_wrap=True)),
            TextColumn(
                "{task.fields[step]}",
                style="dim",
                table_column=Column(
                    no_wrap=True, overflow="ellipsis", min_width=0, ratio=1
                ),
            ),
            console=self.console,
            auto_refresh=False,
            transient=False,
            redirect_stdout=self.console.is_terminal,
            redirect_stderr=self.console.is_terminal,
            expand=True,
        )

    def _start_locked(self) -> None:
        if not self._started:
            self._progress.start()
            self._started = True

    def _stop_if_idle_locked(self) -> None:
        if (
            self._explicit_depth == 0
            and self._active_tasks == 0
            and self._started
        ):
            self._progress.stop()
            for task in list(self._progress.tasks):
                self._progress.remove_task(task.id)
            self._started = False
            self._last_refresh = 0.0

    def _refresh_locked(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or (now - self._last_refresh) >= _REFRESH_INTERVAL_SECONDS:
            self._progress.refresh()
            self._last_refresh = now

    def __enter__(self) -> RichProgressReporter:
        with self._lock:
            self._explicit_depth += 1
            self._start_locked()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        with self._lock:
            self._explicit_depth = max(0, self._explicit_depth - 1)
            self._stop_if_idle_locked()

    def _step_task(self, task_id: TaskID, label: str) -> None:
        with self._lock:
            self._progress.update(task_id, step=escape(label))
            self._refresh_locked()

    def _advance_task(self, handle: _RichTaskProgress, n: int) -> None:
        with self._lock:
            handle.completed += n
            self._progress.update(handle.task_id, advance=n)
            self._refresh_locked()

    @contextmanager
    def task(
        self,
        description: str,
        total: int | None,
        unit: str,
    ) -> Iterator[TaskProgress]:
        with self._lock:
            self._active_tasks += 1
            self._start_locked()
            task_id = self._progress.add_task(
                escape(description),
                total=total,
                unit=escape(unit),
                step="",
            )
            self._refresh_locked(force=True)

        handle = _RichTaskProgress(self, task_id, self.logger)
        failed = False
        try:
            yield handle
        except BaseException:
            failed = True
            raise
        finally:
            with self._lock:
                if not failed:
                    if total is None:
                        self._progress.update(
                            task_id,
                            total=handle.completed,
                            completed=handle.completed,
                            step="",
                        )
                    elif handle.completed >= total:
                        self._progress.update(
                            task_id,
                            completed=handle.completed,
                            step="",
                        )
                self._progress.stop_task(task_id)
                self._refresh_locked(force=True)
                self._active_tasks -= 1
                self._stop_if_idle_locked()
