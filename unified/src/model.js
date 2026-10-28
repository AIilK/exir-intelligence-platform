// Pure shaping of the finance / sales API responses for the unified pages.
import { dayOfYear, growth, isNum, JMONTHS } from './data.js'

const sum = (xs, f) => xs.reduce((s, x) => s + (Number(f(x)) || 0), 0)
export const normName = (s) => String(s ?? '').replace(/\/.*$/, '').replace(/ي/g, 'ی').replace(/ك/g, 'ک')
  .replace(/[‌\s]+/g, ' ').trim()

// ---------------------------------------------------------------- received cheques (liquidity report, horizon 365)
export function receivedOverview(r) {
  const d = r?.data
  if (!d) return null
  const t = d.timeline || []
  const span = (a, b) => {
    const xs = t.slice(a, b)
    return { amount: sum(xs, (x) => x.definite_rial), reliance: sum(xs, (x) => x.reliance_rial), count: sum(xs, (x) => x.count) }
  }
  const total = d.kpis?.horizon?.definite_rial ?? sum(t, (x) => x.definite_rial)
  const customers = [...(d.customers || [])].sort((a, b) => (b.definite_rial || 0) - (a.definite_rial || 0))
  return {
    asOf: r.as_of_jalali,
    total,
    count: sum(t, (x) => x.count),
    reliancePct: d.kpis?.horizon?.reliance_percent,
    buckets: [
      { key: 'overdue', label: 'سررسید گذشته', amount: d.overdue?.definite_rial || 0, count: d.overdue?.count || 0, tone: 'danger', note: 'جدا از جمع' },
      { key: 'today', label: 'امروز', ...span(0, 1), tone: 'warn' },
      { key: 'd7', label: '۱ تا ۷ روز', ...span(1, 8), tone: 'fin' },
      { key: 'd30', label: '۸ تا ۳۰ روز', ...span(8, 31), tone: 'fin' },
      { key: 'later', label: 'بیش از ۳۰ روز', ...span(31, t.length), tone: 'fin2' },
    ],
    byChannel: (d.by_channel || []).map((c) => ({ key: c.channel, label: c.channel === 'hybrid' ? 'هیبرید' : 'B2B', amount: c.definite_rial || 0 })),
    returned: { amount: d.returned_open?.amount_rial || 0, count: d.returned_open?.count || 0 },
    top10Share: total ? (sum(customers.slice(0, 10), (c) => c.definite_rial) / total) * 100 : null,
    customerCount: d.customer_count,
  }
}

// ---------------------------------------------------------------- issued cheques (liquidity report, horizon 365)
export function issuedOverview(r) {
  const d = r?.data
  if (!d) return null
  const c = d.calendar || []
  const span = (a, b) => {
    const xs = c.slice(a, b)
    return { amount: sum(xs, (x) => x.amount_rial), count: sum(xs, (x) => x.count) }
  }
  const banks = new Map()
  for (const ch of d.cheques || []) {
    const k = String(ch.bank_name || 'سایر').replace(/\s*-.*$/, '').trim() || 'سایر'
    banks.set(k, (banks.get(k) || 0) + (ch.amount_rial || 0))
  }
  const bankRows = [...banks.entries()].map(([label, amount]) => ({ label, amount })).sort((a, b) => b.amount - a.amount)
  const k = d.kpis || {}
  return {
    asOf: r.as_of_jalali,
    total: k.total_due_by_horizon_end?.amount_rial ?? 0,
    count: k.total_due_by_horizon_end?.count ?? 0,
    buckets: [
      { key: 'overdue', label: 'سررسید گذشته (تا ۲۰ روز)', amount: k.overdue?.amount_rial || 0, count: k.overdue?.count || 0, tone: 'danger' },
      { key: 'today', label: 'امروز', ...span(0, 1), tone: 'out' },
      { key: 'd7', label: '۱ تا ۷ روز', ...span(1, 8), tone: 'out' },
      { key: 'd14', label: '۸ تا ۱۴ روز', ...span(8, 15), tone: 'out' },
      { key: 'd30', label: '۱۵ تا ۳۰ روز', ...span(15, 31), tone: 'out' },
      { key: 'later', label: 'بیش از ۳۰ روز', ...span(31, c.length), tone: 'out2' },
    ],
    banks: bankRows,
    peakDay: k.peak_day,
    needsReview: { amount: d.needs_status_review?.amount_rial || 0, count: d.needs_status_review?.count || 0 },
    topPayee: (d.top_payees || [])[0],
  }
}

// ---------------------------------------------------------------- weekly net cash flow (liquidity summary, reliance scenario)
export function weeklyFlow(s, weeks = 5) {
  const sc = (s?.data?.scenarios || []).find((x) => x.key === (s.data.base_scenario || 'reliance'))
  if (!sc) return null
  const days = sc.days || []
  const out = []
  for (let w = 0; w < weeks; w++) {
    const xs = days.slice(w * 7, w * 7 + 7)
    if (!xs.length) break
    out.push({
      label: w === 0 ? 'این هفته' : `هفته ${['', 'دوم', 'سوم', 'چهارم', 'پنجم', 'ششم'][w]}`,
      from: xs[0].date_jalali, to: xs[xs.length - 1].date_jalali,
      inflow: sum(xs, (x) => x.inflow_rial),
      outflow: sum(xs, (x) => x.outflow_rial),
      issued: sum(xs, (x) => x.issued_cheques_rial),
      payroll: sum(xs, (x) => x.payroll_rial),
      received: sum(xs, (x) => x.received_cheques_rial),
      net: sum(xs, (x) => x.net_rial),
      closing: xs[xs.length - 1].closing_rial,
    })
  }
  const d30 = days[Math.min(29, days.length - 1)]
  return { weeks: out, scenario: sc.label, net30: d30?.closing_rial, basis: s.data.basis }
}

// ---------------------------------------------------------------- hybrids: finance sales network ⨝ sales branches
// growth against a tiny base (e.g. 50M → 1B) says nothing; below this previous-period net it is not shown
export const MIN_GROWTH_BASE_RIAL = 5e9 // 500 million toman

/**
 * Status = receivables health (days of sales outstanding) plus a sales drop judged against the
 * company-wide trend, so a month where everyone sells less does not paint every hybrid red.
 */
export function hybridLevel({ dso, growth: g, overall }) {
  const rel = isNum(g) ? g - (isNum(overall) ? overall : 0) : null
  if ((isNum(dso) && dso > 120) || (isNum(rel) && rel < -35)) return 'critical'
  if ((isNum(dso) && dso > 75) || (isNum(rel) && rel < -15)) return 'warn'
  return 'ok'
}

const byBranch = (resp) => new Map((resp?.branches || []).map((b) => [normName(b.key), b]))

export function hybridRows({ network, salesCur, salesPrev, ytd, ytdPrev, fullPrev, today }) {
  const fin = network?.branches || []
  const cur = byBranch(salesCur)
  const prev = byBranch(salesPrev)
  const yCur = byBranch(ytd)
  const yPrev = byBranch(ytdPrev)
  const yFull = byBranch(fullPrev)
  const doy = today ? dayOfYear(today) : null
  const overall = growth(salesCur?.kpis?.net, salesPrev?.kpis?.net)
  const seen = new Set()
  const rows = fin.map((b) => {
    const k = normName(b.branch_name)
    seen.add(k)
    return row(k, b.branch_name, b, cur.get(k), prev.get(k))
  })
  for (const [k, s] of cur) if (!seen.has(k)) rows.push(row(k, s.label || s.key, null, s, prev.get(k)))
  return rows.sort((a, b) => a.rank - b.rank || (b.debt || 0) - (a.debt || 0))

  function row(k, name, f, s, p) {
    const debt = f?.debt?.open_account_receivable_rial
    const yearSales = f?.current_year_sales_rial
    const dso = isNum(debt) && yearSales > 0 && doy ? debt / (yearSales / doy) : null
    const g = p?.net >= MIN_GROWTH_BASE_RIAL ? growth(s?.net, p?.net) : null
    const level = hybridLevel({ dso, growth: g, overall })
    const yc = yCur.get(k)?.net
    const yp = yPrev.get(k)?.net
    return {
      key: k, name, branchId: f?.branch_id ?? null, people: f?.hybrids || [],
      salesNet: s?.net ?? null, prevNet: p?.net ?? null, growth: g, reqConv: s?.req_conv,
      ytdNet: yc ?? null, ytdPrevNet: yp ?? null, ytdGrowth: yp >= MIN_GROWTH_BASE_RIAL ? growth(yc, yp) : null,
      fullPrevNet: yFull.get(k)?.net ?? null,
      debt: debt ?? null, debtors: f?.debt?.debtor_customer_count, openCheques: f?.open_cheque_amount_rial ?? null,
      openChequeCount: f?.open_cheque_count, dso, level, rank: { critical: 0, warn: 1, ok: 2 }[level], overall,
      inSales: !!s, inFinance: !!f,
    }
  }
}

export const LEVEL = {
  critical: { label: 'بحرانی', cls: 'bad' },
  warn: { label: 'نیازمند توجه', cls: 'warn' },
  ok: { label: 'سالم', cls: 'good' },
}

/** Company-wide totals of the hybrid rows, for the management summary. */
export function hybridTotals(rows) {
  const s = (f) => rows.reduce((a, r) => a + (Number(r[f]) || 0), 0)
  const debt = s('debt')
  return {
    count: rows.length,
    debt, debtors: s('debtors'), openCheques: s('openCheques'), openChequeCount: s('openChequeCount'),
    levels: { critical: rows.filter((r) => r.level === 'critical').length, warn: rows.filter((r) => r.level === 'warn').length, ok: rows.filter((r) => r.level === 'ok').length },
  }
}

/** Monthly sales of this year next to the same month last year (sales backend /api/monthly). */
export function yearCompare(months, year) {
  const by = new Map((months || []).map((m) => [m.month, m.net]))
  return JMONTHS.map((label, i) => {
    const mm = String(i + 1).padStart(2, '0')
    return { label, prev: by.get(`${year - 1}/${mm}`) ?? null, cur: by.get(`${year}/${mm}`) ?? null }
  })
}

/** Per visitor name: open, overdue and returned cheques among a file's cheque rows. */
export function chequesByVisitor(rows) {
  const out = new Map()
  for (const x of rows || []) {
    const k = normName(x.visitor_name)
    if (!k) continue
    const a = out.get(k) || { open: 0, openN: 0, overdue: 0, overdueN: 0, returned: 0, returnedN: 0 }
    if (x.bucket === 'returned') { a.returned += x.amount_rial || 0; a.returnedN += 1 } else {
      a.open += x.amount_rial || 0; a.openN += 1
      if (x.bucket === 'overdue') { a.overdue += x.amount_rial || 0; a.overdueN += 1 }
    }
    out.set(k, a)
  }
  return out
}

// ---------------------------------------------------------------- hybrid file: open cheques of one branch (finance branch file rows)
export function branchCheques(file) {
  const rows = (file?.cheques?.rows || []).filter((x) => ['open', 'returned'].includes(x.return_risk?.state))
  const bucketOf = (x) => {
    if (x.return_risk?.state === 'returned') return 'returned'
    const d = x.days_until_due
    if (!isNum(d)) return 'later'
    if (d < 0) return 'overdue'
    if (d === 0) return 'today'
    if (d <= 7) return 'd7'
    if (d <= 30) return 'd30'
    return 'later'
  }
  const withB = rows.map((x) => ({ ...x, bucket: bucketOf(x) }))
  const defs = [
    ['all', 'همه چک‌های باز و برگشتی'], ['overdue', 'سررسید گذشته'], ['today', 'امروز'], ['d7', 'تا ۷ روز'],
    ['d30', '۸ تا ۳۰ روز'], ['later', 'بیش از ۳۰ روز'], ['returned', 'برگشتی'],
  ]
  const buckets = defs.map(([key, label]) => {
    const xs = key === 'all' ? withB : withB.filter((x) => x.bucket === key)
    return { key, label, count: xs.length, amount: sum(xs, (x) => x.amount_rial) }
  })
  return { rows: withB, buckets, summary: file?.cheques?.summary || {} }
}
