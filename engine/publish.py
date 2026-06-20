"""The publish seam (PUBLISH-ALWAYS).

A headless ``claude -p`` build cannot authorize the outbound ``wrangler pages deploy`` — so the deploy
is owned by an authed surface (today: ``studio.py``'s ``publish_preview`` from the operator's shell;
in prod: a worker holding the project's scoped Cloudflare token). ``Publisher`` abstracts that.

Contract: ``publish_preview`` returns the live preview URL on success, or ``None`` on failure. On
``None`` the orchestrator keeps the prior URL and flags it stale — never a silent stale URL
(CLAUDE.md PUBLISH-ALWAYS, SYSTEM.md §3 "studio-owned publish net").
"""

from __future__ import annotations

from abc import ABC, abstractmethod


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
