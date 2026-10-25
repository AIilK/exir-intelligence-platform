import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApp, useRkFetch, fmtMoney, fmtInt, fmtPct, fmtCompact, faDigits, UNITS, isNum, fmtFull } from '../lib.jsx'
import { Kpi, Card, Loading, ErrorBox, Empty, DataTable, MultiSelect } from '../components/ui.jsx'
import { Chart, HBar, baseOption, useTheme } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { brandColor } from '../brands.js'
import { MAP_VIEWBOX, MAP_PATHS, BUBBLE_POS } from '../iranMap.js'

// فروش B2B نمایندگان استانی از راهکاران؛ نمای اصلی معادل شیت Bubble Chart فایل B2B-Sales Report
const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
export const monthLabel = (m) => `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}`
const periodLabel = (p) => (p.value === 'YTD' ? `از ابتدای سال ${faDigits(p.label.slice(-4))}` : monthLabel(p.value))
const money = (v) => (isNum(v) ? `${fmtCompact(v).value} ${fmtCompact(v).unit}` : '—')
const growthText = (g) => (isNum(g) ? `${g >= 0 ? '▲' : '▼'} ${fmtPct(Math.abs(g))} نسبت به سال قبل` : 'بدون فروش در همین دوره سال قبل')
/** پارامترهای درخواست؛ مقدار آرایه (مثل product) پارامتر تکراری می‌شود */
export const q = (o) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else if (v) p.set(k, v)
  }
  return p.toString()
}

/** فیلتر کالا (کد کالا، چندانتخابی)؛ برای مقایسه مستقیم با گزارش «فروش محصول به تفکیک مشتری» راهکاران.
 * list: فهرست آماده [{code, name, cat}]؛ بدون آن از /api/rk_sales/products خوانده می‌شود */
export function ProductFilter({ value, onChange, list }) {
  const { data } = useRkFetch(list ? null : '/api/rk_sales/products')
  const items = list || data?.products
  const options = useMemo(() => (items || []).map((p) => ({ value: p.code, label: `${p.code} — ${p.name}`, group: p.cat })), [items])
  return <MultiSelect label="کالا" value={value} onChange={onChange} options={options} />
}

/** single: پرونده یک کد مشتری (کارت شمارش مشتری نمی‌آید) */
function RkKpis({ k, single = false }) {
  return (
    <div className="kpis">
      <Kpi label="فروش ناخالص" value={k.gross} hint="جمع مبلغ ناخالص اقلام فاکتور (قبل از کسور)؛ GROSS SALES شیت Bubble Chart"
        sub={`نرخ تخفیف ${fmtPct(k.disc_rate)}`} />
      <Kpi label="فروش خالص" value={k.net} hint="مبلغ خالص اقلام فاکتور پس از کسور و اضافات؛ Net SALES شیت Bubble Chart"
        sub={growthText(k.growth)} />
      <Kpi label="جمع کل (خالص + تخفیف نقدی)" value={k.net_cash}
        hint="فروش خالص به‌اضافه تخفیف نقدی؛ تخفیف نقدی = مبلغ سیاست فروش «تخفیف مشتریان اصلی ۱۴۰۵» روی اقلام فاکتور (شیت «فاکتور با سیاست فروش»)"
        sub={`تخفیف نقدی ${money(k.cash)}`} />
      <Kpi label="تعداد فروش (عدد)" value={k.qty} type="int" sub={`${fmtInt(k.skus)} کالای فروش‌رفته`} />
      <Kpi label="فاکتور" value={k.invoices} type="int" hint="ترکیب (مشتری، روز)؛ چند فاکتور یک مشتری در یک روز یکی حساب می‌شود (مثل شیت Calc)"
        sub={`میانگین فاکتور ${money(k.avg_invoice)}`} />
      {!single && (
        <Kpi label="مشتری فعال" value={k.customers} type="int"
          hint="تعداد مشتری = تعداد کد مشتری یکتا (هر برند یک نماینده کد جدا دارد). فعال = کدی که از ابتدای سال جاری فاکتور فروش با مبلغ خالص مثبت داشته، مستقل از دوره انتخاب‌شده"
          sub={`از ${fmtInt(k.customers_total)} کد مشتری · ${fmtInt(k.customers_inactive)} بدون خرید از ابتدای سال${k.customers_period !== k.customers ? ` · ${fmtInt(k.customers_period)} خرید در این دوره` : ''}`} />
      )}
      <Kpi label="برگشت از فروش" value={k.returns} hint="فاکتورهای برگشت از فروش راهکاران؛ در اکسل نیستند و از فروش کم نشده‌اند"
        sub={`نرخ برگشت ${fmtPct(k.return_rate)}`} />
      {k.req_gross != null && (
        <Kpi label="درخواست فروش (ناخالص)" value={k.req_gross}
          hint="درخواست‌های فروش تأییدشده و بسته‌شده راهکاران؛ ستون «ریال ناخالص درخواست» شیت‌های Customer Brand و Total report" />
      )}
    </div>
  )
}

/** نقشه ایران با حباب فروش خالص هر استان (شکل‌ها و جای حباب‌ها از خود فایل اکسل)؛
 * brand: فقط فروش همان برند، مثل لیست کشویی برند کنار نمودار حبابی اکسل */
function BubbleMap({ provinces, selected, onSelect, unit, brand }) {
  const [hover, setHover] = useState(null)
  const wrap = useRef(null)
  const t = useTheme()
  const by = useMemo(() => Object.fromEntries(provinces.map((p) => {
    if (!brand) return [p.key, p]
    const net = (p.brands || []).find((b) => b.brand === brand)?.net || 0
    return [p.key, { ...p, net, all: p.net, brands: net ? [{ brand, net }] : [] }]
  })), [provinces, brand])
  const total = Object.values(by).reduce((a, p) => a + (p.net || 0), 0)
  const color = brand ? brandColor(brand, t) : undefined
  const max = Math.max(...Object.values(by).map((p) => p.net || 0), 1)
  const W = MAP_VIEWBOX[2]
  const radius = (v) => (v > 0 ? 7 + 46 * Math.sqrt(v / max) : 0)
  const show = (e, key) => {
    const b = wrap.current.getBoundingClientRect()
    setHover({ key, x: e.clientX - b.left, y: e.clientY - b.top })
  }
  const order = Object.keys(BUBBLE_POS).filter((k) => by[k]?.net > 0).sort((a, b) => by[b].net - by[a].net)
  const h = hover && by[hover.key]
  return (
    <div className="rk-map" ref={wrap} onMouseLeave={() => setHover(null)}>
      <svg viewBox={MAP_VIEWBOX.join(' ')} role="img" aria-label="نقشه حبابی فروش استان‌ها">
        {MAP_PATHS.map((s, i) => {
          if (!s.p && !s.water) return null // تکه‌های بی‌نام نقشه اکسل
          const p = s.p && by[s.p]
          const op = p?.net ? 0.1 + 0.4 * Math.sqrt(p.net / max) : 0
          return (
            <path key={i} d={s.d} className={s.water ? 'water' : `land${s.p ? ' prov' : ''}${s.p === selected ? ' sel' : ''}`}
              style={!s.water && op ? { fillOpacity: op, fill: color } : undefined}
              onMouseMove={s.p ? (e) => show(e, s.p) : undefined} onClick={s.p ? () => onSelect(s.p) : undefined} />
          )
        })}
        {[...order].reverse().map((k) => {
          const [x, y] = BUBBLE_POS[k]
          const r = radius(by[k].net)
          return (
            <g key={k} className={`bubble${k === selected ? ' sel' : ''}`} onMouseMove={(e) => show(e, k)} onClick={() => onSelect(k)}>
              <circle cx={x} cy={y} r={r} style={color ? { fill: color } : undefined} />
              {r >= 17 && <text x={x} y={y + 5} textAnchor="middle">{fmtMoney(by[k].net, unit)}</text>}
            </g>
          )
        })}
        {/* نام استان‌ها؛ زیر حباب، یا روی خود استان اگر فروشی ندارد */}
        {Object.entries(BUBBLE_POS).map(([k, [x, y]]) => {
          const r = by[k]?.net > 0 ? radius(by[k].net) : 0
          return (
            <text key={k} className={`prov-name${r ? '' : ' dim'}`} x={x} y={r ? y + r + 12 : y + 4} textAnchor="middle"
              onMouseMove={(e) => by[k] && show(e, k)} onClick={() => by[k] && onSelect(k)}>{k}</text>
          )
        })}
      </svg>
      {h && (
        <div className="rk-tip" style={{ left: Math.min(hover.x + 14, (wrap.current?.clientWidth || W) - 230), top: hover.y + 14 }}>
          <b>{h.key}</b>
          <div>فروش خالص{brand ? ` ${brand}` : ''}: <b>{fmtMoney(h.net, unit)}</b> {UNITS[unit].label}</div>
          <div className="small">{fmtFull(h.net)}</div>
          {brand
            ? <div className="muted">سهم از فروش {brand} {fmtPct(total ? h.net / total : null)} · {fmtPct(h.all ? h.net / h.all : null)} از فروش استان</div>
            : <div className="muted">سهم {fmtPct(h.share)} · {fmtInt(h.customers)} از {fmtInt(h.customers_total)} کد مشتری خرید داشته‌اند</div>}
          {(h.brands || []).slice(0, 6).map((b) => (
            <div key={b.brand} className="small">{b.brand}: {fmtFull(b.net)}</div>
          ))}
          <div className="muted small">برای جزئیات کلیک کنید</div>
        </div>
      )}
      {!order.length && <div className="state rk-map-empty">فروشی{brand ? ` برای ${brand}` : ''} در این دوره نیست</div>}
    </div>
  )
}

function BrandDonut({ rows, onClick, unit }) {
  const data = rows.filter((r) => r.net > 0)
  if (!data.length) return <Empty />
  return (
    <Chart height={300} onClick={(p) => onClick?.(data[p.dataIndex])}
      option={(t) => ({
        tooltip: { ...baseOption(t).tooltip, trigger: 'item',
          formatter: (p) => `${p.name}<br/><b>${fmtMoney(p.value, unit)}</b> ${UNITS[unit].label} · ${fmtPct(p.percent / 100)}<br/><span style="opacity:.75">${fmtFull(p.value)}</span>` },
        legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle', textStyle: { color: t.text } },
        series: [{
          type: 'pie', radius: ['45%', '72%'], center: ['38%', '50%'], cursor: onClick ? 'pointer' : 'default',
          itemStyle: { borderColor: t.surface, borderWidth: 2 },
          label: { color: t.text, formatter: (p) => (p.percent >= 4 ? fmtPct(p.percent / 100, 0) : '') },
          data: data.map((r) => ({ name: r.key, value: r.net, itemStyle: { color: brandColor(r.key, t) } })),
        }],
      })} />
  )
}

/** فروش خالص ماه‌به‌ماه سال جاری کنار همان ماه سال قبل */
function MonthlyBars({ monthly, unit, onClick }) {
  if (!monthly?.length) return <Empty />
  return (
    <Chart height={280} onClick={onClick && ((p) => onClick(monthly[p.dataIndex].month))}
      option={(t) => ({
        grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
        legend: { top: 0, right: 0, textStyle: { color: t.text } },
        tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (ps) => `${monthLabel(monthly[ps[0].dataIndex].month)}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtMoney(p.value, unit)}</b> <span style="opacity:.75">(${fmtFull(p.value)})</span>`).join('<br/>') },
        xAxis: { type: 'category', inverse: true, data: monthly.map((m) => MONTHS[Number(m.month.slice(5, 7)) - 1]),
          axisLabel: { color: t.text }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
        yAxis: { type: 'value', position: 'right', axisLabel: { color: t.text, formatter: (v) => fmtMoney(v, unit) }, splitLine: { lineStyle: { color: t.grid } } },
        series: [
          { name: 'امسال', type: 'bar', data: monthly.map((m) => m.net), itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] }, barMaxWidth: 22, cursor: onClick ? 'pointer' : 'default' },
          { name: 'سال قبل', type: 'bar', data: monthly.map((m) => m.ly_net), itemStyle: { color: t.axis, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 22 },
        ],
      })} />
  )
}

const growthCol = { key: 'growth', label: 'رشد نسبت به سال قبل', type: 'pct' }
const withGrowth = (rows) => rows.map((r) => ({ ...r, growth: r.ly_net ? r.net / r.ly_net - 1 : null }))

function ProvinceDetail({ name, period, brand, products, unit, onCustomer, onClose }) {
  const { data, loading, error } = useRkFetch(`/api/rk_sales/province?${q({ name, period, brand, product: products })}`)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const cols = [
    { key: 'short', label: 'نماینده', render: (r) => <span title={r.name}>{r.short} {r.source === 'auto' && <span className="rk-new" title="کد جدید در راهکاران که در شیت draft نبود؛ خودکار اضافه شده">جدید</span>}</span> },
    { key: 'city', label: 'شهر' }, { key: 'brand', label: 'برند' },
    { key: 'net', label: 'فروش خالص', type: 'money' }, { key: 'share', label: 'سهم', type: 'pct' },
    { key: 'cash', label: 'تخفیف نقدی', type: 'money' }, { key: 'net_cash', label: 'جمع کل (خالص + تخفیف نقدی)', type: 'money' },
    { key: 'gross', label: 'فروش ناخالص', type: 'money' }, { key: 'ly_net', label: 'سال قبل', type: 'money' }, growthCol,
    { key: 'invoices', label: 'فاکتور', type: 'int' }, { key: 'qty', label: 'تعداد', type: 'int' },
    { key: 'last_date', label: 'آخرین خرید', type: 'date' }, { key: 'code', label: 'کد مشتری' },
  ]
  return (
    <section className="rk-detail">
      <div className="rk-detail-head">
        <h2>استان {data.province}{brand ? ` — ${brand}` : ''}</h2>
        <button className="btn ghost sm" onClick={onClose}>بستن ✕</button>
      </div>
      <RkKpis k={data.kpis} />
      <div className="grid g2">
        <Card title="فروش خالص شهرها" subtitle="جمع نمایندگان هر شهر (شهر از شیت draft)">
          <HBar rows={data.cities.map((c) => ({ ...c, label: `${c.key} (${fmtInt(c.active)}/${fmtInt(c.customers)})` }))} unit={unit} />
        </Card>
        <Card title="سهم برندها در استان"><BrandDonut rows={data.brands} unit={unit} /></Card>
        <Card title="روند ماهانه استان" className="span2"><MonthlyBars monthly={data.monthly} unit={unit} /></Card>
        <Card title="نمایندگان استان" className="span2"
          subtitle="همه مشتریان فهرست در این استان، حتی بدون خرید در دوره؛ برای پرونده هر نماینده روی سطر کلیک کنید">
          <DataTable rows={withGrowth(data.customers)} columns={cols} unit={unit} pageSize={20}
            exportName={`rahkaran-${data.province}`} onRowClick={(r) => onCustomer(r.code)} />
        </Card>
      </div>
    </section>
  )
}

export function CustomerDetail({ code, period, products = [], unit: unitProp, onProvince, onClose }) {
  const { unit: appUnit } = useApp()
  const unit = unitProp || appUnit
  const { data, loading, error } = useRkFetch(`/api/rk_sales/customer?${q({ code, period, product: products })}`)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const c = data.customer
  return (
    <section className="rk-detail">
      <div className="rk-detail-head">
        <div>
          <h2>{c.name}</h2>
          <div className="muted small">
            کد {faDigits(c.code)} · برند {c.brand} · {c.city} · <a href="#" onClick={(e) => { e.preventDefault(); onProvince(c.province) }}>استان {c.province}</a>
            {data.first_date && <> · اولین خرید {faDigits(data.first_date)} · آخرین خرید {faDigits(data.last_date)}</>}
          </div>
        </div>
        <button className="btn ghost sm" onClick={onClose}>بستن ✕</button>
      </div>
      <RkKpis k={data.kpis} single />
      <div className="grid g2">
        <Card title="روند ماهانه خرید" className="span2"><MonthlyBars monthly={data.monthly} unit={unit} /></Card>
        <Card title="گروه کالا" subtitle="گروه کالا از شیت draft (Category 2)">
          {data.categories.length ? <HBar rows={data.categories.slice(0, 15).map((r) => ({ ...r, label: r.key }))} unit={unit} /> : <Empty />}
        </Card>
        <Card title="فاکتورها و درخواست‌ها" subtitle={`فاکتورهای فروش، برگشتی و درخواست‌های فروش دوره${products.length ? ' برای کالاهای انتخاب‌شده' : ''}؛ مبلغ = ناخالص، جمع مبلغ کل = خالص، مثل گزارش‌های راهکاران (راهکاران به ریال است: عدد تومان × ۱۰)`}>
          <DataTable rows={data.invoices} unit={unit} pageSize={12} exportName={`rahkaran-invoices-${c.code}`} defaultSort={{ key: 'date', dir: 'desc' }}
            columns={[{ key: 'inv', label: 'شماره' }, { key: 'date', label: 'تاریخ', type: 'date' }, { key: 'kind', label: 'نوع' },
              { key: 'qty', label: 'مقدار', type: 'int' }, { key: 'gross', label: 'مبلغ', type: 'money' }, { key: 'net', label: 'جمع مبلغ کل', type: 'money' },
              { key: 'cash', label: 'تخفیف نقدی', type: 'money' }, { key: 'net_cash', label: 'خالص + تخفیف نقدی', type: 'money' },
              { key: 'lines', label: 'سطر', type: 'int' }]} />
        </Card>
        <Card title="کالاها" className="span2">
          <DataTable rows={data.products} unit={unit} pageSize={15} exportName={`rahkaran-products-${c.code}`}
            columns={[{ key: 'product_code', label: 'کد کالا' }, { key: 'product', label: 'نام کالا' }, { key: 'cat2', label: 'گروه' },
              { key: 'net', label: 'فروش خالص', type: 'money' }, { key: 'cash', label: 'تخفیف نقدی', type: 'money' },
              { key: 'net_cash', label: 'خالص + تخفیف نقدی', type: 'money' }, { key: 'gross', label: 'ناخالص', type: 'money' }, { key: 'qty', label: 'تعداد', type: 'int' }]} />
        </Card>
      </div>
    </section>
  )
}

export default function Rahkaran() {
  const { unit, setUnit } = useApp()
  const theme = useTheme()
  const [sp, setSp] = useSearchParams()
  const period = sp.get('period') || 'YTD'
  const brand = sp.get('brand') || ''
  const province = sp.get('province')
  const customer = sp.get('customer')
  const products = sp.getAll('product')
  // برند نمودار حبابی جدا از فیلتر برند صفحه، مثل لیست کشویی کنار نمودار در اکسل
  const mapBrand = brand || sp.get('mbrand') || ''
  const set = (patch) => {
    const next = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) v ? next.set(k, v) : next.delete(k)
    setSp(next)
  }
  const { data, loading, error } = useRkFetch(`/api/rk_sales?${q({ period, brand, product: products })}`)
  const setProducts = (v) => {
    const next = new URLSearchParams(sp)
    next.delete('product')
    v.forEach((x) => next.append('product', x))
    setSp(next)
  }
  const detail = useRef(null)
  useEffect(() => {
    if (province || customer) detail.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [province, customer])
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const k = data.kpis
  const openProvince = (p) => set({ province: p, customer: null })
  const openCustomer = (c) => set({ customer: c })
  return (
    <>
      <PageHead title="فروش راهکاران — نمایندگان B2B"
        desc={`فروش کارخانه به ${fmtInt(k.customers_total)} کد مشتری نماینده استانی (فهرست شیت draft)، لایو از راهکاران؛ اعداد برابر فایل B2B-Sales Report`}>
        <div className="rk-controls">
          <label className="unit-select">
            <span className="ms-label">دوره</span>
            <select value={data.period} onChange={(e) => set({ period: e.target.value === 'YTD' ? null : e.target.value })}>
              {data.periods.map((p) => <option key={p.value} value={p.value}>{periodLabel(p)}</option>)}
            </select>
          </label>
          <label className="unit-select">
            <span className="ms-label">برند</span>
            <select value={brand} onChange={(e) => set({ brand: e.target.value })}>
              <option value="">همه برندها</option>
              {data.brand_list.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
          <ProductFilter value={products} onChange={setProducts} />
          <label className="unit-select">
            <span className="ms-label">واحد مبالغ</span>
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              {Object.entries(UNITS).map(([key, u]) => <option key={key} value={key}>{u.label}</option>)}
            </select>
          </label>
          <span className={`rk-live ${data.live ? 'on' : ''}`} title={`خوانده‌شده: ${data.fetched}`}>
            {data.live ? 'لایو' : `بروزرسانی ${faDigits((data.fetched || '').slice(11, 16))}`}
          </span>
        </div>
      </PageHead>
      <RkKpis k={k} />
      <div className="grid g2">
        <Card title="نقشه حبابی فروش خالص استان‌ها" className="span2"
          subtitle={`اندازه حباب و پررنگی استان = فروش خالص ${data.period === 'YTD' ? 'از ابتدای سال' : monthLabel(data.period)}${mapBrand ? ` برند ${mapBrand}` : ''} (${UNITS[unit].label})؛ برای جزئیات روی استان کلیک کنید`}
          actions={!brand && (
            <div className="rk-brand-chips" role="group" aria-label="برند نمودار حبابی">
              <button className={`chip${mapBrand ? '' : ' on'}`} onClick={() => set({ mbrand: null })}>Total</button>
              {data.brands.filter((b) => b.net > 0).map((b) => (
                <button key={b.key} className={`chip${mapBrand === b.key ? ' on' : ''}`} onClick={() => set({ mbrand: b.key })}>
                  <i style={{ background: brandColor(b.key, theme) }} />{b.key}
                </button>
              ))}
            </div>
          )}>
          <BubbleMap provinces={data.provinces} selected={province} onSelect={openProvince} unit={unit} brand={mapBrand} />
        </Card>
        <Card title="سهم برندها از فروش خالص" subtitle={brand ? 'برای همه برندها، فیلتر برند را بردارید' : 'برای فیلتر برند روی آن کلیک کنید'}>
          <BrandDonut rows={data.brands} unit={unit} onClick={(r) => set({ brand: r.key === brand ? null : r.key })} />
        </Card>
        <Card title="فروش خالص استان‌ها" subtitle="برای جزئیات روی استان کلیک کنید">
          {data.provinces.some((p) => p.net > 0)
            ? <HBar rows={data.provinces.filter((p) => p.net > 0).map((p) => ({ ...p, label: p.key }))} unit={unit} onClick={(r) => openProvince(r.key)} />
            : <Empty />}
        </Card>
        <Card title="مشتریان سازنده ۸۰٪ فروش" subtitle={`${fmtInt(data.top80.length)} نماینده از ${fmtInt(data.top80_of)} نماینده دارای خرید (TOP 80%)؛ برای پرونده کلیک کنید`}>
          {data.top80.length
            ? <HBar rows={data.top80.map((r) => ({ ...r, label: `${r.short} (${r.brand}) — ${r.city}` }))} unit={unit} labelWidth={200}
                colorOf={(r, th) => brandColor(r.brand, th)} onClick={(r) => openCustomer(r.code)} />
            : <Empty />}
        </Card>
        <Card title="گروه کالا" subtitle="فروش خالص به تفکیک گروه کالا (Category 2 شیت draft)">
          {data.categories.length ? <HBar rows={data.categories.slice(0, 15).map((r) => ({ ...r, label: r.key }))} unit={unit} colorIndex={2} /> : <Empty />}
        </Card>
        <Card title="روند ماهانه فروش خالص" className="span2" subtitle="امسال در برابر همان ماه سال قبل؛ برای دیدن یک ماه روی آن کلیک کنید">
          <MonthlyBars monthly={data.monthly} unit={unit} onClick={(m) => set({ period: m })} />
        </Card>
      </div>
      <div ref={detail} className="rk-anchor">
        {customer ? (
          <CustomerDetail key={customer} code={customer} period={period} products={products} unit={unit}
            onProvince={openProvince} onClose={() => set({ customer: null })} />
        ) : province ? (
          <ProvinceDetail key={province} name={province} period={period} brand={brand} products={products} unit={unit}
            onCustomer={openCustomer} onClose={() => set({ province: null })} />
        ) : null}
      </div>
    </>
  )
}
