import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Порт > 50000 — обход WinError 10013 (Hyper-V захватывает диапазон 1024–50000)
  server: {
    host: '127.0.0.1',
    port: 60001,
    strictPort: true,
  },
})
