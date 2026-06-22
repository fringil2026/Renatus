"""Store conformance — the SAME contract runs against both ProjectStore backends.

This is how we guarantee the SQL store and the filesystem store behave identically: one ``contract``
battery, executed against ``FilesystemProjectStore`` (temp dir) and ``SqlProjectStore`` (sqlite). If a
backend diverges on numbering, immutability, append-only reports, round-tripping, etc., it fails here.
Production's Postgres store rides the same SQL path as sqlite, so passing on sqlite is strong evidence.

    python3 tests/test_store_conformance.py
    pytest tests/test_store_conformance.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import (  # noqa: E402
    Catalog,
    CatalogOwner,
    CatalogSource,
    DecisionState,
    EditState,
    FilesystemProjectStore,
    ImmutableTransition,
    IncidentState,
    Ownership,
    OwnershipStatus,
    Project,
    ProjectExists,
    ProjectStore,
    ReportExists,
    Run,
    RunStatus,
    SqlProjectStore,
    SqlRunStore,
    Stage,
)


def contract(store: ProjectStore) -> None:
    # -- projects (incl. catalog + ownership round-trip) ------------------- #
    assert store.list_projects() == []
    store.create_project(
        Project(
            slug="acme", name="Acme", domain="https://acme.example", stage=Stage.QUEUED,
            catalog=Catalog(CatalogSource.ETSY_EXPORT, CatalogOwner.CLIENT),
            ownership=Ownership(status=OwnershipStatus.VERIFIED, domain="acme.example"),
        )
    )
    assert store.list_projects() == ["acme"]
    p = store.get_project("acme")
    assert p.name == "Acme"
    assert p.catalog.source is CatalogSource.ETSY_EXPORT and p.catalog.owner is CatalogOwner.CLIENT
    assert p.ownership.is_verified
    assert store.get_project("nope") is None
    try:
        store.create_project(Project(slug="acme"))
    except ProjectExists:
        pass
    else:
        raise AssertionError("expected ProjectExists")
    store.set_stage("acme", Stage.PROTOTYPE, "built")
    p = store.get_project("acme")
    assert p.stage is Stage.PROTOTYPE and "built" in p.log

    # -- edits ------------------------------------------------------------- #
    e1 = store.create_edit("acme", "Make hero bigger", "## Requested change\nbigger\n")
    e2 = store.create_edit("acme", "Add FAQ", "faq")
    assert (e1.n, e2.n) == (1, 2)
    done = store.transition_edit("acme", 1, EditState.DONE, resolution="changed Hero.astro")
    assert done.state is EditState.DONE and "## Resolution" in done.body
    assert done.filename == "001-DONE-make-hero-bigger.md"
    assert len(store.pending_edits("acme")) == 1
    assert store.next_edit_n("acme") == 3  # robust to the DONE gap
    try:
        store.transition_edit("acme", 1, EditState.BLOCKED)
    except ImmutableTransition:
        pass
    else:
        raise AssertionError("expected ImmutableTransition on DONE edit")

    # -- decisions --------------------------------------------------------- #
    dec = store.create_decision("acme", "Choose concept", "q: which?\n")
    assert dec.state is DecisionState.OPEN
    store.resolve_decision("acme", dec.n, choice="B")
    assert store.open_decisions("acme") == []
    assert "resolved_choice: B" in store.list_decisions("acme")[0].body
    try:
        store.resolve_decision("acme", dec.n)
    except ImmutableTransition:
        pass
    else:
        raise AssertionError("expected ImmutableTransition on RESOLVED decision")

    # -- incidents --------------------------------------------------------- #
    inc = store.create_incident("acme", "Button broken", "## SYMPTOM\nno-op\n")
    store.transition_incident("acme", inc.n, IncidentState.RESOLVED)
    assert store.open_incidents("acme") == []
    try:
        store.transition_incident("acme", inc.n, IncidentState.OPEN)
    except ImmutableTransition:
        pass
    else:
        raise AssertionError("expected ImmutableTransition reopening RESOLVED incident")

    # -- reports (append-only, newest-first) ------------------------------- #
    store.add_report("acme", "build", "# build\nok\n", timestamp="2026-06-19-2100")
    store.add_report("acme", "qa-audit", "# qa\npass\n", timestamp="2026-06-19-2130")
    assert [r.kind for r in store.list_reports("acme")] == ["qa-audit", "build"]
    try:
        store.add_report("acme", "build", "dupe", timestamp="2026-06-19-2100")
    except ReportExists:
        pass
    else:
        raise AssertionError("expected ReportExists")
    try:
        store.add_report("acme", "build", "x", timestamp="not-a-stamp")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a bad timestamp")

    # -- artifacts --------------------------------------------------------- #
    art = store.artifacts("acme")
    art.put("00-source/crawl.json", b'{"pages": 3}')
    assert art.exists("00-source/crawl.json")
    assert art.get("00-source/crawl.json") == b'{"pages": 3}'
    assert "00-source/crawl.json" in list(art.list("00-source"))


# --------------------------------------------------------------------------- #
def test_filesystem_store_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        contract(FilesystemProjectStore(Path(tmp)))


def test_sql_store_contract() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        contract(SqlProjectStore(conn, placeholder="?"))
    finally:
        conn.close()


def test_sql_run_store() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        store = SqlRunStore(conn, placeholder="?")
        store.create(Run(id="run_a", slug="acme", kind="assemble", status=RunStatus.QUEUED, created="t1"))
        store.save(Run(id="run_a", slug="acme", kind="assemble", status=RunStatus.SUCCEEDED, created="t1"))
        store.create(Run(id="run_b", slug="acme", kind="diagnostic", status=RunStatus.RUNNING, created="t2"))
        assert store.get("run_a").status is RunStatus.SUCCEEDED
        assert [r.id for r in store.list("acme")] == ["run_b", "run_a"]  # newest-first by created
        assert store.get("missing") is None
    finally:
        conn.close()


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
