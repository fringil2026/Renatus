// Product data layer for Phase 1: reads the static seed in src/data/products.json.
// In Phase 2 this module is the seam that swaps to live Supabase reads — pages and
// components import ONLY from here, never from the JSON directly, so the swap is local.
import seed from "../data/products.json";

export type Difficulty = "beginner" | "intermediate" | "expert";
export type ProductStatus = "active" | "draft" | "archived";

export interface Product {
  id: string;
  slug: string;
  genus: string;
  species: string;
  common_name: string;
  origin: string;            // e.g. "Borneo · warm-growing" (mono line on the tag)
  description: string;
  price_cents: number;
  currency: string;
  stock_qty: number;
  status: ProductStatus;
  care_light: string;
  care_water: string;
  care_temp: string;         // warm | intermediate | cool growing
  difficulty: Difficulty;
  bloom_now: boolean;
  photos: string[];          // storage paths; empty in Phase 1 (no licensed photography yet)
}

const ALL = (seed.products as Product[]).filter((p) => p.status === "active");

export const products = (): Product[] => ALL;
export const inStock = (): Product[] => ALL.filter((p) => p.stock_qty > 0);
export const outOfStock = (): Product[] => ALL.filter((p) => p.stock_qty <= 0);
export const bloomingNow = (): Product[] => ALL.filter((p) => p.bloom_now && p.stock_qty > 0);

export const bySlug = (slug: string): Product | undefined => ALL.find((p) => p.slug === slug);

export const genera = (): string[] =>
  [...new Set(ALL.map((p) => p.genus))].sort((a, b) => a.localeCompare(b));

export const difficulties: Difficulty[] = ["beginner", "intermediate", "expert"];

export const isAvailable = (p: Product): boolean => p.stock_qty > 0;

export const latin = (p: Product): string => `${p.genus} ${p.species}`;

export const priceLabel = (p: Product): string =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: p.currency }).format(p.price_cents / 100);

export const difficultyColor = (d: Difficulty): string =>
  d === "beginner" ? "var(--color-leaf)" : d === "intermediate" ? "var(--color-conservatory)" : "var(--color-petal)";
