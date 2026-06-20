"""Dependency wiring — build a configured ``Application`` for a given environment.

This is the one place that picks concrete engine implementations (which store, which driver, which
publisher). Tests bypass it and inject mocks directly; the dev server uses ``build_default_app``.
"""

from __future__ import annotations

import os
from pathlib import Path

from engine import (
    FilesystemProjectStore,
    FilesystemRunStore,
    LocalClaudeDriver,
    ThreadRunner,
)
from engine.publish import Publisher, UnconfiguredPublisher

from .core import Application

_REPO_ROOT = Path(__file__).resolve().parent.parent


def build_default_app(
    *,
    clients_root: str | Path | None = None,
    token: str | None = None,
    publisher: Publisher | None = None,
    enforce_ownership: bool | None = None,
) -> Application:
    """A dev/local app: filesystem store over ``clients/``, the ``claude -p`` driver, no deploy.

    - ``clients_root`` defaults to ``<repo>/clients`` (or ``$WS_CLIENTS_ROOT``).
    - ``token`` defaults to ``$WS_API_TOKEN`` (auth disabled when unset — dev only).
    - ``publisher`` defaults to ``UnconfiguredPublisher`` (the dev API does not deploy; production
      injects a real publisher).
    - ``enforce_ownership`` defaults to ``$WS_ENFORCE_OWNERSHIP`` != "0" (i.e. on unless disabled).
    """
    root = Path(clients_root or os.environ.get("WS_CLIENTS_ROOT") or (_REPO_ROOT / "clients"))
    store = FilesystemProjectStore(root)
    driver = LocalClaudeDriver(str(_REPO_ROOT))  # claude -p runs from the repo root, as studio.py does
    if enforce_ownership is None:
        enforce_ownership = os.environ.get("WS_ENFORCE_OWNERSHIP", "1") != "0"
    # Real background execution, durable across restarts (runs persisted under each client).
    runner = ThreadRunner(FilesystemRunStore(root))
    return Application(
        store,
        driver=driver,
        publisher=publisher or UnconfiguredPublisher(),
        token=token if token is not None else os.environ.get("WS_API_TOKEN"),
        enforce_ownership=enforce_ownership,
        runner=runner,
        reviewer_token=os.environ.get("WS_REVIEWER_TOKEN"),  # ops approve/reject (ADR-0002 #2)
        enforce_billing=os.environ.get("WS_ENFORCE_BILLING", "0") != "0",  # paywall (ADR-0002 #4)
    )
