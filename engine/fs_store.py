"""Filesystem-backed ``ProjectStore`` over the existing ``clients/<slug>/`` layout.

This is the dev/parity implementation: it reads and writes exactly the files the studio uses today, so
the new engine and the live ``studio.py`` can operate on the same tree during the migration. The
production store (Postgres + R2) will implement the same ``ProjectStore`` interface; engine code above
the interface won't know the difference.

Layout it maps onto::

    clients/<slug>/
      status.json                       -> Project
      02-intake/edits/NNN-STATE-name.md       -> Edit
      02-intake/decisions/NNN-STATE-name.yaml -> Decision
      02-intake/incidents/NNN-STATE-name.md   -> Incident
      02-intake/reports/<ts>-<kind>.md        -> Report
      <anything>                        -> artifact blobs (keyed by path relative to the client root)
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from .errors import ImmutableTransition, ProjectExists, ReportExists
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
from .store import ArtifactStore, ProjectStore

_INTAKE = "02-intake"


def _slugify(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in name.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "item"


class FilesystemArtifactStore(ArtifactStore):
    """Artifacts as files under the project root, keyed by relative path."""

    def __init__(self, root: Path) -> None:
        # Resolve once so every path comparison below is consistent (avoids the macOS
        # /var -> /private/var symlink mismatch between resolved and unresolved paths).
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        # Prevent escaping the project root via ``..`` or absolute keys.
        p = (self._root / key).resolve()
        if p != self._root and self._root not in p.parents:
            raise ValueError(f"artifact key escapes project root: {key!r}")
        return p

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        p = self._path(key)
        if not p.is_file():
            raise KeyError(key)
        return p.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> Iterable[str]:
        base = self._path(prefix) if prefix else self._root
        if base.is_file():
            yield str(base.relative_to(self._root))
            return
        if not base.is_dir():
            return
        for p in sorted(base.rglob("*")):
            if p.is_file():
                yield str(p.relative_to(self._root))

    def url(self, key: str) -> str:
        return str(self._path(key))


class FilesystemProjectStore(ProjectStore):
    """``ProjectStore`` over ``<clients_root>/<slug>/``."""

    def __init__(self, clients_root: str | Path) -> None:
        self._root = Path(clients_root)

    # -- paths ------------------------------------------------------------- #
    def _proj_dir(self, slug: str) -> Path:
        return self._root / slug

    def _status_path(self, slug: str) -> Path:
        return self._proj_dir(slug) / "status.json"

    def _edits_dir(self, slug: str) -> Path:
        return self._proj_dir(slug) / _INTAKE / "edits"

    def _decisions_dir(self, slug: str) -> Path:
        return self._proj_dir(slug) / _INTAKE / "decisions"

    def _incidents_dir(self, slug: str) -> Path:
        return self._proj_dir(slug) / _INTAKE / "incidents"

    def _reports_dir(self, slug: str) -> Path:
        return self._proj_dir(slug) / _INTAKE / "reports"

    # -- projects ---------------------------------------------------------- #
    def list_projects(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(
            p.name for p in self._root.iterdir() if p.is_dir() and (p / "status.json").is_file()
        )

    def get_project(self, slug: str) -> Project | None:
        sp = self._status_path(slug)
        if not sp.is_file():
            return None
        data = json.loads(sp.read_text())
        return Project.from_dict(slug, data)

    def create_project(self, project: Project) -> Project:
        if self._status_path(project.slug).is_file():
            raise ProjectExists(project.slug)
        return self.save_project(project)

    def save_project(self, project: Project) -> Project:
        sp = self._status_path(project.slug)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False) + "\n")
        return project

    # -- generic NNN-STATE-name helpers ------------------------------------ #
    @staticmethod
    def _read_text(p: Path) -> str:
        try:
            return p.read_text()
        except (OSError, UnicodeDecodeError):
            return ""

    # -- edits ------------------------------------------------------------- #
    def list_edits(self, slug: str) -> list[Edit]:
        d = self._edits_dir(slug)
        out: list[Edit] = []
        if d.is_dir():
            for p in d.iterdir():
                parsed = Edit.parse_filename(p.name)
                if parsed is None:
                    continue
                n, state, name = parsed
                try:
                    st = EditState(state)
                except ValueError:
                    continue
                out.append(Edit(n=n, name=name, state=st, body=self._read_text(p), filename=p.name))
        out.sort(key=lambda e: e.n)
        return out

    def create_edit(self, slug: str, name: str, body: str) -> Edit:
        n = self.next_edit_n(slug)
        slug_name = _slugify(name)
        d = self._edits_dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{n:03d}-PENDING-{slug_name}.md"
        (d / fn).write_text(body)
        return Edit(n=n, name=slug_name, state=EditState.PENDING, body=body, filename=fn)

    def transition_edit(
        self, slug: str, n: int, state: EditState, *, resolution: str | None = None
    ) -> Edit:
        existing = {e.n: e for e in self.list_edits(slug)}
        edit = existing.get(n)
        if edit is None:
            raise KeyError(f"edit {n} not found in {slug}")
        if edit.state is not EditState.PENDING:
            raise ImmutableTransition(
                f"edit {n} is {edit.state.value} (immutable); cannot transition to {state.value}"
            )
        d = self._edits_dir(slug)
        old = d / edit.filename
        body = edit.body
        if resolution:
            sep = "" if body.endswith("\n") else "\n"
            body = f"{body}{sep}\n## Resolution\n{resolution}\n"
        new_fn = f"{n:03d}-{state.value}-{edit.name}.md"
        (d / new_fn).write_text(body)
        if old.name != new_fn and old.is_file():
            old.unlink()
        return Edit(n=n, name=edit.name, state=state, body=body, filename=new_fn)

    # -- decisions --------------------------------------------------------- #
    def list_decisions(self, slug: str) -> list[Decision]:
        d = self._decisions_dir(slug)
        out: list[Decision] = []
        if d.is_dir():
            for p in d.iterdir():
                parsed = Decision.parse_filename(p.name)
                if parsed is None:
                    continue
                n, state, name = parsed
                try:
                    st = DecisionState(state)
                except ValueError:
                    continue
                out.append(
                    Decision(n=n, name=name, state=st, body=self._read_text(p), filename=p.name)
                )
        out.sort(key=lambda x: x.n)
        return out

    def create_decision(self, slug: str, name: str, body: str) -> Decision:
        n = self.next_decision_n(slug)
        slug_name = _slugify(name)
        d = self._decisions_dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{n:03d}-OPEN-{slug_name}.yaml"
        (d / fn).write_text(body)
        return Decision(n=n, name=slug_name, state=DecisionState.OPEN, body=body, filename=fn)

    def resolve_decision(self, slug: str, n: int, *, choice: str | None = None) -> Decision:
        existing = {x.n: x for x in self.list_decisions(slug)}
        dec = existing.get(n)
        if dec is None:
            raise KeyError(f"decision {n} not found in {slug}")
        if dec.state is DecisionState.RESOLVED:
            raise ImmutableTransition(f"decision {n} already RESOLVED (immutable)")
        d = self._decisions_dir(slug)
        old = d / dec.filename
        body = dec.body
        if choice:
            sep = "" if body.endswith("\n") else "\n"
            body = f"{body}{sep}resolved_choice: {choice}\n"
        new_fn = f"{n:03d}-RESOLVED-{dec.name}.yaml"
        (d / new_fn).write_text(body)
        if old.name != new_fn and old.is_file():
            old.unlink()
        return Decision(n=n, name=dec.name, state=DecisionState.RESOLVED, body=body, filename=new_fn)

    # -- incidents --------------------------------------------------------- #
    def list_incidents(self, slug: str) -> list[Incident]:
        d = self._incidents_dir(slug)
        out: list[Incident] = []
        if d.is_dir():
            for p in d.iterdir():
                parsed = Incident.parse_filename(p.name)
                if parsed is None:
                    continue
                n, state, name = parsed
                try:
                    st = IncidentState(state)
                except ValueError:
                    continue
                out.append(
                    Incident(n=n, name=name, state=st, body=self._read_text(p), filename=p.name)
                )
        out.sort(key=lambda x: x.n)
        return out

    def create_incident(self, slug: str, name: str, body: str) -> Incident:
        n = self.next_incident_n(slug)
        slug_name = _slugify(name)
        d = self._incidents_dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{n:03d}-OPEN-{slug_name}.md"
        (d / fn).write_text(body)
        return Incident(n=n, name=slug_name, state=IncidentState.OPEN, body=body, filename=fn)

    def transition_incident(self, slug: str, n: int, state: IncidentState) -> Incident:
        existing = {x.n: x for x in self.list_incidents(slug)}
        inc = existing.get(n)
        if inc is None:
            raise KeyError(f"incident {n} not found in {slug}")
        if inc.state is IncidentState.RESOLVED:
            raise ImmutableTransition(f"incident {n} already RESOLVED (immutable)")
        d = self._incidents_dir(slug)
        old = d / inc.filename
        new_fn = f"{n:03d}-{state.value}-{inc.name}.md"
        (d / new_fn).write_text(inc.body)
        if old.name != new_fn and old.is_file():
            old.unlink()
        return Incident(n=n, name=inc.name, state=state, body=inc.body, filename=new_fn)

    # -- reports (append-only) --------------------------------------------- #
    def list_reports(self, slug: str) -> list[Report]:
        d = self._reports_dir(slug)
        out: list[Report] = []
        if d.is_dir():
            for p in d.iterdir():
                parsed = Report.parse_filename(p.name)
                if parsed is None:
                    continue
                ts, kind = parsed
                out.append(Report(timestamp=ts, kind=kind, body=self._read_text(p), filename=p.name))
        out.sort(key=lambda r: r.timestamp, reverse=True)  # newest first
        return out

    def add_report(self, slug: str, kind: str, body: str, *, timestamp: str) -> Report:
        # Fail fast on a malformed stamp: the report-filename convention is YYYY-MM-DD-HHMM, and a
        # non-conforming stamp would write a report that list_reports() can never discover.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{4}", timestamp):
            raise ValueError(f"report timestamp must be YYYY-MM-DD-HHMM, got {timestamp!r}")
        d = self._reports_dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        fn = f"{timestamp}-{_slugify(kind)}.md"
        p = d / fn
        if p.exists():
            raise ReportExists(fn)
        p.write_text(body)
        return Report(timestamp=timestamp, kind=_slugify(kind), body=body, filename=fn)

    # -- artifacts --------------------------------------------------------- #
    def artifacts(self, slug: str) -> ArtifactStore:
        return FilesystemArtifactStore(self._proj_dir(slug))
