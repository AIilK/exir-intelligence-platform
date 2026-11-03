import path from 'node:path'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwind from '@tailwindcss/postcss'
import scopeCss from './build/scope-css.js'
import embedSources from './build/embed-sources.js'

const here = path.dirname(fileURLToPath(import.meta.url))

// پنل مغایرت‌گیری (frontend/app/reconciliation) کلید API بک‌اند را از همین Proxy می‌گیرد تا مرورگر کلید را نبیند
// (همان کار frontend/vite.config.ts)؛ کلید از backend/.env خوانده می‌شود.
function backendEnvValue(name) {
  try {
    const line = readFileSync(path.resolve(here, '../backend/.env'), 'utf8').split(/\r?\n/).find((r) => r.trim().startsWith(`${name}=`))
    return line ? line.slice(line.indexOf('=') + 1).trim().replace(/^["']|["']$/g, '') : ''
  } catch {
    return ''
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, here, '')
  const recKey = (env.RECONCILIATION_API_KEY || backendEnvValue('RECONCILIATION_API_KEY')).trim()
  const proxy = {
    '/__reconciliation_proxy': {
      target: env.FINANCE_API || 'http://127.0.0.1:8010', changeOrigin: true,
      headers: recKey ? { 'X-Reconciliation-API-Key': recKey } : {},
      rewrite: (p) => p.replace('/__reconciliation_proxy', '/api/v1/treasury'),
    },
    // finance (FastAPI, /api/v1/...) and sales (FastAPI, /api/...) backends
    '/api/v1': { target: env.FINANCE_API || 'http://127.0.0.1:8010', changeOrigin: true },
    '/api': { target: env.SALES_API || 'http://127.0.0.1:8000', changeOrigin: true },
  }
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
      alias: [
        { find: '@sales', replacement: salesSrc },
        { find: '@finance', replacement: financeApp },
        // finance globals.css does `@import "tailwindcss"`, but ../frontend has no node_modules
        { find: /^tailwindcss$/, replacement: path.join(here, 'node_modules/tailwindcss/index.css') },
      ],
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
      proxy,
    },
    // RUN_UNIFIED.bat: «vite build» + «vite preview» روی همین پورت و همین Proxy (نسخه production، بسیار سریع‌تر از dev)
    preview: { host: '0.0.0.0', port: Number(env.UNIFIED_PORT || 5180), strictPort: true, proxy },
    build: { chunkSizeWarningLimit: 4000 },
  }
})
