"""Engine exceptions."""

from __future__ import annotations


class EngineError(Exception):
    """Base class for all engine errors."""


class ProjectExists(EngineError):
    """Raised when creating a project whose slug already exists."""


class ImmutableTransition(EngineError):
    """Raised when attempting to change a terminal/immutable artifact.

    DONE/BLOCKED edits and RESOLVED decisions/incidents are immutable (CLAUDE.md), as are reports
    (append-only). The store refuses these transitions rather than silently corrupting history.
    """


class ReportExists(EngineError):
    """Raised when adding a report whose (timestamp, kind) already exists — reports never overwrite."""
