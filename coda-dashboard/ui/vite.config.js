import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    // Mirrors the reverse proxy in ui/nginx.conf so relative API calls
    // (same-origin) also work against the Vite dev server.
    proxy: {
      '^/(auth|datasets|users|query|role-changes)': 'http://localhost:8000',
    },
  },
})
