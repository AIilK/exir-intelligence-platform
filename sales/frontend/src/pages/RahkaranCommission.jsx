import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useRkFetch, fetchJson, fmtInt, fmtMoney, fmtPct, faDigits, isNum, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { MONTH_NAMES } from '../jalali.js'

// پورسانت نمایندگان راهکاران (B2B) و مشتریان صادراتی؛ جدولی مثل «پورسانت» هیبریدها.
// هنوز دستورالعمل کامل ندارد: فعلاً ۰٫۲٪ × (فروش خالص + درصد نقدی)؛ محاسبه در بک‌اند (rk_commission.py).
const monthName = (m) => `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${faDigits(m.slice(0, 4))}`
const CHANNELS = [{ value: 'b2b', label: 'نمایندگان B2B' }, { value: 'export', label: 'صادرات' }]
const ratio = (a, b) => (b > 0 ? a / b : null)
const RATE = 0.002  // نرخ پورسانت فعلی (اعلام کاربر)؛ محاسبه در بک‌اند rk_commission.py
const pct2 = (key, label, hint) => ({ key, label, type: 'pct', hint, render: (r) => fmtPct(r[key], 2) })

// مطالبات هر کد از داشبورد مالی (پرتفوی مطالبات مشتریان راهکاران؛ کلید = کد مشتری). در داشبورد فروش تنها خالی می‌ماند.
const PORTFOLIO_URL = '/api/v1/finance/customer-collection-portfolio?limit=1000'
function finOf(f) {
  if (!f) return null
  const cp = f.collection_position || {}
  const debt = cp.open_account_receivable_rial ?? f.account_position?.balance_rial ?? null
  const openCheques = cp.open_cheque_amount_rial ?? f.future_open_cheque_amount ?? 0
  return {
    debt, openCheques, uncovered: Math.max(0, (debt || 0) - (openCheques || 0)),
    openChequeCount: f.open_cheque_count ?? null,
    overdue: f.overdue_open_amount ?? 0, overdueCount: f.overdue_open_cheque_count ?? null,
    returned: cp.returned_account_rial ?? 0, returnedCount: f.returned_cheque_count ?? 0,
    coverage: cp.cheque_coverage_percent, lastInvoice: f.last_invoice_date_jalali,
    explanation: f.human_explanation, actions: f.recommended_actions,
  }
}
function usePortfolio() {
  const [state, setState] = useState({ map: null, loading: true, error: null })
  useEffect(() => {
    let alive = true
    fetchJson(PORTFOLIO_URL)
      .then((d) => alive && setState({ map: new Map((d.customers || []).map((f) => [String(f.counterpart_code), f])), loading: false, error: null }))
      .catch((e) => alive && setState({ map: null, loading: false, error: e.message }))
    return () => { alive = false }
  }, [])
  return state
}

// تایید اعتباری مثل هیبریدها: (مانده بدهی + چک برگشتی) کمتر از ۲۰٪ فروش خالص از ابتدای سال
const APPROVAL_LIMIT = 0.2
const OK = 'تایید', NOT_OK = 'عدم تایید'
const withApproval = (r) => (!isNum(r.debt) ? { ...r, ok_net: null }
  : { ...r, ok_net: (r.debt || 0) + (r.returned || 0) < APPROVAL_LIMIT * (r.net_ytd || 0) ? OK : NOT_OK })
const approvalPill = (r) => (r.ok_net == null ? '' : <span className={`pill ${r.ok_net === OK ? 'st-green' : 'st-red'}`}>{r.ok_net}</span>)

function RowCalc({ r }) {
  const m = (v) => `${fmtMoney(v, 'rial')} ریال`
  return (
    <div className="calc">
      <p><b>{r.label}</b> — کد {faDigits(r.code)} · {r.name}</p>
      <ul className="small">
        <li>فروش ناخالص {m(r.gross)} − تخفیف مدیریتی {m(r.mgmt)} − تخفیف نقدی {m(r.cash)} − سایر تخفیف‌ها {m(r.other_disc)} + مالیات {m(r.tax)} = خالص فاکتورها {m(r.inv_net)}</li>
        <li>خالص فاکتورها {m(r.inv_net)} − برگشتی {m(r.returns)} = <b>فروش خالص {m(r.net)}</b></li>
        {r.mgmt_n > 0 && <li>{fmtInt(r.mgmt_n)} فاکتور با تخفیف مدیریتی؛ ناخالص همان فاکتورها {m(r.mgmt_inv_gross)}، نرخ تخفیف {fmtPct(r.mgmt_rate, 2)}</li>}
        <li>پورسانت = (فروش خالص + درصد نقدی) {m(r.net_cash)} × {fmtPct(r.rate, 1)} = <b>{m(r.commission)}</b></li>
        {isNum(r.debt) && <li>مانده بدهی {m(r.debt)} + چک برگشتی {m(r.returned)} {r.ok_net === OK ? 'کمتر' : 'بیشتر'} از {fmtPct(APPROVAL_LIMIT, 0)} فروش خالص از ابتدای سال ({m(r.net_ytd)}) ← {r.ok_net}</li>}
      </ul>
    </div>
  )
}

/** ریز مطالبات نمایندگان یک استان (یا مشتریان یک کشور) زیر جدول پورسانت، مثل «ریز مانده حساب ویزیتورها» هیبریدها.
 *  همه کدهای آن استان که امسال فروش داشته‌اند (نه فقط همین ماه)؛ داده: پرتفوی مطالبات داشبورد مالی. */
function ProvinceDebt({ rows, place, exp, fin }) {
  const [open, setOpen] = useState(() => new Set())
  const toggle = (k) => setOpen((s) => { const x = new Set(s); if (x.has(k)) x.delete(k); else x.add(k); return x })
  const title = `ریز مطالبات ${exp ? 'مشتریان' : 'نمایندگان'} — ${place}`
  if (fin.loading) return <Card title={title}><Loading /></Card>
  if (fin.error) return <Card title={title}><p className="muted">مطالبات از بخش مالی خوانده نشد: {fin.error}</p></Card>
  const list = rows.filter((r) => r.fin).sort((a, b) => (b.debt || 0) - (a.debt || 0))
  if (!list.length) return <Card title={title}><p className="muted">مانده حسابی از بخش مالی برای این {exp ? 'کشور' : 'استان'} نیامد.</p></Card>
  const m = (v) => fmtMoney(v, 'rial')
  const U = UNITS.rial.label
  const sum = (k) => list.reduce((a, r) => a + (r[k] || 0), 0)
  const cls = (v) => `num${v > 0 ? ' neg' : ''}`
  return (
    <Card title={title}
      subtitle={`مانده حساب، چک‌های باز، سررسیدگذشته و برگشتی هر کد از بخش مالی؛ بدون پوشش = مانده بدهی − چک باز. ${list.length < rows.length ? `${fmtInt(rows.length - list.length)} کد در بخش مالی پیدا نشد. ` : ''}روی هر ردیف کلیک کنید.`}>
      <div className="table-scroll"><table>
        <thead><tr>
          <th>{exp ? 'مشتری' : 'نماینده'}</th><th>برند</th>
          <th className="num">فروش خالص امسال ({U})</th><th className="num">مانده بدهی ({U})</th><th className="num">مطالبات ÷ فروش امسال</th>
          <th className="num">چک باز ({U})</th><th className="num">پوشش چک</th><th className="num">بدون پوشش ({U})</th>
          <th className="num">سررسید گذشته ({U})</th><th className="num">چک برگشتی ({U})</th><th>آخرین فاکتور</th><th>تایید</th>
        </tr></thead>
        <tbody>{list.flatMap((r) => {
          const isOpen = open.has(r.code)
          const head = (
            <tr key={r.code} className="clickable" onClick={() => toggle(r.code)}>
              <td>{isOpen ? '▾' : '◂'} {r.label} <span className="muted small">({faDigits(r.code)})</span></td>
              <td>{r.brand || '—'}</td>
              <td className="num">{m(r.net_ytd)}</td><td className="num"><b>{m(r.debt)}</b></td>
              <td className={`num${ratio(r.debt, r.net_ytd) > APPROVAL_LIMIT ? ' neg' : ''}`}>{fmtPct(ratio(r.debt, r.net_ytd), 1)}</td>
              <td className="num">{m(r.open_cheques)}</td><td className="num">{isNum(r.fin.coverage) ? fmtPct(r.fin.coverage / 100, 0) : '—'}</td>
              <td className="num">{m(r.fin.uncovered)}</td>
              <td className={cls(r.overdue)}>{m(r.overdue)}</td><td className={cls(r.returned)}>{m(r.returned)}</td>
              <td>{r.fin.lastInvoice ? faDigits(r.fin.lastInvoice) : '—'}</td><td>{approvalPill(r)}</td>
            </tr>)
          if (!isOpen) return [head]
          const x = r.fin
          return [head, (
            <tr key={`${r.code}-d`}><td colSpan={12}>
              <ul className="small">
                <li>چک باز: {fmtInt(x.openChequeCount)} فقره · سررسیدگذشته: {fmtInt(x.overdueCount)} فقره · برگشتی: {fmtInt(x.returnedCount)} فقره</li>
                {x.explanation && <li>{x.explanation}</li>}
                {(x.actions || []).map((a, i) => <li key={i}>{typeof a === 'string' ? a : a.title || a.text || JSON.stringify(a)}</li>)}
                {!exp && <li><Link to={`/files/rahkaran/${encodeURIComponent(r.code)}`}>پرونده کامل نماینده (چک‌ها و فاکتورها) ←</Link></li>}
              </ul>
            </td></tr>)]
        })}</tbody>
        <tfoot><tr className="total-row"><td colSpan={2}>جمع {fmtInt(list.length)} کد</td>
          <td className="num">{m(sum('net_ytd'))}</td><td className="num"><b>{m(sum('debt'))}</b></td>
          <td className="num">{fmtPct(ratio(sum('debt'), sum('net_ytd')), 1)}</td>
          <td className="num">{m(sum('open_cheques'))}</td><td />
          <td className="num">{m(list.reduce((a, r) => a + (r.fin.uncovered || 0), 0))}</td>
          <td className="num">{m(sum('overdue'))}</td><td className="num">{m(sum('returned'))}</td><td colSpan={2} /></tr></tfoot>
      </table></div>
    </Card>
  )
}

export default function RahkaranCommission() {
  const [channel, setChannel] = useState('b2b')
  const [month, setMonth] = useState('')
  const [f, setF] = useState({ brand: '', province: '', active: '1' })
  const [sel, setSel] = useState(null)
  const { data, error } = useRkFetch(`/api/rk_commission?channel=${channel}${month ? `&month=${encodeURIComponent(month)}` : ''}`)
  const fin = usePortfolio()
  const exp = channel === 'export'

  const rows = useMemo(() => (data?.rows || []).map((r) => {
    const x = finOf(fin.map?.get(String(r.code)))
    const row = { ...r, key: r.code, label: r.label || r.short || r.name, comm_pct: ratio(r.commission, r.net_cash) }
    return withApproval(x ? { ...row, fin: x, debt: x.debt, returned: x.returned, open_cheques: x.openCheques, overdue: x.overdue } : row)
  }), [data, fin.map])

  if (error && !data) return <ErrorBox error={error} />
  if (!data) return <Loading />

  const uniq = (k) => [...new Set(rows.map((r) => r[k]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fa'))
  const scoped = rows.filter((r) => (!f.brand || r.brand === f.brand) && (!f.province || r.province === f.province))
  const shown = scoped.filter((r) => f.active !== '1' || r.gross || r.returns)
  const year = faDigits(data.month.slice(0, 4))
  const where = exp ? 'کشور' : 'استان'
  // ترتیب ستون‌ها مثل جدول پورسانت هیبریدها: محل و نام، فروش، فاکتورهای مدیریتی، پورسانت، فروش از ابتدای سال، مطالبات
  const cols = [
    { key: 'province', label: where, sticky: true },
    { key: 'label', label: exp ? 'نام مشتری' : 'نام نماینده', sticky: true },
    { key: 'code', label: 'کد' },
    { key: 'brand', label: exp ? 'برند حساب' : 'برند' },
    ...(!exp ? [{ key: 'city', label: 'شهر', exportOnly: true }] : []),
    { key: 'name', label: 'نام حساب', exportOnly: true },
    { key: 'invoices', label: 'تعداد فاکتور', type: 'int' },
    { key: 'gross', label: 'فروش ناخالص', type: 'money', hint: 'جمع قبل از تخفیف اقلام فاکتور (Price)' },
    { key: 'net', label: 'فروش خالص', type: 'money', hint: 'خالص فاکتورها (NetPrice راهکاران: ناخالص − همه تخفیف‌ها + مالیات) منهای خالص برگشتی‌های همین ماه' },
    { key: 'inv_net', label: 'خالص فاکتورها', type: 'money', exportOnly: true, hint: 'فروش خالص قبل از کسر برگشتی' },
    { key: 'cash', label: 'تخفیف نقدی', type: 'money', hint: 'سیاست فروش «تخفیف مشتریان اصلی» (همان درصد نقدی گزارش‌های راهکاران)' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی', type: 'money', hint: 'فروش خالص (پس از کسر برگشتی) به‌اضافه تخفیف نقدی' },
    ...(exp ? [
      { key: 'gross_usd', label: 'ناخالص (دلار)', type: 'int' },
      { key: 'net_usd', label: 'خالص (دلار)', type: 'int', hint: 'مبالغ ریالی صادرات = دلار × نرخ ارز همان سند (یا میانگین نرخ ماه)' },
    ] : []),
    { key: 'mgmt_n', label: 'تعداد فاکتور با تخفیف مدیریتی', type: 'int', hint: 'فاکتورهای فروشی که تخفیف مدیریتی دارند' },
    { key: 'mgmt_inv_gross', label: 'ناخالص فاکتورهای با تخفیف مدیریتی', type: 'money', hint: 'جمع ناخالص (قبل تخفیف) فاکتورهایی که تخفیف مدیریتی دارند' },
    { key: 'mgmt_inv_net_cash', label: 'خالص + نقدی فاکتورهای با تخفیف مدیریتی', type: 'money', hint: 'فروش خالص به‌اضافه تخفیف نقدی همان فاکتورها' },
    { key: 'mgmt', label: 'مبلغ تخفیف مدیریتی', type: 'money', hint: 'سیاست فروش «تخفیف مدیریتی» روی اقلام فاکتور' },
    pct2('mgmt_rate', 'نرخ تخفیف مدیریتی', 'مبلغ تخفیف مدیریتی ÷ مبلغ ناخالص همان فاکتورها'),
    pct2('mgmt_pct', 'درصد فروش مدیریتی', 'مجموع تخفیف مدیریتی ÷ فروش ناخالص'),
    { key: 'other_disc', label: 'سایر تخفیف‌ها', type: 'money', hint: 'کالای رایگان، فروش ویژه، تخفیف مبلغی و…: ناخالص + مالیات − خالص فاکتورها − نقدی − مدیریتی' },
    { key: 'tax', label: 'مالیات', type: 'money', exportOnly: exp, hint: 'مالیات و عوارض اقلام فاکتور (در خالص راهکاران آمده است)' },
    pct2('disc_pct', 'درصد کل تخفیف', '(ناخالص + مالیات − خالص فاکتورها) ÷ ناخالص'),
    pct2('cash_pct', 'درصد نقدی', 'تخفیف نقدی ÷ فروش ناخالص'),
    pct2('comm_pct', 'درصد پورسانت', 'پورسانت محاسبه‌شده ÷ (فروش خالص + درصد نقدی)'),
    { key: 'commission', label: 'پورسانت محاسبه‌شده', type: 'money', hint: `${fmtPct(RATE, 1)} × (فروش خالص + درصد نقدی)؛ مبنای منفی = صفر` },
    { key: 'reserve', label: 'ذخیره پورسانت', type: 'money' },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره' },
    { key: 'gross_ytd', label: `فروش ناخالص از ابتدای ${year}`, type: 'money', hint: 'جمع قبل تخفیف فاکتورها از ۱ فروردین تا پایان همین ماه' },
    { key: 'net_ytd', label: `فروش خالص از ابتدای ${year}`, type: 'money', hint: 'فروش خالص (برگشتی‌ها کسر شده) از ۱ فروردین تا پایان همین ماه' },
    { key: 'debt', label: 'مانده بدهی', type: 'money', hint: 'مطالبات باز همین کد از داشبورد مالی (همان پرونده نماینده)' },
    { key: 'open_cheques', label: 'چک باز', type: 'money' },
    { key: 'overdue', label: 'چک سررسید گذشته', type: 'money' },
    { key: 'returned', label: 'چک برگشتی', type: 'money', hint: 'مانده چک‌های برگشتی تسویه‌نشده روی حساب' },
    { key: 'ok_net', label: `تایید (${faDigits(APPROVAL_LIMIT * 100)}٪ خالص ${year})`, render: approvalPill,
      hint: `اگر مانده بدهی + چک برگشتی کمتر از ${faDigits(APPROVAL_LIMIT * 100)}٪ فروش خالص از ابتدای ${year} باشد «تایید»، وگرنه «عدم تایید»` },
  ]
  const totals = (rs) => {
    const sum = (k) => rs.reduce((a, r) => a + (r[k] || 0), 0)
    const t = Object.fromEntries(cols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, sum(c.key)]))
    const hasFin = rs.some((r) => isNum(r.debt))
    return withApproval({ ...t, ...(hasFin ? {} : { debt: null, open_cheques: null, overdue: null, returned: null }), key: '__total', label: 'جمع کل',
      disc_pct: ratio(t.gross + (t.tax || 0) - t.inv_net, t.gross), cash_pct: ratio(t.cash, t.gross), mgmt_rate: ratio(t.mgmt, t.mgmt_inv_gross),
      mgmt_pct: ratio(t.mgmt, t.gross), comm_pct: ratio(t.commission, t.net_cash) })
  }
  const tot = totals(shown)
  const select = (k, label, list) => (
    <label className="unit-select"><span className="ms-label">{label}</span>
      <select value={f[k]} onChange={(e) => { setF({ ...f, [k]: e.target.value }); setSel(null) }}>
        <option value="">همه</option>
        {list.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    </label>
  )
  const money = (v) => `${fmtMoney(v, 'rial')} ${UNITS.rial.label}`
  return (
    <>
      <PageHead title="پورسانت نمایندگان و صادرات"
        desc={`فروش ناخالص، خالص، خالص + نقدی و تخفیف‌های مدیریتی هر ${exp ? 'مشتری صادراتی' : 'نماینده'} از راهکاران، کنار مطالبات؛ با انتخاب ${where}، ریز مطالبات زیر جدول می‌آید.`}>
        <label className="unit-select"><span className="ms-label">ماه</span>
          <select value={data.month} onChange={(e) => { setMonth(e.target.value); setSel(null) }}>
            {data.months.map((m) => <option key={m} value={m}>{monthName(m)}{m === data.current ? ' (جاری)' : ''}</option>)}
          </select>
        </label>
      </PageHead>
      <Card actions={<Tabs value={channel} onChange={(c) => { setChannel(c); setSel(null); setF({ brand: '', province: '', active: '1' }) }} tabs={CHANNELS} />}
        title={`پورسانت ${exp ? 'صادرات' : 'نمایندگان B2B'} — ${monthName(data.month)}`}
        subtitle={`فروش ناخالص ${money(tot.gross)} · خالص ${money(tot.net)} · تخفیف مدیریتی ${money(tot.mgmt)} · پورسانت ${money(tot.commission)}${data.month === data.current ? ` · تا ${faDigits(data.today)}` : ''}`}>
        <div className="filter-bar">
          {select('brand', exp ? 'برند حساب' : 'برند', uniq('brand'))}
          {select('province', where, uniq('province'))}
          <label className="unit-select"><span className="ms-label">ردیف‌ها</span>
            <select value={f.active} onChange={(e) => setF({ ...f, active: e.target.value })}>
              <option value="1">فقط دارای فروش در این ماه</option><option value="0">همه دارای فروش امسال</option>
            </select>
          </label>
          {fin.loading && <span className="muted small">در حال خواندن مطالبات از بخش مالی…</span>}
          {fin.error && <span className="muted small">مطالبات از بخش مالی خوانده نشد: {fin.error}</span>}
          <span className="muted small">روی هر ردیف کلیک کنید تا ریز محاسبه باز شود.</span>
        </div>
        <DataTable rows={shown} columns={cols} unit="rial" pageSize={100} exportName={`rk-commission-${channel}-${data.month.replace('/', '-')}`}
          defaultSort={{ key: 'net', dir: 'desc' }} totals={totals}
          onRowClick={(r) => setSel(r.key === sel ? null : r.key)} expandedKey={sel}
          renderExpanded={(r) => <RowCalc r={r} />} />
      </Card>
      {f.province && <ProvinceDebt rows={scoped} place={f.province} exp={exp} fin={fin} />}
    </>
  )
}
