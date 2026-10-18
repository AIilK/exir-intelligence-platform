import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react'

// ---------------------------------------------------------------- formatting
const fa = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 })
const fa1 = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 })

// مبالغ در فایل به ریال هستند؛ نمایش به تومان (۱ تومان = ۱۰ ریال)
const RIAL_PER_TOMAN = 10
export const UNITS = {
  toman: { label: 'تومان', div: RIAL_PER_TOMAN },
  thousand: { label: 'هزار تومان', div: RIAL_PER_TOMAN * 1e3 },
  million: { label: 'میلیون تومان', div: RIAL_PER_TOMAN * 1e6 },
  billion: { label: 'میلیارد تومان', div: RIAL_PER_TOMAN * 1e9 },
}

export const isNum = (v) => typeof v === 'number' && Number.isFinite(v)
export const fmtInt = (v) => (isNum(v) ? fa.format(v) : '—')
export const fmtNum1 = (v) => (isNum(v) ? fa1.format(v) : '—')
export const fmtPct = (v, d = 1) =>
  isNum(v) ? new Intl.NumberFormat('fa-IR', { maximumFractionDigits: d }).format(v * 100) + '٪' : '—'
export const fmtMoney = (v, unit = 'million') => {
  if (!isNum(v)) return '—'
  const u = UNITS[unit]
  const x = v / u.div
  return (Math.abs(x) >= 100 || unit === 'toman' ? fa : fa1).format(x)
}
// نمایش خلاصه برای کارت‌ها: انتخاب خودکار واحد
export const fmtCompact = (v) => {
  if (!isNum(v)) return { value: '—', unit: '' }
  const t = v / RIAL_PER_TOMAN
  const a = Math.abs(t)
  if (a >= 1e9) return { value: fa1.format(t / 1e9), unit: 'میلیارد تومان' }
  if (a >= 1e6) return { value: fa1.format(t / 1e6), unit: 'میلیون تومان' }
  return { value: fa.format(t), unit: 'تومان' }
}
export const faDigits = (s) => String(s ?? '').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])

// ---------------------------------------------------------------- filters
export const EMPTY_FILTERS = {
  date_from: '', date_to: '', branch: [], supervisor: [], seller: [], brand: [],
  category: [], group: [], city: [], payment: [], inv_type: [],
}
export const FILTER_LABELS = {
  branch: 'شعبه', supervisor: 'سرپرست', seller: 'فروشنده', brand: 'برند',
  category: 'گروه کالا', group: 'زیرگروه کالا', city: 'شهر', payment: 'نحوه پرداخت', inv_type: 'نوع فاکتور',
}

export function toQuery(f) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(f)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else if (v) p.set(k, v)
  }
  return p.toString()
}

const Ctx = createContext(null)

function loadStored(key, fallback) {
  try {
    const v = localStorage.getItem(key)
    return v ? { ...fallback, ...JSON.parse(v) } : fallback
  } catch {
    return fallback
  }
}

export function AppProvider({ children }) {
  const [filters, setFilters] = useState(() => loadStored('sd.filters', EMPTY_FILTERS))
  const [unit, setUnit] = useState(() => {
    try {
      const u = localStorage.getItem('sd.unit')
      return u in UNITS ? u : 'million'
    } catch { return 'million' }
  })
  // مبالغ خالص با ارزش افزوده (مثل «مبلغ کل» گزارش‌های کارآمد)؛ پیش‌فرض: با ارزش افزوده
  const [vat, setVat] = useState(() => {
    try { return localStorage.getItem('sd.vat') !== '0' } catch { return true }
  })
  const [reportDay, setReportDay] = useState(() => {
    try { return localStorage.getItem('sd.reportDay') || '' } catch { return '' }
  })
  const [version, setVersion] = useState(0)
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState(null)

  useEffect(() => {
    try { localStorage.setItem('sd.filters', JSON.stringify(filters)) } catch { /* ignore */ }
  }, [filters])
  useEffect(() => {
    try { localStorage.setItem('sd.unit', unit) } catch { /* ignore */ }
  }, [unit])
  useEffect(() => {
    try { localStorage.setItem('sd.reportDay', reportDay) } catch { /* ignore */ }
  }, [reportDay])
  useEffect(() => {
    try { localStorage.setItem('sd.vat', vat ? '1' : '0') } catch { /* ignore */ }
  }, [vat])
  // مقادیر فیلتر ذخیره‌شده‌ای که در فایل فعلی وجود ندارند (مثلاً پس از تغییر فایل) حذف می‌شوند
  useEffect(() => {
    if (!meta) return
    setFilters((f) => {
      let changed = false
      const next = { ...f }
      for (const [k, opts] of Object.entries(meta.options)) {
        if (!Array.isArray(f[k]) || !f[k].length) continue
        const valid = new Set(opts.map((o) => o.value))
        const kept = f[k].filter((v) => valid.has(v))
        if (kept.length !== f[k].length) { next[k] = kept; changed = true }
      }
      return changed ? next : f
    })
  }, [meta])
  // روز گزارش ذخیره‌شده‌ای که در فایل فعلی نیست، کنار گذاشته می‌شود
  useEffect(() => {
    if (meta && reportDay && !meta.sales_dates.includes(reportDay)) setReportDay('')
  }, [meta, reportDay])
  useEffect(() => {
    setMetaError(null)
    fetchJson('/api/meta').then(setMeta).catch((e) => { setMeta(null); setMetaError(e.message) })
  }, [version])

  // داده لایو SQL در سرور هر چند ثانیه تازه می‌شود؛ با تغییر stamp صفحه‌ها دوباره بارگذاری می‌شوند
  // (/api/stamp فقط یک عدد است و هزینه‌ای ندارد؛ وقتی تب پنهان است بررسی نمی‌شود)
  useEffect(() => {
    let last = null
    const check = () => {
      if (document.hidden) return
      fetchJson('/api/stamp').then(({ stamp }) => {
        if (last !== null && stamp !== last) setVersion((v) => v + 1)
        last = stamp
      }).catch(() => { /* سرور در دسترس نیست؛ دفعه بعد */ })
    }
    check()
    const id = setInterval(check, 5000)
    document.addEventListener('visibilitychange', check)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', check) }
  }, [])

  const reload = useCallback((resetFilters) => {
    if (resetFilters) setFilters(EMPTY_FILTERS)
    setVersion((v) => v + 1)
  }, [])

  const value = useMemo(
    () => ({ filters, setFilters, unit, setUnit, vat, setVat, version, reload, meta, metaError, reportDay, setReportDay }),
    [filters, unit, vat, version, reload, meta, metaError, reportDay],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
export const useApp = () => useContext(Ctx)

// ---------------------------------------------------------------- api
export async function fetchJson(url, opts) {
  const r = await fetch(url, opts)
  let body = null
  try { body = await r.json() } catch { /* ignore */ }
  if (!r.ok) throw new Error(body?.detail || `خطای سرور (${r.status})`)
  // سرور قدیمی مسیرهای جدید API را نمی‌شناسد و صفحه HTML برمی‌گرداند
  if (body === null) throw new Error('پاسخ سرور قابل خواندن نیست؛ احتمالاً سرور بعد از به‌روزرسانی دوباره راه‌اندازی نشده است (run.bat را ببندید و دوباره اجرا کنید).')
  return body
}

// شمارنده درخواست‌های در جریان، برای نوار بارگذاری سراسری
let inflight = 0
const listeners = new Set()
const bump = (d) => { inflight += d; listeners.forEach((l) => l(inflight)) }
export function useBusy() {
  const [n, setN] = useState(inflight)
  useEffect(() => { listeners.add(setN); return () => { listeners.delete(setN) } }, [])
  return n > 0
}

export function useApi(path, extra = '') {
  const { filters, vat, version } = useApp()
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const q = `${toQuery(filters)}&vat=${vat ? 1 : 0}`
  const url = `${path}${path.includes('?') ? '&' : '?'}${q}${extra}`
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    bump(1)
    fetchJson(url)
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e) => alive && setState({ data: null, loading: false, error: e.message }))
      .finally(() => bump(-1))
    return () => { alive = false }
  }, [url, version])
  return state
}

/** مثل useApi ولی بدون فیلترهای سراسری (صفحه برنامه‌ریزی کنترل‌های خودش را دارد). setData برای جایگزینی با پاسخ ذخیره. */
export function useFetch(url) {
  const { version } = useApp()
  const [state, setState] = useState({ data: null, loading: true, error: null })
  useEffect(() => {
    if (!url) return undefined
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    bump(1)
    fetchJson(url)
      .then((data) => alive && setState({ data, loading: false, error: null }))
      .catch((e) => alive && setState({ data: null, loading: false, error: e.message }))
      .finally(() => bump(-1))
    return () => { alive = false }
  }, [url, version])
  const setData = useCallback((data) => setState({ data, loading: false, error: null }), [])
  return { ...state, setData }
}

/** درخواست ذخیره با نوار بارگذاری سراسری */
export async function sendJson(url, method, body) {
  bump(1)
  try {
    return await fetchJson(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } finally { bump(-1) }
}

// ---------------------------------------------------------------- دسته شعب (A / B / سایر)
/** تب‌های «کل / A / B» برای فهرست‌های برترین؛ شعب غیرهیبرید فقط در «کل» می‌آیند */
// eslint-disable-next-line no-unused-vars
export const tierTabs = (present) => [
  { value: 'all', label: 'کل' }, { value: 'A', label: 'هیبرید A' }, { value: 'B', label: 'هیبرید B' },
]
export const TIER_HINT = 'هیبرید A: تهران، آذربایجان غربی، خراسان، کرمان، اصفهان — هیبرید B: بقیه هیبریدها —  '
/** دسته شعبه از meta (تعریف در config.json → branch_tiers) */
export const tierOf = (meta, branch) => meta?.branch_tier?.[branch] ?? (String(branch).includes('هیبرید') ? 'B' : 'سایر')

/** مسیر صفحه جزئیات؛ within = [[بعد والد، کلید]] مثلاً [['brand', 'پادینا']] برای «اسپری مو» فقط در پادینا */
export const detailPath = (dim, key, within = []) => {
  const q = within.map(([d, k]) => `within=${encodeURIComponent(`${d}:${k}`)}`).join('&')
  return `/detail/${dim}/${encodeURIComponent(key)}${q ? `?${q}` : ''}`
}

/** اجداد یک گره جدول درختی به‌صورت محدوده والد برای detailPath */
export const nodeWithin = (n, dims) => n.id.split('\x1f').slice(0, -1).map((k, i) => [dims[i], k])
