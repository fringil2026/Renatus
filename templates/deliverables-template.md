---
template: deliverables-request
mirrors: discovery-handbook §2
client: <slug>
generated: <YYYY-MM-DD>
instructions: >
  MASTER taxonomy. Do NOT hand this to a client whole. Command 1's final step
  instantiates 02-intake/deliverables-request.md by FILTERING (drop rows that don't
  apply to this archetype / detected stack / spec phases) and SPECIALIZING (name the
  detected GA4 ID, reference detected forms by page, etc.). §2.1 and §2.2 are ALWAYS
  BLOCKING. Append an "Omitted as not applicable" list so every omission is auditable.
---

# Deliverables Request — <CLIENT>

What we need from you (and what we can find ourselves). Each row has a **status** that
updates IN PLACE as things arrive — rows are never deleted. Priority: **BLOCKING** (launch
cannot happen), **PHASE-n** (needed for that build phase), **NICE-TO-HAVE**.
Status flow: **NEEDED → REQUESTED → RECEIVED → VERIFIED**.

> Standard fallback for any row you can't answer: *"If you don't know — who might (your
> developer, host, agency, registrar)? And may we investigate it via public records and
> public tooling, no passwords involved?"*

## 2.1 Access & control  — ALWAYS BLOCKING
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.1.1 | Domain registrar + login (or ability to change nameservers/DNS) | Can't point the domain at the new site without it | BLOCKING | NEEDED | Who registered the domain? We can confirm the registrar via public WHOIS. |
| D-2.1.2 | DNS host + full current zone export (all records) | We re-create every record exactly; a missed record breaks email/subdomains | BLOCKING | NEEDED | We can read the public zone; the authoritative export still needs your DNS login. |
| D-2.1.3 | Current hosting provider + control-panel access | To retrieve assets and decommission cleanly after cutover | BLOCKING | NEEDED | Who hosts the current site? We can fingerprint it from headers. |
| D-2.1.4 | CMS/admin access (if any) | To export content/users the scrape can't reach | PHASE-1 | NEEDED | We detected the CMS from the page source; login still required for export. |
| D-2.1.5 | CDN / reverse proxy account (e.g. Cloudflare) | Redirects + caching live at the edge; we need the zone | BLOCKING | NEEDED | We can detect the proxy; the account is yours to grant. |
| D-2.1.6 | SSL/TLS specifics (cert provider, any pinning) | Avoid an HTTPS gap at cutover | PHASE-1 | NEEDED | We can read the live cert chain; provider account confirms renewal. |

## 2.2 Email infrastructure  — ALWAYS BLOCKING (never edited by us without sign-off)
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.2.1 | Email host / provider | Confirms whose MX must be preserved through cutover | BLOCKING | NEEDED | We can read public MX records to identify the provider. |
| D-2.2.2 | MX / SPF / DKIM / DMARC records to carry forward | A DNS move that drops these silently breaks email deliverability | BLOCKING | NEEDED | We can read all four from public DNS and propose carry-forward for your confirmation. |
| D-2.2.3 | Subdomains in use (mail, shop, blog, vpn, etc.) | Each must be re-created in the new zone | BLOCKING | NEEDED | We can enumerate some via public records; you confirm internal ones. |

## 2.3 Server-side functionality
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.3.1 | Where each form submits + access to past submissions | Rebuilt forms must reach the same inbox/CRM; archives are records | PHASE-1 | NEEDED | We list detected forms by page; you confirm each destination. |
| D-2.3.2 | CRM / ESP accounts (mailing list, newsletter) | Reconnect signup flows to the same list | PHASE-n | NEEDED | We detect embedded ESP tags; account access is yours. |
| D-2.3.3 | Gated content / registered-user lists | Migrate accounts without lockout | PHASE-n | NEEDED | Export from the current CMS/login system. |
| D-2.3.4 | Payment processor account | Checkout must pay out to you; keys are per-site | BLOCKING-for-commerce | NEEDED | Your processor account; we issue new keys, never reuse. |
| D-2.3.5 | Scheduling / chat / booking embeds | Re-embed the same widgets | NICE-TO-HAVE | NEEDED | We detect the embed; account is yours. |
| D-2.3.6 | Search backend (if server-side) | Replace or re-point site search | PHASE-n | NEEDED | We note the current search; static search may replace it. |
| D-2.3.7 | Scheduled jobs / automations (cron, webhooks) | Don't silently drop a nightly export or sync | PHASE-n | NEEDED | Often invisible externally — you or your developer must list these. |

## 2.4 Accounts, keys & licenses
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.4.1 | GA4 property (existing) | Carry analytics history forward; never start a new property | PHASE-1 | NEEDED | We detected the measurement ID in the page; you grant property access. |
| D-2.4.2 | Search Console (+ Bing Webmaster) | Submit sitemap, watch the migration, keep history | PHASE-1 | NEEDED | We verify the new property; you grant the existing one. |
| D-2.4.3 | Google Business Profile | Keep the map listing pointed at the live site | NICE-TO-HAVE | NEEDED | Public listing visible; management access is yours. |
| D-2.4.4 | Tag Manager + ad/marketing pixels | Re-fire the same conversions | PHASE-n | NEEDED | We list detected tags/pixels; accounts are yours. |
| D-2.4.5 | Embedded third-party API keys | Re-wire maps, embeds, integrations | PHASE-n | NEEDED | We flag detected keys; you reissue/scope them. |
| D-2.4.6 | Font licenses | Ship type legally | PHASE-1 | NEEDED | We can substitute license-safe (Google Fonts) if none provided. |
| D-2.4.7 | Stock-image licenses | Legal right to ship each image | BLOCKING-at-launch | NEEDED | At Finish, unlicensed images are FOR REVIEW + replaced. |
| D-2.4.8 | Copy / asset provenance (who wrote/shot it) | Scraped copy/imagery is DRAFT until ownership confirmed | BLOCKING-at-launch | NEEDED | You confirm authorship; otherwise we draft/replace. |

## 2.5 Historical & SEO
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.5.1 | GSC performance export (top queries/pages) | Protect the URLs and terms that already earn traffic | PHASE-1 | NEEDED | We infer high-value deep pages from the crawl; the export is richer. |
| D-2.5.2 | Backlink profile | Know which inbound links must keep landing | NICE-TO-HAVE | NEEDED | Partial via public tools; full needs your SEO account. |
| D-2.5.3 | Existing server-level redirects | Preserve redirect chains already in place | PHASE-1 | NEEDED | We test live redirects; the server config is authoritative. |
| D-2.5.4 | Analytics history (pre-GA4 if any) | Continuity of reporting | NICE-TO-HAVE | NEEDED | Export from the old analytics property. |
| D-2.5.5 | Domain history / prior penalties | Avoid inheriting an SEO problem | NICE-TO-HAVE | NEEDED | Partly public; you fill gaps. |

## 2.6 Business & legal
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.6.1 | Privacy / cookie obligations | The new site needs the correct notices | PHASE-1 | NEEDED | We template standard notices; your counsel confirms specifics. |
| D-2.6.2 | Compliance / accessibility language required | Some sectors mandate specific statements | PHASE-n | NEEDED | We apply WCAG defaults; you confirm sector rules. |
| D-2.6.3 | Brand assets — vector logo + guidelines | Crisp logo + correct colors/spacing | PHASE-1 | NEEDED | We can trace a raster logo as a stopgap, flagged FOR REVIEW. |
| D-2.6.4 | People — bios, headshots (with permission), certifications | Real team content, used only with consent | PHASE-n | NEEDED | Blanks stay blank + FOR REVIEW; never fabricated. |
| D-2.6.5 | Business legal name (for receipts/footer) | Required on transactional email + legal footer | BLOCKING-for-commerce | NEEDED | You provide; we never guess a legal name. |

## 2.7 Project-specific  — populated from the binding spec's "client facts required"
| ID | What we need | Why | Priority | Status | Fallback |
|---|---|---|---|---|---|
| D-2.7.1 | <spec fact 1> | <why, from spec> | <BLOCKING/PHASE-n> | NEEDED | <who would know> |

---

## Omitted as not applicable
*(Command 1 fills this when specializing — one line per omitted row with the reason, so
every omission is auditable.)*
- (none yet)
