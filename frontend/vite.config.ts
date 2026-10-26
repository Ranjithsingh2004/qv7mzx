import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

/**
 * In development the API runs as a separate container (see docker-compose.yml),
 * so `/api` is proxied to it and the browser only ever talks to one origin.
 * In production the same relative `/api` path is served by the deployment
 * (Vercel rewrites it to the Python function), which is why the frontend never
 * needs a hard-coded backend host. `VITE_API_BASE_URL` overrides this for the
 * split-host case.
 */
/** Where `/api` is proxied during local development and preview. */
const apiTarget = process.env.VITE_DEV_API_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  // `vite preview` serves the production bundle; proxying /api here too means
  // the built artefact can be verified against a real backend before deploying.
  preview: {
    port: 4173,
    host: true,
    proxy: { '/api': { target: apiTarget, changeOrigin: true } },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // The vendor split above is deliberate; this keeps the expected size from
    // being reported as a warning on every build.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // React and Recharts are the bulk of the bundle and change far less
        // often than application code, so they are split into a vendor chunk
        // that caches independently of each deploy.
        manualChunks: { vendor: ['react', 'react-dom', 'recharts'] },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
