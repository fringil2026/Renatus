"""The persistence boundary for the rebuild engine.

``ProjectStore`` is the single seam that decouples the engine (and, after refactor, the skills) from
*where* state lives. Today the only implementation is ``FilesystemProjectStore`` (``fs_store.py``),
which maps these calls onto the existing ``clients/<slug>/`` layout. In production a
``PostgresProjectStore`` + R2-backed ``ArtifactStore`` will implement the same interface, and the
engine code above this line will not change.

Design rules baked into the interface (so every backend enforces them):

* **Append-only history.** ``add_report`` only ever creates; there is no ``update_report``. DONE/
  BLOCKED edits and RESOLVED decisions/incidents are immutable — the state-transition methods refuse
  to move *out* of a terminal state.
* **Monotonic numbering.** ``next_edit_n`` etc. return ``max(existing) + 1`` — robust to gaps left by
  DONE/BLOCKED items (matches today's ``_next_edit_n``).
* **Artifacts are opaque blobs** addressed by a string key (e.g. ``00-source/crawl.json``,
  ``03-site/dist/index.html``). The filesystem store keys on relative paths; the object-storage store
  keys on ``<tenant>/<project>/<key>``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .models import (
    Decision,
    DecisionState,
    Edit,
    EditState,
    Incident,
    IncidentState,
    Project,
    Report,
    Stage,
)


class ArtifactStore(ABC):
    """Opaque blob storage for a single project (scrapes, assets, screenshots, dist, boards)."""

    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Return the blob, or raise ``KeyError`` if absent."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str = "") -> Iterable[str]:
        """Yield artifact keys under ``prefix`` (recursive)."""

    @abstractmethod
    def url(self, key: str) -> str:
        """A retrieval URL/path for the blob (a local path today, a signed URL in prod)."""


class ProjectStore(ABC):
    """CRUD + lifecycle for projects and their filename-state artifacts.

    All methods are scoped by ``slug`` (the project id). A production implementation additionally
    scopes by tenant; that scoping lives in the constructor/session, not the method signatures, so the
    engine code stays tenant-agnostic.
    """

    # -- projects ---------------------------------------------------------- #
    @abstractmethod
    def list_projects(self) -> list[str]:
        """Return all project slugs known to this store."""

    @abstractmethod
    def get_project(self, slug: str) -> Project | None:
        """Load a project, or ``None`` if it does not exist."""

    @abstractmethod
    def create_project(self, project: Project) -> Project:
        """Persist a new project. Raises if the slug already exists."""

    @abstractmethod
    def save_project(self, project: Project) -> Project:
        """Persist the full project state (upsert of an existing project)."""

    # Convenience mutators (default implementations on top of get/save). --- #
    def set_stage(self, slug: str, stage: Stage, log_message: str | None = None) -> Project:
        p = self._require(slug)
        p.stage = stage
        if log_message:
            p.log.append(log_message)
        return self.save_project(p)

    def append_log(self, slug: str, message: str) -> Project:
        p = self._require(slug)
        p.log.append(message)
        return self.save_project(p)

    def set_preview(
        self, slug: str, url: str, published_at: str, *, stale: bool = False
    ) -> Project:
        p = self._require(slug)
        p.preview_url = url
        p.preview_published_at = published_at
        p.preview_stale = stale
        return self.save_project(p)

    def mark_preview_stale(self, slug: str) -> Project:
        """Deploy-failure path: keep the old URL, flag it stale (never a silent stale URL)."""
        p = self._require(slug)
        p.preview_stale = True
        return self.save_project(p)

    def _require(self, slug: str) -> Project:
        p = self.get_project(slug)
        if p is None:
            raise KeyError(f"unknown project: {slug!r}")
        return p

    # -- edits (CLAUDE.md Command 5) --------------------------------------- #
    @abstractmethod
    def list_edits(self, slug: str) -> list[Edit]:
        """All edits, ascending by ``n``."""

    @abstractmethod
    def create_edit(self, slug: str, name: str, body: str) -> Edit:
        """Create a new ``PENDING`` edit, auto-numbered ``next_edit_n``. Returns the created edit."""

    @abstractmethod
    def transition_edit(
        self, slug: str, n: int, state: EditState, *, resolution: str | None = None
    ) -> Edit:
        """Move a PENDING edit to DONE or BLOCKED, appending a ``## Resolution`` if given.

        Refuses to transition an already-terminal (DONE/BLOCKED) edit — they are immutable.
        """

    def pending_edits(self, slug: str) -> list[Edit]:
        return [e for e in self.list_edits(slug) if e.state is EditState.PENDING]

    def next_edit_n(self, slug: str) -> int:
        edits = self.list_edits(slug)
        return (max((e.n for e in edits), default=0)) + 1

    # -- decisions (CLAUDE.md "Decision surfaces") ------------------------- #
    @abstractmethod
    def list_decisions(self, slug: str) -> list[Decision]: ...

    @abstractmethod
    def create_decision(self, slug: str, name: str, body: str) -> Decision:
        """Create a new ``OPEN`` decision, auto-numbered."""

    @abstractmethod
    def resolve_decision(self, slug: str, n: int, *, choice: str | None = None) -> Decision:
        """Move an OPEN decision to RESOLVED (immutable thereafter)."""

    def open_decisions(self, slug: str) -> list[Decision]:
        return [d for d in self.list_decisions(slug) if d.state is DecisionState.OPEN]

    def next_decision_n(self, slug: str) -> int:
        return (max((d.n for d in self.list_decisions(slug)), default=0)) + 1

    # -- incidents (CLAUDE.md "Troubleshooting workflow") ------------------ #
    @abstractmethod
    def list_incidents(self, slug: str) -> list[Incident]: ...

    @abstractmethod
    def create_incident(self, slug: str, name: str, body: str) -> Incident:
        """Create a new ``OPEN`` incident, auto-numbered."""

    @abstractmethod
    def transition_incident(self, slug: str, n: int, state: IncidentState) -> Incident:
        """Move an incident's state; refuses to move out of RESOLVED (immutable)."""

    def open_incidents(self, slug: str) -> list[Incident]:
        return [i for i in self.list_incidents(slug) if i.state is not IncidentState.RESOLVED]

    def next_incident_n(self, slug: str) -> int:
        return (max((i.n for i in self.list_incidents(slug)), default=0)) + 1

    # -- reports (CLAUDE.md "Findings & reports") — APPEND-ONLY ------------ #
    @abstractmethod
    def list_reports(self, slug: str) -> list[Report]:
        """All reports, newest first."""

    @abstractmethod
    def add_report(self, slug: str, kind: str, body: str, *, timestamp: str) -> Report:
        """Append a new report. There is intentionally no update/delete — history is immutable."""

    # -- artifacts --------------------------------------------------------- #
    @abstractmethod
    def artifacts(self, slug: str) -> ArtifactStore:
        """The blob store for this project."""
