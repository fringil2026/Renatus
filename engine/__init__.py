"""Web Studio rebuild engine — the headless, storage-agnostic core.

Public surface:

    from engine import (
        ProjectStore, ArtifactStore, FilesystemProjectStore,
        Project, Stage, Edit, EditState, Decision, DecisionState,
        Incident, IncidentState, Report, Version, Catalog,
        CatalogSource, CatalogOwner,
    )

See ``engine/README.md`` and ``docs/adr/0001-foundational-decisions.md``.
"""

from __future__ import annotations

from .agent_sdk_driver import AgentSDKDriver
from .driver import AgentResult, BuildDriver, LocalClaudeDriver, MockBuildDriver, is_transient_failure
from .errors import EngineError, ImmutableTransition, ProjectExists, ReportExists
from .fs_store import FilesystemArtifactStore, FilesystemProjectStore
from .models import (
    Catalog,
    CatalogOwner,
    CatalogSource,
    Decision,
    DecisionState,
    Edit,
    EditState,
    Incident,
    IncidentState,
    LaunchReview,
    LaunchStatus,
    Ownership,
    OwnershipStatus,
    Project,
    Report,
    Stage,
    VerificationMethod,
    Version,
)
from .billing import (
    PLAN_ACTIVE,
    PLAN_FREE,
    NotPaidError,
    get_plan,
    is_paid,
    require_paid_plan,
    set_plan,
)
from .launch import (
    LaunchError,
    NotApprovedError,
    approve,
    reject,
    request_review,
    require_launch_approved,
)
from .metering import UsageSummary, summarize_runs
from .ownership import (
    CheckResult,
    DnsResolver,
    FakeDnsResolver,
    FakeFetcher,
    HttpFetcher,
    NotVerifiedError,
    SystemDnsResolver,
    UrllibFetcher,
    VerificationError,
    challenge_instructions,
    check_verification,
    normalize_domain,
    require_verified,
    start_verification,
)
from .orchestration import (
    CommandOutcome,
    OrchestrationError,
    PreconditionError,
    assemble_prototype,
    process_edits,
    run_command,
    run_cutover,
    run_diagnostic,
    run_finish,
)
from .publish import MockPublisher, Publisher
from .runner import InlineRunner, Runner, ThreadRunner
from .runs import FilesystemRunStore, InMemoryRunStore, Run, RunStatus, RunStore
from .sql_store import InMemoryArtifactStore, SqlProjectStore, SqlRunStore
from .store import ArtifactStore, ProjectStore
from .tenancy import (
    FilesystemTenantStore,
    InMemoryTenantStore,
    Tenant,
    TenantStore,
)
from .transitions import (
    Command,
    available_commands,
    can_transition,
    command_available,
)

__all__ = [
    "AgentResult",
    "AgentSDKDriver",
    "ArtifactStore",
    "BuildDriver",
    "Catalog",
    "CatalogOwner",
    "CatalogSource",
    "CheckResult",
    "Command",
    "CommandOutcome",
    "Decision",
    "DecisionState",
    "DnsResolver",
    "Edit",
    "EditState",
    "EngineError",
    "FakeDnsResolver",
    "FakeFetcher",
    "FilesystemArtifactStore",
    "FilesystemProjectStore",
    "FilesystemRunStore",
    "HttpFetcher",
    "ImmutableTransition",
    "Incident",
    "IncidentState",
    "InlineRunner",
    "InMemoryArtifactStore",
    "InMemoryRunStore",
    "LaunchError",
    "LaunchReview",
    "LaunchStatus",
    "LocalClaudeDriver",
    "MockBuildDriver",
    "MockPublisher",
    "NotApprovedError",
    "NotPaidError",
    "NotVerifiedError",
    "PLAN_ACTIVE",
    "PLAN_FREE",
    "OrchestrationError",
    "Ownership",
    "OwnershipStatus",
    "PreconditionError",
    "Project",
    "ProjectExists",
    "ProjectStore",
    "Publisher",
    "Report",
    "ReportExists",
    "Run",
    "RunStatus",
    "RunStore",
    "Runner",
    "SqlProjectStore",
    "SqlRunStore",
    "FilesystemTenantStore",
    "InMemoryTenantStore",
    "Stage",
    "SystemDnsResolver",
    "Tenant",
    "TenantStore",
    "ThreadRunner",
    "UrllibFetcher",
    "UsageSummary",
    "VerificationError",
    "VerificationMethod",
    "Version",
    "approve",
    "assemble_prototype",
    "available_commands",
    "can_transition",
    "challenge_instructions",
    "check_verification",
    "command_available",
    "get_plan",
    "is_paid",
    "is_transient_failure",
    "normalize_domain",
    "process_edits",
    "reject",
    "request_review",
    "require_launch_approved",
    "require_paid_plan",
    "require_verified",
    "run_command",
    "run_cutover",
    "run_diagnostic",
    "run_finish",
    "set_plan",
    "start_verification",
    "summarize_runs",
]
