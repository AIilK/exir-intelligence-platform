import { useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { useAuth } from '@finance/auth/auth.tsx'
import { buildXlsx } from '@sales/xlsx.js'
import { faDigits, monthName, n0, qs } from '../data.js'
import './productionForecast.css'

const API = '/api/v1/forecast'
const HORIZONS = [1, 2, 3, 4, 6, 12]
const MODES = { production: 'نیاز تولید', inventory: 'موجودی کالا', demand: 'پیش‌بینی فروش', safety: 'ذخیرهٔ اطمینان' }
const CATEGORIES = { 'hair color': 'رنگ مو', oxidant: 'اکسیدان', 'hair spray': 'اسپری مو', 'bleach powder': 'پودر دکلره' }
const EVENT_TYPES = { promotion: 'آفر / پروموشن', price_hike: 'افزایش قیمت', event: 'رویداد بازار' }
const CHANNEL_LABELS = { all: 'همهٔ کانال‌ها', hybrid: 'هیبرید', b2b: 'B2B' }
const DIST_FILTERS = { all: 'همه', due: 'معوق / نزدیک سفارش', overridden: 'تعدیل‌شده' }
const REORDER_LABELS = { overdue: 'معوق سفارش', due_soon: 'نزدیک سفارش', normal: 'عادی' }
const pct = (x) => (x == null || !Number.isFinite(Number(x))) ? '—' : `${faDigits((Number(x) * 100).toFixed(1))}٪`
const COLORS = ['#22c9b5', '#63a5ff', '#f4b751', '#ef87a1', '#a99afc', '#52aabd']
const UNITS = new Intl.NumberFormat('fa-IR', { notation: 'compact', maximumFractionDigits: 1 })
const stamp = (s) => {
  const date = new Date(s || '')
  if (!Number.isFinite(date.getTime())) return '—'
  return new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', dateStyle: 'medium', ...(s.includes('T') ? { timeStyle: 'short' } : {}) }).format(date)
}
const monthLabel = (m) => `${monthName(m)} ${faDigits(m.slice(0, 4))}`
const sourceLink = (url) => typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null
const money = (x) => `${n0(x)} تومان`
const count = (x) => n0(x)
const currency = (rial) => `${n0(rial / 10)} تومان`

async function request(path, options) {
  const result = await fetch(`${API}${path}`, { cache: 'no-store', ...options })
  const data = await result.json().catch(() => ({}))
  if (!result.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'دریافت داده انجام نشد.')
  return data
}

function useForecast(path, refresh = 0, poll = 0) {
  const [value, setValue] = useState({ data: null, error: '', loading: Boolean(path) })
  useEffect(() => {
    if (!path) return undefined
    const controller = new AbortController()
    let pending = false
    const get = async () => {
      if (pending) return
      pending = true
      try {
        const data = await request(path, { signal: controller.signal })
        if (!controller.signal.aborted) setValue({ data, error: '', loading: false })
      } catch (error) {
        if (!controller.signal.aborted) setValue((previous) => ({ ...previous, error: error.message, loading: false }))
      } finally {
        pending = false
      }
    }
    setValue((previous) => ({ ...previous, error: '', loading: true }))
    get()
    const timer = poll ? window.setInterval(get, poll) : null
    return () => { controller.abort(); if (timer) window.clearInterval(timer) }
  }, [path, refresh, poll])
  return value
}

function LoadState({ state, empty }) {
  if (state.error) return <div className="pf-state pf-error" role="alert">{state.error}</div>
  if (state.loading) return <div className="pf-state" role="status">در حال دریافت داده…</div>
  return <div className="pf-state">{empty || 'برای این انتخاب داده‌ای وجود ندارد.'}</div>
}

function Section({ title, description, action, children, className = '' }) {
  return <section className={`pf-panel ${className}`}>
    <div className="pf-panel-head"><div><h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>
    {children}
  </section>
}

function Metric({ label, value, description, tone, onClick }) {
  return <button className={`pf-metric pf-${tone}`} type="button" onClick={onClick}>
    <span>{label}<i aria-hidden="true">↙</i></span>
    <strong>{n0(value)} <small>واحد</small></strong>
    <span className="pf-metric-note">{description}</span>
  </button>
}

function Chart({ labels, series, legend = true, height = 265, currencyAxis = false }) {
  const options = useMemo(() => ({
    animation: false,
    color: COLORS,
    textStyle: { fontFamily: 'Vazirmatn, Tahoma, sans-serif', color: '#96aab9' },
    grid: { left: 58, right: 20, top: legend ? 45 : 19, bottom: 35 },
    legend: legend ? { type: 'scroll', top: 0, textStyle: { color: '#8fa8bb' }, pageTextStyle: { color: '#8fa8bb' } } : undefined,
    tooltip: { trigger: 'axis', confine: true, valueFormatter: currencyAxis ? money : count },
    xAxis: { type: 'category', data: labels, axisTick: { show: false }, axisLabel: { color: '#91a6bb' },
      axisLine: { lineStyle: { color: '#41617b65' } } },
    yAxis: { type: 'value', min: 0, axisLabel: { formatter: (v) => UNITS.format(v), color: '#91a6bb' },
      splitLine: { lineStyle: { color: '#5879902c', type: 'dashed' } } },
    series: series.map((s) => ({ type: 'bar', barMaxWidth: 52, itemStyle: { borderRadius: [6, 6, 0, 0] }, ...s })),
  }), [labels, series, legend, currencyAxis])
  return <ReactECharts option={options} style={{ height, width: '100%' }} notMerge />
}

function Pager({ offset, total, size, setOffset }) {
  return <div className="pf-pager">
    <span>{total ? `${n0(offset + 1)} تا ${n0(Math.min(total, offset + size))} از ${n0(total)}` : '۰ نتیجه'}</span>
    <div>
      <button type="button" className="pf-control" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - size))}>قبلی</button>
      <button type="button" className="pf-control" disabled={offset + size >= total} onClick={() => setOffset(offset + size)}>بعدی</button>
    </div>
  </div>
}

function Horizon({ value, setValue }) {
  return <div className="pf-segments" aria-label="افق برنامه‌ریزی">
    {HORIZONS.map((h) => <button key={h} type="button" aria-pressed={value === h} onClick={() => setValue(h)}>
      {`${n0(h)} ماهه`}
    </button>)}
  </div>
}

function ProductDialog({ code, overview, onClose }) {
  const dialog = useRef(null)
  const state = useForecast(code && `/products/${encodeURIComponent(code)}`)
  useEffect(() => {
    const node = dialog.current
    if (code && node && !node.open) node.showModal()
  }, [code])
  const row = state.data?.product
  return <dialog ref={dialog} className="pf-dialog" onClose={onClose}
    onClick={(event) => { if (event.target === event.currentTarget) event.currentTarget.close() }}>
    <div className="pf-dialog-inner">
      <div className="pf-panel-head">
        <div><small className="pf-muted">جزئیات کالا · {faDigits(code)}</small><h2>{row?.name || 'کالا'}</h2>
          {row?.brand && <p>{row.brand} {row.category && `· ${row.category}`}</p>}</div>
        <button type="button" className="pf-control" onClick={() => dialog.current.close()} aria-label="بستن جزئیات">×</button>
      </div>
      {!row || state.error ? <LoadState state={state} /> : <>
        {row.review && <div className="pf-state pf-warn">{[
          row.missing_inventory_record && 'رکورد موجودی ثبت نشده',
          row.missing_product_status && 'وضعیت فعالیت نامشخص',
          row.missing_safety_history && 'سابقهٔ خطا ناقص',
        ].filter(Boolean).join(' · ')}</div>}
        <div className="pf-detail-stats">
          <div><small>نیاز تولید</small><strong>{n0(row.production_need)}</strong></div>
          <div><small>موجودی کارخانه</small><strong>{n0(row.factory_stock_1_4)}</strong></div>
          <div><small>موجودی شعب</small><strong>{n0(row.branch_stock)}</strong></div>
        </div>
        {row.has_forecast ? <div className="pf-overflow"><table className="pf-table">
          <caption>پیش‌بینی فروش و نیاز تولید به تفکیک ماه</caption>
          <thead><tr><th>ماه</th><th>هیبرید</th><th>B2B</th><th>مجموع فروش</th><th>نیاز تولید ماه</th></tr></thead>
          <tbody>{(state.data.monthly_breakdown || overview.months.map((m) => ({
            month: m, hybrid: row[`hybrid_${m}`], b2b: row[`b2b_${m}`],
            total: (row[`hybrid_${m}`] || 0) + (row[`b2b_${m}`] || 0), monthly_need: null,
          }))).map((item) => <tr key={item.month}><td>{monthLabel(item.month)}</td><td>{n0(item.hybrid)}</td>
            <td>{n0(item.b2b)}</td><td>{n0(item.total)}</td>
            <td><b>{item.monthly_need == null ? '—' : n0(item.monthly_need)}</b></td></tr>)}</tbody>
        </table></div> : <p className="pf-muted">این کالا فقط در دادهٔ موجودی ثبت شده است.</p>}
        <div className="pf-detail-stats pf-safety-detail">
          {HORIZONS.map((h) => <div key={h}><small>نیاز تولید {n0(h)} ماهه</small><strong>{n0(row[`production_need_${h}`] ?? row.production_need)}</strong></div>)}
        </div>
        <div className="pf-detail-stats pf-safety-detail">
          {HORIZONS.map((h) => <div key={h}><small>ذخیرهٔ {n0(h)} ماهه</small><strong>{n0(row[`safety_${h}`])}</strong></div>)}
        </div>
        <p className="pf-muted">خطای ماهانه (RMSE) و کلاس. هیبرید {n0(row.hybrid_rmse)} واحد، {row.hybrid_class || '—'} · B2B {n0(row.b2b_rmse)} واحد، {row.b2b_class || '—'}</p>
        <div className="pf-location-grid">
          {[['انبارهای کارخانه', state.data.factory, 'store'], ['موجودی شعب', state.data.branches, 'branch']].map(([title, items, key]) =>
            <div key={key}><h3>{title}</h3>{items.length ? <ul>{items.map((item) =>
              <li key={item[key]}><span>{faDigits(item[key])}</span><b>{n0(item.qty)}</b></li>)}</ul> :
              <p className="pf-muted">رکوردی در این منبع وجود ندارد.</p>}</div>)}
        </div>
      </>}
    </div>
  </dialog>
}

function ProductTable({ mode, setMode, horizon, refresh, onProduct, tableRef }) {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const size = 20
  useEffect(() => {
    const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0) }, 200)
    return () => clearTimeout(timer)
  }, [query])
  useEffect(() => setOffset(0), [mode, horizon])
  const state = useForecast(`/products?${qs({ mode, horizon, query: search, offset, limit: size })}`, refresh)
  const metric = mode === 'inventory' ? null : { production: `production_need_${horizon}`, demand: `demand_${horizon}`, safety: `safety_${horizon}` }[mode]

  const exportExcel = async () => {
    setExporting(true)
    setExportError('')
    try {
      const res = await request(`/products/export?${qs({ mode, horizon, query: search })}`)
      const months = res.months || []
      const num = (v) => (v == null || !Number.isFinite(Number(v)) ? 0 : Math.round(Number(v)))
      const cols = [
        ['کد کالا', 'text', (r) => String(r.code || '')],
        ['نام کالا', 'text', (r) => r.name || ''],
        ['برند', 'text', (r) => r.brand || ''],
        ['دسته‌بندی', 'text', (r) => r.category || ''],
        ['موجودی کارخانه', 'int', (r) => num(r.factory_stock_1_4)],
        ['موجودی شعب', 'int', (r) => num(r.branch_stock)],
        ['مجموع موجودی', 'int', (r) => num((r.factory_stock_1_4 || 0) + (r.branch_stock || 0))],
        [`نیاز تولید (${n0(horizon)} ماهه)`, 'int', (r) => num(r[`production_need_${horizon}`])],
        [`پیش‌بینی فروش (${n0(horizon)} ماهه)`, 'int', (r) => num(r[`demand_${horizon}`])],
        [`ذخیرهٔ اطمینان (${n0(horizon)} ماهه)`, 'int', (r) => num(r[`safety_${horizon}`])],
        ...months.flatMap((m) => [
          [`هیبرید ${monthLabel(m)}`, 'int', (r) => num(r[`hybrid_${m}`])],
          [`B2B ${monthLabel(m)}`, 'int', (r) => num(r[`b2b_${m}`])],
          [`جمع ${monthLabel(m)}`, 'int', (r) => num((r[`hybrid_${m}`] || 0) + (r[`b2b_${m}`] || 0))],
        ]),
        ...HORIZONS.map((h) => [`نیاز تولید ${n0(h)} ماهه`, 'int', (r) => num(r[`production_need_${h}`])]),
        ['کلاس هیبرید', 'text', (r) => r.hybrid_class || '—'],
        ['کلاس B2B', 'text', (r) => r.b2b_class || '—'],
        ['وضعیت بررسی', 'text', (r) => (r.review ? 'دادهٔ ناقص' : 'کامل')],
      ]
      const data = (res.rows || []).map((r) => cols.map(([, , fn]) => fn(r)))
      const total = cols.map(([, kind], i) => (i === 0 ? 'جمع' : kind === 'int' ? data.reduce((s, row) => s + (row[i] || 0), 0) : null))
      const blob = buildXlsx(cols.map(([label, kind]) => ({ label, kind })), [...data, total], 'کالاها', { filterRows: data.length, freezeCol: 2 })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `forecast-products-${mode}-${horizon}m.xlsx`
      a.click()
      window.setTimeout(() => URL.revokeObjectURL(a.href), 2000)
    } catch (err) {
      setExportError(err.message || 'ساخت فایل اکسل انجام نشد.')
    } finally {
      setExporting(false)
    }
  }

  return <div ref={tableRef} className="pf-scroll-anchor"><Section title="کالاها" description="برای مشاهدهٔ موجودی هر انبار و شعبه، پیش‌بینی ماهانه و نیاز تولید هر افق، روی کالا کلیک کنید."
    action={<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <input className="pf-control pf-search" aria-label="جستجوی کالا" placeholder="نام کالا، کد یا برند" value={query} onChange={(e) => setQuery(e.target.value)} />
      <button type="button" className="pf-control" disabled={exporting || !state.data?.total} onClick={exportExcel}>
        {exporting ? 'در حال ساخت اکسل…' : 'خروجی اکسل'}
      </button>
    </div>}>
    {exportError && <div className="pf-state pf-error" role="alert">{exportError}</div>}
    <div className="pf-market-controls">
      <div className="pf-segments" aria-label="نوع گزارش">
        {Object.entries(MODES).map(([key, label]) => <button type="button" key={key} aria-pressed={mode === key} onClick={() => setMode(key)}>{label}</button>)}
      </div>
      {mode !== 'inventory' && <span className="pf-muted">افق انتخاب‌شده: {n0(horizon)} ماهه</span>}
    </div>
    {!state.data?.rows.length || state.error ? <LoadState state={state} /> : <>
      <div className="pf-overflow"><table className="pf-table">
        <thead><tr><th>کالا و کد</th><th>کارخانه</th><th>شعب</th><th>{metric ? `${MODES[mode]} (${n0(horizon)} ماهه)` : 'مجموع موجودی'}</th><th>بررسی</th></tr></thead>
        <tbody>{state.data.rows.map((row) => <tr key={row.code} onClick={() => onProduct(row.code)}>
          <td><button className="pf-product" type="button" onClick={(event) => { event.stopPropagation(); onProduct(row.code) }}>
            <b>{row.name || faDigits(row.code)}</b><small>{faDigits(row.code)} {row.brand && `· ${row.brand}`}</small>
          </button></td>
          <td>{n0(row.factory_stock_1_4)}</td><td>{n0(row.branch_stock)}</td>
          <td><b>{n0(metric ? row[metric] : row.factory_stock_1_4 + row.branch_stock)}</b></td>
          <td>{row.review ? <span className="pf-review">دادهٔ ناقص</span> : '—'}</td>
        </tr>)}</tbody>
      </table></div>
      <Pager offset={offset} total={state.data.total} size={size} setOffset={setOffset} />
    </>}
  </Section></div>
}

const PERIODS = { monthly: 'ماهانه', quarterly: 'فصلی', annual: 'سالانه' }
const periodLabel = (period, key) => {
  if (period === 'monthly') return monthLabel(key)
  if (period === 'quarterly') {
    const [year, quarter] = key.split('-Q')
    return `${['بهار', 'تابستان', 'پاییز', 'زمستان'][Number(quarter) - 1]} ${faDigits(year)}`
  }
  return `سال ${faDigits(key)}`
}

function CategoryProduction({ refresh }) {
  const [period, setPeriod] = useState('monthly')
  const [selected, setSelected] = useState('')
  const [offset, setOffset] = useState(0)
  useEffect(() => setOffset(0), [period, selected])
  const state = useForecast(`/categories?${qs({ period, selected })}`, refresh)
  const data = state.data
  const top = data?.rows.filter((row) => row.production_need > 0).slice(0, 10) || []
  return <Section title="نیاز تولید به تفکیک دسته‌بندی" description="جمع نیاز تولید کالاهای هر دسته، پس از کسر مرحله‌ای موجودی و لحاظ ذخیرهٔ اطمینان.">
    <div className="pf-market-controls">
      <div className="pf-segments" aria-label="بازهٔ نیاز تولید دسته‌بندی">
        {Object.entries(PERIODS).map(([key, label]) => <button key={key} type="button" aria-pressed={period === key}
          onClick={() => { setPeriod(key); setSelected('') }}>{label}</button>)}
      </div>
      {data && <label>بازه <select className="pf-control" aria-label="انتخاب بازهٔ تولید" value={data.selected}
        onChange={(event) => setSelected(event.target.value)}>
        {data.periods.map((key) => <option key={key} value={key}>{periodLabel(period, key)}</option>)}
      </select></label>}
    </div>
    {!data || state.error ? <LoadState state={state} /> : <>
      <div className="pf-category-total"><div><span className="pf-muted">مجموع نیاز تولید در بازهٔ انتخاب‌شده</span>
        <strong>{n0(data.total_production)} <small>واحد</small></strong></div>
        <span className="pf-muted">پوشش پیش‌بینی {n0(data.covered_months)} از {n0(data.expected_months)} ماه</span>
      </div>
      {!data.complete && <p className="pf-state pf-warn">این بازه به‌صورت جزئی پوشش داده شده است. اعداد مربوط به {data.months.map(monthLabel).join('، ')} هستند. پیش‌بینی ماه‌های باقی‌مانده هنوز منتشر نشده است.</p>}
      {top.length > 0 && <Chart labels={top.map((row) => row.category)} legend={false} height={250}
        series={[{ name: 'نیاز تولید', data: top.map((row) => row.production_need) }]} />}
      <div className="pf-overflow"><table className="pf-table">
        <thead><tr><th>دسته‌بندی</th><th>تعداد کالا</th><th>کالای نیازمند تولید</th><th>پیش‌بینی فروش</th><th>نیاز تولید</th></tr></thead>
        <tbody>{data.rows.slice(offset, offset + 15).map((row) => <tr key={row.category}>
          <td><b>{row.category}</b></td><td>{n0(row.products)}</td><td>{n0(row.production_skus)}</td>
          <td>{n0(row.demand)}</td><td><b>{n0(row.production_need)}</b></td>
        </tr>)}</tbody>
      </table></div>
      <Pager offset={offset} total={data.rows.length} size={15} setOffset={setOffset} />
      <p className="pf-muted">موجودی هر کالا در طول ماه‌ها یک بار مصرف می‌شود. ذخیرهٔ اطمینان با جذر طول بازه افزایش می‌یابد. جمع نیاز ماهانه با برنامهٔ کل بازه منطبق است.</p>
    </>}
  </Section>
}

function RivalMarket({ refresh }) {
  const [channel, setChannel] = useState('retail')
  const [category, setCategory] = useState('')
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => { setSearch(query.trim()); setOffset(0) }, 250)
    return () => window.clearTimeout(timer)
  }, [query])
  const state = useForecast(`/rivals?${qs({ channel, category, query: search, offset, limit: 15 })}`, refresh)
  const trend = state.data?.trend || []
  const months = [...new Set(trend.map((x) => x.pmonth))].sort().slice(-18)
  const series = [...new Set(trend.map((x) => x.company))].map((company) => ({
    name: company, type: 'line', showSymbol: false, data: months.map((month) =>
      trend.find((x) => x.pmonth === month && x.company === company)?.per100 ?? null),
  }))
  return <Section title="قیمت محصولات رقبا" description={state.data?.last_offer_date && `آخرین مشاهده در این انتخاب · ${stamp(state.data.last_offer_date)}`}>
    <div className="pf-market-controls">
      <div className="pf-segments" aria-label="کانال قیمت">
        {[['retail', 'خرده‌فروشی'], ['wholesale', 'عمده‌فروشی']].map(([id, label]) =>
          <button type="button" key={id} aria-pressed={channel === id} onClick={() => { setChannel(id); setOffset(0) }}>{label}</button>)}
      </div>
      <label>گروه کالا <select className="pf-control" value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0) }}>
        <option value="">همهٔ دسته‌بندی‌ها</option>
        {Object.entries(CATEGORIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <form className="pf-rival-search" role="search" onSubmit={(event) => { event.preventDefault(); setSearch(query.trim()); setOffset(0) }}>
        <label className="pf-search-label" htmlFor="pf-rival-query">جستجوی محصولات رقبا</label>
        <div><input id="pf-rival-query" type="search" className="pf-control pf-search" maxLength={80}
          placeholder="نام محصول، برند، شرکت یا منبع" value={query} onChange={(event) => setQuery(event.target.value)} />
          <button type="submit" className="pf-control pf-primary">جستجو</button>
          {query && <button type="button" className="pf-control" onClick={() => { setQuery(''); setSearch(''); setOffset(0) }}>پاک کردن</button>}
        </div>
      </form>
    </div>
    {state.data && <p className="pf-muted" role="status">{n0(state.data.total)} محصول{search && ` برای «${search}»`}</p>}
    {months.length > 1 && <div>
      <p className="pf-muted">میانهٔ قیمت قابل مقایسه در ترب، به تومان برای ۱۰۰ {category === 'bleach powder' ? 'گرم' : 'میلی‌لیتر'}</p>
      <Chart labels={months.map(monthLabel)} series={series} currencyAxis height={250} />
    </div>}
    <details className="pf-method">
      <summary>منبع و روش محاسبهٔ قیمت‌ها</summary>
      <p>سابقهٔ خرده‌فروشی از نمودار قیمت محصول در <a href="https://torob.com/" target="_blank" rel="noreferrer">ترب</a> استخراج شده است.
        برای نمودار، قیمت‌ها را به ۱۰۰ گرم یا میلی‌لیتر تبدیل می‌کنیم. رنگ مو با بستهٔ ۱۰۰ میلی‌لیتری مقایسه می‌شود.
        ابتدا میانهٔ هر محصول در ماه و بعد میانهٔ محصولات هر شرکت محاسبه می‌شود. نقاط بدون مشاهده خالی می‌مانند.</p>
      <p>قیمت‌های عمده از پیشنهادهای بازارگاه‌ها و فروشگاه‌های عمده به دست می‌آیند. قیمت بسته بر تعداد واحدهای اعلام‌شده تقسیم می‌شود.
        جدول قیمت مشاهده‌شدهٔ هر واحد و تاریخ و منبع آن را نشان می‌دهد. برای نمودار تاریخی عمده به مشاهدهٔ ماه‌های بیشتری نیاز است.</p>
    </details>
    {!state.data?.rows.length || state.error ? <LoadState state={state} /> : <>
      <div className="pf-overflow"><table className="pf-table">
        <thead><tr><th>محصول</th><th>شرکت</th><th>قیمت واحد</th><th>تاریخ مشاهده</th><th>منبع</th></tr></thead>
        <tbody>{state.data.rows.map((r, index) => <tr key={`${r.source}-${r.title}-${r.date}-${index}`}>
          <td><b>{r.title}</b><small className="pf-muted">{r.brand} {r.pack_size ? `· ${n0(r.pack_size)} ${r.size_unit === 'g' ? 'گرم' : r.size_unit === 'ml' ? 'میلی‌لیتر' : ''}` : ''}</small></td>
          <td>{r.company === 'Exir' ? 'اکسیر' : r.company}</td><td>{money(r.price)}</td><td>{stamp(r.date)}</td>
          <td>{sourceLink(r.source_url) ? <a href={r.source_url} target="_blank" rel="noreferrer">{r.source} ↗</a> : r.source}</td>
        </tr>)}</tbody>
      </table></div>
      <Pager offset={offset} total={state.data.total} size={15} setOffset={setOffset} />
    </>}
  </Section>
}

function DistributorForecast({ isAdmin, refresh, onUpdated }) {
  const [status, setStatus] = useState('all')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState({ months: {}, note: '' })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const size = 12
  useEffect(() => {
    const timer = window.setTimeout(() => { setSearch(query.trim()); setOffset(0) }, 200)
    return () => window.clearTimeout(timer)
  }, [query])
  useEffect(() => setOffset(0), [status])
  const state = useForecast(`/distributors?${qs({ status, query: search, offset, limit: size })}`, refresh)
  const data = state.data
  const months = data?.months || []
  const summary = data?.summary || {}

  const startEdit = (row) => {
    const base = {}
    months.forEach((m) => { base[m] = String(Math.round(row.effective_forecast?.[m] ?? row.forecast?.[m] ?? 0)) })
    setDraft({ months: base, note: row.override?.note || '' })
    setEditing(row.key)
    setMsg('')
  }

  const saveEdit = async (key) => {
    setSaving(true)
    setMsg('')
    try {
      const payloadMonths = {}
      months.forEach((m) => { payloadMonths[m] = Math.max(0, Number(draft.months[m] || 0)) })
      await request('/distributors/overrides', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, months: payloadMonths, note: draft.note }),
      })
      setEditing(null)
      setMsg('تعدیل توزیع‌کننده ذخیره شد و در نیاز تولید لحاظ گردید.')
      onUpdated()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  const resetEdit = async (key) => {
    setSaving(true)
    setMsg('')
    try {
      await request(`/distributors/overrides/${encodeURIComponent(key)}`, { method: 'DELETE' })
      setEditing(null)
      setMsg('تعدیل توزیع‌کننده به مقدار پایه مدل بازگردانی شد.')
      onUpdated()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return <Section
    title="پیش‌بینی توزیع‌کنندگان عمده (B2B) و تعدیل فروش"
    description="ادغام حساب‌های چندبرندی راهکاران به توزیع‌کنندهٔ مادر (۳۰ مشتری برتر)، وضعیت چرخهٔ سفارش و امکان تعدیل توسط مدیر فروش/BI."
    action={<input className="pf-control pf-search" aria-label="جستجوی توزیع‌کننده" placeholder="نام توزیع‌کننده یا برند" value={query} onChange={(e) => setQuery(e.target.value)} />}
  >
    {data && <div className="pf-detail-stats">
      <div><small>سهم ۲۰ توزیع‌کنندهٔ اول</small><strong>{pct(summary.top20_share)}</strong></div>
      <div><small>سهم ۳۰ توزیع‌کنندهٔ اول</small><strong>{pct(summary.top30_share)}</strong></div>
      <div><small>معوق / نزدیک سفارش</small><strong>{n0((summary.overdue_count || 0) + (summary.due_soon_count || 0))}</strong></div>
      <div><small>تعدیل‌های فعال BI</small><strong>{n0(summary.active_overrides || 0)}</strong><small>{summary.override_delta_units ? `${summary.override_delta_units > 0 ? '+' : ''}${n0(summary.override_delta_units)} واحد` : 'بدون اختلاف'}</small></div>
    </div>}
    <div className="pf-market-controls">
      <div className="pf-segments" aria-label="فیلتر توزیع‌کنندگان">
        {Object.entries(DIST_FILTERS).map(([k, label]) => (
          <button key={k} type="button" aria-pressed={status === k} onClick={() => setStatus(k)}>{label}</button>
        ))}
      </div>
    </div>
    {msg && <div className="pf-state" role="status">{msg}</div>}
    {!data?.rows?.length || state.error ? <LoadState state={state} empty="ردیف توزیع‌کننده‌ای یافت نشد." /> : <>
      <div className="pf-overflow"><table className="pf-table">
        <thead>
          <tr>
            <th>توزیع‌کننده و برند</th>
            <th>فروش ۱۲ماهه</th>
            <th>وضعیت سفارش</th>
            {months.map((m) => <th key={m}>{monthLabel(m)}</th>)}
            <th>جمع پیش‌بینی</th>
            {isAdmin && <th>تعدیل BI</th>}
          </tr>
        </thead>
        <tbody>{data.rows.map((r) => {
          const isEdit = editing === r.key
          const clsBadge = r.reorder_status === 'overdue' ? 'pf-badge pf-badge-overdue' : (r.reorder_status === 'due_soon' ? 'pf-badge pf-badge-soon' : 'pf-badge pf-badge-ok')
          return <tr key={r.key}>
            <td>
              <b>{r.distributor} · {r.brand}</b>
              <small title={(r.accounts || []).join('، ')}>
                {n0((r.accounts || []).length)} حساب · آخرین خرید {r.last_order_month ? monthLabel(r.last_order_month) : '—'}
              </small>
            </td>
            <td>{n0(r.last_12m)}<small>۳ماهه: {n0(r.last_3m)}</small></td>
            <td>
              <span className={clsBadge}>{REORDER_LABELS[r.reorder_status] || 'عادی'}</span>
              <small>{r.median_gap ? `میانه دوره ${faDigits(r.median_gap)} ماه` : 'دوره نامنظم'}</small>
            </td>
            {months.map((m) => <td key={m}>
              {isEdit ? (
                <input type="number" min="0" step="10" className="pf-control pf-inline-input"
                  value={draft.months[m] ?? ''}
                  onChange={(e) => setDraft((prev) => ({ ...prev, months: { ...prev.months, [m]: e.target.value } }))} />
              ) : (
                <>
                  <span>{n0(r.effective_forecast?.[m] ?? 0)}</span>
                  {r.has_override && Math.round((r.effective_forecast?.[m] ?? 0) - (r.forecast?.[m] ?? 0)) !== 0 && (
                    <small>پایه: {n0(r.forecast?.[m] ?? 0)}</small>
                  )}
                </>
              )}
            </td>)}
            <td>
              <b>{n0(r.effective_total)}</b>
              {r.has_override && Math.round(r.delta_total) !== 0 && (
                <small>{r.delta_total > 0 ? `+${n0(r.delta_total)}` : n0(r.delta_total)}</small>
              )}
            </td>
            {isAdmin && <td>
              {isEdit ? <div style={{ display: 'grid', gap: 4 }}>
                <input className="pf-control pf-inline-input" style={{ width: 130 }} placeholder="یادداشت کوتاه"
                  value={draft.note} onChange={(e) => setDraft((prev) => ({ ...prev, note: e.target.value }))} />
                <div style={{ display: 'flex', gap: 4 }}>
                  <button type="button" className="pf-control pf-primary pf-btn-sm" disabled={saving} onClick={() => saveEdit(r.key)}>ثبت</button>
                  <button type="button" className="pf-control pf-btn-sm" disabled={saving} onClick={() => setEditing(null)}>لغو</button>
                </div>
              </div> : <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                <button type="button" className="pf-control pf-btn-sm" onClick={() => startEdit(r)}>ویرایش</button>
                {r.has_override && <button type="button" className="pf-control pf-btn-sm" disabled={saving} onClick={() => resetEdit(r.key)}>بازنشانی</button>}
              </div>}
            </td>}
          </tr>
        })}</tbody>
      </table></div>
      <Pager offset={offset} total={data.total} size={size} setOffset={setOffset} />
    </>}
  </Section>
}

function PlannedEventsCard({ months, isAdmin, refresh, onUpdated }) {
  const state = useForecast('/events', refresh)
  const events = state.data?.events || []
  const defaultMonth = months?.[0] || '1405/09'
  const [form, setForm] = useState({
    month: defaultMonth, type: 'promotion', channel: 'all', scope: 'همه',
    expected_lift_pct: '10', apply_to_forecast: false, note: '',
  })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (months?.length && !form.month) setForm((prev) => ({ ...prev, month: months[0] }))
  }, [months])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setMsg('')
    try {
      await request('/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          expected_lift_pct: Number(form.expected_lift_pct || 0),
        }),
      })
      setForm((prev) => ({ ...prev, note: '' }))
      setMsg('رویداد برنامه‌ریزی‌شده ثبت شد.')
      onUpdated()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id) => {
    setBusy(true)
    setMsg('')
    try {
      await request(`/events/${encodeURIComponent(id)}`, { method: 'DELETE' })
      onUpdated()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <div style={{ gridColumn: '1 / -1' }}>
    <h3>رویدادها، آفرها و تغییر قیمت برنامه‌ریزی‌شده</h3>
    <p className="pf-muted">ثبت برنامه‌های فروش پیش‌رو (آفر ۱+۱، کمپین یا افزایش قیمت) و در صورت نیاز اعمال مستقیم ضریب آن روی پیش‌بینی.</p>
    {msg && <div className="pf-state" role="status" style={{ marginTop: 8 }}>{msg}</div>}
    {isAdmin && <form className="pf-event-form" onSubmit={submit}>
      <select className="pf-control" value={form.month} onChange={(e) => setForm((p) => ({ ...p, month: e.target.value }))}>
        {(months || ['1405/09', '1405/10', '1405/11', '1405/12']).map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
      </select>
      <select className="pf-control" value={form.type} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
        {Object.entries(EVENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <select className="pf-control" value={form.channel} onChange={(e) => setForm((p) => ({ ...p, channel: e.target.value }))}>
        {Object.entries(CHANNEL_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <input className="pf-control" style={{ width: 130 }} placeholder="برند یا دسته (یا همه)"
        value={form.scope} onChange={(e) => setForm((p) => ({ ...p, scope: e.target.value }))} />
      <input className="pf-control" style={{ width: 95 }} type="number" step="1" min="-80" max="300" placeholder="اثر ٪"
        title="درصد تغییر مورد انتظار" value={form.expected_lift_pct} onChange={(e) => setForm((p) => ({ ...p, expected_lift_pct: e.target.value }))} />
      <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '.78rem', color: 'var(--u-text)' }}>
        <input type="checkbox" checked={form.apply_to_forecast} onChange={(e) => setForm((p) => ({ ...p, apply_to_forecast: e.target.checked }))} />
        اعمال در پیش‌بینی
      </label>
      <input className="pf-control" style={{ flex: 1, minWidth: 150 }} placeholder="توضیح (مثلاً آفر پادینا)"
        value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} />
      <button type="submit" className="pf-control pf-primary" disabled={busy}>افزودن</button>
    </form>}
    {events.length ? <ul className="pf-event-list">
      {events.map((ev) => <li key={ev.id}>
        <div>
          <b>{EVENT_TYPES[ev.type] || ev.type} · {monthLabel(ev.month)}</b>
          {' '}
          <span className="pf-badge">{CHANNEL_LABELS[ev.channel] || ev.channel}</span>
          {' '}
          <span className="pf-badge">{ev.scope || 'همه'}</span>
          {' '}
          <span className={ev.apply_to_forecast ? 'pf-badge pf-badge-ok' : 'pf-badge'}>
            {ev.expected_lift_pct > 0 ? `+${faDigits(ev.expected_lift_pct)}٪` : `${faDigits(ev.expected_lift_pct)}٪`}
            {ev.apply_to_forecast ? ' · فعال روی پیش‌بینی' : ' · ثبت اطلاعاتی'}
          </span>
          {ev.note && <span className="pf-muted"> — {ev.note}</span>}
        </div>
        {isAdmin && <button type="button" className="pf-control pf-btn-sm" disabled={busy} onClick={() => remove(ev.id)}>حذف</button>}
      </li>)}
    </ul> : <p className="pf-muted" style={{ marginTop: 8 }}>رویداد آتی ثبت نشده است.</p>}
  </div>
}

function AccuracyTracker({ refresh }) {
  const state = useForecast('/accuracy', refresh)
  const data = state.data
  const bt = data?.backtest_summary || {}
  const live = data?.live_monthly || []
  const pending = data?.pending_forecasts || []
  const btMonthly = data?.backtest_monthly || []

  const chartPoints = [
    ...btMonthly.map((row) => ({
      label: monthLabel(row.month),
      hybrid: row.hybrid?.wape != null ? Math.round(row.hybrid.wape * 1000) / 10 : null,
      b2b: row.b2b?.wape != null ? Math.round(row.b2b.wape * 1000) / 10 : null,
    })),
    ...live.map((row) => ({
      label: `${monthLabel(row.target_month)} (زنده)`,
      hybrid: row.hybrid?.wape != null ? Math.round(row.hybrid.wape * 1000) / 10 : null,
      b2b: row.b2b?.wape != null ? Math.round(row.b2b.wape * 1000) / 10 : null,
    })),
  ]

  return <Section
    title="پایش زندهٔ دقت پیش‌بینی (پیش‌بینی در برابر فروش واقعی)"
    description="ارزیابی خارج از نمونه روی ماه‌های اخیر و امتیازدهی خودکار مدل‌های آرشیوشده به محض بسته‌شدن هر ماه."
  >
    {!data || state.error ? <LoadState state={state} /> : <>
      <div className="pf-detail-stats">
        <div><small>خطای ۳ماهه هیبرید (خارج از نمونه)</small><strong>{pct(bt.hybrid_3m_wape)}</strong><small>بایاس: {pct(bt.hybrid_3m_bias)}</small></div>
        <div><small>خطای ۳ماهه B2B (خارج از نمونه)</small><strong>{pct(bt.b2b_3m_wape)}</strong><small>بایاس: {pct(bt.b2b_3m_bias)}</small></div>
        <div><small>ارزیابی‌های زندهٔ ماه‌های بسته‌شده</small><strong>{n0(data.live_evaluated_count || 0)}</strong><small>{(data.archived_models || []).length} مدل آرشیوشده</small></div>
        <div><small>اهداف در انتظار بسته‌شدن ماه</small><strong>{n0(pending.length)}</strong><small>بسته تا {data.closed_month ? monthLabel(data.closed_month) : '—'}</small></div>
      </div>
      {chartPoints.length > 1 && <div>
        <p className="pf-muted">روند خطای ماهانه (WAPE٪) مدل فعال در بازهٔ آزمون و ماه‌های بسته‌شدهٔ زنده</p>
        <Chart labels={chartPoints.map((p) => p.label)} height={230} series={[
          { name: 'هیبرید (٪)', type: 'line', showSymbol: true, data: chartPoints.map((p) => p.hybrid) },
          { name: 'B2B (٪)', type: 'line', showSymbol: true, data: chartPoints.map((p) => p.b2b) },
        ]} />
      </div>}
      {live.length > 0 && <div className="pf-overflow"><table className="pf-table">
        <caption>مقایسهٔ مدل‌های آرشیوشده با فروش واقعی ماه‌های بسته‌شده</caption>
        <thead><tr><th>مدل</th><th>ماه هدف</th><th>هیبرید (پیش‌بینی / واقعی / خطا)</th><th>B2B (پیش‌بینی / واقعی / خطا)</th><th>خطای کل</th><th>بایاس کل</th></tr></thead>
        <tbody>{live.map((item) => <tr key={`${item.model_file}-${item.target_month}`}>
          <td><b>{item.model_file}</b><small>افق {n0(item.horizon)} ماه</small></td>
          <td>{monthLabel(item.target_month)}</td>
          <td>{n0(item.hybrid?.forecast)} / {n0(item.hybrid?.actual)} <small>WAPE: {pct(item.hybrid?.wape)}</small></td>
          <td>{n0(item.b2b?.forecast)} / {n0(item.b2b?.actual)} <small>WAPE: {pct(item.b2b?.wape)}</small></td>
          <td><b>{pct(item.total?.wape)}</b></td>
          <td>{pct(item.total?.bias)}</td>
        </tr>)}</tbody>
      </table></div>}
      {pending.length > 0 && <p className="pf-muted">مدل‌های آرشیوشده منتظر بسته‌شدن فروش واقعی برای {pending.slice(0, 4).map((p) => `${monthLabel(p.target_month)} (${p.model_file})`).join(' · ')} هستند.</p>}
    </>}
  </Section>
}

function LiveUsdCard({ initialUsd }) {
  const [tick, setTick] = useState(0)
  const [forced, setForced] = useState(null)
  const [busy, setBusy] = useState(false)
  const state = useForecast('/usd-live', tick, 60_000)
  const usd = forced || state.data || initialUsd
  if (!usd) return null
  const trend = Array.isArray(usd.trend) ? usd.trend : []
  const diff = Number(usd.change_rial || 0)
  const diffPct = Number(usd.change_pct || 0)
  const arrow = diff > 0 ? '▲' : (diff < 0 ? '▼' : '—')
  const toneCls = diff > 0 ? 'pf-up' : (diff < 0 ? 'pf-down' : 'pf-muted')

  const refreshNow = async () => {
    setBusy(true)
    try {
      const fresh = await request('/usd-live?force=true')
      setForced(fresh)
      setTick((t) => t + 1)
    } catch {
      setTick((t) => t + 1)
    } finally {
      setBusy(false)
    }
  }

  return <div>
    <div className="pf-usd-head">
      <h3>دلار بازار آزاد {usd.live && <span className="pf-live-dot">زنده</span>}</h3>
      <button type="button" className="pf-control pf-btn-sm" disabled={busy} onClick={refreshNow}>
        {busy ? 'در حال دریافت…' : 'به‌روزرسانی لحظه‌ای'}
      </button>
    </div>
    <strong>{currency(usd.rial)}</strong>
    <div className="pf-usd-meta">
      {(diff !== 0 || diffPct !== 0) && (
        <span className={`pf-badge ${toneCls}`}>
          {arrow} {n0(Math.abs(diff) / 10)} تومان ({diff > 0 ? '+' : ''}{faDigits(diffPct)}٪)
        </span>
      )}
      {usd.low_rial && usd.high_rial && (
        <span className="pf-muted">کف {n0(usd.low_rial / 10)} · سقف {n0(usd.high_rial / 10)} تومان</span>
      )}
    </div>
    <p className="pf-muted">
      آخرین نرخ: {stamp(usd.updated_at || usd.date)} · <a href={sourceLink(usd.source)} target="_blank" rel="noreferrer">شبکهٔ اطلاع‌رسانی طلا و ارز (TGJU)</a>
    </p>
    {trend.length > 0 && <Chart labels={trend.map((x) => monthLabel(x.month))}
      series={[{ type: 'line', showSymbol: false, data: trend.map((x) => x.close / 10) }]}
      legend={false} currencyAxis height={190} />}
  </div>
}

export default function ProductionForecast() {
  const { profile } = useAuth()
  const [horizon, setHorizon] = useState(4)
  const [mode, setMode] = useState('production')
  const [code, setCode] = useState(null)
  const [manual, setManual] = useState('')
  const [busy, setBusy] = useState(false)
  const [busyMarket, setBusyMarket] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const table = useRef(null)
  const state = useForecast('/overview', refresh, 45_000)
  const data = state.data
  const job = data?.jobs?.plan
  const marketJob = data?.jobs?.market
  const publish = data?.published_at || ''
  const external = data?.external || {}
  const stock = data?.totals
  const byHorizon = data?.production_by_horizon || {}
  const activeH = byHorizon[String(horizon)]
  const go = (key) => { setMode(key); table.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const trigger = async (endpoint, setPending, message) => {
    setPending(true)
    setManual('')
    try {
      await request(endpoint, { method: 'POST' })
      setManual(message)
      setRefresh((value) => value + 1)
    } catch (error) {
      setManual(error.message)
    } finally {
      setPending(false)
    }
  }
  return <div className="u-page pf-page" dir="rtl">
    <header className="pf-hero">
      <div><h1>Forecast تولید</h1><p>پیش‌بینی فروش و برنامهٔ تولید هیبرید و B2B</p>
        {data && <div className="pf-dates">
          <span><small>بازهٔ تولید</small><b>{monthLabel(data.months[0])} تا {monthLabel(data.months.at(-1))}</b></span>
          <span><small>آخرین ماه کامل فروش</small><b>{monthLabel(data.closed_month)}</b></span>
          <span><small>برداشت موجودی</small><b>{stamp(data.inventory_at)}</b></span>
        </div>}
      </div>
      {profile?.user?.is_admin && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="pf-control pf-primary"
          disabled={busy || job?.state === 'running'}
          onClick={() => trigger('/refresh', setBusy, 'درخواست به‌روزرسانی برنامه ثبت شد.')}>
          {job?.state === 'running' ? 'در حال به‌روزرسانی…' : 'به‌روزرسانی برنامه'}
        </button>
        <button type="button" className="pf-control"
          disabled={busyMarket || marketJob?.state === 'running'}
          onClick={() => trigger('/refresh-market', setBusyMarket, 'درخواست به‌روزرسانی بازار ثبت شد.')}>
          {marketJob?.state === 'running' ? 'در حال به‌روزرسانی بازار…' : 'به‌روزرسانی بازار'}
        </button>
      </div>}
    </header>
    {manual && <div className="pf-state" role="status">{manual}</div>}
    {job?.state === 'failed' && <div className="pf-state pf-warn">{job.message} · آخرین تلاش {stamp(job.at)}</div>}
    {state.error && <LoadState state={state} />}
    {!data ? !state.error && <LoadState state={state} /> : <>
      <div className="pf-market-controls">
        <span className="pf-muted">افق نیاز تولید:</span>
        <Horizon value={horizon} setValue={setHorizon} />
        {horizon > data.months.length && <span className="pf-muted">افق‌های ۶ و ۱۲ ماهه بر مبنای نرخ میانگین {n0(data.months.length)} ماه منتشرشده تخمین زده شده‌اند.</span>}
      </div>
      <div className="pf-metrics">
        <Metric label="نیاز تولید" value={activeH?.need ?? stock.production_need} description={`${n0(activeH?.skus ?? data.production_skus)} کالا نیازمند تولید · ${n0(horizon)} ماهه`} tone="mint" onClick={() => go('production')} />
        <Metric label="موجودی کالا" value={stock.factory_stock_1_4 + stock.branch_stock}
          description={`کارخانه ${n0(stock.factory_stock_1_4)} · شعب ${n0(stock.branch_stock)}`} tone="blue" onClick={() => go('inventory')} />
        <Metric label="پیش‌بینی فروش" value={activeH?.demand ?? stock.demand_3m} description={`افق ${n0(horizon)} ماهه`} tone="violet" onClick={() => go('demand')} />
        <Metric label="ذخیرهٔ اطمینان" value={activeH?.safety ?? stock[`safety_${horizon}`]} description={`افق ${n0(horizon)} ماهه`} tone="gold" onClick={() => go('safety')} />
      </div>
      {(data.adjustments?.override_count > 0 || data.adjustments?.applied_events_count > 0) && (
        <div className="pf-state pf-badge-ok" role="status">
          تعدیل‌های فعال در اعداد اعمال شده‌اند:
          {data.adjustments.override_count > 0 && ` ${n0(data.adjustments.override_count)} تعدیل توزیع‌کننده (${data.adjustments.override_delta_units > 0 ? '+' : ''}${n0(data.adjustments.override_delta_units)} واحد)`}
          {data.adjustments.applied_events_count > 0 && ` · ${n0(data.adjustments.applied_events_count)} رویداد فعال`}
        </div>
      )}
      <Section title="نیاز تولید به تفکیک افق (۱ تا ۱۲ ماهه)" description="برای انتخاب افق در کل صفحه و جدول کالاها روی هر دکمه یا بازه کلیک کنید."
        action={<Horizon value={horizon} setValue={setHorizon} />}>
        <div className="pf-detail-stats">
          {HORIZONS.map((h) => {
            const item = byHorizon[String(h)]
            return <div key={h} style={h === horizon ? { border: '1px solid var(--u-fin)' } : undefined}>
              <small>{n0(h)} ماهه{item?.estimated ? ' (تخمینی)' : ''}</small>
              <strong>{n0(item?.need ?? 0)}</strong>
              <small>{n0(item?.skus ?? 0)} کالا</small>
            </div>
          })}
        </div>
        <Chart labels={HORIZONS.map((h) => `${n0(h)} ماهه`)}
          series={[{ name: 'نیاز تولید', data: HORIZONS.map((h) => ({ value: byHorizon[String(h)]?.need ?? 0,
            itemStyle: { color: h === horizon ? '#22c9b5' : '#628197' } })) }]} legend={false} height={190} />
      </Section>
      <div className="pf-analytics-grid">
        <Section title="پیش‌بینی فروش ماهانه" description="هیبرید از فروش شعب کارآمد و B2B از فروش بیرون شبکه در راهکاران محاسبه می‌شود.">
          <Chart labels={data.monthly.map((x) => monthLabel(x.month))} series={[
            { name: 'هیبرید', data: data.monthly.map((x) => x.hybrid) },
            { name: 'B2B', data: data.monthly.map((x) => x.b2b) },
          ]} />
        </Section>
        <Section title="ذخیرهٔ اطمینان" description="براساس خطای تاریخی هر کالا و کلاس آن در دو کانال."
          action={<Horizon value={horizon} setValue={setHorizon} />}>
          <Chart labels={HORIZONS.map((h) => `${n0(h)} ماه`)}
            series={[{ data: HORIZONS.map((h) => ({ value: stock[`safety_${h}`],
              itemStyle: { color: h === horizon ? '#f4b751' : '#628197' } })) }]} legend={false} height={184} />
          <p className="pf-muted">هدف خدمت کلاس A برابر ۹۵٪ و کلاس B برابر ۹۰٪ است؛ این اهداف تضمین نیستند. {data.safety?.method === 'joint_empirical_3m' ? 'ذخیرهٔ سه‌ماهه از خطاهای تجمعی مشترک دو کانال برآورد شده است.' : 'روش فعلی مبتنی بر RMSE است و پوشش آن تأیید نشده است.'} افق‌های دیگر با جذر زمان تخمین زده می‌شوند و پوشش آن‌ها ارزیابی نشده است.</p>
          {data.safety?.validation?.filter((row) => row.method === 'joint_empirical').map((row) => <p className="pf-muted" key={row.class}>پوشش مشاهده‌شدهٔ کلاس {row.class}: {n0(row.coverage * 100)}٪ در {n0(row.validation_observations)} مشاهدهٔ تاریخی</p>)}
        </Section>
      </div>
      {data.review_skus > 0 && <div className="pf-state pf-warn">{n0(data.review_skus)} کالای نیازمند تولید، موجودی یا وضعیت یا سابقهٔ خطای ناقص دارند. جزئیات در فهرست کالاها آمده است.</div>}
      <CategoryProduction refresh={publish} />
      <ProductTable mode={mode} setMode={setMode} horizon={horizon} refresh={publish} onProduct={setCode} tableRef={table} />
      <DistributorForecast isAdmin={Boolean(profile?.user?.is_admin)} refresh={refresh} onUpdated={() => setRefresh((v) => v + 1)} />
      <AccuracyTracker refresh={`${publish}-${refresh}`} />
      <Section title="شاخص‌های بیرونی" description="برای تحلیل بازار، آفرها و مقایسه با پیش‌بینی">
        <div className="pf-external">
          <LiveUsdCard initialUsd={external.usd} />
          <div><h3>تقویم پروموشن‌های اعلام‌شده</h3>
            {external.campaign_months?.length ? <ul className="pf-campaigns">{external.campaign_months.map((row) =>
              <li key={row.campaign_month}><span>{monthLabel(row.campaign_month)}</span><b>{n0(row.size)} شرط آفر</b></li>)}</ul> :
              <p className="pf-muted">تقویم وارد نشده است.</p>}
            <p className="pf-muted">منبع، نامه‌های واحد فروش است. برای لحاظ کردن اثر کمپین یا تغییر قیمت، از فرم رویدادهای زیر استفاده کنید.</p>
          </div>
          <PlannedEventsCard months={data.months} isAdmin={Boolean(profile?.user?.is_admin)} refresh={refresh} onUpdated={() => setRefresh((v) => v + 1)} />
        </div>
      </Section>
      <RivalMarket refresh={data.jobs?.market?.at || refresh} />
      <Section title="منابع و زمان به‌روزرسانی">
        <div className="pf-schedules">
          <div><b>کارآمد</b><span>فروش خالص، کالا و برند، تخفیف و گردش موجودی، موجودی هر شعبه</span></div>
          <div><b>راهکاران</b><span>فاکتورهای B2B، برگشتی قطعی، دریافت از تولید و موجودی انبارهای ۱ تا ۴</span></div>
          <div><b>برنامهٔ انتشار</b><span>{data.scheduler.enabled ? 'موجودی هر روز ۰۶:۱۵ تهران. بازآموزی از روز سوم ماه شمسی پس از بسته‌شدن فروش. قیمت بازار شنبه ۰۹:۱۵.' : 'زمان‌بندی خودکار در تنظیمات سرور غیرفعال است.'}</span></div>
          <div><b>آخرین آموزش</b><span>{stamp(data.model_at)} · آخرین انتشار {stamp(publish)}</span></div>
        </div>
        {data.jobs?.market?.state === 'failed' && <p className="pf-muted">{data.jobs.market.message} · {stamp(data.jobs.market.at)}</p>}
      </Section>
      {code && <ProductDialog key={code} code={code} overview={data} onClose={() => setCode(null)} />}
    </>}
  </div>
}
