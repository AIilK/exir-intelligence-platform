// Rahkaran B2B reps: the sales side (sales backend, /api/rk_sales) joined to the finance side
// (finance backend, customer collection portfolio). Join key = Rahkaran customer code
// (SLS3.Customer.Number in sales = counterpart_code in finance).
import { useMemo } from 'react'
import { useJson, isNum, dayOfYear } from './data.js'

export const PORTFOLIO_URL = '/api/v1/finance/customer-collection-portfolio?limit=1000'
export const rahkaranPath = (code, tab) => `/files/rahkaran/${encodeURIComponent(code)}${tab ? `?tab=${tab}` : ''}`
export const RISK_FA = { high: 'ریسک بالا', medium: 'ریسک متوسط', low: 'ریسک کم' }
export const riskCls = (r) => (r === 'high' ? 'bad' : r === 'medium' ? 'warn' : r === 'low' ? 'good' : 'muted')

/** Finance numbers of one portfolio row, in the shape the pages use. */
export function finFacts(f, today) {
  if (!f) return null
  const cp = f.collection_position || {}
  const debt = cp.open_account_receivable_rial ?? f.account_position?.balance_rial ?? null
  const yearSales = f.invoice_current_year_rial
  const doy = today ? dayOfYear(today) : null
  return {
    ref: f.counterpart_ref,
    name: f.counterpart_name,
    debt,
    credit: cp.customer_credit_rial,
    openCheques: cp.open_cheque_amount_rial ?? f.future_open_cheque_amount,
    openChequeCount: f.open_cheque_count,
    overdue: f.overdue_open_amount,
    overdueCount: f.overdue_open_cheque_count,
    // returned_cheque_amount is the whole history (mostly settled); the unsettled part is on the account
    returned: cp.returned_account_rial ?? 0,
    returnedHist: f.returned_cheque_amount,
    returnedCount: f.returned_cheque_count,
    coverage: cp.cheque_coverage_percent,
    exposure: cp.total_collection_exposure_rial,
    risk: f.risk_level,
    yearSalesFin: yearSales,
    lastInvoice: f.last_invoice_date_jalali,
    // days of sales the open balance represents (same rule as the hybrid file)
    dso: isNum(debt) && debt > 0 && yearSales > 0 && doy ? debt / (yearSales / doy) : null,
    // open balance but no purchase this year: old debt, no days-of-sales to measure it by
    staleDebt: debt > 0 && !(yearSales > 0),
    actions: f.recommended_actions,
    explanation: f.human_explanation,
  }
}

export const repLevel = (r) => (r.returned > 0 || r.dso > 120 || r.staleDebt ? 'critical' : r.overdue > 0 || r.dso > 75 ? 'warn' : 'ok')

/** All reps: sales list + finance portfolio, one row per sales customer code. */
export function useRahkaranReps() {
  const sales = useJson('/api/rk_sales/customers?period=YTD')
  const fin = useJson(PORTFOLIO_URL)
  const rows = useMemo(() => {
    if (!sales.data) return null
    const today = sales.data.today
    const byCode = new Map((fin.data?.customers || []).map((f) => [String(f.counterpart_code), f]))
    return sales.data.customers.map((s) => {
      const f = finFacts(byCode.get(String(s.code)), today)
      return {
        key: s.code, code: s.code, name: s.name, short: s.short, city: s.city, province: s.province, brand: s.brand,
        net: s.net, cash: s.cash, netCash: s.net_cash, lyNet: s.ly_net, growth: s.ly_net > 0 ? ((s.net - s.ly_net) / s.ly_net) * 100 : null,
        invoices: s.invoices, lastDate: s.last_date || '',
        hasFin: !!f, ...(f ? {
          ref: f.ref, debt: f.debt, openCheques: f.openCheques, overdue: f.overdue, returned: f.returned,
          dso: f.dso, staleDebt: f.staleDebt, risk: f.risk, coverage: f.coverage,
        } : {}),
      }
    }).map((r) => ({ ...r, level: repLevel(r) }))
  }, [sales.data, fin.data])
  return { sales, fin, rows, today: sales.data?.today }
}
