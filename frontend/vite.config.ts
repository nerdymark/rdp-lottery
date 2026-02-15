import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/logs/stream': {
        target: 'http://localhost:8000',
        headers: { 'Accept': 'text/event-stream' },
      },
      '/api': 'http://localhost:8000',
    },
  },
})
