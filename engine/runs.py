"""Run records + their store — the persistence half of the durable-workflow seam.

A ``Run`` is one execution of an orchestration action (assemble / process-edits / diagnose). Today
``studio.py`` tracks builds in-memory (a driver thread + a reaper), which a restart orphans
(SYSTEM.md §3d). Modeling runs as persisted records is the first step toward real durability: the
``Runner`` (see ``runner.py``) drives the state machine and writes it here, so a poller can see live
status and a restart can recover.

``InMemoryRunStore`` is the simplest backend; ``FilesystemRunStore`` persists each run as JSON under
the project (matching the filename-state philosophy) so dev runs survive a restart. Production swaps a
Postgres-backed store + a real workflow engine (Temporal/Inngest) behind the same interface.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PAUSED = "paused"      # transient failure — resumable (mirrors orchestration's pause policy)
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in (RunStatus.SUCCEEDED, RunStatus.PAUSED, RunStatus.FAILED)


@dataclass(slots=True)
class Run:
    id: str
    slug: str
    kind: str  # "assemble" | "process-edits" | "diagnostic"
    status: RunStatus = RunStatus.QUEUED
    created: str = ""
    started: str = ""
    finished: str = ""
    result: dict[str, Any] | None = None  # the CommandOutcome, on terminal success/pause
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "kind": self.kind,
            "status": self.status.value,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "result": self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Run":
        return cls(
            id=d["id"],
            slug=d["slug"],
            kind=d["kind"],
            status=RunStatus(d.get("status", "queued")),
            created=d.get("created", ""),
            started=d.get("started", ""),
            finished=d.get("finished", ""),
            result=d.get("result"),
            error=d.get("error", ""),
        )


class RunStore(ABC):
    @abstractmethod
    def create(self, run: Run) -> Run: ...

    @abstractmethod
    def save(self, run: Run) -> Run: ...

    @abstractmethod
    def get(self, run_id: str) -> Run | None: ...

    @abstractmethod
    def list(self, slug: str | None = None) -> list[Run]:
        """All runs (optionally for one project), newest-first by created timestamp."""


class InMemoryRunStore(RunStore):
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def create(self, run: Run) -> Run:
        self._runs[run.id] = run
        return run

    def save(self, run: Run) -> Run:
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def list(self, slug: str | None = None) -> list[Run]:
        runs = [r for r in self._runs.values() if slug is None or r.slug == slug]
        return sorted(runs, key=lambda r: r.created, reverse=True)


class FilesystemRunStore(RunStore):
    """Persists runs as ``<clients_root>/<slug>/02-intake/runs/<id>.json``."""

    def __init__(self, clients_root: str | Path) -> None:
        self._root = Path(clients_root)

    def _dir(self, slug: str) -> Path:
        return self._root / slug / "02-intake" / "runs"

    def _path(self, run: Run) -> Path:
        return self._dir(run.slug) / f"{run.id}.json"

    def create(self, run: Run) -> Run:
        return self.save(run)

    def save(self, run: Run) -> Run:
        p = self._path(run)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(run.to_dict(), indent=2) + "\n")
        return run

    def get(self, run_id: str) -> Run | None:
        # run_id is unique; scan project run dirs for the file.
        if not self._root.is_dir():
            return None
        for proj in self._root.iterdir():
            f = proj / "02-intake" / "runs" / f"{run_id}.json"
            if f.is_file():
                return Run.from_dict(json.loads(f.read_text()))
        return None

    def list(self, slug: str | None = None) -> list[Run]:
        runs: list[Run] = []
        slugs = [slug] if slug else (
            [p.name for p in self._root.iterdir() if p.is_dir()] if self._root.is_dir() else []
        )
        for s in slugs:
            d = self._dir(s)
            if d.is_dir():
                for f in d.glob("*.json"):
                    try:
                        runs.append(Run.from_dict(json.loads(f.read_text())))
                    except (OSError, ValueError):
                        continue
        return sorted(runs, key=lambda r: r.created, reverse=True)
