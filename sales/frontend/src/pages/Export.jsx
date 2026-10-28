import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useRkFetch, fmtInt, fmtPct, faDigits, isNum, fmtExact } from '../lib.jsx'
import { Kpi, Card, Loading, ErrorBox, Empty, DataTable, Tabs, MultiSelect } from '../components/ui.jsx'
import { Chart, HBar, baseOption } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { brandColor } from '../brands.js'

// فروش صادراتی از راهکاران؛ معادل شیت‌های فایل Export SalesReport (مبالغ به دلار)
const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const SHEETS = [
  { value: 'dashboard', label: 'داشبورد' }, { value: 'customer', label: 'مشتری' },
  { value: 'sku', label: 'کالا و گروه (SKU)' }, { value: 'country', label: 'کشور' }, { value: 'trend', label: 'روند YTD' },
]
const SLICERS = [['month', 'ماه'], ['brand', 'برند'], ['cat', 'گروه کالا'], ['country', 'کشور'], ['customer', 'مشتری'], ['product', 'کالا']]
const METRIC_TABS = [{ value: 'net', label: 'دلار خالص' }, { value: 'gross', label: 'دلار ناخالص' }, { value: 'pcs', label: 'تعداد' },
  { value: 'req', label: 'درخواست $' }, { value: 'req_pcs', label: 'درخواست تعداد' }]
const usd = (v) => (isNum(v) ? `${fmtInt(v)} $` : '—')
const growth = (g, what = '') => (isNum(g) ? `${g >= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(g))} نسبت به همین بازه سال قبل${what}` : 'بدون فروش در همین بازه سال قبل')

/** میله افقی دلاری یا تعدادی؛ rows با key */
function Bars({ rows, value, onClick, colorOf, colorIndex }) {
  const data = rows.filter((r) => r[value] > 0).map((r) => ({ ...r, label: r.label || r.key }))
  if (!data.length) return <Empty />
  return <HBar rows={data} value={value} valueType="int" onClick={onClick} colorOf={colorOf} colorIndex={colorIndex} />
}

/** ماهانه یا انباشته دو سال؛ cum = انباشته (شیت YTD Trend) */
function YearsChart({ rows, metric, cum, year, ly, height = 300 }) {
  const k = (cum ? 'cum_' : '') + metric
  const cur = rows.map((r) => (r.future ? null : r[k]))
  return (
    <Chart height={height}
      option={(t) => ({
        grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
        legend: { top: 0, right: 0, textStyle: { color: t.text } },
        tooltip: { ...baseOption(t).tooltip, trigger: 'axis',
          formatter: (ps) => `${MONTHS[ps[0].dataIndex]}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${p.value == null ? '—' : fmtExact(p.value)}</b>`).join('<br/>') },
        xAxis: { type: 'category', inverse: true, data: MONTHS, axisLabel: { color: t.text }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
        yAxis: { type: 'value', position: 'right', axisLabel: { color: t.text, formatter: (v) => fmtInt(v) }, splitLine: { lineStyle: { color: t.grid } } },
        series: cum ? [
          { name: faDigits(year), type: 'line', data: cur, symbolSize: 6, lineStyle: { width: 3, color: t.series[0] }, itemStyle: { color: t.series[0] } },
          { name: faDigits(ly), type: 'line', data: rows.map((r) => r[k + '_ly']), symbolSize: 5, lineStyle: { width: 2, color: t.axis, type: 'dashed' }, itemStyle: { color: t.axis } },
        ] : [
          { name: faDigits(year), type: 'bar', data: cur, itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
          { name: faDigits(ly), type: 'bar', data: rows.map((r) => r[k + '_ly']), itemStyle: { color: t.axis, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
        ],
      })} />
  )
}

const twoYearCols = (ly, y, first) => [
  first,
  { key: 'pcs_ly', label: `${faDigits(ly)} تعداد`, type: 'int' }, { key: 'net_ly', label: `${faDigits(ly)} دلار`, type: 'int' },
  { key: 'pcs', label: `${faDigits(y)} تعداد`, type: 'int' }, { key: 'net', label: `${faDigits(y)} دلار`, type: 'int' },
  { key: 'share', label: 'سهم دلاری', type: 'pct' },
]

/** پرونده یک کد مشتری (هر برند مشتری کد جدا دارد) */
function CustomerFile({ code, query, onClose }) {
  const ref = useRef(null)
  const [metric, setMetric] = useState('net')
  const { data, loading, error } = useRkFetch(`/api/rk_export/customer?code=${encodeURIComponent(code)}${query ? `&${query}` : ''}`)
  useEffect(() => { ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [code])
  return (
    <section className="rk-detail rk-anchor" ref={ref}>
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <div className="rk-detail-head">
            <div>
              <h2>{data.label} — {data.country}</h2>
              <div className="muted small">
                {data.name} · کد {faDigits(data.code)}
                {data.last_date && <> · آخرین خرید {faDigits(data.last_date)}</>}
              </div>
            </div>
            <button className="btn ghost sm" onClick={onClose}>بستن ✕</button>
          </div>
          <div className="kpis">
            <Kpi label={`فروش دلاری ${faDigits(data.year)}`} value={data.kpis.net} type="int" sub={growth(data.kpis.growth)} />
            <Kpi label={`فروش ناخالص ${faDigits(data.year)}`} value={data.kpis.gross} type="int" />
            <Kpi label={`فروش تعدادی ${faDigits(data.year)}`} value={data.kpis.pcs} type="int" />
            <Kpi label={`درخواست ${faDigits(data.year)}`} value={data.kpis.req} type="int" sub={`${fmtInt(data.kpis.req_pcs)} عدد`}
              hint="ناخالص درخواست‌های فروش تأییدشده و بسته‌شده (دلار)" />
            <Kpi label={`کل سال ${faDigits(data.ly)}`} value={data.kpis.net_ly_full} type="int" sub={`${fmtInt(data.kpis.pcs_ly_full)} عدد`} />
            <Kpi label="فاکتور" value={data.kpis.invoices} type="int" hint="ترکیب (کد مشتری، روز) با مبلغ" />
          </div>
          <div className="grid g2">
            <Card title="روند ماهانه، دو سال" className="span2"
              actions={<Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />}>
              <YearsChart rows={data.monthly} metric={metric} year={data.year} ly={data.ly} />
            </Card>
            <Card title="برندها"><Bars rows={data.brands} value="net" colorOf={(r, t) => brandColor(r.key, t)} /></Card>
            <Card title="گروه کالا"><Bars rows={data.categories} value="net" colorIndex={2} /></Card>
            <Card title="کالاها" className="span2" subtitle={`سال ${faDigits(data.year)}`}>
              <DataTable rows={data.products} pageSize={12} exportName={`export-products-${data.code}`}
                columns={[{ key: 'product_code', label: 'کد کالا' }, { key: 'product', label: 'نام کالا' }, { key: 'brand', label: 'برند' },
                  { key: 'cat2', label: 'گروه' }, { key: 'pcs', label: 'تعداد', type: 'int' }, { key: 'net', label: 'دلار', type: 'int' }]} />
            </Card>
            <Card title="فاکتورها و درخواست‌ها" className="span2" subtitle="مبلغ فاکتور خالص و مبلغ درخواست ناخالص، به دلار">
              <DataTable rows={data.invoices} pageSize={12} exportName={`export-invoices-${data.code}`} defaultSort={{ key: 'date', dir: 'desc' }}
                columns={[{ key: 'kind', label: 'نوع' }, { key: 'inv', label: 'شماره' }, { key: 'date', label: 'تاریخ', type: 'date' }, { key: 'code', label: 'کد مشتری' },
                  { key: 'pcs', label: 'تعداد', type: 'int' }, { key: 'net', label: 'دلار', type: 'int' }, { key: 'lines', label: 'سطر', type: 'int' }]} />
            </Card>
          </div>
        </>
      )}
    </section>
  )
}

/** شیت SKU&Category: مشتری ← گروه کالا ← کالا */
function SkuTree({ rows, onCustomer }) {
  const [open, setOpen] = useState(() => new Set())
  const tree = useMemo(() => {
    const by = new Map()
    for (const r of rows) {
      const c = by.get(r.code) || { key: r.code, label: r.label, net: 0, pcs: 0, cats: new Map() }
      c.net += r.net; c.pcs += r.pcs
      const g = c.cats.get(r.cat2) || { key: r.cat2, net: 0, pcs: 0, items: [] }
      g.net += r.net; g.pcs += r.pcs; g.items.push(r)
      c.cats.set(r.cat2, g); by.set(r.code, c)
    }
    return [...by.values()].sort((a, b) => b.net - a.net || b.pcs - a.pcs)
  }, [rows])
  if (!tree.length) return <Empty />
  const toggle = (id) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const total = tree.reduce((a, c) => [a[0] + c.pcs, a[1] + c.net], [0, 0])
  return (
    <div className="tree-scroll">
      <table className="tree dense rk-xtable">
        <thead><tr><th>مشتری / گروه کالا / کالا</th><th className="num">تعداد (PCS)</th><th className="num">فروش دلاری</th><th /></tr></thead>
        <tbody>
          {tree.map((c) => (
            <Fragment key={c.key}>
              <tr className="rk-brand clickable" onClick={() => toggle(c.key)}>
                <td><span className="tree-toggle">{open.has(c.key) ? '▾' : '◂'}</span>{c.label} <span className="muted small">کد {faDigits(c.key)}</span></td>
                <td className="num">{fmtInt(c.pcs)}</td><td className="num" title={fmtExact(c.net)}>{fmtInt(c.net)}</td>
                <td><button className="btn ghost sm" onClick={(e) => { e.stopPropagation(); onCustomer(c.key) }}>پرونده</button></td>
              </tr>
              {open.has(c.key) && [...c.cats.values()].sort((a, b) => b.net - a.net || b.pcs - a.pcs).map((g) => (
                <Fragment key={g.key}>
                  <tr className="clickable" onClick={() => toggle(`${c.key}|${g.key}`)}>
                    <td style={{ paddingRight: 28 }}><span className="tree-toggle">{open.has(`${c.key}|${g.key}`) ? '▾' : '◂'}</span>{g.key}</td>
                    <td className="num">{fmtInt(g.pcs)}</td><td className="num" title={fmtExact(g.net)}>{fmtInt(g.net)}</td><td />
                  </tr>
                  {open.has(`${c.key}|${g.key}`) && g.items.sort((a, b) => b.net - a.net).map((p) => (
                    <tr key={p.product_code}>
                      <td className="muted" style={{ paddingRight: 52 }} title={p.product_code}>{p.product}</td>
                      <td className="num">{fmtInt(p.pcs)}</td><td className="num" title={fmtExact(p.net)}>{fmtInt(p.net)}</td><td />
                    </tr>
                  ))}
                </Fragment>
              ))}
            </Fragment>
          ))}
          <tr className="rk-total"><td>Grand Total</td><td className="num">{fmtInt(total[0])}</td><td className="num">{fmtInt(total[1])}</td><td /></tr>
        </tbody>
      </table>
    </div>
  )
}

/** شیت Country: کشور ← مشتری با ۱۴۰۴ و ۱۴۰۵ کنار هم */
function CountryTable({ rows, y, ly, onCustomer }) {
  const [closed, setClosed] = useState(() => new Set())
  if (!rows.length) return <Empty />
  const cells = (r) => [r.pcs_ly, r.net_ly, r.pcs, r.net, r.pcs_ly + r.pcs, r.net_ly + r.net]
    .map((v, i) => <td key={i} className={`num${i === 4 ? ' rk-blk' : ''}`} title={v ? fmtExact(v) : undefined}>{v ? fmtInt(v) : <span className="rk-zero">۰</span>}</td>)
  const total = ['pcs_ly', 'net_ly', 'pcs', 'net'].reduce((a, k) => ({ ...a, [k]: rows.reduce((s, r) => s + r[k], 0) }), {})
  return (
    <div className="tree-scroll">
      <table className="tree dense rk-xtable">
        <thead>
          <tr>
            <th rowSpan={2}>کشور / مشتری</th>
            <th colSpan={2} className="grp">{faDigits(ly)}</th><th colSpan={2} className="grp">{faDigits(y)}</th><th colSpan={2} className="grp">جمع</th>
            <th rowSpan={2} className="num">رشد دلاری</th>
          </tr>
          <tr>{['تعداد (Pcs)', 'دلار (Usd)', 'تعداد (Pcs)', 'دلار (Usd)', 'Total Pcs', 'Total Usd'].map((l, i) => <th key={i} className={`num${i === 4 ? ' rk-blk' : ''}`}>{l}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <Fragment key={c.key}>
              <tr className="rk-brand clickable" onClick={() => setClosed((s) => { const n = new Set(s); n.has(c.key) ? n.delete(c.key) : n.add(c.key); return n })}>
                <td><span className="tree-toggle">{closed.has(c.key) ? '◂' : '▾'}</span>{c.key}</td>{cells(c)}<td className="num">{fmtPct(c.growth)}</td>
              </tr>
              {!closed.has(c.key) && c.customers.map((r) => (
                <tr key={r.key} className="clickable" onClick={() => onCustomer(r.key)}>
                  <td style={{ paddingRight: 28 }}>{r.label} <span className="muted small">کد {faDigits(r.key)}</span></td>{cells(r)}<td className="num">{fmtPct(r.growth)}</td>
                </tr>
              ))}
            </Fragment>
          ))}
          <tr className="rk-total"><td>Grand Total</td>{cells(total)}<td className="num">{fmtPct(total.net_ly ? total.net / total.net_ly - 1 : null)}</td></tr>
        </tbody>
      </table>
    </div>
  )
}

export default function Export() {
  const [sp, setSp] = useSearchParams()
  const sheet = sp.get('sheet') || 'dashboard'
  const picked = Object.fromEntries(SLICERS.map(([k]) => [k, sp.getAll(k)]))
  const query = useMemo(() => {
    const p = new URLSearchParams()
    if (sp.get('year')) p.set('year', sp.get('year'))
    for (const [k] of SLICERS) sp.getAll(k).forEach((v) => p.append(k, v))
    return p.toString()
  }, [sp])
  const [file, setFile] = useState(null)
  const [metric, setMetric] = useState('pcs')
  const { data, loading, error } = useRkFetch(`/api/rk_export${query ? `?${query}` : ''}`)
  const set = (k, v) => {
    const n = new URLSearchParams(sp)
    n.delete(k)
    ;(Array.isArray(v) ? v : [v]).filter(Boolean).forEach((x) => n.append(k, x))
    setSp(n)
  }
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const { kpis: k, year: y, ly } = data
  // سال جاری: تا امروز؛ سال‌های گذشته: کل سال
  const span = data.current ? '' : ' (کل سال)'
  const g = (v) => (data.current ? growth(v) : isNum(v) ? `${v >= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(v))} نسبت به کل ${faDigits(ly)}` : `بدون فروش در ${faDigits(ly)}`)
  const options = {
    month: MONTHS.map((m, i) => ({ value: String(i + 1).padStart(2, '0'), label: m })),
    ...Object.fromEntries(['brand', 'cat', 'country'].map((key) => [key, data.options[key].map((v) => ({ value: v, label: v }))])),
    customer: data.options.customer.map((c) => ({ value: c.code, label: `${c.label} — ${c.code}`, group: c.country })),
    product: data.options.product.map((p) => ({ value: p.code, label: `${p.code} — ${p.name}`, group: p.cat })),
  }
  const active = SLICERS.some(([key]) => picked[key].length)
  const open = (name) => setFile(name)
  return (
    <>
      <PageHead title="فروش صادراتی" desc={`فروش و درخواست صادراتی به ${fmtInt(data.options.customer.length)} کد مشتری در ${fmtInt(data.options.country.length)} کشور، به دلار، از ${faDigits(data.years.at(-1))}، لایو از راهکاران؛ معادل فایل Export SalesReport`}>
        <span className={`rk-live ${data.live ? 'on' : ''}`} title={`خوانده‌شده: ${data.fetched}`}>
          {data.live ? 'لایو' : `بروزرسانی ${faDigits((data.fetched || '').slice(11, 16))}`}
        </span>
      </PageHead>
      <div className="filterbar rk-slicers">
        <label className="inline-field">
          <span>سال</span>
          <select value={y} onChange={(e) => set('year', e.target.value === data.years[0] ? null : e.target.value)}>
            {data.years.map((v) => <option key={v} value={v}>{faDigits(v)}</option>)}
          </select>
        </label>
        {SLICERS.map(([key, label]) => <MultiSelect key={key} label={label} value={picked[key]} onChange={(v) => set(key, v)} options={options[key]} />)}
        {active && <button className="btn ghost" onClick={() => setSp(Object.fromEntries([['sheet', sheet], ['year', sp.get('year')]].filter(([key, v]) => v && v !== 'dashboard')))}>حذف فیلترها</button>}
      </div>
      <div className="kpis">
        <Kpi label={`فروش دلاری (NetSales $) ${faDigits(y)}${span}`} value={k.net} type="int" sub={g(k.growth)}
          hint="مبلغ خالص اقلام فاکتورهای صادراتی (دلار)، از ابتدای سال؛ مقایسه با همان بازه سال قبل. تا ۱۴۰۳ فاکتورهای ریالی با نرخ دلار همان ماه به دلار تبدیل شده‌اند" />
        <Kpi label={`فروش ناخالص (GrossSales $) ${faDigits(y)}${span}`} value={k.gross} type="int"
          sub={<>{g(k.growth_gross)}{isNum(k.disc_rate) && <><br />کسورات {fmtPct(k.disc_rate)} از ناخالص</>}</>}
          hint="مبلغ اقلام فاکتور پیش از کسور و اضافات (دلار)" />
        <Kpi label={`فروش تعدادی (NetSales PCS) ${faDigits(y)}${span}`} value={k.pcs} type="int" sub={g(k.growth_pcs)}
          hint="همه اقلام فاکتور، از جمله نمونه و هدیه بدون مبلغ" />
        <Kpi label={`درخواست فروش ${faDigits(y)}${span}`} value={k.req} type="int"
          sub={<>{g(k.growth_req)}<br />{fmtInt(k.req_pcs)} عدد{isNum(k.fill) && ` · ${fmtPct(k.fill)} آن فاکتور شده (تعدادی)`}</>}
          hint="مبلغ ناخالص درخواست‌های فروش صادراتی «تأییدشده» و «بسته‌شده» (دلار)" />
        <Kpi label={`کل سال ${faDigits(ly)}`} value={k.net_ly_full} type="int" sub={`${fmtInt(k.pcs_ly_full)} عدد`} />
        <Kpi label="مشتری فعال" value={k.customers} type="int"
          hint="تعداد مشتری = تعداد کد مشتری یکتا (هر برند یک مشتری کد جدا دارد). فعال = کدی که از ابتدای سال جاری خرید داشته"
          sub={`از ${fmtInt(k.customers_total)} کد مشتری · ${fmtInt(k.customers_inactive)} بدون خرید از ابتدای سال · ${fmtInt(k.countries)} کشور`} />
        <Kpi label="فاکتور" value={k.invoices} type="int" hint="ترکیب (کد مشتری، روز) با مبلغ" sub={`میانگین ${usd(k.avg_invoice)}`} />
      </div>
      <div className="rk-sheet-tabs"><Tabs value={sheet} onChange={(v) => set('sheet', v === 'dashboard' ? null : v)} tabs={SHEETS} /></div>
      {sheet === 'dashboard' && (
        <div className="grid g2">
          <Card title="فروش دلاری برندها" subtitle="برای فیلتر برند روی آن کلیک کنید">
            <Bars rows={data.brands} value="net" colorOf={(r, t) => brandColor(r.key, t)} onClick={(r) => set('brand', [r.key])} />
          </Card>
          <Card title="روند ماهانه" subtitle={`${faDigits(y)} در برابر ${faDigits(ly)}`}
            actions={<Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />}>
            <YearsChart rows={data.trend} metric={metric} year={y} ly={ly} />
          </Card>
          <Card title="گروه کالا — فروش دلاری" subtitle="Category (Cate1)؛ برای فیلتر کلیک کنید">
            <Bars rows={data.categories} value="net" colorIndex={2} onClick={(r) => set('cat', [r.key])} />
          </Card>
          <Card title="گروه کالا — فروش تعدادی" subtitle="Net Sales PCS">
            <Bars rows={[...data.categories].sort((a, b) => b.pcs - a.pcs)} value="pcs" colorIndex={3} onClick={(r) => set('cat', [r.key])} />
          </Card>
        </div>
      )}
      {sheet === 'customer' && (
        <div className="grid g2">
          <Card title="فروش دلاری مشتریان (NETSALES USD)" subtitle="برای پرونده مشتری کلیک کنید">
            <Bars rows={data.customers} value="net" onClick={(r) => open(r.key)} />
          </Card>
          <Card title="فروش تعدادی مشتریان (مقدار قلم فاکتور)">
            <Bars rows={[...data.customers].sort((a, b) => b.pcs - a.pcs)} value="pcs" colorIndex={1} onClick={(r) => open(r.key)} />
          </Card>
          <Card title="جدول مشتریان" className="span2">
            <DataTable rows={data.customers} pageSize={20} exportName="export-customers" onRowClick={(r) => open(r.key)}
              columns={[{ key: 'key', label: 'کد مشتری' }, { key: 'label', label: 'مشتری' }, { key: 'country', label: 'کشور' }, { key: 'name', label: 'نام حساب' },
                ...twoYearCols(ly, y).slice(1), { key: 'gross', label: `${faDigits(y)} ناخالص`, type: 'int' },
                { key: 'req', label: `${faDigits(y)} درخواست $`, type: 'int' }, { key: 'req_pcs', label: `${faDigits(y)} درخواست تعداد`, type: 'int' },
                { key: 'growth', label: 'رشد دلاری', type: 'pct' }]} />
          </Card>
        </div>
      )}
      {sheet === 'sku' && (
        <Card title={`مشتری ← گروه کالا ← کالا (${faDigits(y)})`} subtitle="روی مشتری و گروه برای باز کردن کلیک کنید">
          <SkuTree rows={data.sku} onCustomer={open} />
        </Card>
      )}
      {sheet === 'country' && (
        <Card title="کشور ← مشتری" subtitle={`${faDigits(ly)} کل سال و ${faDigits(y)} از ابتدای سال، مثل شیت Country؛ رشد دلاری = ${faDigits(y)} ÷ ${faDigits(ly)}. روی کشور برای بستن و روی مشتری برای پرونده کلیک کنید`}>
          <CountryTable rows={data.countries} y={y} ly={ly} onCustomer={open} />
        </Card>
      )}
      {sheet === 'trend' && (
        <div className="grid g2">
          <Card title="روند انباشته از ابتدای سال" className="span2" subtitle={`${faDigits(y)} (خط پررنگ) در برابر ${faDigits(ly)}؛ برای یک گروه کالا از فیلتر «گروه کالا» استفاده کنید`}
            actions={<Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />}>
            <YearsChart rows={data.trend} metric={metric} cum year={y} ly={ly} height={340} />
          </Card>
          <Card title="جدول ماهانه" className="span2">
            <DataTable rows={data.trend.map((r) => ({ ...r, month: MONTHS[Number(r.mm) - 1] }))} pageSize={12} search={false} exportName="export-ytd-trend"
              columns={[{ key: 'month', label: 'ماه' },
                { key: 'pcs_ly', label: `${faDigits(ly)} تعداد`, type: 'int' }, { key: 'cum_pcs_ly', label: `${faDigits(ly)} تعداد انباشته`, type: 'int' },
                { key: 'pcs', label: `${faDigits(y)} تعداد`, type: 'int' }, { key: 'cum_pcs', label: `${faDigits(y)} تعداد انباشته`, type: 'int' },
                { key: 'net_ly', label: `${faDigits(ly)} دلار`, type: 'int' }, { key: 'net', label: `${faDigits(y)} دلار`, type: 'int' },
                { key: 'gross_ly', label: `${faDigits(ly)} ناخالص`, type: 'int' }, { key: 'gross', label: `${faDigits(y)} ناخالص`, type: 'int' },
                { key: 'req_ly', label: `${faDigits(ly)} درخواست $`, type: 'int' }, { key: 'req', label: `${faDigits(y)} درخواست $`, type: 'int' },
                { key: 'req_pcs', label: `${faDigits(y)} درخواست تعداد`, type: 'int' }]} />
          </Card>
        </div>
      )}
      {file && <CustomerFile key={file} code={file} query={query} onClose={() => setFile(null)} />}
    </>
  )
}
