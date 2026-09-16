import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    preview: {
      allowedHosts: true,
    },
    define: {
      'import.meta.env.LEGACY_CUSTOMER_APP_ENABLED': JSON.stringify(
        env.LEGACY_CUSTOMER_APP_ENABLED ?? ''
      ),
    },
  }
})
