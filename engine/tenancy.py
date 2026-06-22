"""Tenants — the multi-tenant identity layer (PRODUCT-PLAN §3.5).

A ``Tenant`` is a customer org; every project/run belongs to exactly one. The studio today is
single-operator (one flat ``clients/`` tree); a SaaS needs hard isolation between customers. The
design here is deliberately thin and **provider-agnostic**: a ``TenantStore`` maps an opaque API
token → tenant. *Who mints that token* (Clerk, Auth0, Supabase Auth, …) is an external choice that
plugs into this seam later — the platform only needs the token→tenant resolution.

Isolation itself is enforced one level up by the ``TenantRouter`` (``api/tenancy.py``), which gives
each tenant its own ``ProjectStore``/``RunStore`` instance — so this module is just the registry.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Tenant:
    id: str
    name: str = ""
    api_token: str = ""  # the bearer token that identifies this tenant (issued externally in prod)
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "api_token": self.api_token, "created": self.created}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Tenant":
        return cls(
            id=d["id"], name=d.get("name", ""), api_token=d.get("api_token", ""),
            created=d.get("created", ""),
        )


class TenantStore(ABC):
    @abstractmethod
    def create(self, tenant: Tenant) -> Tenant: ...

    @abstractmethod
    def get(self, tenant_id: str) -> Tenant | None: ...

    @abstractmethod
    def resolve_token(self, token: str) -> Tenant | None:
        """Map a bearer token to its tenant, or None."""

    @abstractmethod
    def list(self) -> list[Tenant]: ...


class InMemoryTenantStore(TenantStore):
    def __init__(self, tenants: list[Tenant] | None = None) -> None:
        self._by_id: dict[str, Tenant] = {}
        for t in tenants or []:
            self._by_id[t.id] = t

    def create(self, tenant: Tenant) -> Tenant:
        self._by_id[tenant.id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        return self._by_id.get(tenant_id)

    def resolve_token(self, token: str) -> Tenant | None:
        if not token:
            return None
        for t in self._by_id.values():
            if t.api_token and t.api_token == token:
                return t
        return None

    def list(self) -> list[Tenant]:
        return sorted(self._by_id.values(), key=lambda t: t.id)


class FilesystemTenantStore(TenantStore):
    """Persists the tenant registry as a single ``tenants.json`` under ``root``."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._path = self._root / "tenants.json"

    def _load(self) -> dict[str, Tenant]:
        if not self._path.is_file():
            return {}
        data = json.loads(self._path.read_text())
        return {tid: Tenant.from_dict(d) for tid, d in data.items()}

    def _save(self, tenants: dict[str, Tenant]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({tid: t.to_dict() for tid, t in tenants.items()}, indent=2) + "\n")

    def create(self, tenant: Tenant) -> Tenant:
        tenants = self._load()
        tenants[tenant.id] = tenant
        self._save(tenants)
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        return self._load().get(tenant_id)

    def resolve_token(self, token: str) -> Tenant | None:
        if not token:
            return None
        for t in self._load().values():
            if t.api_token and t.api_token == token:
                return t
        return None

    def list(self) -> list[Tenant]:
        return sorted(self._load().values(), key=lambda t: t.id)
