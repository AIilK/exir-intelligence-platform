import SalesDateRange from '../components/SalesDateRange.jsx'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApp, useRkFetch, fmtInt, fmtPct, fmtMoney, UNITS } from '../lib.jsx'
import { Card, Kpi, Loading, ErrorBox, Empty, DataTable, Tabs, MultiSelect } from '../components/ui.jsx'
import { Chart, HBar, baseOption, useTheme } from '../components/Chart.jsx'
import { brandColor } from '../brands.js'
import { TreeTable } from '../components/TreeTable.jsx'
import { PageHead } from '../components/Layout.jsx'
import ProductMix from '../components/ProductMix.jsx'
import DayPicker, { parseDays, isDays } from '../components/DayPicker.jsx'
import { BrandDonut, BubbleMap, CustomerDetail, ProductFilter, monthLabel, q } from './Rahkaran.jsx'
import Reorder from './Reorder.jsx'

const PAGES = [
  ['overview', 'نمای کلی فروش'], ['performance', 'عملکرد نمایندگان'], ['products', 'محصولات و گروه‌ها'],
  ['analysis', 'تحلیل کیفیت فروش'], ['orders', 'سفارش‌ها و پیگیری نمایندگان'],
]
function MonthlyComparison({ rows, unit, metric }) {
  if (!rows.length) return <Empty />
  const quantity = metric === 'qty'
  const format = (v) => quantity ? `${fmtInt(v)} عدد` : `${fmtMoney(v, unit)} ${UNITS[unit].label}`
  return <Chart height={290} option={(t) => ({
    legend: { top: 0, textStyle: { color: t.text } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps) => `${monthLabel(rows[ps[0].dataIndex].month)}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: ${format(rows[p.dataIndex][p.seriesIndex ? `ly_${metric}` : metric] || 0)}`).join('<br/>') },
    grid: { left: 16, right: 16, top: 40, bottom: 24, containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => monthLabel(r.month)), inverse: true, axisLabel: { color: t.text } },
    yAxis: { type: 'value', position: 'right', name: quantity ? 'عدد' : UNITS[unit].label, axisLabel: { color: t.text }, splitLine: { lineStyle: { color: t.grid } } },
    series: [[metric, 'امسال'], [`ly_${metric}`, 'سال قبل']].map(([key, name], i) => ({
      name, type: 'bar', data: rows.map((r) => (r[key] || 0) / (quantity ? 1 : UNITS[unit].div)),
      lineStyle: { color: t.series[i], width: 2 }, itemStyle: { color: t.series[i] },
    })),
  })} />
}

export function topContributors(customers, metric = 'net') {
  const ranked = customers.filter((r) => r[metric] > 0).sort((a, b) => b[metric] - a[metric])
  const total = ranked.reduce((sum, row) => sum + row[metric], 0)
  const rows = []
  let cumulative = 0
  for (const row of ranked) {
    if (cumulative >= total * .8) break
    rows.push({ ...row, label: `${row.label} (${row.brand || '—'})${row.city || row.province ? ` — ${row.city || row.province}` : ''}` })
    cumulative += row[metric]
  }
  return { rows, population: ranked.length }
}

function TopContributors({ customers, metric, unit, actions, onCustomer }) {
  const result = topContributors(customers, metric)
  return <Card title="مشتریان سازنده ۸۰٪ فروش" actions={actions}
    subtitle={`${fmtInt(result.rows.length)} نماینده از ${fmtInt(result.population)} کد نماینده دارای ${metric === 'qty' ? 'فروش تعدادی مثبت' : 'خرید مثبت'}؛ بر اساس ${metric === 'qty' ? 'تعداد فروش' : 'فروش خالص'} (TOP 80%)؛ برای پرونده کلیک کنید`}>
    {result.rows.length ? <HBar rows={result.rows} value={metric} valueType={metric === 'qty' ? 'int' : 'money'} unit={unit}
      labelWidth={230} colorOf={(r, t) => brandColor(r.brand, t)} onClick={(r) => onCustomer(r.key)} /> : <Empty />}
  </Card>
}

function Workspace({ mode, children }) {
  const { unit, setUnit } = useApp()
  const [sp, setSp] = useSearchParams()
  const theme = useTheme()
  const [level, setLevel] = useState('province')
  const [analysisBy, setAnalysisBy] = useState('category')
  const [customerCode, setCustomerCode] = useState(null)
  const metricFor = (chart) => sp.get(`metric_${chart}`) === 'qty' ? 'qty' : 'net'
  const ranked = (rows, chart) => [...rows].filter((r) => r[metricFor(chart)] > 0).sort((a, b) => b[metricFor(chart)] - a[metricFor(chart)])
  const chartProps = (chart) => ({ value: metricFor(chart), valueType: metricFor(chart) === 'qty' ? 'int' : 'money', unit })
  const mapBrand = sp.get('map_brand') || ''
  const period = sp.get('period') || 'YTD'
  const query = q({ period, brand: sp.get('brand'), province: sp.get('province'), customer: sp.get('customer'),
    product: sp.getAll('product'), group: sp.getAll('group'), quality_only: mode === 'analysis' ? '1' : null })
  const { data, loading, error } = useRkFetch(`/api/rk_sales/workspace?${query}`)
  const set = (key, value) => {
    const next = new URLSearchParams(sp)
    next.delete(key)
    ;(Array.isArray(value) ? value : [value]).filter(Boolean).forEach((v) => next.append(key, v))
    if (key === 'brand' || key === 'province') next.delete('customer')
    setSp(next)
    setCustomerCode(null)
  }
  const metricTabs = (chart) => <Tabs value={metricFor(chart)} onChange={(v) => set(`metric_${chart}`, v)}
    tabs={[{ value: 'net', label: 'مبلغ' }, { value: 'qty', label: 'تعداد' }]} />
  const title = PAGES.find(([key]) => key === mode)[1]
  const customerColumns = [
    { key: 'key', label: 'کد مشتری' }, { key: 'label', label: 'نماینده' }, { key: 'province', label: 'استان' }, { key: 'brand', label: 'برند' },
  ]
  const metrics = [
    { key: 'gross', label: 'فروش ناخالص', type: 'money' }, { key: 'net', label: 'خالص فاکتور', type: 'money' },
    { key: 'net_cash', label: 'خالص + نقدی', type: 'money' }, { key: 'qty', label: 'تعداد فروش', type: 'int' },
    { key: 'req_gross', label: 'ناخالص درخواست', type: 'money' }, { key: 'returns', label: 'برگشتی', type: 'money' },
    { key: 'share', label: 'سهم فروش', type: 'pct' }, { key: 'growth', label: 'رشد نسبت به سال قبل', type: 'pct' },
    { key: 'disc_rate', label: 'نرخ تخفیف', type: 'pct' }, { key: 'return_rate', label: 'نرخ برگشت', type: 'pct' },
    { key: 'invoices', label: 'فاکتور مؤثر', type: 'int' }, { key: 'avg_invoice', label: 'میانگین فاکتور', type: 'money' },
  ]
  const openRow = (row) => level === 'customer' ? setCustomerCode(row.key) : set('province', row.key)
  return <>
    <PageHead title={`${title} — B2B`} desc="فروش کارخانه به نمایندگان راهکاران؛ فاکتور فروش، برگشتی و درخواست به‌صورت جداگانه" />
    {children}
    {error ? <ErrorBox error={error} /> : loading && !data ? <Loading /> : !data ? <Empty /> : <>
      <div className="filterbar rk-controls">
        <SalesDateRange today={data.today} dates={data.sale_days || []}
          from={period.startsWith('R:') ? period.split(':')[1] : period === 'YTD' ? `${data.today.slice(0,4)}/01/01` : `${period.slice(0,7)}/01`}
          to={period.startsWith('R:') ? period.split(':')[2] : data.today}
          onChange={(from, to) => set('period', `R:${from}:${to}`)} />
        {[['brand', 'برند', data.options.brands], ['province', 'استان', data.options.provinces]].map(([key, label, values]) =>
          <label className="inline-field" key={key}><span>{label}</span><select value={sp.get(key) || ''} onChange={(e) => set(key, e.target.value)}>
            <option value="">همه</option>{values.map((v) => <option key={v} value={v}>{v}</option>)}
          </select></label>)}
        <MultiSelect label="نماینده" single value={sp.get('customer') ? [sp.get('customer')] : []}
          onChange={(values) => set('customer', values[0] || null)}
          options={data.options.customers.filter((c) => (!sp.get('brand') || c.brand === sp.get('brand')) && (!sp.get('province') || c.province === sp.get('province')))
            .map((c) => ({ value: c.code, label: `${c.short} — ${c.brand} — ${c.code}`, group: c.province }))} />
        <MultiSelect label="گروه کالا" value={sp.getAll('group')} onChange={(v) => set('group', v)} options={data.options.groups.map((v) => ({ value: v, label: v }))} />
        <ProductFilter value={sp.getAll('product')} onChange={(v) => set('product', v)} />
        <label className="inline-field"><span>واحد مبالغ</span><select value={unit} onChange={(e) => setUnit(e.target.value)}>
          {Object.entries(UNITS).map(([key, v]) => <option key={key} value={key}>{v.label}</option>)}
        </select></label>
        <button className="btn ghost sm" onClick={() => { setSp({}); setCustomerCode(null) }}>حذف فیلترها</button>
      </div>
      {loading && <div className="muted small" role="status">در حال به‌روزرسانی گزارش با فیلترهای انتخاب‌شده…</div>}
      <p className="muted small">برگشتی از خالص فاکتور کسر نشده است. درخواست شامل درخواست‌های تأییدشده و بسته‌شده است و به معنی «درخواست باز» نیست. تعداد نمایندگان بر اساس کد مشتری است.</p>
      {mode === 'overview' && <div className="kpis">
        <Kpi label="خالص فاکتورهای فروش" value={data.kpis.net} sub={`رشد نسبت به سال قبل ${fmtPct(data.kpis.growth)}`} />
        <Kpi label="فروش ناخالص" value={data.kpis.gross} />
        {mode === 'overview' && <Kpi label="نرخ تخفیف" type="pct"
          value={data.kpis.gross > 0 ? (data.kpis.gross + (data.kpis.tax || 0) - data.kpis.net) / data.kpis.gross : null}
          hint="مجموع تخفیف‌ها ÷ فروش ناخالص؛ مجموع تخفیف‌ها = ناخالص + مالیات − خالص فاکتورها. مالیات تخفیف محسوب نمی‌شود."
          sub={`نقدی ${fmtPct(data.kpis.gross > 0 ? (data.kpis.cash || 0) / data.kpis.gross : null)} · مدیریتی ${fmtPct(data.kpis.gross > 0 ? (data.kpis.mgmt || 0) / data.kpis.gross : null)}`} />}
        <Kpi label="خالص + تخفیف نقدی" value={data.kpis.net_cash} />
        <Kpi label="فروش تعدادی" value={data.kpis.qty} type="int" sub={`${fmtInt(data.kpis.skus)} کالای فروش‌رفته`} />
        <Kpi label="ناخالص درخواست" value={data.kpis.req_gross} />
        <Kpi label="برگشت از فروش" value={data.kpis.returns} />
        <Kpi label="کد مشتری خریدار در دوره" value={data.kpis.customers_period} type="int" sub={`${fmtInt(data.kpis.customers_inactive)} کد بدون خرید از ابتدای سال`} />
      </div>}
      {mode === 'overview' && <div className="grid g2">
        <Card title={`نقشه ایران — فروش ${metricFor('map') === 'qty' ? 'تعدادی' : 'خالص استان‌ها'}${mapBrand ? ` — ${mapBrand}` : ''}`} className="span2"
          subtitle={`اندازه حباب = ${metricFor('map') === 'qty' ? 'تعداد فروش' : `فروش خالص (${UNITS[unit].label})`}؛ فیلتر برند این کارت فقط روی نقشه اثر دارد`}
          actions={<>{metricTabs('map')}<div className="rk-brand-chips" role="group" aria-label="برند نقشه ایران">
            <button className={`chip${mapBrand ? '' : ' on'}`} aria-pressed={!mapBrand} onClick={() => set('map_brand', null)}>Total</button>
            {data.options.brands.map((b) => <button key={b} className={`chip${mapBrand === b ? ' on' : ''}`} aria-pressed={mapBrand === b} onClick={() => set('map_brand', b)}>
              <i style={{ background: brandColor(b, theme) }} />{b}
            </button>)}
          </div></>}>
          <BubbleMap provinces={data.provinces} selected={sp.get('province')} onSelect={(p) => set('province', p)} unit={unit} metric={metricFor('map')} brand={mapBrand} />
        </Card>
        <Card title={`فروش ${metricFor('provinces') === 'qty' ? 'تعدادی' : 'خالص'} استان‌ها`} actions={metricTabs('provinces')}><HBar rows={ranked(data.provinces, 'provinces')} {...chartProps('provinces')} onClick={(r) => set('province', r.key)} /></Card>
        <Card title={`فروش ${metricFor('brands') === 'qty' ? 'تعدادی' : 'خالص'} برندها`} actions={metricTabs('brands')}><HBar rows={ranked(data.brands, 'brands')} {...chartProps('brands')} onClick={(r) => set('brand', r.key)} /></Card>
        <Card title="سهم برندها از فروش" subtitle={`سهم از ${metricFor('share') === 'qty' ? 'تعداد فروش' : 'فروش خالص'}؛ برای فیلتر روی برند کلیک کنید`} actions={metricTabs('share')}>
          <BrandDonut rows={ranked(data.brands, 'share')} unit={unit} metric={metricFor('share')} onClick={(r) => set('brand', r.key === sp.get('brand') ? null : r.key)} />
        </Card>
        <Card title="نمایندگان برتر" subtitle={`بر اساس ${metricFor('customers') === 'qty' ? 'تعداد' : 'مبلغ'}؛ برای مشاهده پرونده کلیک کنید`} actions={metricTabs('customers')}><HBar rows={ranked(data.customers, 'customers').slice(0, 15)} {...chartProps('customers')} onClick={(r) => setCustomerCode(r.key)} /></Card>
        <TopContributors customers={data.customers} metric={metricFor('top80')} unit={unit} actions={metricTabs('top80')} onCustomer={setCustomerCode} />
        <Card title="۱۵ گروه کالای پرفروش" subtitle={`بر اساس ${metricFor('categories') === 'qty' ? 'تعداد' : 'مبلغ'}`} actions={metricTabs('categories')}><HBar rows={ranked(data.categories, 'categories').slice(0, 15)} {...chartProps('categories')} onClick={(r) => set('group', r.key)} /></Card>
        <Card title={`روند ماهانه ${metricFor('monthly') === 'qty' ? 'تعدادی' : 'مبلغی'}؛ امسال و سال قبل`} className="span2" subtitle="همه ماه‌های سال تا ماه جاری، با فیلترهای صفحه به‌جز دوره" actions={metricTabs('monthly')}><MonthlyComparison rows={data.monthly} unit={unit} metric={metricFor('monthly')} /></Card>
      </div>}
      {mode === 'performance' && <div className="grid g2">
        <details className="card span2">
          <summary>گزارش‌های تفصیلی نمایندگان</summary>
          <p className="muted small">گزارش‌های اختصاصی با فیلترها و خروجی اکسل خودشان باز می‌شوند.</p>
          <div className="report-tools">
            <Link className="btn ghost sm" to="/rahkaran/customer-brand">ماتریس مشتری × برند</Link>
            <Link className="btn ghost sm" to="/rahkaran/total-report">گزارش کل؛ روز، ماه و سال در یک جدول</Link>
          </div>
        </details>
        <Card title="جدول عملکرد" className="span2" actions={<Tabs value={level} onChange={setLevel} tabs={[{ value: 'province', label: 'استان' }, { value: 'customer', label: 'نماینده' }]} />}>
          <DataTable rows={level === 'province' ? data.provinces : data.customers} columns={[...(level === 'province' ? [{ key: 'label', label: 'استان' }] : customerColumns), ...metrics]}
            unit={unit} pageSize={25} exportName={`b2b-performance-${level}`} onRowClick={openRow} />
        </Card>
      </div>}
      {mode === 'products' && <>
        <ProductMix nodes={data.goods.nodes} total={data.goods.total} />
        <div className="grid g2">
          <Card title="۱۵ کالای پرفروش تعدادی"><HBar rows={data.goods.nodes.filter((n) => n.level === 2 && n.qty > 0).sort((a, b) => b.qty - a.qty).slice(0, 15)} value="qty" valueType="int" unit={unit} /></Card>
          <Card title={`فروش ${metricFor('product_brands') === 'qty' ? 'تعدادی' : 'خالص'} برندها`} actions={metricTabs('product_brands')}>
            <HBar rows={ranked(data.brands, 'product_brands')} {...chartProps('product_brands')} onClick={(r) => set('brand', r.key)} />
          </Card>
          <Card title="۱۵ گروه کالای پرفروش" className="span2" subtitle={`بر اساس ${metricFor('product_categories') === 'qty' ? 'تعداد فروش' : 'فروش خالص'}؛ برای فیلتر روی گروه کلیک کنید`}
            actions={metricTabs('product_categories')}>
            <HBar rows={ranked(data.categories, 'product_categories').slice(0, 15)} {...chartProps('product_categories')} onClick={(r) => set('group', r.key)} />
          </Card>
          <Card title="برند ← گروه کالا ← کالا" className="span2"><TreeTable nodes={data.goods.nodes} total={data.goods.total}
            columns={[{ key: 'label' }, { key: 'code', label: 'کد کالا' }, { key: 'qty', label: 'تعداد', type: 'int' }, { key: 'net', label: 'خالص فاکتور', type: 'money' },
              { key: 'gross', label: 'ناخالص', type: 'money' }, { key: 'ret_qty', label: 'تعداد برگشتی', type: 'int' }, { key: 'share', label: 'سهم', type: 'pct' }, { key: 'net_growth', label: 'رشد مبلغی', type: 'pct' }]}
            sortKey="net" colorGroups firstLabel="برند / گروه / کالا" levelNames={['برند', 'گروه', 'کالا']} exportName="b2b-products" /></Card>
        </div>
      </>}
      {mode === 'analysis' && <>
        <div className="kpis">
          {[
            ['total', 'نرخ کل تخفیف', data.kpis.discount, data.kpis.disc_rate],
            ['cash', 'تخفیف نقدی', data.kpis.cash, data.kpis.cash_rate],
            ['mgmt', 'تخفیف مدیریتی', data.kpis.mgmt, data.kpis.mgmt_rate],
            ['other', 'سایر تخفیف‌ها', data.kpis.other_disc, data.kpis.other_rate],
          ].map(([key, label, amount, rate]) => <Kpi key={key} label={label} type="pct"
            value={rate}
            sub={`مبلغ: ${fmtMoney(amount, unit)} ${UNITS[unit].label}`}
            hint={`${label} ÷ فروش ناخالص فاکتورهای فروش همین دوره؛ مالیات و برگشتی در تخفیف محسوب نمی‌شوند${key === 'other' ? '؛ سایر = ناخالص + مالیات − خالص − نقدی − مدیریتی' : ''}`} />)}
        </div>
        <Quality data={data} by={analysisBy} onChange={setAnalysisBy} unit={unit} />
      </>}
      {customerCode && <CustomerDetail key={`${customerCode}|${query}`} code={customerCode} period={period} products={sp.getAll('product')} groups={sp.getAll('group')}
        unit={unit} onClose={() => setCustomerCode(null)} onProvince={(p) => { set('province', p); setCustomerCode(null) }} />}
    </>}
  </>
}

function Quality({ data, by, onChange, unit }) {
  const rows = data[{ province: 'provinces', customer: 'customers', brand: 'brands', category: 'categories' }[by]]
  const discounts = rows.filter((r) => r.gross > 0).map((r) => ({ ...r, total_rate: r.disc_rate }))
    .sort((a, b) => b.total_rate - a.total_rate)
  const tabs = <Tabs value={by} onChange={onChange} tabs={[{ value: 'category', label: 'گروه کالا' }, { value: 'brand', label: 'برند' }, { value: 'province', label: 'استان' }, { value: 'customer', label: 'نماینده' }]} />
  return <div className="grid g2">
    <Card title="نرخ تخفیف" className="span2" actions={tabs}
      subtitle="سهم تخفیف نقدی، مدیریتی و سایر تخفیف‌ها از فروش ناخالص کالاهای تجاری؛ استند، تستر، اقلام تبلیغاتی و گروه‌های نامشخص حذف شده‌اند. مرتب از بیشترین نرخ؛ سایر تخفیف‌ها شامل تخفیف حجمی و دیگر سیاست‌هاست.">
      <DiscountComposition rows={discounts.slice(0, 15)} unit={unit} />
    </Card>
    <Card title="بیشترین نرخ تخفیف مدیریتی" subtitle="تخفیف مدیریتی ÷ فروش ناخالص؛ مطابق دسته‌بندی انتخاب‌شده">
      <HBar rows={discounts.filter((r) => r.mgmt_rate > 0).sort((a, b) => b.mgmt_rate - a.mgmt_rate).slice(0, 15)} value="mgmt_rate" valueType="pct" unit={unit} />
    </Card>
    <Card title="بیشترین نرخ تخفیف نقدی" subtitle="تخفیف نقدی ÷ فروش ناخالص؛ مطابق دسته‌بندی انتخاب‌شده">
      <HBar rows={discounts.filter((r) => r.cash_rate > 0).sort((a, b) => b.cash_rate - a.cash_rate).slice(0, 15)} value="cash_rate" valueType="pct" unit={unit} />
    </Card>
  </div>
}

function DiscountComposition({ rows, unit }) {
  if (!rows.length) return <Empty />
  const data = [...rows].reverse()
  const parts = [['other_rate', 'سایر تخفیف‌ها', 'other_disc', 0], ['cash_rate', 'تخفیف نقدی', 'cash', 1], ['mgmt_rate', 'تخفیف مدیریتی', 'mgmt', 2]]
  const escape = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
  return <Chart height={Math.max(280, data.length * 36 + 80)} option={(t) => ({
    grid: { left: 24, right: 16, top: 42, bottom: 20, containLabel: true },
    legend: { top: 0, right: 0, textStyle: { color: t.text } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps) => {
      const row = data[ps[0].dataIndex]
      return `${escape(row.label)}<br/>` + parts.map(([rate, name, amount]) => `${name}: <b>${fmtPct(row[rate])}</b> — ${fmtMoney(row[amount], unit)} ${UNITS[unit].label}`).join('<br/>')
        + `<br/>کل تخفیف: <b>${fmtPct(row.total_rate)}</b>`
    } },
    xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtPct(v, 0) }, splitLine: { lineStyle: { color: t.grid } } },
    yAxis: { type: 'category', position: 'right', data: data.map((r) => r.label), axisLabel: { color: t.text, width: 220, overflow: 'truncate' }, axisTick: { show: false } },
    series: parts.map(([rate, name, , color], i) => ({ name, type: 'bar', stack: 'discount', data: data.map((r) => r[rate]), barMaxWidth: 22,
      itemStyle: { color: t.series[color], borderColor: t.surface, borderWidth: 1 },
      ...(i === parts.length - 1 ? { label: { show: true, position: 'left', color: t.text, fontWeight: 600, formatter: (p) => fmtPct(data[p.dataIndex].total_rate) } } : {}),
    })),
  })} />
}

export function Overview() { return <Workspace mode="overview" /> }
export function Performance() { return <Workspace mode="performance" /> }
export function Products() { return <Workspace mode="products" /> }
export function Analysis() { return <Workspace mode="analysis" /> }
export function Orders() { return <Reorder title="سفارش‌ها و پیگیری نمایندگان — B2B" urlFilters /> }
