"""The execution half of the durable-workflow seam.

A ``Runner`` takes an opaque ``job`` (a zero-arg callable that performs one orchestration action and
returns a ``CommandOutcome``), wraps it in run-state transitions (queued → running → succeeded /
paused / failed), and persists each transition to a ``RunStore``. Keeping the job opaque keeps the
runner decoupled from the action catalog — the API builds the closure (binding store/driver/
publisher/now) and the runner only manages lifecycle + durability.

Two implementations:

* ``InlineRunner`` — runs synchronously on ``submit`` (the default; deterministic for tests).
* ``ThreadRunner`` — runs in a background thread; ``submit`` returns immediately with a QUEUED run,
  the caller polls the ``RunStore``. This is the "real async" behavior the API exposes as
  ``202 + run id``.

Production replaces both with a Temporal/Inngest-backed runner behind this same interface — at which
point a worker crash mid-run is recoverable rather than orphaned (the failure mode SYSTEM.md §3d
describes). ``ThreadRunner`` is the local stand-in, not the durable answer.
"""

from __future__ import annotations

import secrets
import threading
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from .orchestration import CommandOutcome
from .runs import Run, RunStatus, RunStore

Job = Callable[[], CommandOutcome]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return "run_" + secrets.token_hex(8)


class Runner(ABC):
    def __init__(self, runs: RunStore, *, now_fn: Callable[[], str] = _iso_now) -> None:
        self.runs = runs
        self._now = now_fn

    @abstractmethod
    def submit(self, slug: str, kind: str, job: Job) -> Run:
        """Enqueue a job. Returns the run record (terminal for inline; queued for background)."""

    # -- shared lifecycle -------------------------------------------------- #
    def _new_run(self, slug: str, kind: str) -> Run:
        run = Run(id=_new_run_id(), slug=slug, kind=kind, status=RunStatus.QUEUED, created=self._now())
        return self.runs.create(run)

    def _execute(self, run: Run, job: Job) -> Run:
        run.status = RunStatus.RUNNING
        run.started = self._now()
        self.runs.save(run)
        try:
            outcome = job()
            run.result = {
                "ok": outcome.ok,
                "paused": outcome.paused,
                "preview_url": outcome.preview_url,
                "message": outcome.message,
            }
            run.status = (
                RunStatus.SUCCEEDED if outcome.ok
                else RunStatus.PAUSED if outcome.paused
                else RunStatus.FAILED
            )
        except Exception as e:  # noqa: BLE001 - the run captures the failure; it must not crash the worker
            run.status = RunStatus.FAILED
            run.error = f"{type(e).__name__}: {e}"
        run.finished = self._now()
        self.runs.save(run)
        return run


class InlineRunner(Runner):
    """Executes synchronously — the run is terminal by the time ``submit`` returns."""

    def submit(self, slug: str, kind: str, job: Job) -> Run:
        run = self._new_run(slug, kind)
        return self._execute(run, job)


class ThreadRunner(Runner):
    """Executes in a daemon thread; ``submit`` returns a QUEUED snapshot immediately."""

    def __init__(self, runs: RunStore, *, now_fn: Callable[[], str] = _iso_now) -> None:
        super().__init__(runs, now_fn=now_fn)
        self._threads: list[threading.Thread] = []

    def submit(self, slug: str, kind: str, job: Job) -> Run:
        run = self._new_run(slug, kind)
        t = threading.Thread(target=self._execute, args=(run, job), daemon=True)
        t.start()
        self._threads.append(t)
        # Return a snapshot so the caller serializes a stable state, not one the thread is mutating.
        return replace(run)

    def wait(self, timeout: float | None = None) -> None:
        """Block until all submitted jobs finish (for tests + graceful shutdown)."""
        for t in list(self._threads):
            t.join(timeout)
