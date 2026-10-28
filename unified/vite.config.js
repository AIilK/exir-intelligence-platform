import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/postcss'
import scopeCss from './build/scope-css.js'
import embedSources from './build/embed-sources.js'

const here = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, here, '')
  // The two dashboards live next to this folder in the repo: ../sales and ../frontend.
  const salesFront = path.resolve(here, env.SALES_FRONTEND || '../sales/frontend')
  const financeFront = path.resolve(here, env.FINANCE_FRONTEND || '../frontend')
  const salesSrc = path.join(salesFront, 'src')
  const financeApp = path.join(financeFront, 'app')
  const under = (dir) => {
    const d = dir.replace(/\\/g, '/').toLowerCase() + '/'
    return (file) => file.toLowerCase().startsWith(d)
  }

  return {
    plugins: [embedSources({ financeApp, salesSrc }), react()],
    resolve: {
      alias: { '@sales': salesSrc, '@finance': financeApp },
      // one React / router / echarts for all three code bases
      dedupe: ['react', 'react-dom', 'react-router-dom', 'react-router', 'echarts', 'echarts-for-react'],
    },
    css: {
      postcss: {
        plugins: [
          tailwind({ base: financeFront }),
          scopeCss({
            rules: [
              { test: under(financeApp), scope: '.fin-scope' },
              { test: under(salesSrc), scope: '.sales-scope' },
            ],
          }),
        ],
      },
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.UNIFIED_PORT || 5180),
      strictPort: true,
      fs: { allow: [here, salesFront, financeFront] },
      proxy: {
        // finance (FastAPI, /api/v1/...) and sales (FastAPI, /api/...) backends
        '/api/v1': { target: env.FINANCE_API || 'http://127.0.0.1:8010', changeOrigin: true },
        '/api': { target: env.SALES_API || 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
    build: { chunkSizeWarningLimit: 4000 },
  }
})
