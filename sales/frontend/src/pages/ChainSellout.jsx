import { useState } from 'react'
import { useFetch, useApp, fmtInt, fmtPct, fmtCompact, faDigits } from '../lib.jsx'
import { Card, Kpi, Loading, ErrorBox, DataTable, Tabs, Empty } from '../components/ui.jsx'
import { Chart, CompareBars, HBar, baseOption } from '../components/Chart.jsx'
import { brandColor } from '../brands.js'
import { C } from '../cols.js'

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const monthName = (m) => (m ? `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}` : '—')
const compact = (v) => (v == null ? '—' : `${fmtCompact(v).value} ${fmtCompact(v).unit}`)

// دو مفهوم اصلی با زبان ساده:
//   فروش فروشگاه به مشتری = آنچه فروشگاه زنجیره‌ای به مصرف‌کننده فروخته (از فایل اکسل زنجیره)
//   فروش ما به فروشگاه   = آنچه ما به همان زنجیره فروخته‌ایم (فاکتور منهای برگشتی در کارآمد)
const OUT = 'فروش فروشگاه به مشتری'
const IN = 'فروش ما به فروشگاه'
const SO = {
  value: { key: 'value', label: `${OUT} (مبلغ)`, type: 'money', hint: 'مبلغ فروش فروشگاه به مصرف‌کننده طبق فایل زنجیره، با قیمت فروشگاه (پس از برگشتی، بدون ارزش افزوده، قبل از تخفیف سهم تأمین‌کننده)' },
  qty: { key: 'qty', label: `${OUT} (تعداد)`, type: 'int' },
  disc: { key: 'disc', label: 'تخفیف', type: 'money', hint: 'تخفیف گزارش‌شده در فایل زنجیره (هایپر می: سهم تأمین‌کننده؛ مادر دزفول: مبلغ تخفیف)' },
  sellin_net: { key: 'sellin_net', label: `${IN} (مبلغ)`, type: 'money', hint: 'فاکتورهای فروش ما به این زنجیره در همان ماه منهای برگشتی‌ها، با قیمت فروش ما (کارآمد، بدون ارزش افزوده)' },
  sellin_qty: { key: 'sellin_qty', label: `${IN} (تعداد)`, type: 'int' },
  st: { key: 'sell_through', label: 'فروش فروشگاه ÷ خرید از ما', type: 'pct', hint: 'تعداد فروش فروشگاه به مشتری ÷ تعداد فروش ما به فروشگاه در همان ماه. بیش از ۱۰۰٪: فروشگاه بیشتر از خریدش فروخته (از موجودی قبلی)؛ کمتر از ۱۰۰٪: بخشی از خرید هنوز در قفسه/انبار فروشگاه مانده' },
  avg: { key: 'avg_price', label: 'قیمت میانگین در فروشگاه', type: 'money', hint: 'مبلغ فروش فروشگاه ÷ تعداد' },
  sku: { key: 'sku', label: 'تنوع کالا', type: 'int' },
}

const METRIC_TABS = [{ value: 'value', label: 'مبلغ' }, { value: 'qty', label: 'تعداد' }]

/** فروش فروشگاه‌های زنجیره‌ای به مشتری (از فایل‌های ماهانه زنجیره‌ها)، در کنار فروش ما به همان فروشگاه‌ها */
export function ChainSelloutSection() {
  const [month, setMonth] = useState('')
  const [chain, setChain] = useState('')
  const q = new URLSearchParams({ ...(month && { month }), ...(chain && { chain }) }).toString()
  const { data, loading, error } = useFetch(`/api/chain_sellout${q ? `?${q}` : ''}`)
  const { unit } = useApp()
  const [dim, setDim] = useState('brands')
  const [metric, setMetric] = useState('value')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data.month) {
    return (
      <Card title={`${OUT} در فروشگاه‌های زنجیره‌ای`}>
        <Empty text={`هنوز فایلی خوانده نشده است. فایل‌های اکسل ماهانه زنجیره‌ها را در پوشه ${data.folder} بگذارید.`} />
        <FilesTable files={data.files} />
      </Card>
    )
  }
  const k = data.kpis
  const all = data.month === 'all'
  const period = all ? `همه ماه‌ها (${data.months.map(monthName).join('، ')})` : monthName(data.month)
  const multi = data.months.length > 1
  const chains = data.chains
  // شعب فروشگاه فقط برای زنجیره‌ای که فروش هر شعبه را می‌دهد (فعلاً فقط هایپر می) و فقط وقتی همان زنجیره انتخاب شده
  const hasStores = !!chain && data.stores.length > 0
  const prodCols = [C.label('کالا'), C.text('brand', 'برند'), C.text('category', 'گروه کالا'), C.text('barcode', 'بارکد'),
    SO.qty, SO.value, SO.avg, SO.sellin_qty, SO.st, SO.sellin_net,
    ...(!chain ? chains.map((c) => ({ key: `q:${c}`, label: `تعداد ${c}`, type: 'int' })) : []),
    ...(hasStores ? [{ key: 'stores', label: 'تعداد شعب با فروش', type: 'int' }] : [])]
  const prodRows = data.products.map((r) => {
    const o = { ...r }
    for (const c of chains) o[`q:${c}`] = r.by_chain?.[c] ?? null
    return o
  })
  const chainCols = [C.label('زنجیره'), SO.value, C.share, SO.qty, SO.sellin_net, SO.sellin_qty, SO.st, SO.sku, SO.disc]
  const dimRows = data[dim]
  const dimLabel = { brands: 'برند', categories: 'گروه کالا' }[dim]
  const dimCols = [C.label(dimLabel), SO.qty, SO.value, C.share, SO.sellin_qty, SO.sellin_net, SO.st]
  return (
    <>
      <div className="chain-bar">
        <label className="inline-field"><span>ماه</span>
          <select value={data.month} onChange={(e) => setMonth(e.target.value)}>
            {[...data.months].reverse().map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
            {multi && <option value="all">همه ماه‌ها</option>}
          </select>
        </label>
        <Tabs value={chain} onChange={setChain}
          tabs={[{ value: '', label: 'همه زنجیره‌ها' }, ...chains.map((c) => ({ value: c, label: c }))]} />
      </div>
      <div className="kpis">
        <Kpi label={OUT} value={k.value} hint={SO.value.hint}
          sub={`${period} · ${chain || `${fmtInt(k.chains)} زنجیره`}`} />
        <Kpi label={`${OUT} (تعداد)`} value={k.qty} type="int" sub={`${fmtInt(k.sku)} کالا${k.unmatched ? ` (${fmtInt(k.unmatched)} بدون تطبیق بارکد)` : ''}`} />
        <Kpi label={IN} value={k.sellin_net} hint={SO.sellin_net.hint}
          sub={`${fmtInt(k.sellin_qty)} عدد، همان زنجیره‌ها و همان ماه`} />
        <Kpi label="فروش فروشگاه ÷ خرید از ما" value={k.sell_through} type="pct" hint={SO.st.hint}
          sub={k.sell_through == null ? '' : k.sell_through >= 1 ? 'فروشگاه بیشتر از خریدش فروخته' : 'بخشی از خرید هنوز در فروشگاه مانده'} />
        {hasStores && <Kpi label="شعب فروشگاه با فروش" value={k.stores} type="int" sub={`شعب ${chain}`} />}
        {k.disc > 0 && <Kpi label="تخفیف گزارش‌شده زنجیره" value={k.disc} hint={SO.disc.hint} sub={`${fmtPct(k.value ? k.disc / k.value : null)} از فروش فروشگاه`} />}
      </div>
      {data.missing?.length > 0 && (
        <div className="info muted small" style={{ marginBottom: 12 }}>
          زنجیره‌هایی که این ماه از ما خرید داشته‌اند ولی فایل فروش فروشگاه نفرستاده‌اند:{' '}
          {data.missing.map((m) => `${m.chain} (خرید از ما ${compact(m.sellin_net)})`).join('، ')}
        </div>
      )}
      <div className="grid g2">
        {!chain && (
          <Card title={`${OUT} در برابر ${IN}، به تفکیک زنجیره`} className="span2"
            subtitle="فروش فروشگاه با قیمت فروشگاه است و فروش ما با قیمت فروش ما؛ برای مقایسه حجم، ستون «فروش فروشگاه ÷ خرید از ما» (تعدادی) را ببینید. روی هر زنجیره کلیک کنید">
            <CompareBars rows={data.by_chain} unit={unit} onClick={(r) => setChain(r.key)}
              series={[{ key: 'value', name: OUT, color: 0 }, { key: 'sellin_net', name: IN, color: 1 }]} />
          </Card>
        )}
        {hasStores && <StoreAnalysis data={data} chain={chain} unit={unit} />}
        <Card title="روند ماهانه" className="span2"
          subtitle={multi ? `${OUT} (میله) و ${IN} (خط) در هر ماه` : 'با اضافه شدن فایل ماه‌های بعد، روند ماهانه اینجا نمایش داده می‌شود'}>
          <MonthlyTrend rows={data.trend} unit={unit} />
        </Card>
        <Card title={`${OUT} به تفکیک ${dimLabel}`} className="span2"
          actions={<div className="head-actions">
            <Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />
            <Tabs value={dim} onChange={setDim} tabs={[{ value: 'brands', label: 'برند' }, { value: 'categories', label: 'گروه کالا' }]} />
          </div>}
          subtitle={`نمودار بر اساس ${metric === 'qty' ? 'تعداد' : 'مبلغ'}؛ گروه کالا از کارآمد با تطبیق بارکد، کالای بدون تطبیق جدا آمده است`}>
          <div className="grid g2 inner">
            <HBar rows={[...dimRows].filter((r) => r[metric] > 0).sort((a, b) => b[metric] - a[metric]).slice(0, 15)}
              value={metric} valueType={metric === 'qty' ? 'int' : 'money'} unit={unit}
              colorOf={dim === 'brands' ? (r, t) => brandColor(r.label, t) : undefined} />
            <DataTable rows={dimRows} columns={dimCols} unit={unit} pageSize={10} dense exportName={`chain-${dim}`} />
          </div>
        </Card>
        {!chain && (
          <Card title="جدول زنجیره‌ها" className="span2">
            <DataTable rows={data.by_chain} columns={chainCols} unit={unit} search={false} exportName="chain-summary"
              onRowClick={(r) => setChain(r.key)} />
          </Card>
        )}
        <Card title={`کالاها: ${OUT} و ${IN}`} className="span2"
          subtitle="کالاهایی که زنجیره از ما خریده ولی در فایل فروش فروشگاه نیامده‌اند، با فروش فروشگاه صفر آمده‌اند">
          <DataTable rows={prodRows} columns={prodCols} unit={unit} pageSize={15} dense exportName={`chain-products-${data.month}`} />
        </Card>
        <Card title="فایل‌های دریافتی" className="span2"
          subtitle={`پوشه: ${data.folder} — هر ماه فایل‌های جدید را در همین پوشه بگذارید؛ داده هر ماه در بایگانی ذخیره می‌شود و با حذف یا جایگزینی فایل‌ها از بین نمی‌رود`}>
          <FilesTable files={data.files} />
        </Card>
      </div>
    </>
  )
}

/** تحلیل شعبه‌ای زنجیره‌هایی که فروش هر شعبه را می‌دهند (هایپر می) */
function StoreAnalysis({ data, chain, unit }) {
  const [metric, setMetric] = useState('value')
  const [sel, setSel] = useState(null)
  const stores = data.stores
  const brands = data.brands.filter((b) => stores.some((s) => s.brand_qty?.[b.label])).map((b) => b.label)
  const rows = stores.map((s) => {
    const o = { ...s }
    for (const b of brands) o[`b:${b}`] = s.brand_qty?.[b] ?? null
    return o
  })
  const total = stores.reduce((a, s) => a + (s.value || 0), 0)
  const top5 = [...stores].sort((a, b) => b.value - a.value).slice(0, 5).reduce((a, s) => a + s.value, 0)
  const avg = stores.length ? total / stores.length : 0
  const cols = [C.label('شعبه'), SO.value, C.share, SO.qty, SO.sku, SO.avg,
    ...brands.map((b) => ({ key: `b:${b}`, label: `تعداد ${b}`, type: 'int' }))]
  const selRow = stores.find((s) => s.key === sel)
  const prods = selRow ? data.store_products.filter((p) => p.store === selRow.label) : []
  const prodCols = [C.label('کالا'), C.text('brand', 'برند'), C.text('category', 'گروه کالا'), SO.qty, SO.value]
  return (
    <>
      <Card title={`فروش شعب ${chain} به مشتری`} className="span2"
        subtitle={`${fmtInt(stores.length)} شعبه با فروش · میانگین هر شعبه ${compact(avg)} · ۵ شعبه اول ${fmtPct(total ? top5 / total : null)} از فروش · روی هر شعبه کلیک کنید تا کالاهایش را ببینید`}
        actions={<Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />}>
        <div className="grid g2 inner">
          <HBar rows={[...stores].sort((a, b) => b[metric] - a[metric])} value={metric}
            valueType={metric === 'qty' ? 'int' : 'money'} unit={unit} onClick={(r) => setSel(r.key)} />
          <DataTable rows={rows} columns={cols} unit={unit} pageSize={12} dense exportName={`stores-${chain}`}
            onRowClick={(r) => setSel(r.key)} />
        </div>
      </Card>
      {selRow && (
        <Card title={`کالاهای ${selRow.label.startsWith('شعبه') ? '' : 'شعبه '}${selRow.label}`} className="span2"
          subtitle={`${compact(selRow.value)} · ${fmtInt(selRow.qty)} عدد · ${fmtInt(prods.length)} کالا`}
          actions={<button className="btn ghost" onClick={() => setSel(null)}>بستن</button>}>
          <div className="grid g2 inner">
            <BrandSplit store={selRow} unit={unit} />
            <DataTable rows={prods} columns={prodCols} unit={unit} pageSize={10} dense exportName={`store-${selRow.label}`} />
          </div>
        </Card>
      )}
    </>
  )
}

function BrandSplit({ store, unit }) {
  const rows = Object.entries(store.brand_value || {}).map(([b, v]) => ({ key: b, label: b, value: v, qty: store.brand_qty?.[b] }))
    .sort((a, b) => b.value - a.value)
  return <HBar rows={rows} value="value" unit={unit} colorOf={(r, t) => brandColor(r.label, t)} />
}

function FilesTable({ files }) {
  const cols = [C.text('file', 'فایل'), C.text('chain', 'زنجیره'), { key: 'month', label: 'ماه', render: (r) => monthName(r.month), csv: (r) => r.month },
    C.text('month_from', 'تشخیص ماه از'), { key: 'rows', label: 'سطر', type: 'int' }, { key: 'qty', label: 'تعداد', type: 'int' },
    { key: 'status', label: 'وضعیت', render: (r) => (r.ok ? 'خوانده شد' : <span className="neg">{r.error}</span>), csv: (r) => (r.ok ? 'خوانده شد' : r.error) }]
  return <DataTable rows={files} columns={cols} unit="million" search={false} pageSize={20} dense />
}

function MonthlyTrend({ rows, unit }) {
  if (!rows.length) return <Empty />
  const months = [...new Set(rows.map((r) => r.month))].sort()
  const chains = [...new Set(rows.map((r) => r.chain))]
  const sum = (m, key) => rows.filter((r) => r.month === m).reduce((s, r) => s + (r[key] || 0), 0)
  return (
    <Chart height={280} option={(t) => ({
      grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: t.text } },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis',
        valueFormatter: (v) => `${compact(v)}` },
      xAxis: { type: 'category', inverse: true, data: months.map(monthName), axisLabel: { color: t.text },
        axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
      yAxis: { type: 'value', position: 'right', splitLine: { lineStyle: { color: t.grid } },
        axisLabel: { color: t.text, formatter: (v) => fmtCompact(v).value } },
      series: [
        ...chains.map((c, i) => ({ name: c, type: 'bar', stack: 'so', barMaxWidth: 36, itemStyle: { color: t.series[i % t.series.length] },
          data: months.map((m) => rows.find((r) => r.month === m && r.chain === c)?.value ?? 0) })),
        { name: IN, type: 'line', symbolSize: 8, lineStyle: { width: 2, type: 'dashed' },
          itemStyle: { color: t.textStrong }, data: months.map((m) => sum(m, 'sellin_net')) },
      ],
    })} />
  )
}

/** فیلتر شعبه فقط شعبه(های) زنجیره‌ای است */
export const isChainOnly = (branches) => branches?.length > 0 && branches.every((b) => String(b).includes('زنجیره'))

/** بخش کشویی «فروش فروشگاه‌های زنجیره‌ای به مشتری»: صفحه مثل بقیه شعب می‌ماند و جزئیات زنجیره‌ها با کلیک باز می‌شود */
export function ChainSelloutBlock() {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem('sd.chainOpen') === '1' } catch { return false }
  })
  const toggle = () => {
    setOpen((o) => {
      try { localStorage.setItem('sd.chainOpen', o ? '0' : '1') } catch { /* ignore */ }
      return !o
    })
  }
  return (
    <section className={`chain-sellout card${open ? ' open' : ''}`}>
      <button className="chain-toggle" onClick={toggle} aria-expanded={open}>
        <span className="chain-caret" aria-hidden>{open ? '▾' : '◂'}</span>
        <span>
          <b>جزئیات فروشگاه‌های زنجیره‌ای: {OUT} و {IN}</b>
          <span className="muted small"> — از فایل‌های اکسل ماهانه زنجیره‌ها؛ {open ? 'برای بستن کلیک کنید' : 'برای باز کردن کلیک کنید'}</span>
        </span>
      </button>
      {open && (
        <div className="chain-body">
          <p className="muted small">فیلتر تاریخ و بقیه فیلترهای سراسری روی این بخش اثر ندارند؛ ماه و زنجیره را همین‌جا انتخاب کنید.</p>
          <ChainSelloutSection />
        </div>
      )}
    </section>
  )
}
