# web/ — the customer funnel app (Next.js)

The self-serve product surface. Full funnel design + endpoint map: **`FUNNEL.md`**. This README is
how to run/deploy.

## Run locally
```sh
# 1. start the control-plane API (repo root):
python3 -m api.server                 # http://127.0.0.1:8099
# 2. this app:
cp .env.local.example .env.local      # API_BASE_URL=http://127.0.0.1:8099
npm install
npm run dev                            # http://localhost:3000
```

## What's built (first slice)
- Landing → enter a domain → creates the project + kicks off the **free diagnostic** → routes to the
  project page.
- Project page (`/projects/<slug>`) — live status driven by the project `stage`, run list, reports,
  preview link. Server-side API client (`lib/api.ts`) keeps the tenant token off the browser.

Next slices (per `FUNNEL.md`): paywall (Stripe), ownership verification, concept boards, edits,
launch request, ops review console.

## Deploy (public)
- **Vercel:** import the repo, set **Root Directory = `web`**, add env var `API_BASE_URL` (your
  public API URL) and `WS_TENANT_TOKEN` if using auth. Deploy → public `*.vercel.app` URL.
- **API:** deploy the repo with `render.yaml` (repo root) or any host running
  `uvicorn api.asgi:app`. See repo `docs/NEXT-STEPS.md`.
