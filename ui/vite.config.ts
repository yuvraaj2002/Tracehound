import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The UI reads the backend's model config (src/tracehound/resources/config.json) directly.
  server: { fs: { allow: ['..'] } },
})
