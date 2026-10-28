import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, detailPath, nodeWithin, faDigits, fmtInt } from '../lib.jsx'
import { Loading, ErrorBox, Tabs } from '../components/ui.jsx'
import { TreeTable, ReportDayPicker, Spark } from '../components/TreeTable.jsx'
import { useApp } from '../lib.jsx'

const LEVEL_NAMES = {
  branch: 'شعبه', seller: 'فروشنده', supervisor: 'سرپرست', brand: 'برند', category: 'گروه کالا', group: 'زیرگروه', product: 'کالا',
}
// پس‌زمینه کم‌رنگ آبی متناسب با مقدار (برای ماتریس‌ها)
const heat = (v, max) => (typeof v === 'number' && v > 0 && max > 0
  ? { background: `rgba(57, 135, 229, ${(0.08 + 0.42 * Math.min(v / max, 1)).toFixed(3)})` } : undefined)

/**
 * گزارش «میانگین روزانه / روز گزارش / از ابتدای ماه» — معادل TotalReport (شعبه ← فروشنده)
 * و Goods&Group (برند ← گروه ← کالا).
 */
export function DailyReport({ dims, variant = 'team', exportName }) {
  const { reportDay } = useApp()
  const nav = useNavigate()
  const { data, loading, error } = useApi('/api/report_tree', `&dims=${dims.join(',')}${reportDay ? `&report_day=${encodeURIComponent(reportDay)}` : ''}`)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const rd = `روز گزارش ${faDigits(data.report_day)}`
  const isTeam = variant === 'team'
  const columns = [
    { key: 'label' },
    ...(isTeam ? [{ key: 'seller_code', label: 'کد' }, { key: 'supervisor', label: 'سرپرست' }] : []),
    { key: 'avg_gross', label: 'ناخالص', type: 'money', group: `میانگین روزانه (${fmtInt(data.days)} روز)` },
    { key: 'avg_net', label: 'خالص', type: 'money', group: `میانگین روزانه (${fmtInt(data.days)} روز)` },
    { key: 'avg_qty', label: 'تعداد', type: 'num1', group: `میانگین روزانه (${fmtInt(data.days)} روز)` },
    { key: 'avg_invoices', label: 'فاکتور', type: 'num1', group: `میانگین روزانه (${fmtInt(data.days)} روز)` },
    { key: 'rd_gross', label: 'ناخالص', type: 'money', group: rd },
    { key: 'rd_net', label: 'خالص', type: 'money', group: rd },
    { key: 'rd_qty', label: 'تعداد', type: 'int', group: rd },
    { key: 'rd_invoices', label: 'فاکتور', type: 'int', group: rd },
    ...(isTeam ? [
      { key: 'rd_lines_per_inv', label: 'سطر در فاکتور', type: 'num1', group: rd, hint: 'سطرهای با تعداد مثبت ÷ فاکتور مؤثر' },
      { key: 'rd_rank', label: 'رتبه', type: 'int', group: rd },
    ] : []),
    { key: 'gross', label: 'ناخالص', type: 'money', group: 'از ابتدای ماه' },
    { key: 'net', label: 'خالص', type: 'money', group: 'از ابتدای ماه' },
    { key: 'qty', label: 'تعداد', type: 'int', group: 'از ابتدای ماه' },
    { key: 'invoices', label: 'فاکتور', type: 'int', group: 'از ابتدای ماه' },
    ...(isTeam ? [{ key: 'lines_per_inv', label: 'سطر در فاکتور', type: 'num1', group: 'از ابتدای ماه', hint: 'سطرهای با تعداد مثبت ÷ فاکتور مؤثر' }] : []),
    { key: 'customers', label: 'مشتری', type: 'int', group: 'از ابتدای ماه' },
    ...(isTeam ? [{ key: 'rank', label: 'رتبه', type: 'int', group: 'از ابتدای ماه' }] : []),
    { key: 'req_net', label: 'خالص درخواست', type: 'money', group: 'درخواست' },
    ...(data.full_month ? [
      { key: 'forecast', label: 'ریالی', type: 'money', group: 'پیش‌بینی ماه' },
      { key: 'forecast_qty', label: 'تعدادی', type: 'int', group: 'پیش‌بینی ماه' },
    ] : []),
  ]
  return (
    <>
      <div className="report-tools">
        <ReportDayPicker value={data.report_day} />
        <span className="muted small">
          {isTeam && `رتبه در سطح ${LEVEL_NAMES[dims[dims.length - 1]]} و بر اساس فروش خالص است.`}
          {!data.full_month && ' پیش‌بینی ماه با فیلتر تاریخ محاسبه نمی‌شود.'}
        </span>
      </div>
      <TreeTable nodes={data.nodes} total={data.total} columns={columns} firstLabel={dims.map((d) => LEVEL_NAMES[d]).join(' / ')}
        levelNames={dims.map((d) => LEVEL_NAMES[d])} exportName={exportName}
        onRowClick={(n) => nav(detailPath(n.dim, n.key, nodeWithin(n, dims)))} />
    </>
  )
}

/** ماتریس فروشنده × گروه‌های اصلی کالا (ستون‌های سمت چپ TotalReport). */
export function CategoryMatrix({ dims = ['branch', 'seller'] }) {
  const nav = useNavigate()
  const { data, loading, error } = useApi('/api/category_matrix', `&dims=${dims.join(',')}`)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const cats = data.categories
  const columns = [
    { key: 'label' },
    { key: 'supervisor', label: 'سرپرست' },
    { key: 'net', label: 'فروش خالص کل', type: 'money' },
    ...cats.flatMap((c, i) => [
      { key: `q${i}`, label: 'فروش تعدادی', type: 'int', group: c },
      { key: `s${i}`, label: 'سهم ریالی', type: 'pct', group: c, hint: `فروش خالص ${c} ÷ فروش خالص کل همان ردیف` },
    ]),
  ]
  return (
    <>
      <div className="report-tools">
        <span className="muted small">
          شش گروه اصلی از فهرست core_categories در فایل category_map.json می‌آیند (همان گروه‌های گزارش TotalReport). سهم ریالی = فروش خالص گروه ÷ فروش خالص کل همان ردیف.
        </span>
      </div>
      <TreeTable nodes={data.nodes} total={data.total} columns={columns} firstLabel="شعبه / فروشنده"
        levelNames={['شعبه', 'فروشنده']} exportName="category-matrix" onRowClick={(n) => nav(detailPath(n.dim, n.key, nodeWithin(n, dims)))}
        cellStyle={(n, c) => (c.key.startsWith('s') && c.group ? heat(n[c.key], 1) : undefined)} />
    </>
  )
}

/** روند روزانه هر فروشنده (Trend برای فاکتور، Trend2 برای درخواست) + روزهای فعال. */
export function DailyTrend({ dims = ['branch', 'seller'] }) {
  const nav = useNavigate()
  const [source, setSource] = useState('sales')
  const [metric, setMetric] = useState('net')
  const { data, loading, error } = useApi('/api/daily_matrix', `&dims=${dims.join(',')}&metric=${metric}&source=${source}`)
  const type = metric === 'net' ? 'money' : 'int'
  const controls = (
    <div className="report-tools">
      <Tabs value={source} onChange={setSource} tabs={[{ value: 'sales', label: 'فاکتور فروش' }, { value: 'requests', label: 'درخواست' }]} />
      <Tabs value={metric} onChange={setMetric} tabs={[
        { value: 'net', label: 'فروش خالص' }, { value: 'qty', label: 'فروش تعدادی' }, { value: 'invoices', label: 'تعداد فاکتور' },
      ]} />
    </div>
  )
  if (loading && !data) return <>{controls}<Loading /></>
  if (error) return <>{controls}<ErrorBox error={error} /></>
  const dc = data.dates.map((d, i) => `d${i}`)
  const columns = [
    { key: 'label' },
    ...data.dates.map((d, i) => ({ key: `d${i}`, label: faDigits(d.slice(5)), type, group: 'روزانه' })),
    { key: 'total', label: 'جمع', type },
    { key: 'active_days', label: source === 'sales' ? 'روز با فروش مثبت' : 'روز با درخواست', type: 'int',
      hint: 'تعداد روزهایی که مقدار شاخص مثبت بوده است' },
    { key: 'active_pct', label: 'درصد روزهای فعال', type: 'pct', hint: 'روزهای فعال ÷ روز کاری سپری‌شده' },
    { key: 'spark', label: 'روند', type: 'spark', render: (n) => <Spark values={dc.map((k) => n[k] || 0)} /> },
  ]
  return (
    <>
      {controls}
      <TreeTable nodes={data.nodes} total={data.total} columns={columns} sortKey="total" firstLabel="شعبه / فروشنده"
        levelNames={['شعبه', 'فروشنده']} exportName={`trend-${source}-${metric}`} onRowClick={(n) => nav(detailPath(n.dim, n.key, nodeWithin(n, dims)))}
        cellStyle={(n, c) => (c.group === 'روزانه' ? heat(n[c.key], Math.max(...dc.map((k) => n[k] || 0))) : undefined)} />
    </>
  )
}

/** فاکتور به مشتری و سهم از فروش هر شعبه، کل و به تفکیک برند (پایین TotalReport). */
export function BrandShare() {
  const nav = useNavigate()
  const { data, loading, error } = useApi('/api/brand_share')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const nodes = data.rows.map((r) => ({ ...r, id: r.key, parent: '', level: 0, dim: 'branch' }))
  const columns = [
    { key: 'label' },
    { key: 'ipc', label: 'فاکتور به مشتری', type: 'num1', group: 'کل', hint: 'فاکتور مؤثر ÷ مشتری فعال' },
    { key: 'share', label: 'سهم از فروش', type: 'pct', group: 'کل', hint: 'فروش خالص شعبه ÷ فروش خالص کل' },
    ...data.brands.flatMap((b, i) => [
      { key: `b${i}_ipc`, label: 'فاکتور به مشتری', type: 'num1', group: b },
      { key: `b${i}_share`, label: 'سهم از فروش', type: 'pct', group: b, hint: `فروش خالص ${b} در این شعبه ÷ فروش خالص کل ${b}` },
    ]),
  ]
  return (
    <TreeTable nodes={nodes} columns={columns} sortKey="share" firstLabel="شعبه" exportName="brand-share"
      onRowClick={(n) => nav(detailPath('branch', n.key))}
      cellStyle={(n, c) => (c.key.endsWith('share') ? heat(n[c.key], 0.5) : undefined)} />
  )
}
