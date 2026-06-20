"""Usage metering — aggregate per-run cost + tokens into a summary (ADR-0002 #3/#4).

"Platform-managed, metered" means we pay the Claude + compute COGS and price it in, so we need to
see what each project (and, once tenancy lands, each tenant) consumed. Each ``Run`` already records
``result.cost_usd`` and ``result.usage`` (from the driver's ``AgentResult``); this module sums them.

Pure function over a list of runs — trivially testable, and the same summary feeds an in-app usage
view, plan-limit checks, and billing reconciliation. Subprocess/mock-driven runs report no cost
(``cost_usd`` is None), so summaries are zero-cost until the Agent SDK driver is live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .runs import Run


@dataclass(slots=True)
class UsageSummary:
    runs: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    runs_by_kind: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "cost_usd": round(self.cost_usd, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "runs_by_kind": dict(self.runs_by_kind),
        }


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def summarize_runs(runs: list[Run]) -> UsageSummary:
    """Total cost + token usage across runs (any status — failed/paused runs still cost tokens)."""
    s = UsageSummary()
    for r in runs:
        s.runs += 1
        s.runs_by_kind[r.kind] = s.runs_by_kind.get(r.kind, 0) + 1
        res = r.result or {}
        cost = res.get("cost_usd")
        if isinstance(cost, (int, float)):
            s.cost_usd += float(cost)
        u = res.get("usage") or {}
        s.input_tokens += _int(u.get("input_tokens"))
        s.output_tokens += _int(u.get("output_tokens"))
        s.cache_read_input_tokens += _int(u.get("cache_read_input_tokens"))
    return s
