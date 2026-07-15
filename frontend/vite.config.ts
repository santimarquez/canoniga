import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig(({ command }) => ({
  // Production bundles are served under /app-assets/ by Python; dev uses site root.
  base: command === 'serve' ? '/' : '/app-assets/',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
    fs: {
      allow: ['..'],
    },
  },
  build: {
    outDir: '../assets/dist',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
}))
