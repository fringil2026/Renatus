"""SQL-backed ``ProjectStore`` + ``RunStore`` — the production persistence path (ADR-0001 §3).

Targets a DB-API 2.0 connection and is written to run on **both sqlite (dev/test) and Postgres
(prod)** with one knob — the parameter placeholder (``?`` vs ``%s``). The schema is deliberately
thin: the rich state is a JSON blob (``data``) — projects/runs already serialize via ``to_dict`` —
alongside a few indexed columns for the queries we actually run (slug, stage, status). On Postgres the
blob column is `JSONB`; here it's `TEXT` + ``json`` in Python. Both DBs support ``ON CONFLICT`` upsert.

Artifacts (scrapes, assets, ``dist``) are **not** in SQL — they're blobs that belong in object
storage (R2). ``SqlProjectStore`` takes an ``artifacts_factory``; production injects an R2-backed
``ArtifactStore``, tests use the in-memory one here.

Parity with ``FilesystemProjectStore`` is enforced by the shared contract suite in
``tests/test_store_conformance.py`` (the same battery runs against both backends).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, Callable

from .errors import ImmutableTransition, ProjectExists, ReportExists
from .fs_store import _slugify
from .models import (
    Decision,
    DecisionState,
    Edit,
    EditState,
    Incident,
    IncidentState,
    Project,
    Report,
)
from .runs import Run, RunStore
from .store import ArtifactStore, ProjectStore

_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS projects (slug TEXT PRIMARY KEY, stage TEXT, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS edits (slug TEXT, n INTEGER, name TEXT, state TEXT, body TEXT, "
    "PRIMARY KEY (slug, n))",
    "CREATE TABLE IF NOT EXISTS decisions (slug TEXT, n INTEGER, name TEXT, state TEXT, body TEXT, "
    "PRIMARY KEY (slug, n))",
    "CREATE TABLE IF NOT EXISTS incidents (slug TEXT, n INTEGER, name TEXT, state TEXT, body TEXT, "
    "PRIMARY KEY (slug, n))",
    "CREATE TABLE IF NOT EXISTS reports (slug TEXT, ts TEXT, kind TEXT, body TEXT, "
    "PRIMARY KEY (slug, ts, kind))",
    "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, slug TEXT, status TEXT, data TEXT NOT NULL)",
]


class InMemoryArtifactStore(ArtifactStore):
    """A non-persistent artifact store for tests / the SQL store default (prod uses R2)."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = data

    def get(self, key: str) -> bytes:
        if key not in self._blobs:
            raise KeyError(key)
        return self._blobs[key]

    def exists(self, key: str) -> bool:
        return key in self._blobs

    def list(self, prefix: str = "") -> Iterable[str]:
        return sorted(k for k in self._blobs if k.startswith(prefix))

    def url(self, key: str) -> str:
        return f"memory://{key}"


class _SqlBase:
    def __init__(self, conn: Any, *, placeholder: str = "?") -> None:
        self._conn = conn
        self._ph = placeholder
        cur = conn.cursor()
        for stmt in _SCHEMA:
            cur.execute(stmt)
        conn.commit()

    def _q(self, sql: str) -> str:
        """Substitute the dialect placeholder for the ``%s`` markers written in queries."""
        return sql.replace("%s", self._ph)

    def _exec(self, sql: str, params: tuple = ()) -> Any:
        cur = self._conn.cursor()
        cur.execute(self._q(sql), params)
        return cur


class SqlProjectStore(_SqlBase, ProjectStore):
    def __init__(
        self,
        conn: Any,
        *,
        placeholder: str = "?",
        artifacts_factory: Callable[[str], ArtifactStore] | None = None,
    ) -> None:
        super().__init__(conn, placeholder=placeholder)
        self._artifacts_factory = artifacts_factory or (lambda _slug: InMemoryArtifactStore())
        self._artifacts: dict[str, ArtifactStore] = {}

    # -- projects ---------------------------------------------------------- #
    def list_projects(self) -> list[str]:
        rows = self._exec("SELECT slug FROM projects ORDER BY slug").fetchall()
        return [r[0] for r in rows]

    def get_project(self, slug: str) -> Project | None:
        row = self._exec("SELECT data FROM projects WHERE slug = %s", (slug,)).fetchone()
        return Project.from_dict(slug, json.loads(row[0])) if row else None

    def create_project(self, project: Project) -> Project:
        if self.get_project(project.slug) is not None:
            raise ProjectExists(project.slug)
        return self.save_project(project)

    def save_project(self, project: Project) -> Project:
        self._exec(
            "INSERT INTO projects (slug, stage, data) VALUES (%s, %s, %s) "
            "ON CONFLICT(slug) DO UPDATE SET stage = excluded.stage, data = excluded.data",
            (project.slug, project.stage.value, json.dumps(project.to_dict())),
        )
        self._conn.commit()
        return project

    # -- generic NNN ledger helpers ---------------------------------------- #
    def _filename(self, n: int, state: str, name: str, ext: str) -> str:
        return f"{n:03d}-{state}-{name}.{ext}"

    def _next_n(self, table: str, slug: str) -> int:
        row = self._exec(f"SELECT MAX(n) FROM {table} WHERE slug = %s", (slug,)).fetchone()
        return (row[0] or 0) + 1

    # -- edits ------------------------------------------------------------- #
    def list_edits(self, slug: str) -> list[Edit]:
        rows = self._exec(
            "SELECT n, name, state, body FROM edits WHERE slug = %s ORDER BY n", (slug,)
        ).fetchall()
        return [
            Edit(n=n, name=name, state=EditState(state), body=body or "",
                 filename=self._filename(n, state, name, "md"))
            for (n, name, state, body) in rows
        ]

    def create_edit(self, slug: str, name: str, body: str) -> Edit:
        n = self._next_n("edits", slug)
        sn = _slugify(name)
        self._exec(
            "INSERT INTO edits (slug, n, name, state, body) VALUES (%s, %s, %s, %s, %s)",
            (slug, n, sn, EditState.PENDING.value, body),
        )
        self._conn.commit()
        return Edit(n=n, name=sn, state=EditState.PENDING, body=body,
                    filename=self._filename(n, "PENDING", sn, "md"))

    def transition_edit(
        self, slug: str, n: int, state: EditState, *, resolution: str | None = None
    ) -> Edit:
        row = self._exec("SELECT name, state, body FROM edits WHERE slug = %s AND n = %s", (slug, n)).fetchone()
        if row is None:
            raise KeyError(f"edit {n} not found in {slug}")
        name, cur_state, body = row[0], row[1], row[2] or ""
        if EditState(cur_state) is not EditState.PENDING:
            raise ImmutableTransition(f"edit {n} is {cur_state} (immutable)")
        if resolution:
            sep = "" if body.endswith("\n") else "\n"
            body = f"{body}{sep}\n## Resolution\n{resolution}\n"
        self._exec("UPDATE edits SET state = %s, body = %s WHERE slug = %s AND n = %s",
                   (state.value, body, slug, n))
        self._conn.commit()
        return Edit(n=n, name=name, state=state, body=body, filename=self._filename(n, state.value, name, "md"))

    # -- decisions --------------------------------------------------------- #
    def list_decisions(self, slug: str) -> list[Decision]:
        rows = self._exec(
            "SELECT n, name, state, body FROM decisions WHERE slug = %s ORDER BY n", (slug,)
        ).fetchall()
        return [
            Decision(n=n, name=name, state=DecisionState(state), body=body or "",
                     filename=self._filename(n, state, name, "yaml"))
            for (n, name, state, body) in rows
        ]

    def create_decision(self, slug: str, name: str, body: str) -> Decision:
        n = self._next_n("decisions", slug)
        sn = _slugify(name)
        self._exec(
            "INSERT INTO decisions (slug, n, name, state, body) VALUES (%s, %s, %s, %s, %s)",
            (slug, n, sn, DecisionState.OPEN.value, body),
        )
        self._conn.commit()
        return Decision(n=n, name=sn, state=DecisionState.OPEN, body=body,
                        filename=self._filename(n, "OPEN", sn, "yaml"))

    def resolve_decision(self, slug: str, n: int, *, choice: str | None = None) -> Decision:
        row = self._exec("SELECT name, state, body FROM decisions WHERE slug = %s AND n = %s", (slug, n)).fetchone()
        if row is None:
            raise KeyError(f"decision {n} not found in {slug}")
        name, cur_state, body = row[0], row[1], row[2] or ""
        if DecisionState(cur_state) is DecisionState.RESOLVED:
            raise ImmutableTransition(f"decision {n} already RESOLVED (immutable)")
        if choice:
            sep = "" if body.endswith("\n") else "\n"
            body = f"{body}{sep}resolved_choice: {choice}\n"
        self._exec("UPDATE decisions SET state = %s, body = %s WHERE slug = %s AND n = %s",
                   (DecisionState.RESOLVED.value, body, slug, n))
        self._conn.commit()
        return Decision(n=n, name=name, state=DecisionState.RESOLVED, body=body,
                        filename=self._filename(n, "RESOLVED", name, "yaml"))

    # -- incidents --------------------------------------------------------- #
    def list_incidents(self, slug: str) -> list[Incident]:
        rows = self._exec(
            "SELECT n, name, state, body FROM incidents WHERE slug = %s ORDER BY n", (slug,)
        ).fetchall()
        return [
            Incident(n=n, name=name, state=IncidentState(state), body=body or "",
                     filename=self._filename(n, state, name, "md"))
            for (n, name, state, body) in rows
        ]

    def create_incident(self, slug: str, name: str, body: str) -> Incident:
        n = self._next_n("incidents", slug)
        sn = _slugify(name)
        self._exec(
            "INSERT INTO incidents (slug, n, name, state, body) VALUES (%s, %s, %s, %s, %s)",
            (slug, n, sn, IncidentState.OPEN.value, body),
        )
        self._conn.commit()
        return Incident(n=n, name=sn, state=IncidentState.OPEN, body=body,
                        filename=self._filename(n, "OPEN", sn, "md"))

    def transition_incident(self, slug: str, n: int, state: IncidentState) -> Incident:
        row = self._exec("SELECT name, state, body FROM incidents WHERE slug = %s AND n = %s", (slug, n)).fetchone()
        if row is None:
            raise KeyError(f"incident {n} not found in {slug}")
        name, cur_state, body = row[0], row[1], row[2] or ""
        if IncidentState(cur_state) is IncidentState.RESOLVED:
            raise ImmutableTransition(f"incident {n} already RESOLVED (immutable)")
        self._exec("UPDATE incidents SET state = %s WHERE slug = %s AND n = %s", (state.value, slug, n))
        self._conn.commit()
        return Incident(n=n, name=name, state=state, body=body, filename=self._filename(n, state.value, name, "md"))

    # -- reports (append-only) --------------------------------------------- #
    def list_reports(self, slug: str) -> list[Report]:
        rows = self._exec(
            "SELECT ts, kind, body FROM reports WHERE slug = %s ORDER BY ts DESC", (slug,)
        ).fetchall()
        return [
            Report(timestamp=ts, kind=kind, body=body or "", filename=f"{ts}-{kind}.md")
            for (ts, kind, body) in rows
        ]

    def add_report(self, slug: str, kind: str, body: str, *, timestamp: str) -> Report:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{4}", timestamp):
            raise ValueError(f"report timestamp must be YYYY-MM-DD-HHMM, got {timestamp!r}")
        k = _slugify(kind)
        exists = self._exec(
            "SELECT 1 FROM reports WHERE slug = %s AND ts = %s AND kind = %s", (slug, timestamp, k)
        ).fetchone()
        if exists:
            raise ReportExists(f"{timestamp}-{k}.md")
        self._exec("INSERT INTO reports (slug, ts, kind, body) VALUES (%s, %s, %s, %s)",
                   (slug, timestamp, k, body))
        self._conn.commit()
        return Report(timestamp=timestamp, kind=k, body=body, filename=f"{timestamp}-{k}.md")

    # -- artifacts --------------------------------------------------------- #
    def artifacts(self, slug: str) -> ArtifactStore:
        if slug not in self._artifacts:
            self._artifacts[slug] = self._artifacts_factory(slug)
        return self._artifacts[slug]


class SqlRunStore(_SqlBase, RunStore):
    def create(self, run: Run) -> Run:
        return self.save(run)

    def save(self, run: Run) -> Run:
        self._exec(
            "INSERT INTO runs (id, slug, status, data) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT(id) DO UPDATE SET slug = excluded.slug, status = excluded.status, data = excluded.data",
            (run.id, run.slug, run.status.value, json.dumps(run.to_dict())),
        )
        self._conn.commit()
        return run

    def get(self, run_id: str) -> Run | None:
        row = self._exec("SELECT data FROM runs WHERE id = %s", (run_id,)).fetchone()
        return Run.from_dict(json.loads(row[0])) if row else None

    def list(self, slug: str | None = None) -> list[Run]:
        if slug is None:
            rows = self._exec("SELECT data FROM runs").fetchall()
        else:
            rows = self._exec("SELECT data FROM runs WHERE slug = %s", (slug,)).fetchall()
        runs = [Run.from_dict(json.loads(r[0])) for r in rows]
        return sorted(runs, key=lambda r: r.created, reverse=True)
