"""Tests for the publish seam — MockPublisher, UnconfiguredPublisher, and the real WranglerPublisher.

WranglerPublisher is exercised in dry-run (``dry_run=True`` / ``$WS_DEPLOY_DRYRUN``) so no wrangler
binary or Cloudflare account is touched — only the plumbing (dist resolution, project naming, the
missing-dist -> None contract) is checked. The subprocess path is intentionally not invoked here.

    python3 tests/test_publish.py     # standalone
    pytest tests/test_publish.py       # also works
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    MockPublisher,
    UnconfiguredPublisher,
    WranglerPublisher,
)


def _root() -> tuple[Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    return Path(tmp.name), tmp


def _make_dist(root: Path, slug: str, subdir: str = "03-site") -> None:
    (root / slug / subdir / "dist").mkdir(parents=True)


def test_mock_publisher_returns_synthetic_url() -> None:
    pub = MockPublisher()
    assert pub.publish_preview("acme") == "https://ws-acme.pages.dev"
    assert pub.calls == ["acme"]


def test_mock_publisher_can_simulate_failure() -> None:
    assert MockPublisher(fail=True).publish_preview("acme") is None


def test_unconfigured_never_deploys() -> None:
    assert UnconfiguredPublisher().publish_preview("acme") is None


def test_wrangler_dryrun_synthesises_base_url() -> None:
    root, tmp = _root()
    try:
        _make_dist(root, "acme")
        pub = WranglerPublisher(root, dry_run=True)
        assert pub.publish_preview("acme") == "https://ws-acme.pages.dev"
    finally:
        tmp.cleanup()


def test_wrangler_missing_dist_returns_none() -> None:
    root, tmp = _root()
    try:
        # no dist created — must not deploy, even in dry-run
        pub = WranglerPublisher(root, dry_run=True)
        assert pub.publish_preview("ghost") is None
    finally:
        tmp.cleanup()


def test_wrangler_project_prefix_and_subdir_are_honoured() -> None:
    root, tmp = _root()
    try:
        _make_dist(root, "acme", subdir="site")
        pub = WranglerPublisher(root, project_prefix="tenant42-", site_subdir="site", dry_run=True)
        assert pub.project_name("acme") == "tenant42-acme"
        assert pub.dist_dir("acme") == root / "acme" / "site" / "dist"
        assert pub.publish_preview("acme") == "https://tenant42-acme.pages.dev"
    finally:
        tmp.cleanup()


def test_wrangler_dryrun_via_env(monkeypatch=None) -> None:
    import os

    root, tmp = _root()
    prev = os.environ.get("WS_DEPLOY_DRYRUN")
    try:
        _make_dist(root, "acme")
        os.environ["WS_DEPLOY_DRYRUN"] = "1"
        pub = WranglerPublisher(root)  # no explicit dry_run → reads env
        assert pub.publish_preview("acme") == "https://ws-acme.pages.dev"
    finally:
        if prev is None:
            os.environ.pop("WS_DEPLOY_DRYRUN", None)
        else:
            os.environ["WS_DEPLOY_DRYRUN"] = prev
        tmp.cleanup()


# --------------------------------------------------------------------------- #
# Standalone runner
# --------------------------------------------------------------------------- #
def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    total = len(tests)
    print(f"\n{total - failed}/{total} passed" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
