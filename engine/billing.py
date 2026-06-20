"""Billing entitlement — the paywall between the free diagnostic and the paid rebuild (ADR-0002 #4).

Pricing is "free diagnostic → one-time rebuild fee → hosting+edits subscription", so the rebuild
(``assemble``) is the first paid action; the diagnostic stays free. This module is the entitlement
*gate*, not a payment integration: the plan lives on the project (in ``extra["plan"]`` so it
round-trips without a schema change), and ``require_paid_plan`` gates the rebuild. A real Stripe
checkout + webhook flips the plan in production; the dev API exposes a stub that sets it directly.

Plan likely moves to the *tenant* once multi-tenancy lands (a customer subscribes once, not per site)
— ``get_plan``/``set_plan`` are the seam that change would go through.
"""

from __future__ import annotations

from .errors import EngineError
from .models import Project

PLAN_FREE = "free"
PLAN_ACTIVE = "active"  # rebuild fee paid / hosting subscription active


class NotPaidError(EngineError):
    """Raised by ``require_paid_plan`` when a paid action is attempted on the free plan."""


def get_plan(project: Project) -> str:
    return project.extra.get("plan", PLAN_FREE)


def set_plan(project: Project, plan: str) -> None:
    project.extra["plan"] = plan


def is_paid(project: Project) -> bool:
    return get_plan(project) != PLAN_FREE


def require_paid_plan(project: Project) -> None:
    if not is_paid(project):
        raise NotPaidError(
            f"{project.slug!r} is on the free plan; the rebuild requires payment "
            "(the diagnostic is free)"
        )
