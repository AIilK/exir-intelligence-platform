import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, nodeWithin, fmtInt, tierOf, tierTabs, TIER_HINT } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Kpi } from '../components/ui.jsx'
import { HBar } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'
import { TreeTable } from '../components/TreeTable.jsx'
import { DailyReport, CategoryMatrix, DailyTrend } from './Reports.jsx'

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

// پس‌زمینه کم‌رنگ آبی متناسب با سهم ریالی گروه کالا
const heat = (v) => (typeof v === 'number' && v > 0
  ? { background: `rgba(57, 135, 229, ${(0.08 + 0.42 * Math.min(v, 1)).toFixed(3)})` } : undefined)

/**
 * گزارش کامل تیم فروش: هر هیبرید یک ردیف؛ با کلیک باز می‌شود و ویزیتورهای فعالش (دارای فاکتور مؤثر) می‌آیند.
 * ستون‌ها = خلاصه عملکرد + «از ابتدای ماه» گزارش روزانه + ماتریس گروه کالا. ردیف «کل» بالای جدول است.
 */
function TeamFullReport() {
  const nav = useNavigate()
  const { data, loading, error } = useApi('/api/team_report')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const P = data.full_month ? 'از ابتدای ماه' : 'بازه انتخاب‌شده'
  const D = `میانگین روزانه (${fmtInt(data.days)} روز)`
  const columns = [
    { key: 'label' },
    { key: 'seller_code', label: 'کد' },
    { key: 'supervisor', label: 'سرپرست' },
    { key: 'sellers', label: 'فروشنده فعال', type: 'int', hint: 'فروشندگان دارای فاکتور مؤثر در بازه' },
    { key: 'gross', label: 'ناخالص', type: 'money', group: P },
    { key: 'net', label: 'فروش خالص', type: 'money', group: P },
    { key: 'share', label: 'سهم از کل', type: 'pct', group: P, hint: 'فروش خالص ÷ فروش خالص همه شعب' },
    { key: 'qty', label: 'تعداد', type: 'int', group: P },
    { key: 'invoices', label: 'فاکتور مؤثر', type: 'int', group: P },
    { key: 'lines_per_inv', label: 'سطر در فاکتور', type: 'num1', group: P, hint: 'سطرهای با تعداد مثبت ÷ فاکتور مؤثر' },
    { key: 'customers', label: 'مشتری', type: 'int', group: P },
    { key: 'avg_invoice', label: 'میانگین فاکتور', type: 'money', group: P, hint: 'فروش خالص ÷ فاکتور مؤثر' },
    { key: 'sku', label: 'تنوع کالا', type: 'int', group: P, hint: 'تعداد کالاهای فروخته‌شده (تعداد مثبت)' },
    { key: 'rank', label: 'رتبه کل', type: 'int', group: P, hint: 'رتبه فروش خالص بین همه فروشندگان فعال' },
    { key: 'branch_rank', label: 'رتبه در شعبه', type: 'int', group: P, hint: 'رتبه فروش خالص بین فروشندگان فعال همان شعبه' },
    { key: 'avg_net', label: 'فروش خالص', type: 'money', group: D },
    { key: 'avg_invoices', label: 'فاکتور', type: 'num1', group: D },
    ...(data.full_month ? [{ key: 'forecast', label: 'پیش‌بینی ماه', type: 'money', group: D, hint: 'میانگین روزانه × کل روز کاری ماه' }] : []),
    { key: 'req_net', label: 'خالص درخواست', type: 'money', group: 'درخواست' },
    { key: 'req_conv', label: 'تبدیل درخواست', type: 'pct', group: 'درخواست', hint: 'درخواست‌های تبدیل‌شده به فاکتور ÷ کل درخواست (مبلغ)' },
    { key: 'returns_net', label: 'برگشتی', type: 'money', group: 'کیفیت فروش' },
    { key: 'return_rate', label: 'نرخ برگشتی', type: 'pct', group: 'کیفیت فروش', hint: 'برگشتی ÷ فروش' },
    { key: 'disc_rate', label: 'نرخ تخفیف', type: 'pct', group: 'کیفیت فروش', hint: 'تخفیف ÷ جمع قبل از تخفیف فاکتورهای فروش' },
    { key: 'last_date', label: 'آخرین سند', type: 'date', group: 'کیفیت فروش' },
    ...data.categories.flatMap((c, i) => [
      { key: `q${i}`, label: 'تعداد', type: 'int', group: c },
      { key: `s${i}`, label: 'سهم ریالی', type: 'pct', group: c, hint: `فروش خالص ${c} ÷ فروش خالص کل همان ردیف` },
    ]),
  ]
  return (
    <>
      <div className="report-tools">
        <span className="muted small">
          روی نام هر هیبرید کلیک کنید (یا «باز کردن همه») تا ویزیتورهایش باز شوند؛ روی بقیه خانه‌های ردیف برای پرونده کامل.
          همه مبالغ این جدول و خروجی اکسل آن به ریال کامل است.
          فقط فروشندگان فعال (دارای فاکتور مؤثر در بازه) ردیف دارند؛ اعداد شعبه و کل شامل همه اسناد همان شعبه است.
          سهم ریالی گروه کالا = فروش خالص گروه ÷ فروش خالص همان ردیف.
        </span>
      </div>
      <TreeTable nodes={data.nodes} total={data.total} columns={columns} firstLabel="هیبرید / ویزیتور"
        levelNames={['هیبرید', 'ویزیتور']} exportName="team-full-report" unit="rial" colorGroups
        onRowClick={(n) => nav(detailPath(n.dim, n.key, nodeWithin(n, ['branch', 'seller'])))}
        cellStyle={(n, c) => (c.key.startsWith('s') && c.group && data.categories.includes(c.group) ? heat(n[c.key]) : undefined)} />
    </>
  )
}

const REPORT_DESC = {
  full: 'گزارش کامل: هر هیبرید با کلیک باز می‌شود و ویزیتورهای فعالش با خلاصه عملکرد، از ابتدای ماه و ماتریس گروه کالا می‌آیند',
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
  const [view, setView] = useState('full')
  const [showNoSale, setShowNoSale] = useState(false)
  const [tier, setTier] = useState('all')
  const { meta } = useApp()
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const sellers = data.sellers
  const selling = sellers.filter((s) => s.net > 0)
  // از مهر ۱۴۰۵: فقط ویزیتورهای «لیست ویزیتور» صفحه پورسانت (roster_filter)؛ بقیه در این فهرست نمی‌آیند
  const noSale = sellers.filter((s) => !(s.net > 0) && (!data.roster_filter || s.in_roster))
  const rosterNote = data.roster_filter ? ' فقط ویزیتورهای «لیست ویزیتور» صفحه پورسانت (از مهر ۱۴۰۵) آمده‌اند.' : ''
  // برترین‌ها: کل یا فقط یک دسته شعبه (A / B / سایر)
  const tiered = selling.filter((s) => tier === 'all' || tierOf(meta, s.branch) === tier)
  const present = [...new Set(selling.map((s) => tierOf(meta, s.branch)))]
  // برترین‌ها و ضعیف‌ترین‌ها بین فروشندگان دارای فروش خالص مثبت (غیرفعال‌ها و بدون فروش جدا آمده‌اند)
  const named = (rs) => rs.slice(0, 15).map((s) => ({ ...s, label: `${s.label} — ${s.branch}` }))
  const byNet = [...tiered].sort((a, b) => b.net - a.net)
  const byInvoices = [...tiered].sort((a, b) => b.invoices - a.invoices || b.net - a.net)
  const top = named(byNet)
  const byInv = named(byInvoices)
  const worst = named([...byNet].reverse())
  const worstInv = named([...byInvoices].reverse())
  const BOTTOM_HINT = `${TIER_HINT} — از ضعیف‌ترین؛ فقط فروشندگان دارای فروش خالص مثبت`
  const tierTabsEl = <Tabs value={tier} onChange={setTier} tabs={tierTabs(present)} />
  const k = data.kpis
  const sellerCols = [
    { key: 'rank', label: 'رتبه', type: 'int' }, C.label('فروشنده'), C.text('seller_code', 'کد'), C.text('branch', 'شعبه'),
    C.text('supervisor', 'سرپرست'), C.net, C.share, C.req_net, C.req_conv, C.invoices, C.lines_per_inv, C.customers,
    C.avg_invoice, C.sku, C.disc_rate, C.return_rate, C.last_date,
  ]
  const supCols = [C.label('سرپرست'), C.net, C.share, C.req_net, C.req_conv, C.invoices, C.lines_per_inv, C.customers, C.avg_invoice, C.disc_rate, C.return_rate]
  return (
    <>
      <PageHead title="تیم فروش" desc="رتبه‌بندی و عملکرد فروشندگان و سرپرستان" />
      <div className="kpis">
        <Kpi label="فروشندگان دارای فروش مثبت" value={selling.length} type="int" sub={`از ${fmtInt(sellers.length)} فروشنده دارای فاکتور یا درخواست`} />
        <Kpi label="فروشندگان بدون فروش خالص" value={noSale.length} type="int"
          hint={`فقط درخواست، یا برگشتی بیشتر از فروش.${rosterNote} برای دیدن فهرست کلیک کنید`}
          onClick={noSale.length ? () => setShowNoSale(!showNoSale) : undefined} active={showNoSale} />
        <Kpi label="میانگین فروش هر فروشنده فعال" value={selling.length ? k.net / selling.length : null} />
        <Kpi label="میانگین فاکتور مؤثر هر فروشنده" value={selling.length ? k.invoices / selling.length : null} type="num1" />
      </div>
      {showNoSale && noSale.length > 0 && (
        <Card title="فروشندگان بدون فروش خالص" className="nosale-card"
          subtitle={`فروشندگانی که در بازه انتخاب‌شده فاکتور، برگشتی یا درخواست دارند ولی فروش خالصشان صفر یا منفی است.${rosterNote} برای جزئیات و سطرهای فاکتور روی هر ردیف کلیک کنید.`}
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
        <Card title="۱۵ فروشنده ضعیف — فروش خالص" subtitle={BOTTOM_HINT} actions={tierTabsEl}>
          <HBar rows={worst} unit={unit} colorIndex={7} onClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
        <Card title="۱۵ فروشنده ضعیف — تعداد فاکتور مؤثر" subtitle={BOTTOM_HINT} actions={tierTabsEl}>
          <HBar rows={worstInv} value="invoices" valueType="int" unit={unit} colorIndex={7} onClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
        <Card title="گزارش‌های تیم فروش" className="span2"
          subtitle={REPORT_DESC[view]}
          actions={<Tabs value={view} onChange={setView} tabs={[
            { value: 'full', label: 'گزارش کامل' },
            { value: 'summary', label: 'خلاصه عملکرد' }, { value: 'daily', label: 'گزارش روزانه' },
            { value: 'matrix', label: 'ماتریس گروه کالا' }, { value: 'trend', label: 'روند روزانه' },
          ]} />}>
          {view === 'full' && <TeamFullReport />}
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
      </div>
    </>
  )
}
