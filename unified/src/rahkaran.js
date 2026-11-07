// Rahkaran B2B reps: the sales side (sales backend, /api/rk_sales) joined to the finance side
// (finance backend, customer collection portfolio). Join key = Rahkaran customer code
// (SLS3.Customer.Number in sales = counterpart_code in finance).
import { useMemo } from 'react'
import { useJson, isNum, dayOfYear } from './data.js'

export const PORTFOLIO_URL = '/api/v1/finance/customer-collection-portfolio?limit=1000'
export const rahkaranPath = (code, tab) => `/files/rahkaran/${encodeURIComponent(code)}${tab ? `?tab=${tab}` : ''}`

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

/** یک ستون «ریسک» برای هر نماینده، نسبت به اندازه فروش خودش و سخت‌گیرانه:
 *  نماینده‌ای که فروش بالا دارد طبیعی است بدهی و چک بیشتری هم داشته باشد، پس هر مبلغ با «چند ماه فروش همین نماینده»
 *  سنجیده می‌شود. مبلغ کمتر از ۱٪ فروش سال و کمتر از ۵۰ میلیون تومان نادیده گرفته می‌شود.
 *  - نیازمند توجه: سررسیدگذشته ≥ ۰٫۲۵ ماه فروش، یا برگشتی باز ≥ ۰٫۱۵ ماه، یا مانده بدون پوشش چک ≥ ۳ ماه فروش
 *  - ریسک بالا:    سررسیدگذشته ≥ ۰٫۷۵ ماه، یا برگشتی باز ≥ ۰٫۵ ماه، یا مانده بدون پوشش ≥ ۶ ماه همراه سررسیدگذشته/برگشتی
 *  - بحرانی:       سررسیدگذشته ≥ ۱٫۵ ماه، یا برگشتی باز ≥ ۱ ماه، یا هر دو با هم بالا
 *  سقف مبلغ: «بحرانی» فقط با دست‌کم ۲۰۰ میلیون تومان سررسیدگذشته + برگشتی، «ریسک بالا» با دست‌کم ۱۰۰ میلیون؛
 *  مانده بدون پوشش چک به‌تنهایی حداکثر «نیازمند توجه» است (پرداخت ممکن است روی کد دیگر همین نماینده ثبت شده باشد).
 *  بدون خرید امسال: فقط مانده قدیمی + برگشتی، بحرانی از ۱ میلیارد، ریسک بالا از ۳۰۰ میلیون، توجه از ۵۰ میلیون تومان. */
export const REP_RISK = {
  critical: { label: 'بحرانی', cls: 'bad', rank: 3 },
  high: { label: 'ریسک بالا', cls: 'bad', rank: 2 },
  medium: { label: 'نیازمند توجه', cls: 'warn', rank: 1 },
  low: { label: 'سالم', cls: 'good', rank: 0 },
}
const RISK_ORDER = ['low', 'medium', 'high', 'critical']
const faNum = (v, d = 1) => Number(v).toFixed(d).replace(/\.0$/, '').replace(/\d/g, (x) => '۰۱۲۳۴۵۶۷۸۹'[x]).replace('.', '٫')
const tomanText = (rial) => { const m = rial / 1e7; return m >= 1000 ? `${faNum(m / 1000)} میلیارد تومان` : `${faNum(m, 0)} میلیون تومان` }

export function repRisk(f, today) {
  if (!f) return null
  const ys = f.yearSalesFin > 0 ? f.yearSalesFin : 0
  const doy = today ? dayOfYear(today) : 0
  const monthSales = ys > 0 && doy > 0 ? ys / (doy / 30.44) : 0
  const floor = Math.max(ys * 0.01, 5e8)
  const keep = (v) => (v >= floor ? v : 0)
  const overdue = keep(f.overdue || 0)
  const returned = keep(f.returned || 0)
  const uncovered = keep(Math.max(0, (f.debt || 0) - (f.openCheques || 0)))
  const bad = overdue + returned
  if (!(monthSales > 0)) {
    const old = Math.max(0, f.debt || 0) + returned
    const level = old >= 1e10 ? 'critical' : old >= 3e9 ? 'high' : old >= 5e8 ? 'medium' : 'low'
    return { level, reasons: old > 0 ? [`بدون خرید امسال؛ مانده و برگشتی قدیمی ${tomanText(old)}`] : [] }
  }
  const ovm = overdue / monthSales, retm = returned / monthSales, ucm = uncovered / monthSales
  let level = 'low'
  if (retm >= 0.15 || ovm >= 0.25 || ucm >= 3) level = 'medium'
  if (retm >= 0.5 || ovm >= 0.75 || (ucm >= 6 && bad > 0)) level = 'high'
  if (retm >= 1 || ovm >= 1.5 || (ovm >= 0.75 && retm >= 0.5) || (ucm >= 4 && (ovm >= 0.5 || retm >= 0.25))) level = 'critical'
  const cap = bad >= 2e9 ? 'critical' : bad >= 1e9 ? 'high' : 'medium'
  level = RISK_ORDER[Math.min(RISK_ORDER.indexOf(level), RISK_ORDER.indexOf(cap))]
  const reasons = []
  if (overdue > 0) reasons.push(`سررسیدگذشته ${tomanText(overdue)} (${faNum(ovm)} ماه فروش)`)
  if (returned > 0) reasons.push(`برگشتی باز ${tomanText(returned)} (${faNum(retm)} ماه فروش)`)
  if (ucm >= 3) reasons.push(`مانده بدون پوشش چک ${tomanText(uncovered)} (${faNum(ucm)} ماه فروش)`)
  return { level, reasons }
}

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
      const risk = repRisk(f, today)
      return {
        key: s.code, code: s.code, name: s.name, short: s.short, city: s.city, province: s.province, brand: s.brand,
        net: s.net, cash: s.cash, netCash: s.net_cash, lyNet: s.ly_net, growth: s.ly_net > 0 ? ((s.net - s.ly_net) / s.ly_net) * 100 : null,
        invoices: s.invoices, lastDate: s.last_date || '',
        hasFin: !!f, ...(f ? {
          ref: f.ref, debt: f.debt, openCheques: f.openCheques, overdue: f.overdue, returned: f.returned,
          dso: f.dso, staleDebt: f.staleDebt, coverage: f.coverage,
          riskLevel: risk.level, riskRank: REP_RISK[risk.level].rank, riskReasons: risk.reasons,
        } : {}),
      }
    })
  }, [sales.data, fin.data])
  return { sales, fin, rows, today: sales.data?.today }
}
