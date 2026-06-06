// =====================================================================
// CLIENT CONFIGURATION — single file per client (the ecommerce-catalog archetype).
// Every CLIENT-CUSTOMIZE item maps to the Phase 2 access/inventory list in the
// build spec (Stripe account, Supabase project, Resend domain, etc.).
// =====================================================================
export const SITE = {
  // CLIENT-CUSTOMIZE: identity
  name: "Example Nursery",                    // placeholder client
  legalName: "Example Nursery LLC",           // used on receipts (FOR REVIEW until confirmed)
  tagline: "A living catalogue of specimen plants",
  domain: "https://example-client.com",
  email: "hello@example-client.com",
  instagram: "",                              // link-out (Tier 1); blank = hidden

  // CLIENT-CUSTOMIZE: integrations (wired in later phases — blank in Phase 1)
  currency: "USD",
  stripePublishableKey: "",                   // new keys per rebuild — never reuse
  ga4Id: "",                                  // carry the EXISTING GA4 property forward, not a new one

  // Shipping / live-goods policy surface (Tier 1 policy page)
  shipsLivePlants: true,
  weatherHoldNote: "We hold live-plant shipments during temperature extremes; a heat pack is offered at checkout.",
};

// Indexability is controlled by ONE environment flag.
// Staging builds default to noindex; production sets PUBLIC_INDEXABLE=true.
// This is launch-runbook step zero.
export const INDEXABLE = import.meta.env.PUBLIC_INDEXABLE === "true";
