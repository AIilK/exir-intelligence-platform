import SalesDateRange from '../components/SalesDateRange.jsx'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useRkFetch, fmtInt, fmtPct, fmtExact, faDigits } from '../lib.jsx'
import { Card, Kpi, Loading, ErrorBox, Empty, DataTable, MultiSelect, Tabs } from '../components/ui.jsx'
import { Chart, HBar, baseOption } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { TreeTable } from '../components/TreeTable.jsx'
import ProductMix from '../components/ProductMix.jsx'
import { brandColor } from '../brands.js'
import { YearsChart, CustomerFile, SkuTree } from './Export.jsx'

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const SECTIONS = [
  ['overview', 'نمای کلی فروش'], ['countries', 'عملکرد کشورها و مشتریان'],
  ['products', 'محصولات و گروه‌ها'], ['quality', 'تحلیل کیفیت فروش'], ['comparison', 'روند و مقایسه فروش'],
].map(([value, label]) => ({ value, label }))
const SLICERS = [['month', 'ماه'], ['brand', 'برند'], ['cat', 'گروه کالا'], ['country', 'کشور'], ['customer', 'مشتری'], ['product', 'کالا']]
const usd = (n) => `${fmtExact(n)} دلار`
const escape = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

export function countryCustomerTree(countries, customers) {
  const roots = new Map(countries.map((r) => [r.key, { ...r }]))
  const sumKeys = ['net', 'gross', 'pcs', 'net_ly', 'pcs_ly', 'req', 'req_pcs', 'invoices', 'customers']
  for (const customer of customers) {
    const country = customer.country || 'نامشخص'
    if (!roots.has(country)) roots.set(country, { key: country, label: country, ...Object.fromEntries(sumKeys.map((key) => [key, 0])) })
  }
  const nodes = []
  for (const country of roots.values()) {
    const id = JSON.stringify(['country', country.key])
    nodes.push({ ...country, id, parent: '', level: 0 })
    for (const customer of customers.filter((r) => (r.country || 'نامشخص') === country.key)) {
      nodes.push({ ...customer, code: customer.key, id: JSON.stringify(['customer', country.key, customer.key]), parent: id, level: 1 })
    }
  }
  const total = Object.fromEntries(sumKeys.map((key) => [key, [...roots.values()].reduce((sum, r) => sum + (r[key] || 0), 0)]))
  total.growth = total.net_ly > 0 ? total.net / total.net_ly - 1 : null
  total.qty_growth = total.pcs_ly > 0 ? total.pcs / total.pcs_ly - 1 : null
  total.share = total.net > 0 ? 1 : null
  return { nodes, total }
}

function Bars({ rows, metric, onClick, brands = false }) {
  const selected = rows.filter((r) => r[metric] > 0).sort((a, b) => b[metric] - a[metric])
  return selected.length ? <HBar rows={selected} value={metric} valueType="int" onClick={onClick}
    colorOf={brands ? (r, t) => brandColor(r.key, t) : undefined} /> : <Empty />
}

function CustomerSales({ rows, metric, onClick }) {
  const selected = rows.filter((r) => r[metric] > 0).sort((a, b) => a[metric] - b[metric])
  if (!selected.length) return <Empty />
  const format = (value) => metric === 'net' ? usd(value) : `${fmtInt(value)} عدد`
  return <div style={{ maxHeight: 650, overflowY: 'auto' }}><Chart height={Math.max(280, selected.length * 28 + 60)}
    onClick={(p) => onClick(selected[p.dataIndex])} option={(t) => ({
      grid: { left: 24, right: 16, top: 8, bottom: 28, containLabel: true },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps) => {
        const row = selected[ps[0].dataIndex]
        return `${escape(row.label)}<br/>کد مشتری: ${escape(faDigits(row.key))}<br/>${format(row[metric])}`
      } },
      xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtInt(v) }, splitLine: { lineStyle: { color: t.grid } } },
      yAxis: { type: 'category', position: 'right', data: selected.map((r) => r.label), axisLabel: { color: t.text, width: 200, overflow: 'truncate' } },
      series: [{ name: metric === 'net' ? 'فروش دلاری' : 'فروش تعدادی', type: 'bar', data: selected.map((r) => r[metric]), barMaxWidth: 18,
        itemStyle: { color: t.series[metric === 'net' ? 0 : 1], borderRadius: [4, 0, 0, 4] }, cursor: 'pointer' }],
    })} /></div>
}

function Share({ rows, metric, onClick }) {
  const selected = rows.filter((r) => r[metric] > 0)
  if (!selected.length) return <Empty />
  return <Chart height={300} onClick={(p) => onClick(selected[p.dataIndex])} option={(t) => ({
    legend: { orient: 'vertical', right: 0, top: 'middle', type: 'scroll', textStyle: { color: t.text } },
    tooltip: { ...baseOption(t).tooltip, trigger: 'item', formatter: (p) => `${escape(p.name)}<br/>${metric === 'pcs' ? `${fmtInt(p.value)} عدد` : usd(p.value)} · ${fmtPct(p.percent/100)}` },
    series: [{ type: 'pie', radius: ['42%', '72%'], center: ['38%', '50%'], label: { color: t.text, formatter: (p) => p.percent >= 4 ? fmtPct(p.percent/100) : '' },
      data: selected.map((r) => ({ name: r.label || r.key, value: r[metric], itemStyle: { color: brandColor(r.key, t) } })) }],
  })} />
}

export default function ExportPreview() {
  const [sp, setSp] = useSearchParams()
  const [file, setFile] = useState(null)
  const [qualityBy, setQualityBy] = useState('categories')
  const [compareBy, setCompareBy] = useState('countries')
  const sheet = sp.get('section') === 'customers' ? 'countries' : SECTIONS.some((s) => s.value === sp.get('section')) ? sp.get('section') : 'overview'
  const query = new URLSearchParams()
  for (const key of ['date_from', 'date_to', 'year', 'compare_year', ...SLICERS.map(([key]) => key)]) sp.getAll(key).forEach((v) => query.append(key, v))
  const queryText = query.toString()
  const { data, loading, error } = useRkFetch(`/api/rk_export/workspace${queryText ? `?${queryText}` : ''}`)
  const set = (key, values) => {
    const next = new URLSearchParams(sp)
    next.delete(key)
    ;(Array.isArray(values) ? values : [values]).filter(Boolean).forEach((v) => next.append(key, v))
    setSp(next); setFile(null)
  }
  const selectCountry = (country) => {
    const next = new URLSearchParams(sp)
    next.set('section', 'countries')
    next.set('table', country ? 'customers' : 'countries')
    next.delete('country'); next.delete('customer')
    if (country) next.set('country', country)
    setSp(next); setFile(null)
  }
  const metric = (id) => sp.get(`metric_${id}`) === 'pcs' ? 'pcs' : 'net'
  const metricTabs = (id) => <Tabs value={metric(id)} onChange={(v) => set(`metric_${id}`, v)} tabs={[{ value: 'net', label: 'مبلغ (دلار)' }, { value: 'pcs', label: 'تعداد' }]} />
  const metrics = [
    { key: 'net', label: 'فروش خالص (دلار)', type: 'num1', render: (r) => usd(r.net) },
    { key: 'gross', label: 'ناخالص (دلار)', type: 'num1', render: (r) => usd(r.gross) },
    { key: 'pcs', label: 'تعداد', type: 'int' }, { key: 'net_ly', label: 'خالص سال مقایسه (دلار)', type: 'num1', render: (r) => usd(r.net_ly) },
    { key: 'pcs_ly', label: 'تعداد سال مقایسه', type: 'int' }, { key: 'growth', label: 'رشد دلاری', type: 'pct' }, { key: 'qty_growth', label: 'رشد تعدادی', type: 'pct' },
    { key: 'share', label: 'سهم دلاری', type: 'pct' }, { key: 'req', label: 'ناخالص درخواست (دلار)', type: 'num1' }, { key: 'req_pcs', label: 'تعداد درخواست', type: 'int' },
    { key: 'invoices', label: 'فاکتور دارای مبلغ', type: 'int' },
  ]
  const topMetric = metric('top80')
  const ranked = (data?.customers || []).filter((r) => r[topMetric] > 0).sort((a, b) => b[topMetric] - a[topMetric])
  let cumulative = 0
  const target = ranked.reduce((sum, r) => sum+r[topMetric], 0)*.8
  const top80 = ranked.filter((r) => { if (cumulative >= target) return false; cumulative += r[topMetric]; return true })
  const marketTree = countryCustomerTree(data?.countries || [], data?.customers || [])
  return <>
    <PageHead title="فروش صادراتی" desc="گزارش فروش، مشتریان و کیفیت فروش صادرات" />
    <Tabs value={sheet} onChange={(v) => set('section', v)} tabs={SECTIONS} />
    {error ? <ErrorBox error={error} /> : loading && !data ? <Loading /> : !data ? <Empty /> : <>
      <div className="filterbar rk-slicers">
        <SalesDateRange today={data.today} dates={data.sale_days || []}
          from={sp.get('date_from') || `${data.year}/01/01`} to={sp.get('date_to') || data.today}
          onChange={(from, to) => { const next = new URLSearchParams(sp); next.set('date_from', from); next.set('date_to', to); next.delete('month'); next.delete('year'); setSp(next); setFile(null) }} />
        <label className="inline-field"><span>سال مقایسه</span><select value={data.compare_year} onChange={(e) => set('compare_year', e.target.value)}>
          {[...new Set([data.compare_year, ...data.years.filter((year) => year !== data.year)])].map((year) => <option key={year} value={year}>{faDigits(year)}</option>)}
        </select></label>
        {SLICERS.filter(([key]) => key !== 'month').map(([key, label]) => <MultiSelect key={key} label={label} value={sp.getAll(key)} onChange={(values) => set(key, values)}
          options={key === 'month' ? MONTHS.map((label, i) => ({ value: String(i+1).padStart(2, '0'), label }))
            : key === 'customer' ? data.options.customer.map((c) => ({ value: c.code, label: `${c.label} — ${c.code}`, group: c.country }))
            : key === 'product' ? data.options.product.map((p) => ({ value: p.code, label: `${p.code} — ${p.name}`, group: p.cat }))
            : data.options[key].map((v) => ({ value: v, label: v }))} />)}
        <button className="btn ghost sm" onClick={() => { setSp({ section: sheet }); setFile(null) }}>حذف فیلترها</button>
      </div>
      {loading && <p role="status" className="muted small">در حال به‌روزرسانی گزارش…</p>}
      <p className="muted small">مبالغ به دلار؛ گروه‌ها مشترک با هیبرید. مقایسه با {faDigits(data.compare_year)} و همان ماه‌های انتخاب‌شده است{data.current ? '، تا همان روز سال' : '، تا پایان سال'}. هر کد مشتری یک حساب است. درخواست تأییدشده/بسته‌شده، معادل سفارش باز یا درصد قطعی تکمیل سفارش نیست.</p>
      {sheet === 'overview' && <>
        <div className="kpis">
          <Kpi label="فروش خالص (دلار)" value={data.kpis.net} type="num1" sub={`رشد ${fmtPct(data.kpis.net_growth)}`} />
          <Kpi label="فروش ناخالص (دلار)" value={data.kpis.gross} type="num1" />
          <Kpi label="فروش تعدادی" value={data.kpis.pcs} type="int" sub={`از این تعداد ${fmtInt(data.kpis.zero_amount_qty)} قلم بدون مبلغ؛ لزوماً هدیه نیست`} />
          <Kpi label="درخواست ناخالص (دلار)" value={data.kpis.req} type="num1" sub={`${fmtInt(data.kpis.req_pcs)} عدد`} />
          <Kpi label="کد مشتری دارای خرید در دوره" value={data.kpis.customers} type="int" />
          <Kpi label="کشور دارای فروش" value={data.kpis.countries} type="int" />
        </div>
        <div className="grid g2">
          <Card title="فروش کشورها" subtitle={metric('countries') === 'pcs' ? 'تعداد؛ برای فیلتر کلیک کنید' : 'دلار؛ برای فیلتر کلیک کنید'} actions={metricTabs('countries')}><Bars rows={data.countries} metric={metric('countries')} onClick={(r) => set('country', r.key)} /></Card>
          <Card title="سهم برندها از فروش" actions={metricTabs('share')}><Share rows={data.brands} metric={metric('share')} onClick={(r) => set('brand', r.key)} /></Card>
          <Card title="مشتریان سازنده ۸۰٪ فروش" subtitle={`${fmtInt(top80.length)} کد از ${fmtInt(ranked.length)} کد خریدار؛ برای پرونده کلیک کنید`} actions={metricTabs('top80')}><Bars rows={top80} metric={topMetric} onClick={(r) => setFile(r.key)} /></Card>
          <Card title="روند ماهانه" subtitle={`${faDigits(data.year)} و ${faDigits(data.compare_year)}`} actions={metricTabs('monthly')}><YearsChart rows={data.trend} metric={metric('monthly')} year={data.year} ly={data.compare_year} /></Card>
        </div>
      </>}
      {sheet === 'countries' && <div className="grid g2">
        <Card title="فروش مشتریان" className="span2" actions={metricTabs('customer_sales')}
          subtitle={`${metric('customer_sales') === 'pcs' ? 'تعداد اقلام فاکتور' : 'فروش خالص به دلار'}؛ برای پرونده مشتری کلیک کنید`}>
          <CustomerSales rows={data.customers} metric={metric('customer_sales')} onClick={(r) => setFile(r.key)} />
        </Card>
        <Card title="رتبه‌بندی کشورها" subtitle="روی کشور کلیک کنید تا مشتریان همان کشور در جدول پایین نمایش داده شوند" actions={metricTabs('country_rank')} className="span2">
          <Bars rows={data.countries} metric={metric('country_rank')} onClick={(r) => selectCountry(r.key)} />
        </Card>
        <Card title="جدول عملکرد کشورها و مشتریان" className="span2"
          subtitle="روی کشور کلیک کنید تا مشتریانش زیر همان ردیف باز یا بسته شوند؛ برای پرونده روی مشتری کلیک کنید. جستجو با نام کشور، مشتری یا کد مشتری"
          actions={(sp.getAll('country').length > 0 || sp.getAll('customer').length > 0) && <button className="btn ghost sm" onClick={() => selectCountry(null)}>همه کشورها</button>}>
          <TreeTable nodes={marketTree.nodes} total={marketTree.total} sortKey="net" firstLabel="کشور / مشتری" levelNames={['کشور', 'مشتری']}
            defaultDepth={sp.getAll('country').length ? 1 : 0} toggleParentsOnRowClick colorGroups
            columns={[{ key: 'label' }, { key: 'code', label: 'کد مشتری' },
              ...metrics.map((c) => ({ ...c, group: ['net_ly', 'pcs_ly'].includes(c.key) ? `سال مقایسه ${faDigits(data.compare_year)}` : ['growth', 'qty_growth', 'share'].includes(c.key) ? 'مقایسه و سهم' : `سال ${faDigits(data.year)}` })),
              { key: 'status', label: 'وضعیت دوره' }, { key: 'last_date', label: 'آخرین خرید', type: 'date' }]}
            onRowClick={(r) => { if (r.level === 1) setFile(r.key) }} exportName="export-preview-country-customers" />
        </Card>
      </div>}
      {sheet === 'products' && <>
        <ProductMix nodes={data.goods.nodes} total={data.goods.total} currency="usd" />
        <div className="grid g2">
          <Card title="گروه‌های پرفروش" subtitle={metric('categories') === 'pcs' ? 'تعداد' : 'دلار'} actions={metricTabs('categories')}><Bars rows={data.categories} metric={metric('categories')} onClick={(r) => set('cat', r.key)} /></Card>
          <Card title="فروش برندها" subtitle={metric('brands') === 'pcs' ? 'تعداد' : 'دلار'} actions={metricTabs('brands')}><Bars rows={data.brands} metric={metric('brands')} brands onClick={(r) => set('brand', r.key)} /></Card>
          <Card title="برند ← گروه کالا ← کالا" className="span2"><TreeTable nodes={data.goods.nodes} total={data.goods.total} sortKey="net" firstLabel="برند / گروه / کالا" levelNames={['برند', 'گروه', 'کالا']} exportName="export-preview-products"
            columns={[{ key: 'label' }, { key: 'code', label: 'کد کالا' }, { key: 'qty', label: 'تعداد', type: 'int' }, { key: 'net', label: 'خالص (دلار)', type: 'num1' }, { key: 'ly_net', label: 'خالص سال مقایسه (دلار)', type: 'num1' }, { key: 'net_growth', label: 'رشد دلاری', type: 'pct' }]} /></Card>
        </div>
        <Card title="گزارش تفصیلی مشتری ← گروه ← کالا"><SkuTree rows={data.sku} onCustomer={setFile} searchable /></Card>
      </>}
      {sheet === 'quality' && <>
        <div className="kpis"><Kpi label="تخفیف" type="pct" value={data.quality.kpis.disc_rate} sub={usd(data.quality.kpis.discount)} /></div>
        <Card title="تخفیف" subtitle="مجموع همه تخفیف‌ها نسبت به فروش ناخالص کالاهای تجاری؛ استند، تستر و اقلام تبلیغاتی حذف شده‌اند. مالیات از تخفیف جداست."
          actions={<Tabs value={qualityBy} onChange={setQualityBy} tabs={[{value:'categories',label:'گروه کالا'},{value:'brands',label:'برند'},{value:'countries',label:'کشور'},{value:'customers',label:'مشتری'}]} />}>
          <Discounts rows={data.quality[qualityBy]} />
        </Card>
      </>}
      {sheet === 'comparison' && <div className="grid g2">
        <Card title="روند ماهانه" className="span2" actions={metricTabs('trend')}><YearsChart rows={data.trend} metric={metric('trend')} year={data.year} ly={data.compare_year} /></Card>
        <Card title="روند انباشته" className="span2" actions={metricTabs('cumulative')}><YearsChart rows={data.trend} metric={metric('cumulative')} cum year={data.year} ly={data.compare_year} /></Card>
        <Card title="مقایسه عملکرد با سال انتخاب‌شده" className="span2" actions={<Tabs value={compareBy} onChange={setCompareBy} tabs={[{value:'countries',label:'کشورها'},{value:'customers',label:'مشتریان'},{value:'brands',label:'برندها'},{value:'categories',label:'گروه‌ها'}]} />}>
          <DataTable rows={data[compareBy]} columns={[{ key: 'label', label: 'عنوان' }, ...metrics]} exportName={`export-preview-comparison-${compareBy}`} />
        </Card>
      </div>}
      {file && <CustomerFile key={`${file}|${queryText}`} code={file} query={queryText} onClose={() => setFile(null)} />}
    </>}
  </>
}

function Discounts({ rows }) {
  const ranked = rows.filter((r) => r.gross > 0).map((r) => ({ ...r, total: r.disc_rate }))
    .sort((a,b) => b.total-a.total).slice(0,15).reverse()
  if (!ranked.length) return <Empty />
  return <Chart height={Math.max(280,ranked.length*34+80)} option={(t) => ({
    grid: { left: 24, right: 16, top: 40, bottom: 24, containLabel: true },
    tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps) => { const row=ranked[ps[0].dataIndex]; return `${escape(row.label)}<br/>تخفیف: ${fmtPct(row.disc_rate)} — ${usd(row.discount)}` } },
    xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtPct(v) }, splitLine:{lineStyle:{color:t.grid}} },
    yAxis: { type:'category',position:'right',data:ranked.map((r)=>r.label),axisLabel:{color:t.text,width:200,overflow:'truncate'} },
    series: [{name:'تخفیف',type:'bar',data:ranked.map((r)=>r.disc_rate),itemStyle:{color:t.series[0]},
      label:{show:true,position:'left',color:t.text,formatter:(p)=>fmtPct(ranked[p.dataIndex].total)}}],
  })} />
}
