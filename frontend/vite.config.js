import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Flask API runs on :5000. We proxy /api through the Vite dev server so the
// frontend can use same-origin relative URLs and CORS never becomes a demo-day
// surprise.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
