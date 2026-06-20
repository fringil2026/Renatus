"""Typed domain models for the rebuild engine.

These replace the two ad-hoc state representations the studio uses today:

  * ``clients/<slug>/status.json`` — the per-project state blob, and
  * filename-as-state files — ``NNN-PENDING-<name>.md`` (edits),
    ``NNN-OPEN-<name>.yaml`` (decisions), ``NNN-OPEN-<name>.md`` (incidents),
    ``<YYYY-MM-DD-HHMM>-<kind>.md`` (reports).

The models are storage-agnostic: a ``ProjectStore`` (see ``store.py``) maps them onto the filesystem
today and onto Postgres + object storage in production. To survive the migration without losing data,
``Project`` preserves any unknown ``status.json`` keys verbatim in ``extra`` and merges them back on
serialization — real status files carry many ad-hoc keys (``verification``, ``parent_build``,
``preview_deploy_url``, …) we must not drop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Enums — the controlled vocabularies that were previously bare strings.
# --------------------------------------------------------------------------- #
class Stage(str, Enum):
    """Project lifecycle stage. Values match today's ``status.json`` ``stage`` strings exactly."""

    QUEUED = "queued"
    SCRAPING = "scraping"
    BASELINE_READY = "baseline-ready"
    PROTOTYPE = "prototype"
    AWAITING_OWNER = "awaiting-owner"
    ANSWERS_RECEIVED = "answers-received"
    FINAL = "final"
    CUTOVER_CHECKED = "cutover-checked"
    ARCHIVED = "archived"
    # Off the main line:
    IMPORT_PENDING = "import-pending"  # marketplace-export intake before first build
    ERROR = "error"

    @classmethod
    def _missing_(cls, value: object) -> "Stage":
        # Unknown/legacy stage strings degrade to ERROR rather than blowing up a load.
        return cls.ERROR


class EditState(str, Enum):
    """Edit-ledger state. The filename suffix today (``NNN-PENDING-…``) becomes this enum."""

    PENDING = "PENDING"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class DecisionState(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class IncidentState(str, Enum):
    OPEN = "OPEN"
    BLOCKED = "BLOCKED"
    RESOLVED = "RESOLVED"


class CatalogSource(str, Enum):
    """Where a commerce project's catalog came from (provenance)."""

    SCRAPE = "scrape"
    ETSY_EXPORT = "etsy-export"
    EBAY_EXPORT = "ebay-export"


class CatalogOwner(str, Enum):
    SELF = "self"
    CLIENT = "client"


class OwnershipStatus(str, Enum):
    """Whether the customer has proven control of the project's domain (PRODUCT-PLAN §4 step 3)."""

    UNVERIFIED = "unverified"
    PENDING = "pending"  # a challenge has been issued, awaiting the record/tag/file
    VERIFIED = "verified"


class VerificationMethod(str, Enum):
    DNS_TXT = "dns-txt"      # a TXT record on the domain
    META_TAG = "meta-tag"    # a <meta> tag on the homepage
    HTTP_FILE = "http-file"  # a file under /.well-known/
    OAUTH = "oauth"          # host OAuth (future — not implemented in the skeleton)


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Catalog:
    """``status.json`` ``catalog: {source, owner}`` — marketplace-import provenance (SYSTEM.md §1a)."""

    source: CatalogSource
    owner: CatalogOwner = CatalogOwner.SELF

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source.value, "owner": self.owner.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Catalog":
        return cls(
            source=CatalogSource(d["source"]),
            owner=CatalogOwner(d.get("owner", "self")),
        )


@dataclass(slots=True)
class Ownership:
    """Domain-ownership state for a project — the gate before scrape-heavy or launch steps."""

    status: OwnershipStatus = OwnershipStatus.UNVERIFIED
    domain: str = ""  # normalized host the challenge applies to
    method: VerificationMethod | None = None
    token: str = ""  # the issued challenge token (while PENDING)
    expires: str = ""  # ISO-8601 expiry of the pending challenge
    verified_at: str = ""  # ISO-8601 when VERIFIED

    @property
    def is_verified(self) -> bool:
        return self.status is OwnershipStatus.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status.value}
        if self.domain:
            d["domain"] = self.domain
        if self.method is not None:
            d["method"] = self.method.value
        if self.token:
            d["token"] = self.token
        if self.expires:
            d["expires"] = self.expires
        if self.verified_at:
            d["verified_at"] = self.verified_at
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ownership":
        method = d.get("method")
        return cls(
            status=OwnershipStatus(d.get("status", "unverified")),
            domain=d.get("domain", ""),
            method=VerificationMethod(method) if method else None,
            token=d.get("token", ""),
            expires=d.get("expires", ""),
            verified_at=d.get("verified_at", ""),
        )


@dataclass(slots=True)
class Version:
    """A single multi-version build (SYSTEM.md §3c). One entry per ``status.json`` ``versions[]``."""

    idx: int
    mode: str  # standard | image-led | creative | minimalist | ...
    label: str = ""
    project: str = ""  # the Cloudflare Pages project name (ws-<slug>[-vN])
    site_dir: str = ""  # 03-site, 03-site-v2, ...
    status: str = "queued"
    preview_url: str = ""
    published_at: str = ""
    chosen: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = {
            "idx": self.idx,
            "mode": self.mode,
            "label": self.label,
            "project": self.project,
            "site_dir": self.site_dir,
            "status": self.status,
            "preview_url": self.preview_url,
            "published_at": self.published_at,
        }
        if self.chosen:
            d["chosen"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Version":
        return cls(
            idx=int(d.get("idx", 0)),
            mode=d.get("mode", "standard"),
            label=d.get("label", ""),
            project=d.get("project", ""),
            site_dir=d.get("site_dir", ""),
            status=d.get("status", "queued"),
            preview_url=d.get("preview_url", ""),
            published_at=d.get("published_at", ""),
            chosen=bool(d.get("chosen", False)),
        )


# --------------------------------------------------------------------------- #
# Project — the per-project state (today's status.json)
# --------------------------------------------------------------------------- #
# Keys we model explicitly; everything else in status.json is preserved in ``extra``.
_CORE_KEYS = {
    "name", "domain", "stage", "design_mode", "concept", "created",
    "log", "preview_url", "preview_published_at", "preview_stale",
    "versions", "catalog", "ownership",
}


@dataclass(slots=True)
class Project:
    """A single website rebuild. The unit of work; one per ``clients/<slug>/``."""

    slug: str
    name: str = ""
    domain: str = ""
    stage: Stage = Stage.QUEUED
    design_mode: str = "standard"
    concept: str = ""
    created: str = ""
    log: list[str] = field(default_factory=list)
    preview_url: str = ""
    preview_published_at: str = ""
    preview_stale: bool = False
    versions: list[Version] = field(default_factory=list)
    catalog: Catalog | None = None
    ownership: Ownership | None = None
    # Any status.json key we don't model explicitly, preserved verbatim for round-tripping.
    extra: dict[str, Any] = field(default_factory=dict)

    # -- serialization ----------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        """Serialize back to the status.json shape, preserving unknown keys."""
        d: dict[str, Any] = dict(self.extra)  # unknown keys first; explicit keys win below
        d["name"] = self.name
        d["domain"] = self.domain
        d["stage"] = self.stage.value
        d["design_mode"] = self.design_mode
        if self.concept:
            d["concept"] = self.concept
        if self.created:
            d["created"] = self.created
        d["log"] = list(self.log)
        if self.preview_url:
            d["preview_url"] = self.preview_url
        if self.preview_published_at:
            d["preview_published_at"] = self.preview_published_at
        if self.preview_stale:
            d["preview_stale"] = True
        if self.versions:
            d["versions"] = [v.to_dict() for v in self.versions]
        if self.catalog is not None:
            d["catalog"] = self.catalog.to_dict()
        if self.ownership is not None:
            d["ownership"] = self.ownership.to_dict()
        return d

    @classmethod
    def from_dict(cls, slug: str, d: dict[str, Any]) -> "Project":
        extra = {k: v for k, v in d.items() if k not in _CORE_KEYS}
        catalog = Catalog.from_dict(d["catalog"]) if isinstance(d.get("catalog"), dict) else None
        ownership = Ownership.from_dict(d["ownership"]) if isinstance(d.get("ownership"), dict) else None
        versions = [Version.from_dict(v) for v in d.get("versions", []) if isinstance(v, dict)]
        return cls(
            slug=slug,
            name=d.get("name", ""),
            domain=d.get("domain", ""),
            stage=Stage(d.get("stage", "queued")),
            design_mode=d.get("design_mode", "standard"),
            concept=d.get("concept", ""),
            created=d.get("created", ""),
            log=list(d.get("log", [])),
            preview_url=d.get("preview_url", ""),
            preview_published_at=d.get("preview_published_at", ""),
            preview_stale=bool(d.get("preview_stale", False)),
            versions=versions,
            catalog=catalog,
            ownership=ownership,
            extra=extra,
        )


# --------------------------------------------------------------------------- #
# Filename-as-state artifacts (edits, decisions, incidents, reports)
# --------------------------------------------------------------------------- #
# Edits/decisions/incidents: NNN-<STATE>-<short-name>.<ext>
_NNN_STATE_RE = re.compile(r"^(?P<n>\d+)-(?P<state>[A-Z]+)-(?P<name>.+?)\.(?P<ext>md|yaml|yml)$")
# Reports: <YYYY-MM-DD-HHMM>-<kind>.md
_REPORT_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}-\d{4})-(?P<kind>.+?)\.md$")


@dataclass(slots=True)
class Edit:
    """A revision request in the edit ledger (CLAUDE.md Command 5)."""

    n: int
    name: str  # short-name slug
    state: EditState
    body: str = ""  # markdown content
    filename: str = ""  # source filename when fs-backed (provenance/debug)

    @property
    def is_open(self) -> bool:
        return self.state is EditState.PENDING

    @classmethod
    def parse_filename(cls, filename: str) -> tuple[int, str, str] | None:
        """Return (n, state, name) for an ``NNN-STATE-name.md`` edit filename, else None."""
        m = _NNN_STATE_RE.match(filename)
        if not m or m.group("ext") != "md":
            return None
        return int(m.group("n")), m.group("state"), m.group("name")


@dataclass(slots=True)
class Decision:
    """A human-judgment fork (CLAUDE.md "Decision surfaces"). ``NNN-OPEN-<name>.yaml``."""

    n: int
    name: str
    state: DecisionState
    body: str = ""  # raw yaml content
    filename: str = ""

    @classmethod
    def parse_filename(cls, filename: str) -> tuple[int, str, str] | None:
        m = _NNN_STATE_RE.match(filename)
        if not m or m.group("ext") not in ("yaml", "yml"):
            return None
        return int(m.group("n")), m.group("state"), m.group("name")


@dataclass(slots=True)
class Incident:
    """A troubleshooting incident (CLAUDE.md "Troubleshooting workflow"). ``NNN-OPEN-<name>.md``."""

    n: int
    name: str
    state: IncidentState
    body: str = ""
    filename: str = ""

    @classmethod
    def parse_filename(cls, filename: str) -> tuple[int, str, str] | None:
        m = _NNN_STATE_RE.match(filename)
        if not m or m.group("ext") != "md":
            return None
        return int(m.group("n")), m.group("state"), m.group("name")


@dataclass(slots=True)
class Report:
    """An append-only finding (CLAUDE.md "Findings & reports"). ``<YYYY-MM-DD-HHMM>-<kind>.md``."""

    timestamp: str  # YYYY-MM-DD-HHMM
    kind: str
    body: str = ""
    filename: str = ""

    @classmethod
    def parse_filename(cls, filename: str) -> tuple[str, str] | None:
        m = _REPORT_RE.match(filename)
        if not m:
            return None
        return m.group("ts"), m.group("kind")
