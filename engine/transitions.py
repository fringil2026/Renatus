"""The stage machine — a single source of truth for what's valid at each stage.

Ports the intent of studio.py's ``NEXT`` map + the per-stage button gating
(``advance_action`` / ``full_build_action``) into testable data, so both the engine entrypoints and a
future control-plane API agree on "which command applies at stage X".
"""

from __future__ import annotations

from enum import Enum

from .models import Stage


class Command(str, Enum):
    ASSEMBLE = "assemble"
    PROCESS_EDITS = "process-edits"
    DIAGNOSE = "diagnose"
    FINISH = "finish"
    CUTOVER = "cutover"
    FULL_BUILD = "full-build"
    ARCHIVE = "archive"


# Forward stage transitions the pipeline may make (validation + UI). A no-op (src == dst) is allowed.
ALLOWED_TRANSITIONS: dict[Stage, set[Stage]] = {
    Stage.QUEUED: {Stage.SCRAPING, Stage.ERROR},
    Stage.SCRAPING: {Stage.BASELINE_READY, Stage.ERROR},
    Stage.IMPORT_PENDING: {Stage.PROTOTYPE, Stage.ERROR},
    Stage.BASELINE_READY: {Stage.PROTOTYPE, Stage.ERROR},
    Stage.PROTOTYPE: {Stage.AWAITING_OWNER, Stage.ANSWERS_RECEIVED, Stage.FINAL, Stage.ERROR},
    Stage.AWAITING_OWNER: {Stage.ANSWERS_RECEIVED, Stage.PROTOTYPE, Stage.ERROR},
    Stage.ANSWERS_RECEIVED: {Stage.FINAL, Stage.ERROR},
    Stage.FINAL: {Stage.CUTOVER_CHECKED, Stage.ERROR},
    Stage.CUTOVER_CHECKED: {Stage.ARCHIVED},
    Stage.ERROR: {Stage.SCRAPING, Stage.BASELINE_READY},  # rerun paths
}

# A "built site" exists from prototype onward — the stages where edits make sense.
_BUILT_STAGES = {Stage.PROTOTYPE, Stage.AWAITING_OWNER, Stage.ANSWERS_RECEIVED, Stage.FINAL}

# Which stages each command may run at. DIAGNOSE is read-only assessment → allowed anywhere.
COMMAND_STAGES: dict[Command, set[Stage]] = {
    Command.ASSEMBLE: {Stage.BASELINE_READY},
    Command.PROCESS_EDITS: set(_BUILT_STAGES),
    Command.DIAGNOSE: set(Stage),
    Command.FINISH: {Stage.ANSWERS_RECEIVED},
    Command.CUTOVER: {Stage.FINAL},
    Command.FULL_BUILD: {Stage.BASELINE_READY, *(_BUILT_STAGES)},
    Command.ARCHIVE: {Stage.FINAL, Stage.CUTOVER_CHECKED},
}


def can_transition(src: Stage, dst: Stage) -> bool:
    return src is dst or dst in ALLOWED_TRANSITIONS.get(src, set())


def command_available(command: Command, stage: Stage) -> bool:
    return stage in COMMAND_STAGES.get(command, set())


def available_commands(stage: Stage) -> list[Command]:
    return [c for c in Command if command_available(c, stage)]
