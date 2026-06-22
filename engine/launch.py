"""Launch review — the human gate before go-live (ADR-0002 #2: self-serve build, reviewed launch).

A customer builds and edits self-serve, then *requests launch*; a reviewer (ops) approves or rejects;
only an approved review lets the automated cutover prechecks run. The DNS/indexable flip itself stays
a human step regardless (studio Hard rule) — this gate governs whether we get that far.

Pure state-machine logic over the ``LaunchReview`` model; the API binds identity + timestamps. Mirrors
``engine/ownership.py``: small, testable, and the gate (``require_launch_approved``) is enforced by the
control plane, not the engine.
"""

from __future__ import annotations

from .errors import EngineError
from .models import LaunchReview, LaunchStatus, Project


class LaunchError(EngineError):
    """An invalid launch-review transition (e.g. approving when nothing was requested)."""


class NotApprovedError(EngineError):
    """Raised by ``require_launch_approved`` when go-live is attempted without an approved review."""


def request_review(current: LaunchReview | None, *, now: str) -> LaunchReview:
    """Customer requests launch. Allowed from any state (re-request after a rejection is fine)."""
    return LaunchReview(status=LaunchStatus.PENDING, requested_at=now)


def approve(current: LaunchReview | None, *, reviewer: str, now: str, note: str = "") -> LaunchReview:
    if current is None or current.status is not LaunchStatus.PENDING:
        raise LaunchError("can only approve a launch review that is PENDING")
    return LaunchReview(
        status=LaunchStatus.APPROVED,
        requested_at=current.requested_at,
        decided_at=now,
        reviewer=reviewer,
        note=note,
    )


def reject(current: LaunchReview | None, *, reviewer: str, now: str, note: str) -> LaunchReview:
    if current is None or current.status is not LaunchStatus.PENDING:
        raise LaunchError("can only reject a launch review that is PENDING")
    if not note:
        raise LaunchError("a rejection must include a reason (note)")
    return LaunchReview(
        status=LaunchStatus.REJECTED,
        requested_at=current.requested_at,
        decided_at=now,
        reviewer=reviewer,
        note=note,
    )


def require_launch_approved(project: Project) -> None:
    """Raise ``NotApprovedError`` unless the project's launch has been approved by a reviewer."""
    if not (project.launch_review and project.launch_review.is_approved):
        raise NotApprovedError(
            f"launch for {project.slug!r} is not approved; a reviewer must approve before cutover"
        )
