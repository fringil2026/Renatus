"""Framework-agnostic control-plane core.

The real API logic lives here, with **no web-framework dependency** — ``Application.dispatch()`` takes a
plain ``Request`` and returns a plain ``Response``. That keeps the control plane fully unit-testable
without installing FastAPI/uvicorn, and makes the framework a swappable detail:

* ``api/server.py`` — a stdlib ``http.server`` adapter (dev/local; runnable now).
* ``api/fastapi_app.py`` — the production adapter per ADR-0001 §2 (thin wrapper over this core).

Everything operates on the engine: a ``ProjectStore`` for state and the orchestration entrypoints for
actions. Auth + tenancy are seams here (a bearer-token check resolving a tenant id); production swaps
in real auth and a per-tenant store without touching the handlers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from engine import (
    Catalog,
    CatalogOwner,
    CatalogSource,
    Command,
    Decision,
    DnsResolver,
    Edit,
    HttpFetcher,
    Incident,
    InlineRunner,
    InMemoryRunStore,
    PLAN_ACTIVE,
    LaunchError,
    LaunchReview,
    NotApprovedError,
    NotPaidError,
    NotVerifiedError,
    Ownership,
    PreconditionError,
    Project,
    ProjectExists,
    ProjectStore,
    Report,
    Run,
    Runner,
    Stage,
    SystemDnsResolver,
    UrllibFetcher,
    VerificationError,
    VerificationMethod,
    approve,
    assemble_prototype,
    challenge_instructions,
    check_verification,
    command_available,
    get_plan,
    process_edits,
    reject,
    request_review,
    require_launch_approved,
    require_paid_plan,
    require_verified,
    run_cutover,
    run_diagnostic,
    set_plan,
    start_verification,
    summarize_runs,
)
from engine.driver import BuildDriver
from engine.publish import Publisher


# --------------------------------------------------------------------------- #
# Transport-neutral request/response
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Request:
    method: str
    path: str
    body: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        # case-insensitive header lookup
        low = name.lower()
        for k, v in self.headers.items():
            if k.lower() == low:
                return v
        return None


@dataclass(slots=True)
class Response:
    status: int
    body: dict[str, Any]


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- #
# Serializers (models -> JSON-safe dicts)
# --------------------------------------------------------------------------- #
def _project_json(p: Project) -> dict[str, Any]:
    return {"slug": p.slug, **p.to_dict()}


def _edit_json(e: Edit) -> dict[str, Any]:
    return {"n": e.n, "name": e.name, "state": e.state.value, "filename": e.filename}


def _decision_json(d: Decision) -> dict[str, Any]:
    return {"n": d.n, "name": d.name, "state": d.state.value, "filename": d.filename}


def _incident_json(i: Incident) -> dict[str, Any]:
    return {"n": i.n, "name": i.name, "state": i.state.value, "filename": i.filename}


def _report_json(r: Report) -> dict[str, Any]:
    return {"timestamp": r.timestamp, "kind": r.kind, "filename": r.filename}


def _utc_report_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
_Handler = Callable[["Application", Request, dict[str, str]], Response]
_SEG = re.compile(r"^\{(\w+)\}$")


class Application:
    """The control-plane app. Construct with an engine store + the action seams, then ``dispatch``."""

    def __init__(
        self,
        store: ProjectStore,
        *,
        driver: BuildDriver,
        publisher: Publisher,
        token: str | None = None,
        now_fn: Callable[[], str] = _utc_report_stamp,
        resolver: DnsResolver | None = None,
        fetcher: HttpFetcher | None = None,
        enforce_ownership: bool = True,
        runner: Runner | None = None,
        reviewer_token: str | None = None,
        enforce_billing: bool = False,
    ) -> None:
        self._store = store
        self._driver = driver
        self._publisher = publisher
        self._token = token  # None = dev mode (auth disabled)
        # Reviewer (ops) authz for launch approve/reject — distinct from the customer token, so a
        # customer can't approve their own launch (ADR-0002 #2). None = dev (no reviewer gate).
        # Production replaces this with real RBAC.
        self._reviewer_token = reviewer_token
        # Paywall: gate the rebuild (assemble) behind a paid plan (ADR-0002 #4). Off by default —
        # the entitlement model + gate exist and are tested, but enforcement ships with payment
        # integration (Stripe). The diagnostic is always free.
        self._enforce_billing = enforce_billing
        self._now = now_fn
        # The durable-workflow seam: actions are enqueued and return 202 + a run record. Default is
        # the inline runner (synchronous, in-memory) — the dev server / production inject a
        # background/durable runner. See engine/runner.py.
        self._runner = runner or InlineRunner(InMemoryRunStore())
        # Ownership-verification I/O seams + policy. Enforcement gates expensive actions
        # (assemble, process-edits) behind a verified domain (PRODUCT-PLAN §4 step 3).
        self._resolver = resolver or SystemDnsResolver()
        self._fetcher = fetcher or UrllibFetcher()
        self._enforce_ownership = enforce_ownership
        self._routes: list[tuple[str, list[str], _Handler]] = []
        self._register()

    # -- routing ----------------------------------------------------------- #
    def _route(self, method: str, pattern: str, handler: _Handler) -> None:
        self._routes.append((method, [s for s in pattern.split("/") if s], handler))

    def _register(self) -> None:
        self._route("GET", "/healthz", _h_health)
        self._route("GET", "/v1/projects", _h_list_projects)
        self._route("POST", "/v1/projects", _h_create_project)
        self._route("GET", "/v1/projects/{slug}", _h_get_project)
        self._route("GET", "/v1/projects/{slug}/edits", _h_list_edits)
        self._route("POST", "/v1/projects/{slug}/edits", _h_create_edit)
        self._route("GET", "/v1/projects/{slug}/decisions", _h_list_decisions)
        self._route("GET", "/v1/projects/{slug}/incidents", _h_list_incidents)
        self._route("GET", "/v1/projects/{slug}/reports", _h_list_reports)
        self._route("GET", "/v1/projects/{slug}/ownership", _h_ownership_status)
        self._route("POST", "/v1/projects/{slug}/ownership/challenge", _h_ownership_challenge)
        self._route("POST", "/v1/projects/{slug}/ownership/verify", _h_ownership_verify)
        self._route("GET", "/v1/projects/{slug}/runs", _h_list_runs)
        self._route("GET", "/v1/projects/{slug}/runs/{run_id}", _h_get_run)
        self._route("GET", "/v1/projects/{slug}/usage", _h_usage)
        self._route("GET", "/v1/projects/{slug}/billing", _h_billing_status)
        self._route("POST", "/v1/projects/{slug}/billing/checkout", _h_billing_checkout)
        self._route("GET", "/v1/projects/{slug}/launch", _h_launch_status)
        self._route("POST", "/v1/projects/{slug}/launch/request", _h_launch_request)
        self._route("POST", "/v1/projects/{slug}/launch/approve", _h_launch_approve)
        self._route("POST", "/v1/projects/{slug}/launch/reject", _h_launch_reject)
        self._route("POST", "/v1/projects/{slug}/actions/assemble", _h_assemble)
        self._route("POST", "/v1/projects/{slug}/actions/process-edits", _h_process_edits)
        self._route("POST", "/v1/projects/{slug}/actions/diagnose", _h_diagnose)
        self._route("POST", "/v1/projects/{slug}/actions/cutover", _h_cutover)

    def _match(self, method: str, path: str) -> tuple[_Handler, dict[str, str]] | None:
        segs = [s for s in path.split("/") if s]
        for m, pattern, handler in self._routes:
            if m != method or len(pattern) != len(segs):
                continue
            params: dict[str, str] = {}
            ok = True
            for pat, seg in zip(pattern, segs):
                mm = _SEG.match(pat)
                if mm:
                    params[mm.group(1)] = seg
                elif pat != seg:
                    ok = False
                    break
            if ok:
                return handler, params
        return None

    # -- auth -------------------------------------------------------------- #
    def _authenticate(self, request: Request) -> None:
        """Resolve the caller. Dev mode (no token configured) allows all.

        Production replaces this with real auth that also resolves the tenant and scopes the store.
        """
        if self._token is None:
            return
        auth = request.header("authorization") or ""
        if auth != f"Bearer {self._token}":
            raise ApiError(401, "missing or invalid bearer token")

    # -- dispatch ---------------------------------------------------------- #
    def dispatch(self, request: Request) -> Response:
        try:
            if request.path != "/healthz":  # health is unauthenticated
                self._authenticate(request)
            matched = self._match(request.method, request.path)
            if matched is None:
                raise ApiError(404, f"no route for {request.method} {request.path}")
            handler, params = matched
            return handler(self, request, params)
        except ApiError as e:
            return Response(e.status, {"error": e.message})
        except ProjectExists as e:
            return Response(409, {"error": f"project already exists: {e}"})
        except PreconditionError as e:
            return Response(409, {"error": str(e)})
        except NotVerifiedError as e:
            return Response(403, {"error": str(e)})
        except NotApprovedError as e:
            return Response(403, {"error": str(e)})
        except NotPaidError as e:
            return Response(402, {"error": str(e)})  # 402 Payment Required
        except LaunchError as e:
            return Response(409, {"error": str(e)})
        except VerificationError as e:
            return Response(400, {"error": str(e)})
        except KeyError as e:
            return Response(404, {"error": f"not found: {e}"})
        except ValueError as e:
            return Response(400, {"error": str(e)})

    # -- accessors for handlers ------------------------------------------- #
    @property
    def store(self) -> ProjectStore:
        return self._store

    def _require_project(self, slug: str) -> Project:
        p = self._store.get_project(slug)
        if p is None:
            raise ApiError(404, f"unknown project: {slug}")
        return p


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def _h_health(app: Application, req: Request, _p: dict[str, str]) -> Response:
    return Response(200, {"status": "ok"})


def _h_list_projects(app: Application, req: Request, _p: dict[str, str]) -> Response:
    slugs = app.store.list_projects()
    items = []
    for slug in slugs:
        p = app.store.get_project(slug)
        if p is not None:
            items.append({"slug": p.slug, "name": p.name, "stage": p.stage.value, "domain": p.domain})
    return Response(200, {"projects": items})


def _h_create_project(app: Application, req: Request, _p: dict[str, str]) -> Response:
    body = req.body or {}
    slug = body.get("slug")
    if not slug:
        raise ApiError(400, "field 'slug' is required")
    catalog = None
    cat = body.get("catalog")
    if isinstance(cat, dict) and cat.get("source"):
        catalog = Catalog(
            source=CatalogSource(cat["source"]),
            owner=CatalogOwner(cat.get("owner", "self")),
        )
    project = Project(
        slug=slug,
        name=body.get("name", ""),
        domain=body.get("domain", ""),
        stage=Stage(body.get("stage", "queued")),
        design_mode=body.get("design_mode", "standard"),
        catalog=catalog,
    )
    created = app.store.create_project(project)
    return Response(201, _project_json(created))


def _h_get_project(app: Application, req: Request, p: dict[str, str]) -> Response:
    return Response(200, _project_json(app._require_project(p["slug"])))


def _h_list_edits(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return Response(200, {"edits": [_edit_json(e) for e in app.store.list_edits(p["slug"])]})


def _h_create_edit(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    body = req.body or {}
    name = body.get("name")
    if not name:
        raise ApiError(400, "field 'name' is required")
    content = body.get("body") or f"## Requested change\n{body.get('request', '')}\n"
    edit = app.store.create_edit(p["slug"], name, content)
    return Response(201, _edit_json(edit))


def _h_list_decisions(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return Response(200, {"decisions": [_decision_json(d) for d in app.store.list_decisions(p["slug"])]})


def _h_list_incidents(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return Response(200, {"incidents": [_incident_json(i) for i in app.store.list_incidents(p["slug"])]})


def _h_list_reports(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return Response(200, {"reports": [_report_json(r) for r in app.store.list_reports(p["slug"])]})


def _outcome_json(outcome: Any) -> dict[str, Any]:
    return {
        "ok": outcome.ok,
        "paused": outcome.paused,
        "preview_url": outcome.preview_url,
        "message": outcome.message,
    }


def _run_json(run: Run) -> dict[str, Any]:
    return run.to_dict()


def _enqueue(app: Application, slug: str, kind: str, fn: Callable[..., Any], **kwargs: Any) -> Response:
    """Submit an orchestration action to the runner and return 202 + the run record.

    The actual build runs asynchronously (background runner) or inline (default runner); either way
    the caller polls ``GET /v1/projects/{slug}/runs/{run_id}`` for status + result. Cheap
    preconditions are validated *before* this call so they still surface as synchronous 4xx.
    """
    def job() -> Any:
        return fn(app.store, app._driver, slug, now=app._now(), **kwargs)

    run = app._runner.submit(slug, kind, job)
    return Response(202, {"run": _run_json(run)})


def _h_list_runs(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return Response(200, {"runs": [_run_json(r) for r in app._runner.runs.list(p["slug"])]})


def _h_get_run(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    run = app._runner.runs.get(p["run_id"])
    if run is None or run.slug != p["slug"]:
        raise ApiError(404, f"unknown run: {p['run_id']}")
    return Response(200, {"run": _run_json(run)})


# -- metering + billing (ADR-0002 #3/#4) ----------------------------------- #
def _h_usage(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    summary = summarize_runs(app._runner.runs.list(p["slug"]))
    return Response(200, {"usage": summary.to_dict()})


def _h_billing_status(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    return Response(200, {"plan": get_plan(project), "enforced": app._enforce_billing})


def _h_billing_checkout(app: Application, req: Request, p: dict[str, str]) -> Response:
    """Dev stub for the rebuild-fee checkout. Production: Stripe Checkout + a webhook flips the plan."""
    project = app._require_project(p["slug"])
    set_plan(project, PLAN_ACTIVE)
    app.store.save_project(project)
    return Response(200, {"plan": get_plan(project)})


# -- ownership ------------------------------------------------------------- #
def _ownership_json(o: Ownership | None) -> dict[str, Any]:
    return o.to_dict() if o is not None else {"status": "unverified"}


def _h_ownership_status(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    return Response(200, {"ownership": _ownership_json(project.ownership)})


def _h_ownership_challenge(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    body = req.body or {}
    method_raw = body.get("method")
    if not method_raw:
        raise ApiError(400, "field 'method' is required (dns-txt | meta-tag | http-file)")
    try:
        method = VerificationMethod(method_raw)
    except ValueError:
        raise ApiError(400, f"unknown verification method: {method_raw!r}") from None
    domain = body.get("domain") or project.domain
    if not domain:
        raise ApiError(400, "no domain on the project; pass 'domain' in the body")
    ownership = start_verification(domain, method)  # raises VerificationError on bad input
    project.ownership = ownership
    app.store.save_project(project)
    return Response(201, {"ownership": _ownership_json(ownership), **challenge_instructions(ownership)})


def _h_ownership_verify(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    if project.ownership is None:
        raise ApiError(409, "no challenge to verify; start one first")
    result = check_verification(
        project.ownership, resolver=app._resolver, fetcher=app._fetcher
    )
    project.ownership = result.ownership
    app.store.save_project(project)
    return Response(
        200 if result.verified else 422,
        {"verified": result.verified, "detail": result.detail, "ownership": _ownership_json(result.ownership)},
    )


def _gate_ownership(app: Application, project: Project) -> None:
    """Block expensive actions until the domain is verified (unless enforcement is off)."""
    if app._enforce_ownership:
        require_verified(project)  # raises NotVerifiedError -> 403


# -- launch review (human-reviewed launch, ADR-0002 #2) -------------------- #
def _launch_json(lr: LaunchReview | None) -> dict[str, Any]:
    return lr.to_dict() if lr is not None else {"status": "none"}


def _require_reviewer(app: Application, req: Request) -> str:
    """Authorize an ops reviewer (distinct from the customer). Returns a reviewer identity."""
    if app._reviewer_token is None:
        return "dev-reviewer"  # dev mode — no reviewer gate
    if (req.header("authorization") or "") != f"Bearer {app._reviewer_token}":
        raise ApiError(403, "reviewer authorization required to approve/reject a launch")
    return "reviewer"


def _h_launch_status(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    return Response(200, {"launch": _launch_json(project.launch_review)})


def _h_launch_request(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    project.launch_review = request_review(project.launch_review, now=app._now())
    app.store.save_project(project)
    return Response(200, {"launch": _launch_json(project.launch_review)})


def _h_launch_approve(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    reviewer = _require_reviewer(app, req)
    body = req.body or {}
    project.launch_review = approve(
        project.launch_review, reviewer=reviewer, now=app._now(), note=body.get("note", "")
    )
    app.store.save_project(project)
    return Response(200, {"launch": _launch_json(project.launch_review)})


def _h_launch_reject(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    reviewer = _require_reviewer(app, req)
    body = req.body or {}
    note = body.get("note") or body.get("reason")
    if not note:
        raise ApiError(400, "a rejection requires a 'note' (reason)")
    project.launch_review = reject(project.launch_review, reviewer=reviewer, now=app._now(), note=note)
    app.store.save_project(project)
    return Response(200, {"launch": _launch_json(project.launch_review)})


def _precheck_stage(project: Project, command: Command) -> None:
    """Synchronous stage gate, so the common precondition errors return 4xx instead of a failed run.

    The orchestration entrypoint re-checks (defense in depth); rarer preconditions (e.g. an open
    concept decision) still surface via the run record's error.
    """
    if not command_available(command, project.stage):
        raise ApiError(409, f"action not available at stage {project.stage.value!r}")


def _h_assemble(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    _gate_ownership(app, project)                       # 403 unless domain verified
    if app._enforce_billing:
        require_paid_plan(project)                      # 402 unless the rebuild fee is paid
    _precheck_stage(project, Command.ASSEMBLE)          # 409 unless stage=baseline-ready
    return _enqueue(app, p["slug"], "assemble", assemble_prototype, publisher=app._publisher)


def _h_process_edits(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    _gate_ownership(app, project)
    _precheck_stage(project, Command.PROCESS_EDITS)
    if not app.store.pending_edits(p["slug"]):
        raise ApiError(409, "no PENDING edits to process")
    return _enqueue(app, p["slug"], "process-edits", process_edits, publisher=app._publisher)


def _h_diagnose(app: Application, req: Request, p: dict[str, str]) -> Response:
    app._require_project(p["slug"])
    return _enqueue(app, p["slug"], "diagnostic", run_diagnostic)


def _h_cutover(app: Application, req: Request, p: dict[str, str]) -> Response:
    project = app._require_project(p["slug"])
    _precheck_stage(project, Command.CUTOVER)        # 409 unless stage=final
    require_launch_approved(project)                 # 403 unless a reviewer approved (ADR-0002 #2)
    return _enqueue(app, p["slug"], "cutover", run_cutover)
