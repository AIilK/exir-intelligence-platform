// Tabs shared by the hybrid file and the visitor file (finance data from the Karamad sales network).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useJson, mt, n0, pct, isNum, faDigits, moneyText, growth, signedPct } from './data.js'
import { normName } from './model.js'
import { Card, Pending, Bar, Money, PairBars } from './ui.jsx'

export const visitorPath = (id, tab) => `/files/visitors/${id}${tab ? `?tab=${tab}` : ''}`
export const cleanName = (s) => String(s || '—').replace(/\/.*$/, '').trim()
const RISK = { high: 'احتمال برگشت بالا', medium: 'متوسط', low: 'کم' }

/** visitor name → visitor id, so names inside cheque/debt rows can link to the visitor file */
export const visitorIds = (visitors) => new Map((visitors || []).map((v) => [normName(v.visitor_name), v.visitor_id]))

function VisitorName({ name, ids }) {
  const id = ids?.get(normName(name))
  return id ? <Link className="u-cell-link" to={visitorPath(id)}>{cleanName(name)}</Link> : <>{cleanName(name)}</>
}

/** Sortable header cell. */
function Th({ k, sort, setSort, children, className, unit }) {
  const on = sort.key === k
  return (
    <th className={className}>
      <button type="button" className="u-sort" onClick={() => setSort(on ? { key: k, dir: -sort.dir } : { key: k, dir: -1 })}>
        <span>{children}{unit && <small>{unit}</small>}</span><i aria-hidden>{on ? (sort.dir > 0 ? '▴' : '▾') : '↕'}</i>
      </button>
    </th>
  )
}
const sorter = (sort) => (a, b) => {
  const x = a[sort.key], y = b[sort.key]
  if (typeof x === 'string' || typeof y === 'string') return sort.dir * String(x ?? '').localeCompare(String(y ?? ''), 'fa')
  return sort.dir * ((isNum(x) ? x : -Infinity) - (isNum(y) ? y : -Infinity))
}

// ---------------------------------------------------------------- year chart
/** Monthly sales, this year next to last year, with totals for the months so far. */
export function YearChart({ state, months, Y, title = 'فروش ماهانه', action }) {
  const yl = Y ? faDigits(Y.year) : ''
  const pyl = Y ? faDigits(Y.prevYear) : ''
  // totals over completed months only, so a half-finished current month is not set against a full one
  const curMonth = Y ? Number(Y.today.slice(5, 7)) : 13
  const last = Math.min(curMonth - 2, months.reduce((i, m, j) => (isNum(m.cur) ? j : i), -1))
  const cur = months.slice(0, last + 1).reduce((s, m) => s + (m.cur || 0), 0)
  const prev = months.slice(0, last + 1).reduce((s, m) => s + (m.prev || 0), 0)
  const g = prev > 0 ? growth(cur, prev) : null
  return (
    <Card title={`${title}: ${yl} در برابر ${pyl}`} sub="فروش خالص هر ماه (داشبورد فروش) · نشانگر را روی ستون نگه دارید تا مبلغ را ببینید · ماه جاری تا امروز" action={action}>
      {!state.data ? <Pending state={state} label="فروش ماهانه" height={220} /> : <>
        <div className="u-legend"><span><i className="muted" />{pyl}</span><span><i className="sales" />{yl}</span></div>
        <PairBars items={months} aKey="prev" bKey="cur" aTone="muted" bTone="sales" aName={pyl} bName={yl} fmt={moneyText} height={190} dense />
        {last >= 0 && <div className="u-year-totals">
          <span>ماه‌های کامل‌شده (فروردین تا {months[last]?.label}):</span>
          <span>{yl}: <b>{moneyText(cur)}</b></span>
          <span>{pyl}: <b>{prev > 0 ? moneyText(prev) : 'در این ماه‌ها فروشی نداشته'}</b></span>
          {isNum(g) && <span className={g >= 0 ? 't-good' : 't-bad'}>{signedPct(g)}</span>}
        </div>}
      </>}
    </Card>
  )
}

// ---------------------------------------------------------------- cheque health (overview card)
export function ChequeHealth({ file, ch, go, title = 'وضعیت چک‌های دریافتی' }) {
  if (!file.data) return <Card title={title}><Pending state={file} label="چک‌ها" height={180} /></Card>
  const list = ch.buckets.filter((b) => b.key !== 'all')
  const max = Math.max(1, ...list.map((b) => b.amount))
  const all = ch.buckets.find((b) => b.key === 'all')
  const sm = ch.summary
  return (
    <Card title={title} sub={`${n0(all?.count)} فقره · ${moneyText(all?.amount)} · روی هر ردیف بزنید`} action={<button className="u-link-btn" onClick={() => go('cheques', 'all')}>همه چک‌ها ←</button>}>
      <div className="u-buckets">
        {list.map((b) => (
          <button key={b.key} type="button" className="u-bucket" onClick={() => go('cheques', b.key)}>
            <span className={b.key === 'overdue' || b.key === 'returned' ? 't-bad' : ''}>{b.label}</span>
            <Bar value={b.amount} max={max} tone={b.key === 'overdue' || b.key === 'returned' ? 'danger' : b.key === 'later' ? 'fin2' : 'fin'} />
            <Money rial={b.amount} />
            <small>{n0(b.count)} فقره</small>
          </button>
        ))}
      </div>
      <div className="u-risk-strip">
        <span>احتمال برگشت:</span>
        <b className="t-bad">بالا {n0(sm.high?.count)} فقره ({moneyText(sm.high?.amount_rial)})</b>
        <b className="t-warn">متوسط {n0(sm.medium?.count)}</b>
        <b className="t-good">کم {n0(sm.low?.count)}</b>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- receivables summary (overview card)
export function DebtSummary({ file, dso, go }) {
  if (!file.data) return <Card title="مطالبات"><Pending state={file} label="مطالبات" height={180} /></Card>
  const d = file.data.debt || {}
  return (
    <Card title="مطالبات" sub="مانده دفتر کل مشتریان (کارآمد)" action={go && <button className="u-link-btn" onClick={() => go('debt')}>سن بدهی و بدهکاران ←</button>}>
      <div className="u-facts">
        <div><small>مانده بدهی مشتریان</small><Money rial={d.open_account_receivable_rial} className="t-bad" /><span>{n0(d.debtor_customer_count)} مشتری بدهکار از {n0(d.customer_count)}</span></div>
        <div><small>دوره وصول</small><span className="u-money"><b className={dso > 120 ? 't-bad' : dso > 75 ? 't-warn' : ''}>{isNum(dso) ? n0(dso) : '—'}</b><small>روز</small></span><span>مطالبات ÷ فروش روزانه امسال</span></div>
        <div><small>فاکتورهای تسویه‌نشده {faDigits(file.data.current_year_label)}</small><Money rial={d.current_year_unpaid_invoice_rial} /><span>{n0(d.current_year_unpaid_invoice_count)} فاکتور</span></div>
        <div><small>بستانکاری مشتریان</small><Money rial={d.customer_credit_rial} /><span>پیش‌پرداخت / اضافه پرداخت</span></div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- cheques tab
export function ChequesTab({ file, ch, bucket, go, scopeLabel = 'این هیبرید', ids, showVisitor = true }) {
  if (!file.data) return <Card><Pending state={file} label={`چک‌های ${scopeLabel}`} height={260} /></Card>
  const rows = (bucket === 'all' ? ch.rows : ch.rows.filter((x) => x.bucket === bucket))
    .slice().sort((a, b) => (a.days_until_due ?? 1e9) - (b.days_until_due ?? 1e9))
  const max = Math.max(1, ...ch.buckets.filter((b) => b.key !== 'all').map((b) => b.amount))
  const sm = ch.summary
  return (
    <div className="u-stack">
      <Card title={`سبد چک‌های دریافتی ${scopeLabel}`} sub="منبع: کارآمد · چک‌های باز و برگشتیِ تسویه‌نشده · روی هر دسته بزنید تا جدول فیلتر شود"
        action={<Link to="/finance/receivedCheques">همه چک‌های دریافتی شرکت ←</Link>}>
        <div className="u-bucket-chips">
          {ch.buckets.map((b) => (
            <button key={b.key} className={bucket === b.key ? 'on' : ''} aria-pressed={bucket === b.key} onClick={() => go('cheques', b.key)}>
              <span className={b.key === 'overdue' || b.key === 'returned' ? 't-bad' : ''}>{b.label}</span>
              <Money rial={b.amount} />
              <small>{n0(b.count)} فقره</small>
              {b.key !== 'all' && <Bar value={b.amount} max={max} tone={b.key === 'overdue' || b.key === 'returned' ? 'danger' : 'fin'} />}
            </button>
          ))}
        </div>
        <div className="u-risk-strip">
          <span>احتمال برگشت چک‌های باز:</span>
          <b className="t-bad">بالا {n0(sm.high?.count)} فقره · {moneyText(sm.high?.amount_rial)}</b>
          <b className="t-warn">متوسط {n0(sm.medium?.count)} فقره · {moneyText(sm.medium?.amount_rial)}</b>
          <b className="t-good">کم {n0(sm.low?.count)} فقره · {moneyText(sm.low?.amount_rial)}</b>
        </div>
      </Card>
      <Card title={`ریز چک‌ها — ${ch.buckets.find((b) => b.key === bucket)?.label || ''}`} sub={`${n0(rows.length)} فقره · جمع ${moneyText(rows.reduce((s, x) => s + (x.amount_rial || 0), 0))} · احتمال برگشت از سابقه چک‌های همان مشتری (نشانگر را روی آن نگه دارید)`}>
        <div className="u-table-wrap">
          <table className="u-table">
            <thead><tr><th>سررسید</th><th>زمان</th><th>مشتری</th>{showVisitor && <th>ویزیتور</th>}<th>بانک</th><th>شماره چک</th><th>مبلغ<small>میلیون تومان</small></th><th>وضعیت</th><th>احتمال برگشت</th></tr></thead>
            <tbody>
              {rows.slice(0, 300).map((x) => (
                <tr key={x.cheque_id}>
                  <td className={x.bucket === 'overdue' || x.bucket === 'returned' ? 't-bad' : ''}>{faDigits(x.due_date_jalali || '—')}</td>
                  <td className="t-muted">{!isNum(x.days_until_due) ? '—' : x.days_until_due < 0 ? `${n0(-x.days_until_due)} روز گذشته` : x.days_until_due === 0 ? 'امروز' : `${n0(x.days_until_due)} روز مانده`}</td>
                  <td>{x.customer_name || '—'}{x.customer_code && <small className="u-sub">کد {faDigits(x.customer_code)}</small>}</td>
                  {showVisitor && <td><VisitorName name={x.visitor_name} ids={ids} /></td>}
                  <td className="t-muted">{x.bank || '—'}</td>
                  <td className="t-muted">{faDigits(x.cheque_number || '—')}</td>
                  <td><b>{mt(x.amount_rial)}</b></td>
                  <td><span className={`u-pill ${x.bucket === 'returned' || x.bucket === 'overdue' ? 'bad' : 'muted'}`}>{x.bucket === 'returned' ? 'برگشتی' : x.cheque_status || 'باز'}</span></td>
                  <td title={(x.return_risk?.reasons || []).join('\n')}>
                    {x.return_risk?.level
                      ? <span className={`u-pill ${x.return_risk.level === 'high' ? 'bad' : x.return_risk.level === 'medium' ? 'warn' : 'good'}`}>{pct(x.return_risk.probability_percent)} · {RISK[x.return_risk.level]}</span>
                      : <span className="t-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 300 && <small className="u-note">۳۰۰ ردیف اول نمایش داده شد.</small>}
          {!rows.length && <div className="u-pending">چکی در این دسته نیست.</div>}
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- receivables tab
export function DebtTab({ file, detailUrl, dso, ids, showVisitors = true }) {
  const dd = useJson(detailUrl)
  if (!file.data) return <Card><Pending state={file} label="مطالبات" height={220} /></Card>
  const x = dd.data
  const total = x?.total_debt_rial || 0
  const share = (val) => (total ? pct((val / total) * 100) : '—')
  const maxAging = Math.max(1, ...(x?.aging || []).map((a) => a.amount_rial || 0))
  return (
    <div className="u-stack">
      <DebtSummary file={file} dso={dso} go={null} />
      {!x ? <Card><Pending state={dd} label="ریز بدهی (سن، منشأ، مشتریان) — این محاسبه چند ثانیه طول می‌کشد" height={200} /></Card> : <>
        <div className="u-grid2">
          <Card title="سن بدهی" sub="پرداخت‌ها اول قدیمی‌ترین فاکتورها را تسویه می‌کنند (FIFO)">
            <div className="u-list">
              {(x.aging || []).map((a) => (
                <div key={a.label} className="u-list-row"><span>{a.label}</span><Bar value={a.amount_rial} max={maxAging} tone="warn" /><Money rial={a.amount_rial} /><small>{share(a.amount_rial)} · {n0(a.customer_count)} مشتری</small></div>
              ))}
            </div>
          </Card>
          <Card title={showVisitors ? 'منشأ بدهی و سهم ویزیتورها' : 'منشأ بدهی'}>
            <div className="u-list">
              <div className="u-list-row"><span>فاکتور پرداخت‌نشده</span><Bar value={x.origin?.invoice} max={total} tone="fin" /><Money rial={x.origin?.invoice} /><small>{share(x.origin?.invoice)}</small></div>
              <div className="u-list-row"><span className="t-bad">چک برگشتی تسویه‌نشده</span><Bar value={x.origin?.returned_cheque} max={total} tone="danger" /><Money rial={x.origin?.returned_cheque} /><small>{share(x.origin?.returned_cheque)}</small></div>
              {x.origin?.unmatched > 0 && <div className="u-list-row"><span>مانده قدیمی‌تر</span><Bar value={x.origin.unmatched} max={total} tone="fin2" /><Money rial={x.origin.unmatched} /><small>{share(x.origin.unmatched)}</small></div>}
            </div>
            {showVisitors && <div className="u-list u-list-gap">
              {(x.visitors || []).slice(0, 10).map((v) => {
                const id = ids?.get(normName(v.visitor_name))
                const inner = <><span>{cleanName(v.visitor_name)}</span><Bar value={v.amount_rial} max={total} tone="fin" /><Money rial={v.amount_rial} /><small>{share(v.amount_rial)} · {n0(v.customer_count)} مشتری</small></>
                return id ? <Link key={v.visitor_name} to={visitorPath(id, 'debt')} className="u-list-row">{inner}</Link> : <div key={v.visitor_name} className="u-list-row">{inner}</div>
              })}
            </div>}
          </Card>
        </div>
        <Card title="بزرگ‌ترین بدهکاران" sub={`${n0((x.customers || []).length)} مشتری بدهکار · جمع ${moneyText(total)} · ۳۰ مورد اول`}>
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr><th>مشتری</th><th>بدهی<small>میلیون تومان</small></th><th>از چک برگشتی<small>میلیون تومان</small></th><th>قدیمی‌ترین فاکتور پرداخت‌نشده</th><th>آخرین پرداخت</th>{showVisitors && <th>ویزیتور</th>}</tr></thead>
              <tbody>
                {(x.customers || []).slice(0, 30).map((c) => (
                  <tr key={c.dl_ref}>
                    <td>{c.customer_name || '—'}<small className="u-sub">کد {faDigits(c.customer_code || '—')}</small></td>
                    <td className="t-bad"><b>{mt(c.debt_rial)}</b></td>
                    <td>{c.returned_cheque_rial > 0 ? mt(c.returned_cheque_rial) : '—'}</td>
                    <td>{faDigits(c.oldest_unpaid_invoice_date_jalali || '—')}</td>
                    <td>{faDigits(c.last_payment_date_jalali || '—')}</td>
                    {showVisitors && <td>{(c.visitors || []).map((v, i) => <span key={i}>{i > 0 && '، '}<VisitorName name={v.visitor_name} ids={ids} /></span>)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </>}
    </div>
  )
}

// ---------------------------------------------------------------- recent invoices tab
export function InvoicesTab({ file, ids, showVisitor = true }) {
  if (!file.data) return <Card><Pending state={file} label="فاکتورها" height={200} /></Card>
  const inv = file.data.last_invoices || []
  return (
    <Card title={`آخرین فاکتورهای ${faDigits(file.data.current_year_label)} و وضعیت وصول`} sub="مانده و نحوهٔ وصول هر فاکتور از تسویه فاکتور در کارآمد">
      <div className="u-table-wrap">
        <table className="u-table">
          <thead><tr><th>شماره</th><th>تاریخ</th>{showVisitor && <th>ویزیتور</th>}<th>مبلغ<small>میلیون تومان</small></th><th>وصول‌شده</th><th>مانده<small>میلیون تومان</small></th><th>نحوه وصول</th></tr></thead>
          <tbody>
            {inv.map((x) => (
              <tr key={x.invoice_id}>
                <td>{faDigits(x.number)}</td>
                <td>{faDigits(x.date_jalali)}</td>
                {showVisitor && <td><VisitorName name={x.visitor_name} ids={ids} /></td>}
                <td><b>{mt(x.amount_rial)}</b></td>
                <td><span className="u-inline-bar"><Bar value={x.collected_percent || 0} max={100} tone="fin" /><b>{pct(x.collected_percent)}</b></span></td>
                <td className={x.remaining_rial > 0 ? 't-warn' : ''}>{mt(x.remaining_rial)}</td>
                <td className="t-muted">{(x.collection_breakdown || []).map((b, i) => <small key={i} className="u-sub">{b.method || 'وصول'}: {moneyText(b.amount_rial)}</small>)}{!(x.collection_breakdown || []).length && '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!inv.length && <div className="u-pending">در سال جاری فاکتوری ثبت نشده است.</div>}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------- visitors table (hybrid file)
/**
 * Visitors of one hybrid: yearly sales and receivables (finance), this month's sales (sales
 * dashboard) and cheque problems; each name opens the visitor file.
 */
export function VisitorsTable({ visitors, monthBy, chq, Y, limit, title, sub, action }) {
  const [sort, setSort] = useState({ key: 'cur', dir: -1 })
  const rows = (visitors || []).map((v) => {
    const k = normName(v.visitor_name)
    const c = chq.get(k) || {}
    const debt = v.debt?.open_account_receivable_rial || 0
    const ys = v.current_year_sales_rial || 0
    return {
      ...v, name: cleanName(v.visitor_name), cur: v.current_year_sales_rial, prev: v.previous_year_sales_rial,
      month: monthBy.get(k) ?? null, debtRial: debt, ratio: ys > 0 ? (debt / ys) * 100 : null,
      overdue: c.overdue || 0, overdueN: c.overdueN || 0, returned: c.returned || 0, returnedN: c.returnedN || 0,
    }
  }).sort(sorter(sort))
  const shown = limit ? rows.slice(0, limit) : rows
  const max = Math.max(1, ...rows.map((r) => r.debtRial))
  const yl = Y ? faDigits(Y.year) : 'امسال'
  const pyl = Y ? faDigits(Y.prevYear) : 'پارسال'
  const p = { sort, setSort }
  return (
    <Card title={title || `ویزیتورها (${n0(rows.length)})`} sub={sub || 'روی نام هر ویزیتور بزنید تا پروندهٔ او (فروش، چک، مطالبات، فاکتورها) باز شود · روی عنوان ستون بزنید تا مرتب شود'} action={action}>
      <div className="u-table-wrap">
        <table className="u-table">
          <thead><tr>
            <Th k="name" {...p}>ویزیتور</Th>
            <Th k="supervisor" {...p}>سرپرست</Th>
            <Th k="cur" {...p} className="t-sales" unit="میلیون تومان">فروش {yl}</Th>
            <Th k="prev" {...p} className="t-sales" unit="میلیون تومان">فروش {pyl}</Th>
            <Th k="month" {...p} className="t-sales" unit="میلیون تومان">فروش این ماه</Th>
            <Th k="debtRial" {...p} className="t-fin" unit="میلیون تومان">مطالبات مشتریانش</Th>
            <Th k="ratio" {...p} className="t-fin">مطالبات ÷ فروش امسال</Th>
            <Th k="overdue" {...p} className="t-fin" unit="میلیون تومان">چک سررسید گذشته</Th>
            <Th k="returned" {...p} className="t-fin" unit="میلیون تومان">چک برگشتی</Th>
            <Th k="last_invoice_date_jalali" {...p}>آخرین فاکتور</Th>
          </tr></thead>
          <tbody>
            {shown.map((v) => (
              <tr key={v.visitor_id}>
                <td><Link className="u-row-link" to={visitorPath(v.visitor_id)}>{v.name} <span>←</span></Link>{!v.active && <small className="u-sub">غیرفعال</small>}</td>
                <td className="t-muted">{v.supervisor || '—'}</td>
                <td><b>{mt(v.cur)}</b></td>
                <td className="t-muted">{mt(v.prev)}</td>
                <td>{mt(v.month)}</td>
                <td><Link className="u-cell-link" to={visitorPath(v.visitor_id, 'debt')}><span className="u-inline-bar"><Bar value={v.debtRial} max={max} tone="warn" /><b>{mt(v.debtRial)}</b></span></Link><small className="u-sub">{n0(v.debt?.debtor_customer_count)} مشتری بدهکار</small></td>
                <td className={v.ratio > 40 ? 't-bad' : v.ratio > 25 ? 't-warn' : ''}>{pct(v.ratio)}</td>
                <td>{v.overdue > 0 ? <Link className="u-cell-link t-bad" to={`${visitorPath(v.visitor_id, 'cheques')}&bucket=overdue`}>{mt(v.overdue)}<small className="u-sub">{n0(v.overdueN)} فقره</small></Link> : <span className="t-muted">—</span>}</td>
                <td>{v.returned > 0 ? <Link className="u-cell-link t-bad" to={`${visitorPath(v.visitor_id, 'cheques')}&bucket=returned`}>{mt(v.returned)}<small className="u-sub">{n0(v.returnedN)} فقره</small></Link> : <span className="t-muted">—</span>}</td>
                <td>{faDigits(v.last_invoice_date_jalali || '—')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {limit && rows.length > limit && <small className="u-note">{n0(limit)} ویزیتور اول از {n0(rows.length)} نمایش داده شد.</small>}
    </Card>
  )
}
