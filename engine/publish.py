"""The publish seam (PUBLISH-ALWAYS).

A headless ``claude -p`` build cannot authorize the outbound ``wrangler pages deploy`` — so the deploy
is owned by an authed surface (today: ``studio.py``'s ``publish_preview`` from the operator's shell;
in prod: a worker holding the project's scoped Cloudflare token). ``Publisher`` abstracts that.

Contract: ``publish_preview`` returns the live preview URL on success, or ``None`` on failure. On
``None`` the orchestrator keeps the prior URL and flags it stale — never a silent stale URL
(CLAUDE.md PUBLISH-ALWAYS, SYSTEM.md §3 "studio-owned publish net").
"""

from __future__ import annotations

import os
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class Publisher(ABC):
    @abstractmethod
    def publish_preview(self, slug: str) -> str | None:
        """Deploy the project's current build to its private preview. Returns the URL, or None."""


class MockPublisher(Publisher):
    """Test double — returns a synthetic URL (or None to simulate a deploy failure)."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def publish_preview(self, slug: str) -> str | None:
        self.calls.append(slug)
        if self.fail:
            return None
        return f"https://ws-{slug}.pages.dev"


class UnconfiguredPublisher(Publisher):
    """A publisher that never deploys — for environments where deploy isn't wired (e.g. the dev API).

    Returns ``None`` so the orchestrator does the honest thing: keeps the prior preview URL and flags
    it stale, rather than pretending a deploy happened. Wire a real publisher (studio-owned wrangler
    deploy, or a worker holding the project's Cloudflare token) for production.
    """

    def publish_preview(self, slug: str) -> str | None:
        return None


class WranglerPublisher(Publisher):
    """Studio-owned Cloudflare Pages deploy — the production ``Publisher`` (task 4.7).

    Deploys ``<root>/<slug>/<site_subdir>/dist`` to the project's PRIVATE preview
    (``ws-<slug>.pages.dev``) via ``wrangler pages deploy``, returning the stable base URL on
    success or ``None`` on any failure (the orchestrator then keeps the prior URL + flags it stale —
    never a silent stale URL). Mirrors ``studio.py``'s ``publish_preview`` idiom: ensure the Pages
    project exists (deploy does not auto-create it), deploy the already-built ``dist`` (staging
    noindex is baked into the build, never here), then parse the ``*.pages.dev`` URL from output.

    Pure w.r.t. project state: it shells ``wrangler`` and returns a URL; it never writes status —
    ``run_command`` owns ``set_preview`` / ``mark_preview_stale``. Requires ``wrangler`` on PATH and
    an authed Cloudflare account (``wrangler login`` / ``CLOUDFLARE_API_TOKEN``); the deploy runs in
    the operator's authed surface, never inside a headless ``claude -p`` turn.

    ``dry_run`` (or ``$WS_DEPLOY_DRYRUN`` truthy) synthesises the base URL without calling wrangler —
    for plumbing tests and offline wiring checks. A missing ``dist`` always returns ``None``.
    """

    _URL = re.compile(r"https://[^\s]+\.pages\.dev")

    def __init__(
        self,
        root: str | Path,
        *,
        project_prefix: str = "ws-",
        site_subdir: str = "03-site",
        cwd: str | Path | None = None,
        timeout: int = 600,
        dry_run: bool | None = None,
    ) -> None:
        self.root = Path(root)
        self.project_prefix = project_prefix
        self.site_subdir = site_subdir
        self.cwd = str(cwd) if cwd is not None else None
        self.timeout = timeout
        self.dry_run = dry_run

    def project_name(self, slug: str) -> str:
        return f"{self.project_prefix}{slug}"

    def dist_dir(self, slug: str) -> Path:
        return self.root / slug / self.site_subdir / "dist"

    def _is_dry(self) -> bool:
        if self.dry_run is not None:
            return self.dry_run
        return os.environ.get("WS_DEPLOY_DRYRUN") not in (None, "", "0")

    def publish_preview(self, slug: str) -> str | None:
        dist = self.dist_dir(slug)
        if not dist.is_dir():
            return None
        project = self.project_name(slug)
        base = f"https://{project}.pages.dev"
        if self._is_dry():
            return base
        self._ensure_project(project)
        try:
            proc = subprocess.run(
                ["wrangler", "pages", "deploy", str(dist),
                 "--project-name", project, "--commit-dirty=true"],
                cwd=self.cwd, capture_output=True, text=True, timeout=self.timeout,
            )
        except Exception:
            return None
        out = (proc.stdout or "") + (proc.stderr or "")
        url = next((m.group(0) for m in self._URL.finditer(out)), None)
        if proc.returncode == 0 and url:
            return base  # the stable alias, not the per-deploy hash URL
        return None

    def _ensure_project(self, project: str) -> None:
        """Create the Pages project on demand (deploy never auto-creates it). A pre-existing project
        just returns a harmless error we ignore — idempotent."""
        try:
            subprocess.run(
                ["wrangler", "pages", "project", "create", project,
                 "--production-branch", "main"],
                cwd=self.cwd, capture_output=True, text=True, timeout=120,
            )
        except Exception:
            pass
