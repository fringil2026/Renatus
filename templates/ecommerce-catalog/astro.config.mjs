// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// Phase 1 (this build): fully static catalog — no server endpoints exist yet, so
// no adapter is needed and the whole site prerenders to dist/.
// Phase 2/3 (per the build spec) add the Cloudflare adapter + `output: 'server'`
// so /api/* (checkout, stripe-webhook) and /admin/* run as server endpoints while
// catalog/product/conservatory pages stay `export const prerender = true`.
//
// CLIENT-CUSTOMIZE: set `site` to the client's production domain.
export default defineConfig({
  site: 'https://example-client.com',
  vite: { plugins: [tailwindcss()] },
});
