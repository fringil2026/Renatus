"""Tests for the engine's FilesystemProjectStore.

Two halves:

* **Read path** — runs against the REAL ``clients/`` tree (read-only) to prove the ProjectStore
  abstraction fits today's actual data and round-trips ``status.json`` without losing keys.
* **Write path** — runs against a throwaway temp dir to prove create/transition/immutability/
  append-only semantics. Never mutates real client data.

Runnable two ways::

    python3 tests/test_fs_store.py     # standalone runner (no pytest needed)
    pytest tests/test_fs_store.py      # also works
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    Catalog,
    CatalogOwner,
    CatalogSource,
    EditState,
    FilesystemProjectStore,
    ImmutableTransition,
    IncidentState,
    Project,
    ReportExists,
    Stage,
)

_CLIENTS = _REPO / "clients"


# --------------------------------------------------------------------------- #
# Read path — real data
# --------------------------------------------------------------------------- #
def test_lists_real_projects() -> None:
    store = FilesystemProjectStore(_CLIENTS)
    slugs = store.list_projects()
    assert slugs, "expected at least one real client with a status.json"
    # Every listed slug must load.
    for slug in slugs:
        assert store.get_project(slug) is not None


def test_loads_real_project_typed() -> None:
    store = FilesystemProjectStore(_CLIENTS)
    p = store.get_project("andys-orchids-minimal")
    assert p is not None, "fixture client missing — adjust slug if the tree changed"
    assert p.stage is Stage.AWAITING_OWNER
    assert p.name == "Andy's Orchids (minimalist)"
    assert p.domain.startswith("http")
    assert isinstance(p.log, list) and p.log
    assert p.preview_url.startswith("http")


def test_roundtrip_preserves_unknown_keys() -> None:
    """to_dict() must not drop ad-hoc status.json keys (verification, parent_build, …)."""
    store = FilesystemProjectStore(_CLIENTS)
    raw = json.loads((_CLIENTS / "andys-orchids-minimal" / "status.json").read_text())
    p = Project.from_dict("andys-orchids-minimal", raw)
    out = p.to_dict()
    for k, v in raw.items():
        assert k in out, f"round-trip dropped key {k!r}"
        assert out[k] == v, f"round-trip changed value for {k!r}: {out[k]!r} != {v!r}"


def test_reads_real_decisions() -> None:
    store = FilesystemProjectStore(_CLIENTS)
    decisions = store.list_decisions("strange-wonderful-things")
    assert decisions, "expected the resolved design-concept decision"
    d = decisions[0]
    assert d.n == 1
    assert d.name == "design-concept"
    assert d.state.value == "RESOLVED"


def test_unknown_project_is_none() -> None:
    store = FilesystemProjectStore(_CLIENTS)
    assert store.get_project("definitely-not-a-real-slug-xyz") is None


# --------------------------------------------------------------------------- #
# Write path — temp dir (never touches real clients)
# --------------------------------------------------------------------------- #
def _temp_store() -> tuple[FilesystemProjectStore, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    return FilesystemProjectStore(Path(tmp.name)), tmp


def test_create_and_reload_project() -> None:
    store, tmp = _temp_store()
    try:
        p = Project(
            slug="acme",
            name="Acme Co",
            domain="https://acme.example",
            stage=Stage.QUEUED,
            catalog=Catalog(CatalogSource.ETSY_EXPORT, CatalogOwner.CLIENT),
        )
        store.create_project(p)
        reloaded = store.get_project("acme")
        assert reloaded is not None
        assert reloaded.name == "Acme Co"
        assert reloaded.catalog is not None
        assert reloaded.catalog.source is CatalogSource.ETSY_EXPORT
        assert reloaded.catalog.owner is CatalogOwner.CLIENT
        # stage transition + log
        store.set_stage("acme", Stage.SCRAPING, "started scrape")
        assert store.get_project("acme").stage is Stage.SCRAPING
        assert "started scrape" in store.get_project("acme").log
    finally:
        tmp.cleanup()


def test_edit_ledger_lifecycle() -> None:
    store, tmp = _temp_store()
    try:
        store.create_project(Project(slug="acme", name="Acme"))
        e1 = store.create_edit("acme", "Make hero bigger", "## Requested change\nbigger hero\n")
        e2 = store.create_edit("acme", "Add shipping FAQ", "## Requested change\nfaq\n")
        assert (e1.n, e2.n) == (1, 2), "edits auto-number monotonically"
        assert e1.state is EditState.PENDING
        assert len(store.pending_edits("acme")) == 2

        done = store.transition_edit("acme", 1, EditState.DONE, resolution="changed Hero.astro")
        assert done.state is EditState.DONE
        assert "## Resolution" in done.body and "Hero.astro" in done.body
        assert done.filename == "001-DONE-make-hero-bigger.md"
        assert len(store.pending_edits("acme")) == 1

        # next number is robust to the gap left by the DONE edit
        assert store.next_edit_n("acme") == 3
    finally:
        tmp.cleanup()


def test_edit_immutability() -> None:
    store, tmp = _temp_store()
    try:
        store.create_project(Project(slug="acme", name="Acme"))
        store.create_edit("acme", "thing", "body")
        store.transition_edit("acme", 1, EditState.DONE, resolution="done")
        # DONE is terminal — refuse re-transition.
        try:
            store.transition_edit("acme", 1, EditState.BLOCKED)
        except ImmutableTransition:
            pass
        else:
            raise AssertionError("expected ImmutableTransition on a DONE edit")
    finally:
        tmp.cleanup()


def test_decisions_and_incidents() -> None:
    store, tmp = _temp_store()
    try:
        store.create_project(Project(slug="acme", name="Acme"))
        d = store.create_decision("acme", "Choose concept", "question: which board?\n")
        assert d.state.value == "OPEN"
        assert len(store.open_decisions("acme")) == 1
        store.resolve_decision("acme", d.n, choice="B")
        assert len(store.open_decisions("acme")) == 0
        assert "resolved_choice: B" in store.list_decisions("acme")[0].body

        inc = store.create_incident("acme", "Button does nothing", "## SYMPTOM\nclick = no-op\n")
        assert inc.state is IncidentState.OPEN
        store.transition_incident("acme", inc.n, IncidentState.RESOLVED)
        assert len(store.open_incidents("acme")) == 0
        try:
            store.transition_incident("acme", inc.n, IncidentState.OPEN)
        except ImmutableTransition:
            pass
        else:
            raise AssertionError("expected ImmutableTransition reopening a RESOLVED incident")
    finally:
        tmp.cleanup()


def test_reports_append_only() -> None:
    store, tmp = _temp_store()
    try:
        store.create_project(Project(slug="acme", name="Acme"))
        store.add_report("acme", "build", "# Build report\nok\n", timestamp="2026-06-19-2100")
        store.add_report("acme", "qa-audit", "# QA\npass\n", timestamp="2026-06-19-2130")
        reports = store.list_reports("acme")
        assert [r.kind for r in reports] == ["qa-audit", "build"]  # newest first
        # same (timestamp, kind) must not overwrite
        try:
            store.add_report("acme", "build", "different", timestamp="2026-06-19-2100")
        except ReportExists:
            pass
        else:
            raise AssertionError("expected ReportExists on duplicate report")
    finally:
        tmp.cleanup()


def test_artifacts_roundtrip_and_sandbox() -> None:
    store, tmp = _temp_store()
    try:
        store.create_project(Project(slug="acme", name="Acme"))
        art = store.artifacts("acme")
        art.put("00-source/crawl.json", b'{"pages": 3}')
        assert art.exists("00-source/crawl.json")
        assert art.get("00-source/crawl.json") == b'{"pages": 3}'
        assert "00-source/crawl.json" in list(art.list("00-source"))
        # path traversal is refused
        try:
            art.get("../../etc/passwd")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on path traversal")
    finally:
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
