// سرور production داشبورد یکپارچه (به‌جای «vite preview» که فقط برای پیش‌نمایش است).
// بدون وابستگی: فقط ماژول‌های داخلی Node.
//  - فایل‌های dist را سرو می‌کند: assets (نام‌شان hash دارد) یک سال کش می‌شوند، index.html هیچ‌وقت کش نمی‌شود.
//  - فایل‌های متنی (js/css/html/svg/json) یک بار با brotli و gzip فشرده و در حافظه نگه داشته می‌شوند.
//  - همان Proxyهای vite.config.js: /api/v1 → بک‌اند مالی، /api → بک‌اند فروش، /__reconciliation_proxy → خزانه.
// اجرا: node server.mjs   (تنظیم با UNIFIED_PORT، FINANCE_API، SALES_API، UNIFIED_HOST)
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const DIST = path.join(here, 'dist')
const PORT = Number(process.env.UNIFIED_PORT || 5180)
const HOST = process.env.UNIFIED_HOST || '0.0.0.0'
const FINANCE_API = new URL(process.env.FINANCE_API || 'http://127.0.0.1:8010')
const SALES_API = new URL(process.env.SALES_API || 'http://127.0.0.1:8000')

// همان رفتار vite.config.js: پنل مغایرت‌گیری کلید API را از Proxy می‌گیرد تا مرورگر کلید را نبیند.
function backendEnvValue(name) {
  try {
    const line = fs.readFileSync(path.resolve(here, '../backend/.env'), 'utf8').split(/\r?\n/).find((r) => r.trim().startsWith(`${name}=`))
    return line ? line.slice(line.indexOf('=') + 1).trim().replace(/^["']|["']$/g, '') : ''
  } catch {
    return ''
  }
}
const REC_KEY = (process.env.RECONCILIATION_API_KEY || backendEnvValue('RECONCILIATION_API_KEY')).trim()

const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
}
const COMPRESSIBLE = new Set(['.html', '.js', '.mjs', '.css', '.json', '.svg', '.txt', '.map'])

// فایل‌ها یک بار خوانده و فشرده می‌شوند؛ با هر build تازه (تغییر mtime) دوباره ساخته می‌شوند.
const cache = new Map()
function load(file) {
  const stat = fs.statSync(file)
  const hit = cache.get(file)
  if (hit && hit.mtime === stat.mtimeMs) return hit
  const ext = path.extname(file).toLowerCase()
  const raw = fs.readFileSync(file)
  const entry = { mtime: stat.mtimeMs, ext, raw, type: TYPES[ext] || 'application/octet-stream' }
  if (COMPRESSIBLE.has(ext) && raw.length > 1024) {
    entry.br = zlib.brotliCompressSync(raw, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 9 } })
    entry.gz = zlib.gzipSync(raw, { level: 9 })
  }
  cache.set(file, entry)
  return entry
}

function sendFile(req, res, file, cacheControl) {
  const e = load(file)
  const accept = String(req.headers['accept-encoding'] || '')
  let body = e.raw
  const headers = { 'Content-Type': e.type, 'Cache-Control': cacheControl, Vary: 'Accept-Encoding' }
  if (e.br && /\bbr\b/.test(accept)) { body = e.br; headers['Content-Encoding'] = 'br' }
  else if (e.gz && /\bgzip\b/.test(accept)) { body = e.gz; headers['Content-Encoding'] = 'gzip' }
  headers['Content-Length'] = body.length
  res.writeHead(200, headers)
  res.end(req.method === 'HEAD' ? undefined : body)
}

function serveStatic(req, res) {
  let pathname
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://x').pathname)
  } catch {
    res.writeHead(400).end()
    return
  }
  const file = path.join(DIST, path.normalize(pathname))
  if (!file.startsWith(DIST + path.sep) && file !== DIST) {
    res.writeHead(403).end()
    return
  }
  if (pathname !== '/' && fs.existsSync(file) && fs.statSync(file).isFile()) {
    const immutable = pathname.startsWith('/assets/')
    sendFile(req, res, file, immutable ? 'public, max-age=31536000, immutable' : 'no-cache')
    return
  }
  // مسیرهای React Router (SPA): همیشه index.html تازه
  const index = path.join(DIST, 'index.html')
  if (!fs.existsSync(index)) {
    res.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' }).end('dist/index.html not found - run "npx vite build" first.')
    return
  }
  sendFile(req, res, index, 'no-cache')
}

function proxy(req, res, target, pathRewrite, extraHeaders = {}) {
  const headers = { ...req.headers, ...extraHeaders, host: target.host }
  const upstream = http.request(
    { hostname: target.hostname, port: target.port || 80, method: req.method, path: pathRewrite, headers },
    (up) => {
      res.writeHead(up.statusCode || 502, up.headers)
      up.pipe(res)
    },
  )
  upstream.on('error', (err) => {
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
    res.end(JSON.stringify({ detail: `بک‌اند در دسترس نیست (${target.host}): ${err.code || err.message}` }))
  })
  req.pipe(upstream)
}

const server = http.createServer((req, res) => {
  const url = req.url || '/'
  if (url.startsWith('/__reconciliation_proxy')) {
    proxy(req, res, FINANCE_API, url.replace('/__reconciliation_proxy', '/api/v1/treasury'),
      REC_KEY ? { 'x-reconciliation-api-key': REC_KEY } : {})
  } else if (url.startsWith('/api/v1/') || url === '/api/v1') {
    proxy(req, res, FINANCE_API, url)
  } else if (url.startsWith('/api/') || url === '/api') {
    proxy(req, res, SALES_API, url)
  } else if (req.method === 'GET' || req.method === 'HEAD') {
    try {
      serveStatic(req, res)
    } catch (err) {
      res.writeHead(500).end(String(err))
    }
  } else {
    res.writeHead(405).end()
  }
})
// درخواست‌های طولانی (گزارش‌های سنگین، چت‌بات) قطع نشوند
server.requestTimeout = 0
server.headersTimeout = 65_000
server.keepAliveTimeout = 60_000
server.listen(PORT, HOST, () => {
  console.log(`Exir unified dashboard: http://localhost:${PORT}  (finance ${FINANCE_API.origin}, sales ${SALES_API.origin})`)
})
