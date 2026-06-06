// Per-genus care guides, generated from the catalog's own care data (Edit 003).
// Aggregates the products of each genus into a guide + an FAQ (used for FAQPage schema).
// Prose is DRAFT general horticulture, derived from real per-product care fields.
import { products, type Product } from "./products";

export interface CareGuide {
  genus: string;
  slug: string;
  count: number;
  light: string;
  water: string;
  temps: string[];        // distinct growing temperatures in this genus
  difficulties: string[]; // distinct care levels
  origins: string[];
  examples: Product[];
  faq: Array<{ q: string; a: string }>;
}

const uniq = (xs: string[]) => [...new Set(xs.filter(Boolean))];
export const genusSlug = (g: string) => g.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function buildFaq(genus: string, items: Product[]): Array<{ q: string; a: string }> {
  const lights = uniq(items.map((p) => p.care_light));
  const waters = uniq(items.map((p) => p.care_water));
  const temps = uniq(items.map((p) => p.care_temp));
  const easy = items.some((p) => p.difficulty === "beginner");
  const origins = uniq(items.map((p) => p.origin.split("·")[0].trim()));
  return [
    { q: `How much light does ${genus} need?`, a: `${lights.join("; ") || "Bright, indirect light"}.` },
    { q: `How often should I water ${genus}?`, a: `${waters.join("; ") || "Water when approaching dryness"}.` },
    { q: `What temperatures suit ${genus}?`, a: `Grown ${temps.join(" to ")}-growing. Match the night drop to its origin (${origins.join(", ")}).` },
    { q: `Is ${genus} a good orchid for beginners?`, a: easy
        ? `Yes — this genus includes forgiving, beginner-friendly plants in our catalogue.`
        : `${genus} in our catalogue leans intermediate to expert; start with its easier relatives if you are new.` },
  ];
}

export function careGuides(): CareGuide[] {
  const byGenus = new Map<string, Product[]>();
  for (const p of products()) {
    if (!byGenus.has(p.genus)) byGenus.set(p.genus, []);
    byGenus.get(p.genus)!.push(p);
  }
  return [...byGenus.entries()]
    .map(([genus, items]) => ({
      genus,
      slug: genusSlug(genus),
      count: items.length,
      light: uniq(items.map((p) => p.care_light)).join("; "),
      water: uniq(items.map((p) => p.care_water)).join("; "),
      temps: uniq(items.map((p) => p.care_temp)),
      difficulties: uniq(items.map((p) => p.difficulty)),
      origins: uniq(items.map((p) => p.origin)),
      examples: items,
      faq: buildFaq(genus, items),
    }))
    .sort((a, b) => a.genus.localeCompare(b.genus));
}

export const careGuideBySlug = (slug: string): CareGuide | undefined =>
  careGuides().find((g) => g.slug === slug);
