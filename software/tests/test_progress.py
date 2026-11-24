from __future__ import annotations

import contextlib
import io
import logging
import sys
import threading
import unittest

from rich.console import Console

from schemaorg.progress import (
    LogProgressReporter,
    NullProgressReporter,
    RichProgressReporter,
    configure_rich_logging,
)


def _make_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=110), buf


class TestProgressReporter(unittest.TestCase):
    def test_null_progress_reporter_is_silent(self) -> None:
        reporter = NullProgressReporter()
        with reporter.task("Quiet work", total=2, unit="items") as p:
            p.step("first")
            p.advance(1)
            p.log("ignored", logging.INFO)
            p.advance(1)

    def test_log_progress_reporter_emits_block_and_steps(self) -> None:
        logger = logging.getLogger("test.progress")
        reporter = LogProgressReporter(logger=logger, log_steps=True)
        with self.assertLogs(logger, level=logging.INFO) as captured:
            with reporter.task("Exporting", total=2, unit="files") as p:
                p.step("a.ttl")
                p.advance(1)
                p.step("b.ttl")
                p.advance(1)
                p.log("extra detail", logging.WARNING)

        joined = "\n".join(captured.output)
        self.assertIn("Start: Exporting", joined)
        self.assertIn("Exporting: a.ttl", joined)
        self.assertIn("Exporting: b.ttl", joined)
        self.assertIn("WARNING:test.progress:extra detail", joined)
        self.assertIn("Done: Exporting (2/2 files)", joined)

    def test_rich_progress_spawns_no_threads_and_renders_completed_bar(self) -> None:
        console, buf = _make_console()
        before_threads = threading.active_count()
        reporter = RichProgressReporter(console=console)
        with reporter:
            with reporter.task("Exporting release", total=2, unit="files") as p:
                inside_threads = threading.active_count()
                p.step("a[0].ttl")
                p.advance(1)
                p.step("b.ttl")
                p.advance(1)

        self.assertEqual(inside_threads, before_threads)
        output = buf.getvalue()
        self.assertIn("Exporting release", output)
        self.assertIn("2/2", output)
        self.assertIn("files", output)
        self.assertIn("✓", output)

    def test_rich_progress_stacks_concurrent_tasks_across_threads(self) -> None:
        console, buf = _make_console()
        reporter = RichProgressReporter(console=console)
        barrier = threading.Barrier(2)

        def _worker(name: str, items: int) -> None:
            with reporter.task(name, total=items, unit="items") as p:
                barrier.wait(timeout=5.0)
                for idx in range(items):
                    p.step(f"{name}-{idx}")
                    p.advance(1)

        with reporter:
            with reporter.task("Overall", total=2, unit="stages") as overall:
                t1 = threading.Thread(target=_worker, args=("Alpha", 3))
                t2 = threading.Thread(target=_worker, args=("Beta", 4))
                t1.start()
                t2.start()
                t1.join()
                t2.join()
                overall.advance(2)

        output = buf.getvalue()
        self.assertIn("Overall", output)
        self.assertIn("Alpha", output)
        self.assertIn("3/3", output)
        self.assertIn("Beta", output)
        self.assertIn("4/4", output)

    def test_rich_progress_leaves_failed_task_incomplete(self) -> None:
        console, buf = _make_console()
        reporter = RichProgressReporter(console=console)
        with self.assertRaises(RuntimeError):
            with reporter.task("Validating", total=5, unit="examples") as p:
                p.step("#eg-1")
                p.advance(2)
                raise RuntimeError("boom")

        output = buf.getvalue()
        self.assertIn("Validating", output)
        self.assertIn("2/5", output)
        self.assertNotIn("5/5", output)

    def test_rich_progress_reusable_across_phases_without_duplicating_rows(self) -> None:
        console, buf = _make_console()
        reporter = RichProgressReporter(console=console)

        with reporter.task("Phase One", total=None, unit="steps") as p:
            p.advance(2)
        console.print("--- prompt ---")
        with reporter.task("Phase Two", total=1, unit="files") as p:
            p.advance(1)

        output = buf.getvalue()
        self.assertEqual(output.count("Phase One"), 1)
        self.assertEqual(output.count("Phase Two"), 1)
        self.assertIn("2/2", output)
        self.assertIn("1/1", output)

    def test_configure_rich_logging_shows_warnings_and_hides_info(self) -> None:
        root = logging.getLogger()
        saved_handlers = list(root.handlers)
        saved_level = root.level
        try:
            console, buf = _make_console()
            configure_rich_logging(console, level=logging.WARNING)
            self.assertEqual(root.level, logging.WARNING)

            reporter = RichProgressReporter(
                console=console, logger=logging.getLogger("test.rich.log")
            )
            with reporter.task("Checking", total=1, unit="items") as p:
                p.log("quiet info message", logging.INFO)
                p.log("loud warning [0]", logging.WARNING)
                p.advance(1)

            output = buf.getvalue()
            self.assertNotIn("quiet info message", output)
            self.assertIn("test.rich.log: loud warning [0]", output)
        finally:
            root.handlers = saved_handlers
            root.setLevel(saved_level)

    def test_rich_progress_redirects_stdio_only_on_terminals(self) -> None:
        non_tty_buf = io.StringIO()
        non_tty = Console(file=non_tty_buf, force_terminal=False, width=100)
        captured_out = io.StringIO()
        with contextlib.redirect_stdout(captured_out):
            with RichProgressReporter(console=non_tty) as reporter:
                with reporter.task("Non-TTY", total=1, unit="items") as p:
                    print("stays-on-stdout")
                    p.advance(1)
        self.assertIn("stays-on-stdout", captured_out.getvalue())
        self.assertNotIn("stays-on-stdout", non_tty_buf.getvalue())

        tty_buf = io.StringIO()
        tty = Console(file=tty_buf, force_terminal=True, width=100)
        with RichProgressReporter(console=tty) as reporter:
            with reporter.task("TTY", total=1, unit="items") as p:
                print("routed-above-bar")
                print("stderr-above-bar", file=sys.stderr)
                p.advance(1)
        self.assertIn("routed-above-bar", tty_buf.getvalue())
        self.assertIn("stderr-above-bar", tty_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
