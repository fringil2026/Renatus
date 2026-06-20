# infra/ — infrastructure as code (scaffold)

Provisioning + config for the control plane and workers: Postgres, object storage (Cloudflare R2),
the workflow engine (Temporal/Inngest), sandbox provider (Fly Machines), secrets/credential vault,
observability. See `docs/adr/0001-foundational-decisions.md`.

**Status:** scaffold only — populated as Phases 2+ stand up real infrastructure. The existing
`deploy/` (VPS lift-and-shift for the single-operator tool) is separate and remains valid as an
interim "always-on for me" step.
