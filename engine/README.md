# engine/ — the headless rebuild engine

The studio's crown jewels (the skills, archetypes, playbooks, doctrine) made callable as a service —
**no operator dashboard, no cwd-is-a-client-folder assumptions.** This is the moat; everything else
(api, web, workers) wraps it.

## Status
- ✅ `models.py` — typed domain models (Stage, Project, Edit, Decision, Incident, Report, Version,
  Catalog) that replace `status.json` + filename-as-state.
- ✅ `store.py` — abstract `ProjectStore` + `ArtifactStore` interfaces (the persistence boundary).
- ✅ `fs_store.py` — `FilesystemProjectStore` over the existing `clients/<slug>/` layout (dev parity).
- ✅ `driver.py` — the `BuildDriver` seam (Claude execution): `LocalClaudeDriver` (shells `claude -p`,
  today's model), `MockBuildDriver` (tests), `AgentResult` + the transient-failure classifier.
- ✅ `agent_sdk_driver.py` — `AgentSDKDriver`, the production driver via the Claude Agent SDK
  (`claude-agent-sdk`); lazy-imported, async→sync bridged, captures cost/usage for metering.
- ✅ `publish.py` — the `Publisher` seam (studio-owned deploy net) + `MockPublisher`.
- ✅ `transitions.py` — the stage machine (valid transitions + which command is available per stage).
- ✅ `orchestration.py` — headless command entrypoints `assemble_prototype`, `process_edits`,
  `run_diagnostic` (+ generalized `run_command`): stage gates, PUBLISH-ALWAYS, transient→paused vs
  hard→error, append-only reporting — all taking an explicit `ProjectStore`/`BuildDriver`/`Publisher`.
- ✅ `ownership.py` — domain-ownership verification (DNS-TXT / meta-tag / HTTP-file) behind
  `DnsResolver`/`HttpFetcher` seams; `require_verified` gate.
- ✅ `runs.py` + `runner.py` — the durable-workflow seam: `Run`/`RunStore` (in-memory + filesystem),
  `Runner` (`InlineRunner`, `ThreadRunner`) wrapping orchestration jobs with persisted run-state.
- ✅ `sql_store.py` — `SqlProjectStore` + `SqlRunStore` (DB-API; sqlite for dev/test, Postgres for
  prod) + `InMemoryArtifactStore`. Behavior is proven identical to the filesystem store by the shared
  contract in `tests/test_store_conformance.py`.
- ⏳ Next (decision/infra-bound): the **Postgres binding** (psycopg conn + `placeholder="%s"`) and an
  **R2 `ArtifactStore`**; a **Temporal/Inngest `Runner`**; running `AgentSDKDriver` in a per-tenant
  sandbox (`workers/`); the customer web app (`web/`).

## Tests
`python3 tests/test_fs_store.py` · `test_orchestration.py` · `test_agent_sdk_driver.py` ·
`test_ownership.py` · `test_runner.py` · `test_store_conformance.py` (all run standalone or under
pytest). The live Agent-SDK probe is opt-in: `AGENT_SDK_SMOKE=1 python3 tests/smoke_agent_sdk.py`
(needs the SDK + an authenticated `claude` CLI; spends tokens).

## Production bindings (the remaining swaps, all behind existing interfaces)
- **Postgres:** `SqlProjectStore(psycopg.connect(...), placeholder="%s")` (+ `SqlRunStore`). The SQL is
  already `ON CONFLICT`-portable; only the placeholder and the blob column type (`JSONB`) differ.
- **R2 artifacts:** implement `ArtifactStore` over S3/R2 and inject via `artifacts_factory`.
- **Durable runner:** implement `Runner` over Temporal/Inngest for crash-recovery.

## Why an interface first
The whole tool→SaaS migration hinges on decoupling the engine from the filesystem. Once the skills
read/write through `ProjectStore` instead of raw `clients/<slug>/...` paths, the same engine runs
locally (filesystem) and in production (Postgres + object storage) unchanged. See
`docs/adr/0001-foundational-decisions.md` §3.
