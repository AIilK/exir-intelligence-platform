import { useEffect, useMemo, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { useAuth } from '@finance/auth/auth.tsx'
import { faDigits, monthName, n0, qs } from '../data.js'
import './productionForecast.css'

const API = '/api/v1/forecast'
const HORIZONS = [1, 3, 6, 12]
const MODES = { production: 'نیاز تولید', inventory: 'موجودی کالا', demand: 'پیش‌بینی فروش', safety: 'ذخیرهٔ اطمینان' }
const CATEGORIES = { 'hair color': 'رنگ مو', oxidant: 'اکسیدان', 'hair spray': 'اسپری مو', 'bleach powder': 'پودر دکلره' }
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
    setValue({ data: null, error: '', loading: true })
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
  return <div className="pf-segments" aria-label="افق ذخیرهٔ اطمینان">
    {HORIZONS.map((h) => <button key={h} type="button" aria-pressed={value === h} onClick={() => setValue(h)}>
      {h === 12 ? 'یک‌ساله' : h === 1 ? 'ماهانه' : `${n0(h)} ماهه`}
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
          <caption>پیش‌بینی فروش به تفکیک ماه</caption>
          <thead><tr><th>ماه</th><th>هیبرید</th><th>B2B</th><th>مجموع</th></tr></thead>
          <tbody>{overview.months.map((m) => <tr key={m}><td>{monthLabel(m)}</td><td>{n0(row[`hybrid_${m}`])}</td>
            <td>{n0(row[`b2b_${m}`])}</td><td>{n0(row[`hybrid_${m}`] + row[`b2b_${m}`])}</td></tr>)}</tbody>
        </table></div> : <p className="pf-muted">این کالا فقط در دادهٔ موجودی ثبت شده است.</p>}
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
  const size = 20
  useEffect(() => {
    const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0) }, 200)
    return () => clearTimeout(timer)
  }, [query])
  useEffect(() => setOffset(0), [mode, horizon])
  const state = useForecast(`/products?${qs({ mode, horizon, query: search, offset, limit: size })}`, refresh)
  const metric = mode === 'inventory' ? null : { production: 'production_need', demand: 'demand_3m', safety: `safety_${horizon}` }[mode]
  return <div ref={tableRef} className="pf-scroll-anchor"><Section title="کالاها" description="برای مشاهدهٔ موجودی هر انبار و شعبه، پیش‌بینی ماهانه و ذخیرهٔ اطمینان، روی کالا کلیک کنید."
    action={<input className="pf-control pf-search" aria-label="جستجوی کالا" placeholder="نام کالا، کد یا برند" value={query} onChange={(e) => setQuery(e.target.value)} />}>
    <div className="pf-segments" aria-label="نوع گزارش">
      {Object.entries(MODES).map(([key, label]) => <button type="button" key={key} aria-pressed={mode === key} onClick={() => setMode(key)}>{label}</button>)}
    </div>
    {!state.data?.rows.length || state.error ? <LoadState state={state} /> : <>
      <div className="pf-overflow"><table className="pf-table">
        <thead><tr><th>کالا و کد</th><th>کارخانه</th><th>شعب</th><th>{metric ? MODES[mode] : 'مجموع موجودی'}</th><th>بررسی</th></tr></thead>
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
      <p className="pf-muted">موجودی هر کالا در طول ماه‌ها یک بار مصرف می‌شود. ذخیرهٔ اطمینان با جذر طول بازه افزایش می‌یابد. جمع نیاز ماهانه با برنامهٔ سه‌ماهه منطبق است.</p>
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

export default function ProductionForecast() {
  const { profile } = useAuth()
  const [horizon, setHorizon] = useState(3)
  const [mode, setMode] = useState('production')
  const [code, setCode] = useState(null)
  const [manual, setManual] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const table = useRef(null)
  const state = useForecast('/overview', refresh, 45_000)
  const data = state.data
  const job = data?.jobs?.plan
  const publish = data?.published_at || ''
  const external = data?.external || {}
  const stock = data?.totals
  const go = (key) => { setMode(key); table.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const rerun = async () => {
    setBusy(true)
    setManual('')
    try {
      await request('/refresh', { method: 'POST' })
      setManual('درخواست به‌روزرسانی ثبت شد.')
      setRefresh((value) => value + 1)
    } catch (error) {
      setManual(error.message)
    } finally {
      setBusy(false)
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
      {profile?.user?.is_admin && <button type="button" className="pf-control pf-primary"
        disabled={busy || job?.state === 'running'} onClick={rerun}>{job?.state === 'running' ? 'در حال به‌روزرسانی…' : 'به‌روزرسانی برنامه'}</button>}
    </header>
    {manual && <div className="pf-state" role="status">{manual}</div>}
    {job?.state === 'failed' && <div className="pf-state pf-warn">{job.message} · آخرین تلاش {stamp(job.at)}</div>}
    {state.error && <LoadState state={state} />}
    {!data ? !state.error && <LoadState state={state} /> : <>
      <div className="pf-metrics">
        <Metric label="نیاز تولید" value={stock.production_need} description={`${n0(data.production_skus)} کالا نیازمند تولید`} tone="mint" onClick={() => go('production')} />
        <Metric label="موجودی کالا" value={stock.factory_stock_1_4 + stock.branch_stock}
          description={`کارخانه ${n0(stock.factory_stock_1_4)} · شعب ${n0(stock.branch_stock)}`} tone="blue" onClick={() => go('inventory')} />
        <Metric label="پیش‌بینی فروش" value={stock.demand_3m} description={`بیرون شبکه (B2B) ${n0(stock.b2b_3m)} واحد`} tone="violet" onClick={() => go('demand')} />
        <Metric label="ذخیرهٔ اطمینان" value={stock[`safety_${horizon}`]} description={`افق ${n0(horizon)} ماهه`} tone="gold" onClick={() => go('safety')} />
      </div>
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
          <p className="pf-muted">سطح خدمت هدف برای کلاس A برابر ۹۵٪ و برای کلاس B برابر ۹۰٪ است. ذخیره با جذر طول بازه تغییر می‌کند. برنامهٔ تولید بر مبنای ذخیرهٔ سه‌ماهه است.</p>
        </Section>
      </div>
      {data.review_skus > 0 && <div className="pf-state pf-warn">{n0(data.review_skus)} کالای نیازمند تولید، موجودی یا وضعیت یا سابقهٔ خطای ناقص دارند. جزئیات در فهرست کالاها آمده است.</div>}
      <CategoryProduction refresh={publish} />
      <ProductTable mode={mode} setMode={setMode} horizon={horizon} refresh={publish} onProduct={setCode} tableRef={table} />
      <Section title="شاخص‌های بیرونی" description="برای تحلیل بازار و مقایسه با پیش‌بینی">
        <div className="pf-external">
          {external.usd && <div><h3>دلار بازار آزاد</h3><strong>{currency(external.usd.rial)}</strong>
            <p className="pf-muted">آخرین مشاهده {stamp(external.usd.date)} · <a href={sourceLink(external.usd.source)} target="_blank" rel="noreferrer">شبکهٔ اطلاع‌رسانی طلا و ارز (TGJU)</a></p>
            <Chart labels={external.usd.trend.map((x) => monthLabel(x.month))}
              series={[{ type: 'line', showSymbol: false, data: external.usd.trend.map((x) => x.close / 10) }]}
              legend={false} currencyAxis height={190} />
          </div>}
          <div><h3>تقویم پروموشن‌های اعلام‌شده</h3>
            {external.campaign_months?.length ? <ul className="pf-campaigns">{external.campaign_months.map((row) =>
              <li key={row.campaign_month}><span>{monthLabel(row.campaign_month)}</span><b>{n0(row.size)} شرط آفر</b></li>)}</ul> :
              <p className="pf-muted">تقویم وارد نشده است.</p>}
            <p className="pf-muted">منبع، نامه‌های واحد فروش است. اجرای آفر در فاکتور نیاز به تطبیق دارد. نرخ دلار و تقویم آفر در مدل فعال تولید استفاده نمی‌شوند.</p>
          </div>
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
