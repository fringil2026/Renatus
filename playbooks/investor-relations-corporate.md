# Playbook: Investor Relations / Corporate Holding Site
<!-- Generated 2026-06-11 by the site-diagnostic engine (new-industry path) while diagnosing
     berkshirehathaway.com. Reviewed standard for corporate/IR prospects — refine as real
     IR clients arrive. Keep under ~150 lines. -->

## Buyer & buying moment
Shareholders, prospective investors, analysts, journalists, and acquisition/partnership
counterparties. They arrive with a specific retrieval task — find a filing, a letter, an
annual report, a press release, a meeting date, a contact — and judge the company's
operational seriousness by how fast and confidently they can complete it. Trust and
findability outrank persuasion; nobody is "converted" here, they are reassured.

## Sections that must exist
Archetype: document-forward corporate site (closest existing archetype + a filings index).
Company overview (what the company is, in one screen) · leadership/governance page ·
news/press releases (dated, reverse-chronological) · financial reports & SEC-filings index
(linked to EDGAR where applicable) · annual-meeting / shareholder-information page ·
investor contact path (named function, not a dead inbox) · legal disclaimer. Remove:
marketing-style hero carousels and conversion CTAs — they read as unserious here.

## Trust signals buyers scan for
Dated documents with visible "last updated" stamps · direct EDGAR/SEC links · named
transfer agent and auditor where applicable · physical headquarters address · governance
documents (committee charters, ethics code) · https everywhere · absence of stock-photo
gloss (substance over decoration is the credibility marker in this industry).

## Schema (JSON-LD)
Organization (legalName, address, logo, sameAs → EDGAR/exchange listing) · NewsArticle
for press releases · Event for the annual meeting · BreadcrumbList. Fields that matter:
datePublished/dateModified on every document-bearing page.

## Tone & vocabulary
Voice: measured, factual, unhurried — the company does not need to sell itself. Use:
"filings", "shareholders", "governance", precise dates. Never use: hype ("revolutionary",
"world-class"), exclamation marks, urgency language, vague superlatives.

## Conversion pattern
There is no sales CTA. The primary "conversion" is task completion: a filings/document
finder visible from the homepage, and a clearly labelled investor-relations contact
(email + mailing address). Forms ask for nothing beyond name/email/topic — analysts will
not fill out marketing fields.

## Legal & compliance must-haves
Forward-looking-statements disclaimer on financial pages · clear legal disclaimer page ·
accurate copyright · no implied solicitation of investment · accessibility basics
(screen-reader-navigable document lists; filings as accessible HTML/PDF, not scans).

## Imagery direction
Minimal and real: headquarters, leadership headshots, document covers. Charts over
photography. Anything that looks like a stock-photo handshake actively damages
credibility in this industry.

## FAQ topics that earn AI-search citations
"How do I find <company>'s annual report?" · "When is the <company> annual meeting?" ·
"Who is <company>'s transfer agent?" · "How do I buy <company> shares?" · "Where are
<company>'s SEC filings?" · "How do I contact <company> investor relations?"

## Never do
Never bury filings more than two clicks from the homepage. Never publish undated
financial documents. Never use marketing urgency or sales CTAs on IR pages. Never break
old document URLs (analysts deep-link them). Never serve financial documents over http.
Never let news/press sections go visibly stale (an abandoned news feed reads as distress).
