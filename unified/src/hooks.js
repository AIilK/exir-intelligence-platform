import { useApp } from '@sales/lib.jsx'
import { useJson, qs, salesPeriods, yearPeriods } from './data.js'

/**
 * Sales per branch for every comparison the management pages show, from the sales backend:
 * this month vs the same days of last month, year to date vs the same span of last year,
 * and last year in full. Shared cache: each request runs once for all pages.
 */
export function useSalesSet() {
  const { meta, vat } = useApp()
  const P = salesPeriods(meta)
  const Y = yearPeriods(meta)
  const v = vat ? 1 : 0
  return {
    P, Y, vat: v,
    // no dates = the sales backend's current month (start → today), which also carries the month-end forecast
    cur: useJson(P && `/api/hybrid?vat=${v}`),
    prev: useJson(P && `/api/hybrid?${qs({ ...P.prev, vat: v })}`),
    ytd: useJson(Y && `/api/hybrid?${qs({ ...Y.cur, vat: v })}`),
    ytdPrev: useJson(Y && `/api/hybrid?${qs({ ...Y.prev, vat: v })}`),
    fullPrev: useJson(Y && `/api/hybrid?${qs({ ...Y.fullPrev, vat: v })}`),
  }
}

export const NETWORK_URL = '/api/v1/finance/sales-network'
