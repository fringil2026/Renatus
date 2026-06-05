// =====================================================================
// CLIENT CONFIGURATION — single file per client.
// Every CLIENT-CUSTOMIZE item maps to the Phase 2 access/inventory list.
// =====================================================================
export const SITE = {
  // CLIENT-CUSTOMIZE: identity
  name: "Meridian Grid Assurance",            // placeholder client
  legalName: "Meridian Grid Assurance LLC",
  tagline: "Managed NERC CIP compliance for registered entities",
  domain: "https://example-client.com",
  phone: "+1 (555) 014-0042",
  email: "compliance@example-client.com",
  address: { street: "100 Substation Way", city: "Charlotte", region: "NC", postal: "28202", country: "US" },

  // CLIENT-CUSTOMIZE: integrations (from Phase 2 inventory)
  formEndpoint: "/api/contact",               // CRM/ESP handler or form service URL
  turnstileSiteKey: "",                       // new keys issued per rebuild — never reuse old ones
  ga4Id: "",                                  // carry the EXISTING GA4 property forward, not a new one

  // Regional entities the client operates under — drives the trust band
  regions: ["SERC", "RF", "WECC", "MRO", "Texas RE", "NPCC"],
  certifications: ["CISSP", "CISA", "GICSP", "PMP"],
};

// Indexability is controlled by ONE environment flag.
// Staging builds default to noindex; production sets PUBLIC_INDEXABLE=true.
// This is launch-runbook step zero.
export const INDEXABLE = import.meta.env.PUBLIC_INDEXABLE === "true";
