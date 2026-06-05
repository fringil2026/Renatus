// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// CLIENT-CUSTOMIZE: set `site` to the client's production domain.
// Used for canonical URLs, sitemap, and OG tags.
export default defineConfig({
  site: 'https://example-client.com',
  vite: { plugins: [tailwindcss()] },
});
