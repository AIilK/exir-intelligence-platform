import { useEffect, useState } from 'react'
import { fetchJson, useApp } from '@sales/lib.jsx'

// ---------------------------------------------------------------- fetching
// Small shared cache so moving between the manager view and a hybrid file does not
// refetch the heavy finance reports every time (5 minutes, same as the finance backend cache).
// Sales data is live: its entries are keyed by the sales data version, so a new invoice refetches them.
const TTL = 5 * 60 * 1000
const cache = new Map()
const isSales = (url) => !url.startsWith('/api/v1')

export function loadJson(url, version = 0) {
  const key = isSales(url) ? `${version}|${url}` : url
  const hit = cache.get(key)
  if (hit && Date.now() - hit.at < TTL) return hit.promise
  const promise = fetchJson(url)
  for (const [k, e] of cache) if (Date.now() - e.at >= TTL) cache.delete(k) // older live versions
  cache.set(key, { at: Date.now(), promise })
  promise.catch(() => cache.delete(key))
  return promise
}

/** { data, error, loading } for one url; null url = wait */
export function useJson(url) {
  const { version } = useApp()
  const v = url && isSales(url) ? version : 0
  const [state, setState] = useState({ data: null, error: null, loading: !!url })
  useEffect(() => {
    if (!url) return undefined
    let alive = true
    setState((s) => ({ data: s.data, error: null, loading: true }))
    loadJson(url, v)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: e.message || 'خطا در دریافت داده', loading: false }))
    return () => { alive = false }
  }, [url, v])
  return state
}

export const qs = (o) => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')
  .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')

// ---------------------------------------------------------------- formatting (all money in rial → million toman)
const nf0 = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 })
export const isNum = (v) => typeof v === 'number' && Number.isFinite(v)
export const mt = (rial) => (isNum(rial) ? nf0.format(rial / 1e7) : '—') // million toman
export const bt = (rial) => (isNum(rial) ? nf1.format(rial / 1e10) : '—') // billion toman
export const n0 = (v) => (isNum(v) ? nf0.format(v) : '—')
export const pct = (v, d = 0) => (isNum(v) ? `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: d }).format(v)}٪` : '—')
export const signedPct = (v) => (isNum(v) ? `${v >= 0 ? '▲' : '▼'} ${pct(Math.abs(v))}` : '—')
export const faDigits = (s) => String(s ?? '').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])

/** Amount with a readable unit: ≥1 billion toman → «۳۱٫۴ میلیارد تومان», else «۸۵۰ میلیون تومان». */
export function money(rial) {
  if (!isNum(rial)) return { v: '—', u: '' }
  const t = rial / 10
  const a = Math.abs(t)
  if (a >= 1e9) return { v: nf1.format(t / 1e9), u: 'میلیارد تومان' }
  if (a >= 1e6) return { v: nf0.format(t / 1e6), u: 'میلیون تومان' }
  return { v: nf0.format(t), u: 'تومان' }
}
export const moneyText = (rial) => {
  const m = money(rial)
  return m.u ? `${m.v} ${m.u}` : m.v
}

// ---------------------------------------------------------------- Jalali helpers (dates arrive as "1405/07/21")
export const JMONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
export const monthName = (ym) => JMONTHS[Number(String(ym).slice(5, 7)) - 1] || ym
export const prevMonth = (ym) => {
  const [y, m] = String(ym).split('/').map(Number)
  return m === 1 ? `${y - 1}/12` : `${y}/${String(m - 1).padStart(2, '0')}`
}
/** day of the Jalali year (1..366) */
export const dayOfYear = (date) => {
  const [, m, d] = String(date).split('/').map(Number)
  return (m <= 7 ? (m - 1) * 31 : 186 + (m - 7) * 30) + d
}

/**
 * Current period = start of the sales month → today; previous = the same day span
 * in the month before (capped to that month's length), so growth compares like with like.
 */
export function salesPeriods(meta) {
  const f = meta?.file
  if (!f?.month || !f?.today) return null
  const day = Number(f.today.slice(8, 10))
  const pm = prevMonth(f.month)
  const pmEntry = (f.months || []).find((m) => m.month === pm)
  const pmLen = pmEntry ? Number(pmEntry.to.slice(8, 10)) : 30
  const pd = String(Math.min(day, pmLen)).padStart(2, '0')
  return {
    month: f.month,
    today: f.today,
    day,
    cur: { date_from: `${f.month}/01`, date_to: f.today },
    prev: { date_from: `${pm}/01`, date_to: `${pm}/${pd}` },
    prevLabel: monthName(pm),
    curLabel: monthName(f.month),
  }
}

/**
 * Year to date vs the same span of last year, plus last year in full (Jalali).
 * e.g. today 1405/07/22 → 1405/01/01–1405/07/22 vs 1404/01/01–1404/07/22, and 1404/01/01–1404/12/30.
 */
export function yearPeriods(meta) {
  const today = meta?.file?.today
  if (!today) return null
  const y = Number(today.slice(0, 4))
  const md = today.slice(5)
  const prevMd = md === '12/30' ? '12/29' : md // last year may have a 29-day Esfand
  return {
    year: y, prevYear: y - 1, today,
    cur: { date_from: `${y}/01/01`, date_to: today },
    prev: { date_from: `${y - 1}/01/01`, date_to: `${y - 1}/${prevMd}` },
    fullPrev: { date_from: `${y - 1}/01/01`, date_to: `${y - 1}/12/30` },
    span: `${faDigits(`${y}`)}/۰۱/۰۱ تا ${faDigits(today)}`,
  }
}

export const growth = (cur, prev) => (isNum(cur) && isNum(prev) && prev > 0 ? ((cur - prev) / prev) * 100 : null)
