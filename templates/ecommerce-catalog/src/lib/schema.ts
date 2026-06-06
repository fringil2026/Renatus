// JSON-LD builders. The playbook's highest-leverage rule: every product page emits
// Product schema with offers + availability so deep product URLs win rich results.
import type { Product } from "./products";
import { latin, isAvailable } from "./products";

const AVAIL = {
  inStock: "https://schema.org/InStock",
  outOfStock: "https://schema.org/OutOfStock",
};

// schema.org wants prices as a decimal string in major units.
const priceMajor = (cents: number): string => (cents / 100).toFixed(2);

export function productSchema(p: Product, siteOrigin: string, pageUrl: string) {
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: `${latin(p)} — ${p.common_name}`,
    description: p.description,
    category: p.genus,
    sku: p.id,
    ...(p.photos.length ? { image: p.photos.map((src) => new URL(src, siteOrigin).href) } : {}),
    additionalProperty: [
      { "@type": "PropertyValue", name: "Light", value: p.care_light },
      { "@type": "PropertyValue", name: "Water", value: p.care_water },
      { "@type": "PropertyValue", name: "Temperature", value: p.care_temp },
      { "@type": "PropertyValue", name: "Difficulty", value: p.difficulty },
    ],
    offers: {
      "@type": "Offer",
      url: pageUrl,
      priceCurrency: p.currency,
      price: priceMajor(p.price_cents),
      availability: isAvailable(p) ? AVAIL.inStock : AVAIL.outOfStock,
      itemCondition: "https://schema.org/NewCondition",
    },
  };
}

export function faqSchema(qa: Array<{ q: string; a: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: qa.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: item.a },
    })),
  };
}

export function breadcrumbSchema(crumbs: Array<{ name: string; url: string }>) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: c.url,
    })),
  };
}
