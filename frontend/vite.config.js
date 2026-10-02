import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import basStyleKit from './vite-plugins/basStyleKit.js'

// Django serves the build output from STATICFILES_DIRS, so asset URLs must be rooted at /static/frontend/.
// Entry file names are stable (no content hash) so the Django template can reference them without
// being edited after every build; cache-busting is left to Django's static files storage.
export default defineConfig(({ command }) => ({
  plugins: [react(), basStyleKit({ version: '0.7.4' })],
  root: '.',
  base: command === 'build' ? '/static/frontend/' : '/',
  build: {
    outDir: '../polarrouteserver/frontend/static/frontend',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: (asset) =>
          asset.name && asset.name.endsWith('.css') ? 'assets/[name][extname]' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
}))
