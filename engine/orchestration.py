"""Headless command entrypoints — the deterministic glue around the Claude-driven build.

This is studio.py's ``run_advance`` generalized and made testable: stage-gated entrypoints that take an
explicit ``ProjectStore`` + ``BuildDriver`` + ``Publisher`` instead of assuming a working directory and
a ``claude -p`` subprocess. The *creative/build* work is delegated to the driver (a Claude agent
executing the CLAUDE.md command); the *deterministic* parts live here:

* **precondition gates** — stage + business rules (e.g. assemble requires the concept decision resolved);
* **PUBLISH-ALWAYS** — on a successful build, publish the preview (or flag it stale on deploy failure);
* **failure policy** — transient (budget/rate/overload) → ``paused`` (resumable); real → ``*_failed``;
* **append-only reporting** — every finding-producing flow ends with a report file.

State writes follow studio.py's ordering: the "started" log is written before the agent runs (safe,
pre-spawn); everything else after the agent returns (safe, the agent has exited and released
``status.json``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .driver import BuildDriver
from .errors import EngineError, ReportExists
from .models import Project, Report, Stage
from .publish import Publisher
from .store import ProjectStore
from .transitions import Command, command_available


class OrchestrationError(EngineError):
    """Base for orchestration failures."""


class PreconditionError(OrchestrationError):
    """A command was invoked when its preconditions weren't met (wrong stage, missing input, …)."""


@dataclass(slots=True)
class CommandOutcome:
    ok: bool
    paused: bool = False
    preview_url: str | None = None
    report: Report | None = None
    message: str = ""
    # Telemetry surfaced from the BuildDriver's AgentResult, for per-run metering (ADR-0002 #3/#4).
    # Populated by drivers that report it (AgentSDKDriver); None for subprocess/mock drivers.
    cost_usd: float | None = None
    usage: dict | None = None


def _require(store: ProjectStore, slug: str) -> Project:
    p = store.get_project(slug)
    if p is None:
        raise PreconditionError(f"unknown project: {slug!r}")
    return p


def _gate(project: Project, command: Command) -> None:
    if not command_available(command, project.stage):
        raise PreconditionError(
            f"command {command.value!r} is not available at stage {project.stage.value!r}"
        )


def run_command(
    store: ProjectStore,
    driver: BuildDriver,
    slug: str,
    command: str,
    *,
    kind: str,
    now: str,
    fail_flag: str = "advance_failed",
    publisher: Publisher | None = None,
    report_kind: str | None = None,
    report_body: str | None = None,
) -> CommandOutcome:
    """Generalized ``run_advance``: run the agent, then apply publish-always + failure policy.

    ``publisher`` is passed only for build-type commands that produce a deployable ``dist`` (assemble,
    process-edits); read-only commands (diagnose, config) pass ``None``.
    """
    store.append_log(slug, f"{now} {kind} started: {command}")  # pre-spawn → safe

    result = driver.run(command, slug=slug)
    meter = {"cost_usd": result.cost_usd, "usage": result.usage}  # carried onto every outcome below

    if result.ok:
        p = _require(store, slug)
        p.extra.pop("paused", None)
        p.extra.pop("paused_kind", None)
        p.extra.pop(fail_flag, None)
        store.save_project(p)

        preview_url: str | None = None
        if publisher is not None:
            preview_url = publisher.publish_preview(slug)
            if preview_url:
                store.set_preview(slug, preview_url, now)
                store.append_log(slug, f"{now} {kind}: auto-published preview -> {preview_url}")
            else:
                store.mark_preview_stale(slug)
                store.append_log(slug, f"{now} {kind}: auto-publish FAILED — preview left stale")

        store.append_log(slug, f"{now} {kind} finished ok")

        report: Report | None = None
        if report_kind:
            body = report_body or f"# {kind} report\n\nCommand: `{command}`\nResult: ok\n"
            try:
                report = store.add_report(slug, report_kind, body, timestamp=now)
            except ReportExists:
                report = None  # idempotent re-run at the same timestamp
        return CommandOutcome(ok=True, preview_url=preview_url, report=report, message="ok", **meter)

    # --- failure paths (transient/hard failures still cost tokens — meter them too) ---
    p = _require(store, slug)
    if result.transient:
        p.extra["paused"] = True
        p.extra["paused_kind"] = kind
        p.extra.pop(fail_flag, None)
        p.log.append(f"{now} {kind} PAUSED (transient — resumable): {result.tail_text[-180:]}")
        store.save_project(p)
        return CommandOutcome(ok=False, paused=True, message="paused", **meter)

    p.extra[fail_flag] = True
    p.log.append(f"{now} {kind} FAILED (exit {result.exit_code}) — tail: {result.tail_text}")
    store.save_project(p)
    return CommandOutcome(ok=False, message="failed", **meter)


# --------------------------------------------------------------------------- #
# Entrypoints (CLAUDE.md commands)
# --------------------------------------------------------------------------- #
def assemble_prototype(
    store: ProjectStore,
    driver: BuildDriver,
    slug: str,
    *,
    publisher: Publisher,
    now: str,
) -> CommandOutcome:
    """CLAUDE.md Command 1. Requires stage=baseline-ready AND a resolved concept decision."""
    p = _require(store, slug)
    _gate(p, Command.ASSEMBLE)
    # Command 1 step 0: build to the chosen concept; refuse if the decision is still open.
    if any("concept" in d.name.lower() for d in store.open_decisions(slug)):
        raise PreconditionError("the design-concept decision is unresolved — resolve it before assembling")

    outcome = run_command(
        store, driver, slug, f"Assemble prototype for {slug}",
        kind="assemble", fail_flag="advance_failed",
        publisher=publisher, now=now, report_kind="assemble",
    )
    if outcome.ok:
        # Command 1: stage prototype -> awaiting-owner.
        store.set_stage(slug, Stage.PROTOTYPE, f"{now} prototype assembled")
        store.set_stage(slug, Stage.AWAITING_OWNER, f"{now} awaiting owner answers")
    return outcome


def process_edits(
    store: ProjectStore,
    driver: BuildDriver,
    slug: str,
    *,
    publisher: Publisher,
    now: str,
) -> CommandOutcome:
    """CLAUDE.md Command 5. Requires a built site and at least one PENDING edit."""
    p = _require(store, slug)
    _gate(p, Command.PROCESS_EDITS)
    if not store.pending_edits(slug):
        raise PreconditionError("no PENDING edits to process")

    # The agent implements each edit and transitions PENDING->DONE/BLOCKED in the ledger; the store
    # reflects that on the next read. Orchestration only sequences + publishes.
    return run_command(
        store, driver, slug, f"Process edits for {slug}",
        kind="process-edits", fail_flag="process_failed",
        publisher=publisher, now=now, report_kind="process-edits",
    )


def run_diagnostic(
    store: ProjectStore,
    driver: BuildDriver,
    slug: str,
    *,
    now: str,
) -> CommandOutcome:
    """site-diagnostic over the project's domain. Read-only — no publish."""
    p = _require(store, slug)
    _gate(p, Command.DIAGNOSE)
    target = p.domain or slug
    return run_command(
        store, driver, slug, f"Diagnose site {target}",
        kind="diagnostic", fail_flag="diagnostic_failed",
        publisher=None, now=now, report_kind="diagnostic",
    )


def run_cutover(
    store: ProjectStore,
    driver: BuildDriver,
    slug: str,
    *,
    now: str,
) -> CommandOutcome:
    """CLAUDE.md Command 3 — cutover prechecks. Requires stage=final. No publish.

    The launch-review approval gate (ADR-0002 #2) is enforced by the control plane before this runs;
    the actual DNS/indexable go-live remains a human step (studio Hard rule)."""
    p = _require(store, slug)
    _gate(p, Command.CUTOVER)
    outcome = run_command(
        store, driver, slug, f"Run cutover prechecks for {slug}",
        kind="cutover", fail_flag="cutover_failed",
        publisher=None, now=now, report_kind="cutover",
    )
    if outcome.ok:
        store.set_stage(slug, Stage.CUTOVER_CHECKED, f"{now} cutover prechecks passed")
    return outcome
