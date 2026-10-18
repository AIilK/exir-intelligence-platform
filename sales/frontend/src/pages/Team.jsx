import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtInt, fmtMoney, faDigits, UNITS, tierOf, tierTabs, TIER_HINT } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Kpi } from '../components/ui.jsx'
import { HBar } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'
import { DailyReport, CategoryMatrix, DailyTrend } from './Reports.jsx'
import { MONTH_NAMES } from '../jalali.js'

/** چرا فروش خالص فروشنده صفر یا منفی است */
const noSaleReason = (s) => {
  if (!(s.sales_net > 0) && s.returns_net > 0) return 'فقط برگشتی'
  if (s.sales_net > 0 && s.returns_net >= s.sales_net) return s.returns_net === s.sales_net ? 'برگشتی برابر فروش' : 'برگشتی بیشتر از فروش'
  if (!(s.sales_net > 0) && s.req_net > 0) return 'فقط درخواست، بدون فاکتور'
  return '—'
}
const noSaleCols = [
  C.label('فروشنده'), C.text('seller_code', 'کد'), C.text('branch', 'شعبه'), C.text('supervisor', 'سرپرست'),
  { key: 'reason', label: 'دلیل' },
  { key: 'sales_net', label: 'فروش', type: 'money', hint: 'فروش خالص فاکتورهای فروش در بازه' },
  { key: 'returns_net', label: 'برگشتی', type: 'money' },
  { key: 'net', label: 'فروش خالص', type: 'money' },
  { key: 'req_net', label: 'درخواست', type: 'money' },
  { key: 'req_docs', label: 'تعداد درخواست', type: 'int' },
  { key: 'invoices', label: 'فاکتور مؤثر', type: 'int' },
  { key: 'last_date', label: 'آخرین سند', type: 'date' },
]

const monthName = (m) => `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${faDigits(m.slice(0, 4))}`

/** نوار تاریخچه ماهانه: میله = فروش خالص ماه (آبی مثبت، قرمز منفی)، نقطه نارنجی = ماه دارای درخواست */
function ActivityStrip({ months, hist, since }) {
  const w = 7, h = 30, base = 20
  const max = Math.max(1, ...hist.net.map(Math.abs))
  return (
    <svg width={months.length * w} height={h} className="strip" aria-hidden>
      {months.map((m, i) => {
        const x = (months.length - 1 - i) * w   // راست به چپ: قدیمی‌ترین ماه سمت راست
        const v = hist.net[i]
        const bh = Math.max(v ? 1.5 : 0, (Math.abs(v) / max) * (v >= 0 ? base - 8 : h - base - 1))
        return (
          <g key={m}>
            <title>{`${monthName(m)}: ${fmtInt(hist.req[i])} درخواست، فروش خالص ${fmtMoney(v, 'million')} میلیون تومان`}</title>
            {`${m}/01` >= since && <rect x={x} y={0} width={w} height={h} className="after" />}
            {v !== 0 && <rect x={x + 1} y={v >= 0 ? base - bh : base} width={w - 2} height={bh} className={v >= 0 ? 'pos' : 'neg'} />}
            {hist.req[i] > 0 && <circle cx={x + w / 2} cy={3.5} r={2.2} className="req" />}
          </g>
        )
      })}
      <line x1={0} x2={months.length * w} y1={base} y2={base} className="base" />
    </svg>
  )
}

/** فروشندگانی که از ماه انتخابی هیچ درخواستی ثبت نکرده‌اند، با تاریخچه ماهانه */
function InactiveSellers() {
  const { unit, meta } = useApp()
  const [since, setSince] = useState('1405/02')
  const [sel, setSel] = useState(null)
  const { data, loading, error } = useApi('/api/inactive', `&since=${encodeURIComponent(since)}`)
  const months = (meta?.file.months || []).filter((m) => m.loaded).map((m) => m.month).sort().reverse()
  const picker = (
    <label className="unit-select">
      <span className="ms-label">بدون هیچ درخواستی از ابتدای</span>
      <select value={since} onChange={(e) => { setSince(e.target.value); setSel(null) }}>
        {months.map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
      </select>
    </label>
  )
  if (loading && !data) return <Card title="فروشندگان غیرفعال" className="span2" actions={picker}><Loading /></Card>
  if (error) return <Card title="فروشندگان غیرفعال" className="span2" actions={picker}><ErrorBox error={error} /></Card>
  const rows = data.rows
  const cur = rows.find((r) => r.key === sel)
  const shown = data.since.slice(0, 7)  // ماهِ داده‌ای که الان نمایش داده می‌شود (تا رسیدن پاسخ جدید)
  const cols = [
    C.label('فروشنده'), C.text('seller_code', 'کد'), C.text('branch', 'شعبه'), C.text('supervisor', 'سرپرست'),
    { key: 'last_req', label: 'آخرین درخواست', type: 'date' },
    { key: 'last_sale', label: 'آخرین فاکتور فروش', type: 'date' },
    { key: 'last_return', label: 'آخرین برگشتی', type: 'date' },
    { key: 'status', label: `وضعیت از ${monthName(shown)}`,
      hint: 'فاکتور مستقیم بدون درخواست: بعد از توقف درخواست هنوز فاکتور فروش دارد. فقط برگشتی: فقط برگشت از فروش. بدون فعالیت: هیچ سندی ندارد.' },
    { key: 'returns_after', label: 'برگشتی بعد از توقف', type: 'money' },
    { key: 'req_docs', label: 'کل درخواست‌ها', type: 'int', hint: 'از ۱۴۰۴/۰۱ تا امروز' },
    { key: 'net', label: 'کل فروش خالص', type: 'money', hint: 'از ۱۴۰۴/۰۱ تا امروز' },
    { key: 'hist', label: 'تاریخچه ماهانه', csv: false, render: (r) => <ActivityStrip months={data.months} hist={r.hist} since={data.since} />,
      hint: 'هر ستون یک ماه از ۱۴۰۴/۰۱ (راست) تا ماه جاری (چپ). میله آبی = فروش خالص، قرمز = خالص منفی، نقطه نارنجی = ماه دارای درخواست. زمینه خاکستری = بعد از ماه انتخابی.' },
  ]
  const hm = cur ? data.months.map((m, i) => ({ m, i })).filter(({ i }) => cur.hist.req[i] || cur.hist.net[i] || cur.hist.returns[i]).reverse() : []
  return (
    <Card title="فروشندگان غیرفعال" className="span2" actions={picker}
      subtitle={`${fmtInt(rows.length)} فروشنده از ابتدای ${monthName(shown)} هیچ درخواستی ثبت نکرده‌اند؛ ${fmtInt(data.active)} فروشنده در همین مدت درخواست داشته‌اند. ${fmtInt(data.no_request)} حساب که از ۱۴۰۴ هرگز درخواست نداشته‌اند (مثل دفترها) در این فهرست نیستند. کل تاریخچه بررسی می‌شود و فیلتر تاریخ اثری ندارد؛ برای دیدن تاریخچه ماه‌به‌ماه روی هر ردیف کلیک کنید.`}>
      <DataTable rows={rows} columns={cols} unit={unit} pageSize={15} exportName="inactive-sellers"
        onRowClick={(r) => setSel(r.key === sel ? null : r.key)} />
      {cur && (
        <div className="inactive-hist">
          <div className="report-tools">
            <b>تاریخچه {cur.label} — {cur.branch} (کد {cur.seller_code})</b>
            <span className="muted small">از {faDigits(cur.first_date)} تا {faDigits(cur.last_any)}</span>
            <button className="btn ghost sm" onClick={() => setSel(null)}>بستن</button>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr>
                <th>ماه</th><th className="num">تعداد درخواست</th>
                <th className="num">مبلغ درخواست <span className="th-unit">({UNITS[unit].label})</span></th>
                <th className="num">فاکتور مؤثر</th>
                <th className="num">فروش خالص <span className="th-unit">({UNITS[unit].label})</span></th>
                <th className="num">برگشتی <span className="th-unit">({UNITS[unit].label})</span></th>
              </tr></thead>
              <tbody>
                {hm.map(({ m, i }) => (
                  <tr key={m} className={`${m}/01` >= data.since ? 'active-row' : ''}>
                    <td>{monthName(m)}</td>
                    <td className="num">{fmtInt(cur.hist.req[i])}</td>
                    <td className="num">{fmtMoney(cur.hist.req_net[i], unit)}</td>
                    <td className="num">{fmtInt(cur.hist.invoices[i])}</td>
                    <td className={`num ${cur.hist.net[i] < 0 ? 'neg' : ''}`}>{fmtMoney(cur.hist.net[i], unit)}</td>
                    <td className="num">{fmtMoney(cur.hist.returns[i], unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="muted small">ماه‌های بدون هیچ سندی نمایش داده نمی‌شوند؛ ردیف‌های رنگی بعد از ماه انتخابی‌اند.</div>
        </div>
      )}
    </Card>
  )
}

const REPORT_DESC = {
  summary: 'رتبه‌بندی بر اساس فروش خالص از ابتدای ماه',
  daily: 'میانگین روزانه، روز گزارش و از ابتدای ماه — معادل شیت‌های TotalReport و Sales rep Ranking',
  matrix: 'فروش تعدادی و سهم ریالی گروه‌های اصلی کالا برای هر فروشنده — معادل ستون‌های گروه کالا در TotalReport',
  trend: 'روند روزانه هر فروشنده و روزهای فعال — معادل شیت‌های Trend (فاکتور) و Trend2 (درخواست)',
}

export default function Team() {
  const { data, loading, error } = useApi('/api/team')
  const { unit } = useApp()
  const nav = useNavigate()
  const [level, setLevel] = useState('seller')
  const [view, setView] = useState('summary')
  const [showNoSale, setShowNoSale] = useState(false)
  const [tier, setTier] = useState('all')
  const { meta } = useApp()
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const sellers = data.sellers
  const selling = sellers.filter((s) => s.net > 0)
  const noSale = sellers.filter((s) => !(s.net > 0))
  // برترین‌ها: کل یا فقط یک دسته شعبه (A / B / سایر)
  const tiered = selling.filter((s) => tier === 'all' || tierOf(meta, s.branch) === tier)
  const present = [...new Set(selling.map((s) => tierOf(meta, s.branch)))]
  const top = tiered.slice(0, 15).map((s) => ({ ...s, label: `${s.label} — ${s.branch}` }))
  const byInv = [...tiered].sort((a, b) => b.invoices - a.invoices).slice(0, 15).map((s) => ({ ...s, label: `${s.label} — ${s.branch}` }))
  const tierTabsEl = <Tabs value={tier} onChange={setTier} tabs={tierTabs(present)} />
  const k = data.kpis
  const sellerCols = [
    { key: 'rank', label: 'رتبه', type: 'int' }, C.label('فروشنده'), C.text('seller_code', 'کد'), C.text('branch', 'شعبه'),
    C.text('supervisor', 'سرپرست'), C.net, C.share, C.forecast, C.req_net, C.req_conv, C.invoices, C.lines_per_inv, C.customers,
    C.avg_invoice, C.sku, C.disc_rate, C.return_rate, C.last_date,
  ]
  const supCols = [C.label('سرپرست'), C.net, C.share, C.forecast, C.req_net, C.req_conv, C.invoices, C.lines_per_inv, C.customers, C.avg_invoice, C.disc_rate, C.return_rate]
  return (
    <>
      <PageHead title="تیم فروش" desc="رتبه‌بندی و عملکرد فروشندگان و سرپرستان" />
      <div className="kpis">
        <Kpi label="فروشندگان دارای فروش مثبت" value={selling.length} type="int" sub={`از ${fmtInt(sellers.length)} فروشنده دارای فاکتور یا درخواست`} />
        <Kpi label="فروشندگان بدون فروش خالص" value={noSale.length} type="int"
          hint="فقط درخواست، یا برگشتی بیشتر از فروش — برای دیدن فهرست کلیک کنید"
          onClick={noSale.length ? () => setShowNoSale(!showNoSale) : undefined} active={showNoSale} />
        <Kpi label="میانگین فروش هر فروشنده فعال" value={selling.length ? k.net / selling.length : null} />
        <Kpi label="میانگین فاکتور مؤثر هر فروشنده" value={selling.length ? k.invoices / selling.length : null} type="num1" />
      </div>
      {showNoSale && noSale.length > 0 && (
        <Card title="فروشندگان بدون فروش خالص" className="nosale-card"
          subtitle="فروشندگانی که در بازه انتخاب‌شده فاکتور، برگشتی یا درخواست دارند ولی فروش خالصشان صفر یا منفی است. برای جزئیات و سطرهای فاکتور روی هر ردیف کلیک کنید."
          actions={<button className="btn ghost sm" onClick={() => setShowNoSale(false)}>بستن</button>}>
          <DataTable rows={noSale.map((s) => ({ ...s, reason: noSaleReason(s) }))} columns={noSaleCols} unit={unit}
            pageSize={15} search={noSale.length > 15} exportName="sellers-no-net-sales"
            defaultSort={{ key: 'net', dir: 'asc' }} onRowClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
      )}
      <div className="grid g2">
        <Card title="۱۵ فروشنده برتر — فروش خالص" subtitle={TIER_HINT} actions={tierTabsEl}>
          <HBar rows={top} unit={unit} onClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
        <Card title="۱۵ فروشنده برتر — تعداد فاکتور مؤثر" subtitle={TIER_HINT} actions={tierTabsEl}>
          <HBar rows={byInv} value="invoices" valueType="int" unit={unit} colorIndex={2} onClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
        <Card title="گزارش‌های تیم فروش" className="span2"
          subtitle={REPORT_DESC[view]}
          actions={<Tabs value={view} onChange={setView} tabs={[
            { value: 'summary', label: 'خلاصه عملکرد' }, { value: 'daily', label: 'گزارش روزانه' },
            { value: 'matrix', label: 'ماتریس گروه کالا' }, { value: 'trend', label: 'روند روزانه' },
          ]} />}>
          {view === 'summary' && (
            <>
              <div className="report-tools">
                <Tabs value={level} onChange={setLevel} tabs={[{ value: 'seller', label: 'فروشنده' }, { value: 'supervisor', label: 'سرپرست' }]} />
              </div>
              <DataTable rows={level === 'seller' ? sellers : data.supervisors} columns={level === 'seller' ? sellerCols : supCols}
                unit={unit} pageSize={25} exportName={`team-${level}`} onRowClick={(r) => nav(detailPath(level, r.key))} />
            </>
          )}
          {view === 'daily' && <DailyReport dims={['branch', 'seller']} variant="team" exportName="team-daily-report" />}
          {view === 'matrix' && <CategoryMatrix />}
          {view === 'trend' && <DailyTrend />}
        </Card>
        <InactiveSellers />
      </div>
    </>
  )
}
