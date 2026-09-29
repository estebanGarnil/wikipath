import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(() => {
  const target = process.env.BOILR_API_PROXY_TARGET || "http://backend:8000"
  if (target && !/^https?:\/\//.test(target)) {
    throw new Error('BOILR_API_PROXY_TARGET must start with http:// or https://')
  }
  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      watch: { usePolling: false },
      proxy: target ? {
        '/api': {
          target,
          changeOrigin: true,
        },
      } : undefined,
    },
  }
})