# What I need from you

Everything here requires **you** — accounts, browser logins, secret keys, money, DNS, or business
decisions. Everything *not* on this list, I can build. Already installed on this machine: `claude`,
`wrangler`, `cloudflared`, `psql`, `node`/`npm`, Python **Playwright** — so diagnostics and Cloudflare
deploys can run here once you're logged in. Missing: `gh`, the `stripe` CLI, and a PageSpeed key.

## A. Put the website online (do first)

1. **GitHub repo** — I can't create it or push without a remote. Create an empty repo, then paste me
   the URL (I push) or run: `git remote add origin <url>` then `git push -u origin saas-foundation`.
2. **Vercel account (web app)** — sign up, import the repo, set Root Directory = `web`, add env
   `API_BASE_URL`, Deploy. You get a public `*.vercel.app` URL.
3. **API host (Render/Railway/Fly)** — sign up, deploy the repo (uses the committed `render.yaml`),
   copy its public URL into Vercel's `API_BASE_URL`.

## B. Make the diagnostic + rebuilds actually run

4. **PageSpeed Insights API key** — create a free Google PSI key; give it to me. Fixes the unkeyed
   429s.
5. **Chromium for Playwright on the host** — run `python3 -m playwright install chromium` (one command
   locally; I add it to the host build).
6. **Claude login for headless builds** — run `claude` and sign in so builds can run.
7. **Cloudflare login (to publish rebuilt client sites)** — run `wrangler login` (your account).

## C. Turn on payments

8. **Stripe account + keys** — create a Product + Price; give me the test secret key, Price ID, and a
   webhook signing secret. I build the integration and turn the paywall on.

## D. Automated outreach (sourcing contacts + emails)

9. **Apollo / Reply.io / Clearout / ZeroBounce access** — confirm the existing keys are authed or give
   me new ones. Then I build the Apollo sourcing adapter + funnel glue.
10. **Email-sending setup (only when you send)** — authenticate your sending domain in Reply.io
    (SPF/DKIM via your DNS; I never touch MX/SPF/DKIM/DMARC), and give me a physical mailing address +
    an unsubscribe preference for CAN-SPAM. Sending stays human-approved.

## E. Production data/infra (when you outgrow the dev defaults)

11. **Postgres** — create a Neon/Supabase DB, give me the DSN. I swap the SQL store in.
12. **Object storage (R2/S3), Temporal/Inngest, a sandbox provider (Fly/E2B)** — vendor accounts,
    later, at scale; give me keys when ready.
13. **Auth vendor (Clerk/Auth0/Supabase Auth)** — for real tenant login; plugs into the existing seam.

## F. Decisions, legal, money (no code, but I need answers)

14. **Pricing numbers** — rebuild fee + subscription, for Stripe + the paywall copy.
15. **Launch segment + metro** for outreach (lean: nurseries / small commerce).
16. **Legal pages** — Privacy Policy + Terms + the CAN-SPAM physical address. I can draft; you own/review.
17. **Domain (optional)** — buy a domain, add the DNS record Vercel shows. The `*.vercel.app` URL works
    without this.
18. **Budget/credits** — Claude tokens, Apollo/validation credits, hosting plans. Set ceilings; I cap
    in code.

## The minimum to have a public, shareable website today

Just **A (1–3)** plus **B (4–6)**: GitHub repo → Vercel → API host → PSI key + `playwright install` +
`claude` login. That makes the funnel live and the free diagnostic work. Everything else layers on.

## What I do the moment you hand me each thing

- Repo URL → push the branch.
- API URL → wire `API_BASE_URL` + verify the live funnel.
- PSI key / Stripe keys / Postgres DSN → set env + build the integration.
- `wrangler` / `claude` logged in → run a real diagnostic and a real rebuild end-to-end.
