import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * What the saved cache is valid for: this exact API contract.
 *
 * Saved answers outlive deploys — three weeks on the website, and across App
 * Store updates in the app — and new code handed an answer of the old shape can
 * throw on its first render. So the persister's buster is a short hash of
 * openapi.json, the contract the client's types are generated from (`npm run
 * gen:api`): saved figures are dropped exactly when the API's shape changes,
 * without anyone having to remember to bump a version by hand.
 * scripts/build-seed-cache.mjs computes the same hash for the bundled
 * snapshot, and review:seed fails if the two ever disagree.
 */
const cacheBuster = createHash('sha256')
  .update(readFileSync(new URL('./openapi.json', import.meta.url)))
  .digest('hex')
  .slice(0, 12)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __CACHE_BUSTER__: JSON.stringify(cacheBuster) },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
