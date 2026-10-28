import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApp, useRkFetch, fmtMoney, fmtInt, fmtNum1, fmtPct, faDigits, UNITS, isNum, fullTitle } from '../lib.jsx'
import { Card, Loading, ErrorBox, Empty, MultiSelect } from '../components/ui.jsx'
import { Chart, baseOption, useTheme } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import DateRange from '../components/DateRange.jsx'
import { MONTH_NAMES, addDays, monthEnd, monthLength, parseDate } from '../jalali.js'
import { buildXlsx } from '../xlsx.js'
import { ProductFilter, monthLabel, q } from './Rahkaran.jsx'

// مقایسه فروش راهکاران: چند نماینده / برند / استان / گروه کالا / کالا کنار هم، با تأکید بر فروش تعدادی؛
// هر مورد در بازه اصلی و در صورت انتخاب، در بازه مقایسه (دوره قبل، همین بازه سال قبل یا دلخواه)
const DIMS = [['customer', 'نماینده'], ['brand', 'برند'], ['province', 'استان'], ['cat1', 'گروه کالا'], ['cat2', 'زیرگروه کالا'], ['product', 'کالا']]
const DIM_FA = Object.fromEntries(DIMS)
const MAX = 8
const CMP = [['none', 'بدون دوره مقایسه'], ['prev', 'دوره قبل (هم‌طول)'], ['ly', 'همین بازه سال قبل'], ['custom', 'بازه دلخواه']]
// شاخص نمودارها؛ اندیس در daily = [qty, net, inv]
const METRICS = { qty: { l: 'تعداد (عدد)', i: 0, t: 'int' }, net: { l: 'فروش خالص', i: 1, t: 'money' }, invoices: { l: 'فاکتور', i: 2, t: 'int' } }
const GRANS = [['day', 'روزانه'], ['week', 'هفتگی'], ['month', 'ماهانه']]

// ردیف‌های کارنامه؛ best: کدام جهت بهتر است (برای پررنگ کردن بهترین)
const ROWS = [
  { k: 'qty', l: 'تعداد فروش (عدد)', t: 'int', best: 'max', strong: true, hint: 'جمع MajorUnitQuantity اقلام فاکتور فروش' },
  { k: 'req_qty', l: 'تعداد درخواست فروش', t: 'int', best: 'max', hint: 'درخواست‌های تأییدشده و بسته‌شده' },
  { k: 'fill', l: 'نسبت فاکتور به درخواست (تعدادی)', t: 'pct', best: 'max', hint: 'تعداد فاکتورشده ÷ تعداد درخواست در همان بازه' },
  { k: 'invoices', l: 'تعداد فاکتور', t: 'int', best: 'max', hint: 'ترکیب (مشتری، روز)' },
  { k: 'days', l: 'روزهای دارای فاکتور', t: 'int', best: 'max' },
  { k: 'skus', l: 'تنوع کالای فروخته (SKU)', t: 'int', best: 'max' },
  { k: 'customers', l: 'نمایندگان خریدار (کد)', t: 'int', best: 'max', noDim: 'customer' },
  { k: 'ret_qty', l: 'تعداد برگشتی', t: 'int', best: 'min' },
  { k: 'net', l: 'فروش خالص', t: 'money', best: 'max', strong: true },
  { k: 'net_cash', l: 'جمع کل (خالص + تخفیف نقدی)', t: 'money', best: 'max' },
  { k: 'last_date', l: 'آخرین فاکتور در بازه', t: 'date' },
]

const fmtV = (v, t, unit) => (t === 'int' ? fmtInt(v) : t === 'pct' ? fmtPct(v) : t === 'num1' ? fmtNum1(v)
  : t === 'money' ? fmtMoney(v, unit) : t === 'price' ? fmtMoney(v, 'toman') : t === 'date' ? (v ? faDigits(v) : '—') : v)
const dayShort = (s) => { const d = parseDate(s); return d ? `${faDigits(d.jd)} ${MONTH_NAMES[d.jm - 1]}` : '' }
const dayFull = (s) => { const d = parseDate(s); return d ? `${dayShort(s)} ${faDigits(d.jy)}` : '' }
const rangeText = (r) => (r ? `${dayFull(r[0])} تا ${dayFull(r[1])}` : '')

function daysOf(from, to) {
  const out = []
  for (let d = from; d <= to && out.length < 1200; d = addDays(d, 1)) out.push(d)
  return out
}
/** روزهای بازه ← سطل‌های روز / هفته (از روز اول بازه) / ماه */
function buckets(days, gran) {
  if (gran === 'day') return days.map((d) => ({ label: dayShort(d), title: dayFull(d), days: [d] }))
  if (gran === 'week') {
    const out = []
    for (let i = 0; i < days.length; i += 7) {
      const w = days.slice(i, i + 7)
      out.push({ label: `هفته ${faDigits(out.length + 1)}`, title: `${dayFull(w[0])} تا ${dayFull(w[w.length - 1])}`, days: w })
    }
    return out
  }
  const m = new Map()
  days.forEach((d) => { const k = d.slice(0, 7); m.has(k) ? m.get(k).push(d) : m.set(k, [d]) })
  return [...m].map(([k, ds]) => ({ label: monthLabel(k), title: `${dayFull(ds[0])} تا ${dayFull(ds[ds.length - 1])}`, days: ds }))
}
function shiftYear(s) {
  const d = parseDate(s)
  return `${d.jy - 1}/${String(d.jm).padStart(2, '0')}/${String(Math.min(d.jd, monthLength(d.jy - 1, d.jm))).padStart(2, '0')}`
}
/** تغییر: درصد برای مقادیر، واحد درصد برای نسبت‌ها */
function Delta({ a, b, t, invert, suffix = '' }) {
  if (!isNum(a) || !isNum(b) || t === 'date') return null
  if (t === 'pct') {
    const d = a - b
    if (Math.abs(d) < 0.0005) return <span className="cmp-delta">بدون تغییر{suffix}</span>
    return <span className={`cmp-delta ${(d > 0) !== !!invert ? 'up' : 'down'}`}>{d > 0 ? '▲' : '▼'} {fmtNum1(Math.abs(d) * 100)} واحد درصد{suffix}</span>
  }
  if (!b) return a ? <span className="cmp-delta up">جدید{suffix}</span> : null
  const g = (a - b) / Math.abs(b)
  return <span className={`cmp-delta ${(g >= 0) !== !!invert ? 'up' : 'down'}`}>{g >= 0 ? '▲' : '▼'} {fmtPct(Math.abs(g))}{suffix}</span>
}

function download(name, headers, rows) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(buildXlsx(headers, rows, name))
  a.download = `${name}.xlsx`
  a.click()
  URL.revokeObjectURL(a.href)
}

function Seg({ value, onChange, options }) {
  return (
    <div className="seg" role="radiogroup">
      {options.map(([k, l]) => <button key={k} role="radio" aria-checked={value === k} className={value === k ? 'active' : ''} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  )
}

export default function RahkaranCompare() {
  const { unit, setUnit } = useApp()
  const theme = useTheme()
  const [sp, setSp] = useSearchParams()
  const dim = sp.get('dim') || 'customer'
  const items = sp.getAll('item')
  const cmp = sp.get('cmp') || 'none'
  const bd = sp.get('bd') || (dim === 'cat2' ? 'product' : 'cat2')
  const metric = METRICS[sp.get('m')] ? sp.get('m') : 'qty'
  const gran = sp.get('g') || 'month'
  const cum = sp.get('cum') === '1'
  const scope = { brand: sp.getAll('s_brand'), province: sp.getAll('s_province'), cat1: sp.getAll('s_cat1') }
  const products = sp.getAll('product')
  const [bdQ, setBdQ] = useState('')
  const [bdAll, setBdAll] = useState(false)
  const set = (patch) => {
    const n = new URLSearchParams(sp)
    for (const [k, v] of Object.entries(patch)) {
      n.delete(k)
      ;(Array.isArray(v) ? v : [v]).filter((x) => x != null && x !== '').forEach((x) => n.append(k, x))
    }
    setSp(n)
  }

  // بازه اصلی از URL؛ بدون آن پیش‌فرض سرور (از ابتدای سال تا امروز)
  const aFrom = sp.get('a_from') || ''
  const aTo = sp.get('a_to') || ''
  let bFrom = '', bTo = ''
  if (aFrom && aTo && cmp === 'prev') { bTo = addDays(aFrom, -1); bFrom = addDays(bTo, -(daysOf(aFrom, aTo).length - 1)) }
  if (aFrom && aTo && cmp === 'ly') { bFrom = shiftYear(aFrom); bTo = shiftYear(aTo) }
  if (cmp === 'custom') { bFrom = sp.get('b_from') || ''; bTo = sp.get('b_to') || '' }
  const url = `/api/rk_sales/compare?${q({ dim, item: items, a_from: aFrom, a_to: aTo, b_from: bFrom, b_to: bTo, bd,
    s_brand: scope.brand, s_province: scope.province, s_cat1: scope.cat1, product: products })}`
  const { data, loading, error } = useRkFetch(url)

  // بدون بازه در URL، بازه پیش‌فرض سرور برای محاسبه دوره مقایسه در URL نوشته می‌شود
  const needDefault = data && !aFrom && cmp !== 'none' && cmp !== 'custom'
  useEffect(() => { if (needDefault) set({ a_from: data.a[0], a_to: data.a[1] }) }, [needDefault])  // eslint-disable-line react-hooks/exhaustive-deps

  const today = data?.today
  const meta = useMemo(() => {
    if (!data) return null
    const cur = today.slice(0, 7)
    const first = data.since || data.dates[0] || `${today.slice(0, 4)}/01/01`
    const months = []
    for (let m = cur; m >= first.slice(0, 7);) {
      const [y, mm] = m.split('/').map(Number)
      months.push({ month: m, from: `${m}/01`, to: m === cur ? today : monthEnd(y, mm), loaded: true })
      m = mm === 1 ? `${y - 1}/12` : `${y}/${String(mm - 1).padStart(2, '0')}`
    }
    return { file: { month: cur, today, month_to: today, months }, dates: data.dates }
  }, [data, today])

  const t = theme
  const color = (i) => t.series[i % t.series.length]
  const view = useMemo(() => {
    if (!data) return null
    const aDays = daysOf(data.a[0], data.a[1])
    const bDays = data.b ? daysOf(data.b[0], data.b[1]) : []
    return { aDays, bDays, aB: buckets(aDays, gran), bB: buckets(bDays, gran) }
  }, [data, gran])

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  // بدون انتخاب کاربر هیچ موردی نمایش داده نمی‌شود (پیش‌فرض ندارد)
  const its = items.length ? data.items : []
  const hasB = !!data.b
  const rangeA = (f) => set({ a_from: f.date_from || meta.file.months[0].from, a_to: f.date_to || today })
  const rangeB = (f) => set({ b_from: f.date_from || meta.file.months[0].from, b_to: f.date_to || today })
  const setItems = (v) => set({ item: v.slice(0, MAX) })
  const rows = ROWS.filter((r) => r.noDim !== dim)
  const val = (r, x, side) => (side === 'b' ? x.b : x.a)?.[r.k] ?? null
  // ستون‌های جدول: هر مورد در بازه اصلی و با دوره مقایسه، همان مورد در دوره مقایسه کنارش (یک مورد = دو ستون)
  const cols = its.flatMap((x, i) => [{ x, i, side: 'a' }, ...(hasB ? [{ x, i, side: 'b' }] : [])])
  const bestOf = (r) => {
    if (!r.best || cols.length < 2) return null
    const vs = cols.map((c) => val(r, c.x, c.side)).filter(isNum)
    if (vs.length < 2 || new Set(vs).size < 2) return null
    return r.best === 'max' ? Math.max(...vs) : Math.min(...vs)
  }
  const M = METRICS[metric]
  const mFmt = (v) => (M.t === 'money' ? fmtMoney(v, unit) : fmtInt(v))
  const sumDays = (x, days) => days.reduce((s, d) => s + (x.daily[d]?.[M.i] || 0), 0)
  const seriesOf = (x, bks) => {
    let acc = 0
    return bks.map((b) => { const v = sumDays(x, b.days); acc += v; return cum ? acc : v })
  }

  // ---------------- تفکیک
  const bdRows = data.breakdown.filter((r) => !bdQ || `${r.label} ${r.sub} ${r.key}`.includes(bdQ.trim()))
  const bdShown = bdAll ? bdRows : bdRows.slice(0, 25)
  const tot = (x, side) => (side === 'b' ? x.b : x.a)?.qty

  const exportScore = () => download('مقایسه فروش',
    [{ label: 'شاخص', kind: 'text' }, ...its.flatMap((x) => [{ label: `${x.label} — دوره اصلی`, kind: 'dec' },
      ...(hasB ? [{ label: `${x.label} — دوره مقایسه`, kind: 'dec' }] : [])])],
    rows.map((r) => [`${r.l}${r.t === 'money' ? ` (${UNITS[unit].label})` : r.t === 'price' ? ' (تومان)' : r.t === 'pct' ? ' (٪)' : ''}`,
      ...its.flatMap((x) => [val(r, x, 'a'), ...(hasB ? [val(r, x, 'b')] : [])].map((v) => (r.t === 'date' ? v || ''
        : !isNum(v) ? '' : r.t === 'money' ? Math.round((v / UNITS[unit].div) * 10) / 10 : r.t === 'price' ? Math.round(v / 10)
          : r.t === 'pct' ? Math.round(v * 1000) / 10 : Math.round(v * 10) / 10)))]))
  const exportBd = () => download(`تفکیک ${DIM_FA[data.bd]}`,
    [{ label: DIM_FA[data.bd], kind: 'text' }, ...its.flatMap((x) => [{ label: `${x.label} — تعداد`, kind: 'int' },
      { label: `${x.label} — خالص (${UNITS[unit].label})`, kind: 'dec' }, ...(hasB ? [{ label: `${x.label} — تعداد دوره مقایسه`, kind: 'int' }] : [])])],
    bdRows.map((r) => [r.label, ...its.flatMap((x) => [r.qty[x.key] || 0, Math.round(((r.net[x.key] || 0) / UNITS[unit].div) * 10) / 10,
      ...(hasB ? [r.bqty[x.key] || 0] : [])])]))

  // ---------------- فیلترهای فعال (هرکدام جدا قابل حذف) و حذف همه
  const listChips = (k, label, vs) => vs.map((v) => ({ id: `${k}:${v}`, l: `${label}: ${v}`, clear: { [k]: vs.filter((y) => y !== v) } }))
  const actives = [
    ...(items.length ? [{ id: 'item', l: `${faDigits(items.length)} ${DIM_FA[dim]} انتخابی`, clear: { item: [] } }] : []),
    ...(aFrom ? [{ id: 'a', l: `بازه: ${rangeText(data.a)}`, clear: { a_from: null, a_to: null } }] : []),
    ...(cmp !== 'none' ? [{ id: 'cmp', l: `مقایسه با ${CMP.find((c) => c[0] === cmp)[1]}`, clear: { cmp: null, b_from: null, b_to: null } }] : []),
    ...listChips('s_brand', 'برند', scope.brand),
    ...listChips('s_province', 'استان', scope.province),
    ...listChips('s_cat1', 'گروه کالا', scope.cat1),
    ...(products.length ? [{ id: 'product', l: `${faDigits(products.length)} کالا`, clear: { product: [] } }] : []),
  ]
  const clearAll = () => set({ item: [], a_from: null, a_to: null, cmp: null, b_from: null, b_to: null,
    s_brand: [], s_province: [], s_cat1: [], product: [] })

  // ---------------- خلاصه به زبان ساده
  const qa = (x) => x.a?.qty || 0
  const ranked = [...its].sort((x, y) => qa(y) - qa(x))
  const maxQty = Math.max(1, ...its.map(qa))
  const growth = (x) => (hasB && x.b?.qty ? qa(x) / x.b.qty - 1 : null)
  const insights = []
  if (its.length > 1 && qa(ranked[0])) {
    const [p, s] = ranked
    insights.push(<>بیشترین فروش تعدادی: <b>{p.label}</b> با {fmtInt(qa(p))} عدد
      {qa(s) > 0 && <> — {fmtPct(qa(p) / qa(s) - 1)} بیشتر از {s.label}</>}</>)
  }
  if (hasB) {
    const gs = its.map((x) => [x, growth(x)]).filter(([, g]) => isNum(g)).sort((a, b) => b[1] - a[1])
    if (gs.length && gs[0][1] > 0) insights.push(<>بیشترین رشد نسبت به دوره مقایسه: <b>{gs[0][0].label}</b> <span className="cmp-delta up">▲ {fmtPct(gs[0][1])}</span></>)
    const w = gs[gs.length - 1]
    if (w && w[1] < 0) insights.push(<>بیشترین افت: <b>{w[0].label}</b> <span className="cmp-delta down">▼ {fmtPct(-w[1])}</span></>)
  }

  const dimOpts = data.options.map((o) => ({ value: o.value, label: o.label, group: `${o.group ? `${o.group} · ` : ''}${fmtInt(o.qty)} عدد` }))
  const bdTop = bdRows.slice(0, 12)

  return (
    <>
      <PageHead title="مقایسه فروش راهکاران"
        desc="چند نماینده، برند، استان، گروه کالا یا کالا را در یک بازه کنار هم بگذارید و در صورت نیاز با دوره قبل یا سال قبل مقایسه کنید؛ تمرکز اصلی روی فروش تعدادی، لایو از راهکاران">
        <div className="rk-controls">
          <label className="unit-select">
            <span className="ms-label">واحد مبالغ</span>
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              {Object.entries(UNITS).map(([k, u]) => <option key={k} value={k}>{u.label}</option>)}
            </select>
          </label>
          <span className={`rk-live ${data.live ? 'on' : ''}`} title={`خوانده‌شده: ${data.fetched}`}>
            {data.live ? 'لایو' : `بروزرسانی ${faDigits((data.fetched || '').slice(11, 16))}`}
          </span>
        </div>
      </PageHead>

      <Card className="cmp-setup" title="تنظیمات مقایسه"
        subtitle="از بالا به پایین پر کنید؛ هر تغییر بلافاصله اعمال می‌شود"
        actions={<button className="btn ghost sm cmp-reset" disabled={!actives.length} onClick={clearAll}
          title="پاک کردن انتخاب‌ها، بازه (از ابتدای سال تا امروز) و محدوده">
          ✕ حذف همه فیلترها{actives.length > 0 && <span className="cmp-count">{faDigits(actives.length)}</span>}</button>}>
        <div className="cmp-step">
          <span className="cmp-step-l">۱. چه چیزی را مقایسه کنید؟</span>
          <Seg value={dim} onChange={(v) => set({ dim: v, item: [], bd: v === bd ? null : bd })} options={DIMS} />
        </div>
        <div className="cmp-step">
          <span className="cmp-step-l">۲. انتخاب {DIM_FA[dim]}‌ها</span>
          <MultiSelect label={`${DIM_FA[dim]} (حداکثر ${faDigits(MAX)})`} value={its.map((x) => x.key)} onChange={setItems} options={dimOpts} />
          <span className="muted small">فهرست به ترتیب تعداد فروش در بازه اصلی است · {fmtInt(data.ranked)} {DIM_FA[dim]} دارای فروش</span>
        </div>
        <div className="cmp-step">
          <span className="cmp-step-l">۳. بازه‌ها</span>
          <DateRange label="بازه اصلی" curHint={null} meta={meta} filters={{ date_from: data.a[0], date_to: data.a[1] }} setFilters={rangeA} />
          <label className="unit-select">
            <span className="ms-label">مقایسه با</span>
            <select value={cmp} onChange={(e) => set({ cmp: e.target.value === 'none' ? null : e.target.value,
              ...(e.target.value === 'custom' && !sp.get('b_from') ? { b_from: data.a[0], b_to: data.a[1] } : {}) })}>
              {CMP.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          {cmp === 'custom' && hasB && <DateRange label="بازه مقایسه" curHint={null} meta={meta} filters={{ date_from: data.b[0], date_to: data.b[1] }} setFilters={rangeB} />}
          {hasB && cmp !== 'custom' && <span className="muted small">دوره مقایسه: {rangeText(data.b)}</span>}
        </div>
        <div className="cmp-step">
          <span className="cmp-step-l">۴. محدوده (اختیاری)</span>
          <MultiSelect label="برند" value={scope.brand} onChange={(v) => set({ s_brand: v })} options={data.scope_lists.brand.map((b) => ({ value: b, label: b }))} />
          <MultiSelect label="استان" value={scope.province} onChange={(v) => set({ s_province: v })} options={data.scope_lists.province.map((b) => ({ value: b, label: b }))} />
          <MultiSelect label="گروه کالا" value={scope.cat1} onChange={(v) => set({ s_cat1: v })} options={data.scope_lists.cat1.map((b) => ({ value: b, label: b }))} />
          <ProductFilter value={products} onChange={(v) => set({ product: v })} />
          {(scope.brand.length + scope.province.length + scope.cat1.length + products.length > 0) &&
            <button className="link" onClick={() => set({ s_brand: [], s_province: [], s_cat1: [], product: [] })}>پاک کردن محدوده</button>}
        </div>
        <div className="cmp-step">
          <span className="cmp-step-l">در حال مقایسه</span>
          <div className="cmp-chips">
            {its.map((x, i) => (
              <span key={x.key} className="cmp-chip" style={{ '--c': color(i) }}>
                <i />{x.label}
                <button aria-label={`حذف ${x.label}`} onClick={() => setItems(its.filter((y) => y.key !== x.key).map((y) => y.key))}>×</button>
              </span>
            ))}
            {!its.length && <span className="muted small">هنوز چیزی انتخاب نشده</span>}
          </div>
        </div>
        {actives.length > 0 && (
          <div className="cmp-step cmp-actives">
            <span className="cmp-step-l">فیلترهای فعال</span>
            <div className="cmp-chips">
              {actives.map((a) => (
                <span key={a.id} className="cmp-chip flt">
                  {a.l}
                  <button aria-label={`حذف ${a.l}`} onClick={() => set(a.clear)}>×</button>
                </span>
              ))}
              <button className="link small" onClick={clearAll}>حذف همه</button>
            </div>
          </div>
        )}
      </Card>

      {!its.length ? <Card><Empty text={`هنوز هیچ ${DIM_FA[dim]} برای مقایسه انتخاب نشده؛ از مرحله ۲ انتخاب کنید.`} />
        {actives.length > 0 && <button className="btn sm" onClick={clearAll}>حذف همه فیلترها</button>}</Card> : <>
        {insights.length > 0 && (
          <div className="cmp-insights">
            <span className="cmp-insights-t">خلاصه</span>
            <ul>{insights.map((n, i) => <li key={i}>{n}</li>)}</ul>
          </div>
        )}

        <div className="cmp-cards">
          {its.map((x, i) => {
            const g = growth(x)
            return (
              <div key={x.key} className="cmp-card" style={{ '--c': color(i) }}>
                <div className="cmp-card-head">
                  <span className="cmp-card-name"><i />{x.label}</span>
                  {x.rank ? <span className="cmp-rank" title={`رتبه در تعداد فروش از ${faDigits(data.ranked)}`}>#{faDigits(x.rank)}</span> : null}
                </div>
                {x.sub && <div className="muted small">{x.sub}</div>}
                <div className="cmp-card-big">{fmtInt(qa(x))} <span>عدد</span></div>
                <div className="cmp-card-bar"><span style={{ width: `${(qa(x) / maxQty) * 100}%` }} /></div>
                {hasB && <div className="cmp-card-meta">
                  {isNum(g) ? <Delta a={qa(x)} b={x.b.qty} t="int" suffix=" نسبت به دوره مقایسه" />
                    : qa(x) > 0 ? <span className="cmp-delta up">جدید</span> : null}
                </div>}
                <div className="cmp-card-foot">
                  <span>فروش خالص <b>{fmtMoney(x.a?.net, unit)}</b></span>
                  <span>فاکتور <b>{fmtInt(x.a?.invoices)}</b></span>
                </div>
              </div>
            )
          })}
        </div>
        <Card title="کارنامه مقایسه"
          subtitle={`${hasB ? `بازه اصلی: ${rangeText(data.a)} · دوره مقایسه: ${rangeText(data.b)}. ` : `${rangeText(data.a)}. `}${cols.length > 1 ? 'بهترین مقدار هر ردیف پررنگ است. ' : ''}مبالغ به ${UNITS[unit].label}`}
          actions={<button className="btn ghost sm" onClick={exportScore}>خروجی اکسل</button>}>
          <div className="tree-scroll">
            <table className="tree dense cmp-table">
              <thead>
                <tr>
                  <th className="rk-name">شاخص</th>
                  {cols.map(({ x, i, side }) => (
                    <th key={`${x.key}-${side}`} className={`num cmp-head${side === 'b' ? ' cmp-head-b' : ''}`} style={{ '--c': color(i) }}>
                      <div className="cmp-head-name">
                        <i />{dim === 'customer' ? <Link to={`/rahkaran?customer=${encodeURIComponent(x.key)}`} title="پرونده نماینده">{x.label}</Link> : x.label}
                      </div>
                      {hasB ? <div className="cmp-period">{side === 'a' ? 'بازه اصلی' : 'دوره مقایسه'} · {rangeText(side === 'a' ? data.a : data.b)}</div>
                        : x.sub && <div className="muted small">{x.sub}</div>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const best = bestOf(r)
                  const bar = cols.length > 1 && r.best === 'max' && ['int', 'num1', 'money'].includes(r.t)
                  const rowMax = bar ? Math.max(0, ...cols.map((c) => val(r, c.x, c.side)).filter(isNum)) : 0
                  return (
                    <tr key={r.k} className={r.strong ? 'cmp-strong' : ''}>
                      <td className="rk-name" title={r.hint}>{r.l}{r.hint && <span className="hint-dot">؟</span>}</td>
                      {cols.map(({ x, i, side }) => {
                        const v = val(r, x, side)
                        return (
                          <td key={`${x.key}-${side}`} className={`num${isNum(best) && v === best ? ' cmp-best' : ''}`}>
                            <div title={fullTitle(v, r.t === 'money' ? 'money' : r.t === 'int' || r.t === 'num1' ? 'int' : null)}>{fmtV(v, r.t, unit)}</div>
                            {bar && rowMax > 0 && isNum(v) && <div className={`cmp-cell-bar${side === 'b' ? ' b' : ''}`} style={{ '--c': color(i) }}><span style={{ width: `${(v / rowMax) * 100}%` }} /></div>}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="cmp-toolbar">
          <span className="ms-label">شاخص نمودارها</span>
          <Seg value={metric} onChange={(v) => set({ m: v === 'qty' ? null : v })} options={Object.entries(METRICS).map(([k, m]) => [k, m.l])} />
          <span className="ms-label">بازه زمانی روند</span>
          <Seg value={gran} onChange={(v) => set({ g: v === 'month' ? null : v })} options={GRANS} />
          <label className="small"><input type="checkbox" checked={cum} onChange={(e) => set({ cum: e.target.checked ? '1' : null })} /> تجمعی</label>
        </div>

        <div className="cmp-grid">
          <Card title={`${M.l} — کنار هم`} subtitle={hasB ? 'میله پررنگ: بازه اصلی · میله کم‌رنگ: دوره مقایسه' : rangeText(data.a)}>
            <Chart height={Math.max(260, its.length * (hasB ? 56 : 40) + 60)} option={(th) => ({
              grid: { left: 12, right: 12, top: 28, bottom: 8, containLabel: true },
              legend: hasB ? { top: 0, right: 0, textStyle: { color: th.text } } : undefined,
              tooltip: { ...baseOption(th).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
                formatter: (ps) => `${ps[0].name}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${mFmt(p.value)}</b>`).join('<br/>') },
              xAxis: { type: 'value', inverse: true, axisLabel: { color: th.text, formatter: mFmt }, splitLine: { lineStyle: { color: th.grid } } },
              yAxis: { type: 'category', position: 'right', inverse: true, data: its.map((x) => x.label),
                axisLabel: { color: th.text, width: 140, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: th.axis } } },
              series: [
                { name: 'بازه اصلی', type: 'bar', barMaxWidth: 16, data: its.map((x, i) => ({ value: sumDays(x, view.aDays), itemStyle: { color: color(i), borderRadius: [4, 0, 0, 4] } })),
                  label: { show: true, position: 'left', color: th.text, formatter: (p) => mFmt(p.value) } },
                ...(hasB ? [{ name: 'دوره مقایسه', type: 'bar', barMaxWidth: 16, data: its.map((x, i) => ({ value: sumDays(x, view.bDays), itemStyle: { color: color(i), opacity: 0.38, borderRadius: [4, 0, 0, 4] } })) }] : []),
              ],
            })} />
          </Card>

          <Card title={`روند ${M.l}${cum ? ' (تجمعی)' : ''}`} subtitle={hasB ? 'خط پر: بازه اصلی · خط‌چین: دوره مقایسه (هم‌تراز از ابتدای هر بازه)' : `${GRANS.find((g) => g[0] === gran)[1]} · ${rangeText(data.a)}`}>
            <Chart height={320} option={(th) => ({
              grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
              legend: { top: 0, right: 0, type: 'scroll', textStyle: { color: th.text } },
              tooltip: { ...baseOption(th).tooltip, trigger: 'axis',
                formatter: (ps) => {
                  const i = ps[0].dataIndex
                  const head = `${view.aB[i]?.title || ''}${hasB && view.bB[i] ? `<br/><span style="opacity:.7">مقایسه: ${view.bB[i].title}</span>` : ''}`
                  return `${head}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${mFmt(p.value)}</b>`).join('<br/>')
                } },
              xAxis: { type: 'category', inverse: true, data: view.aB.map((b) => b.label), axisLabel: { color: th.text },
                axisTick: { show: false }, axisLine: { lineStyle: { color: th.axis } } },
              yAxis: { type: 'value', position: 'right', axisLabel: { color: th.text, formatter: mFmt }, splitLine: { lineStyle: { color: th.grid } } },
              series: [
                ...its.map((x, i) => ({ name: x.label, type: 'line', data: seriesOf(x, view.aB), symbolSize: gran === 'day' ? 0 : 6,
                  lineStyle: { width: 2.2, color: color(i) }, itemStyle: { color: color(i) } })),
                ...(hasB ? its.map((x, i) => ({ name: `${x.label} (مقایسه)`, type: 'line', data: seriesOf(x, view.bB).slice(0, Math.max(view.aB.length, 1)),
                  symbolSize: 0, lineStyle: { width: 1.6, type: 'dashed', color: color(i), opacity: 0.7 }, itemStyle: { color: color(i) } })) : []),
              ],
            })} />
          </Card>
        </div>

        <Card title={`تفکیک به ${DIM_FA[data.bd]}`}
          subtitle={`تعداد فروش هر ${DIM_FA[dim]} در هر ${DIM_FA[data.bd]} و سهم آن از کل تعداد همان ${DIM_FA[dim]}${hasB ? '؛ ستون کم‌رنگ: دوره مقایسه' : ''}`}
          actions={<button className="btn ghost sm" onClick={exportBd}>خروجی اکسل</button>}>
          <div className="report-tools">
            <Seg value={data.bd} onChange={(v) => set({ bd: v })} options={DIMS.filter(([k]) => k !== dim)} />
            <input className="input" placeholder="جستجو…" value={bdQ} onChange={(e) => setBdQ(e.target.value)} />
            <span className="muted small">{fmtInt(bdRows.length)} ردیف</span>
          </div>
          {bdTop.length > 0 && (
            <Chart height={Math.max(240, bdTop.length * (cols.length * 9 + 14) + 60)} option={(th) => ({
              grid: { left: 12, right: 12, top: 28, bottom: 8, containLabel: true },
              legend: { top: 0, right: 0, type: 'scroll', textStyle: { color: th.text } },
              tooltip: { ...baseOption(th).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
                formatter: (ps) => `${ps[0].name}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtInt(p.value)}</b> عدد`).join('<br/>') },
              xAxis: { type: 'value', inverse: true, axisLabel: { color: th.text, formatter: fmtInt }, splitLine: { lineStyle: { color: th.grid } } },
              yAxis: { type: 'category', position: 'right', inverse: true, data: bdTop.map((r) => r.label),
                axisLabel: { color: th.text, width: 170, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { lineStyle: { color: th.axis } } },
              series: cols.map(({ x, i, side }) => ({ name: side === 'b' ? `${x.label} (دوره مقایسه)` : x.label, type: 'bar', barMaxWidth: 10, barGap: '15%',
                data: bdTop.map((r) => (side === 'b' ? r.bqty : r.qty)[x.key] || 0),
                itemStyle: { color: color(i), opacity: side === 'b' ? 0.4 : 1, borderRadius: [3, 0, 0, 3] } })),
            })} />
          )}
          <div className="tree-scroll">
            <table className="tree dense cmp-table">
              <thead>
                <tr>
                  <th className="rk-name">{DIM_FA[data.bd]}</th>
                  {cols.map(({ x, i, side }) => (
                    <th key={`${x.key}-${side}`} className={`num cmp-head${side === 'b' ? ' cmp-head-b' : ''}`} style={{ '--c': color(i) }}>
                      <div className="cmp-head-name"><i />{x.label}</div>
                      <div className="muted small">{hasB ? `${side === 'a' ? 'بازه اصلی' : 'دوره مقایسه'} · ` : ''}تعداد · سهم</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bdShown.map((r) => {
                  const vs = cols.map(({ x, side }) => (side === 'b' ? r.bqty : r.qty)[x.key] || 0)
                  const mx = Math.max(...vs)
                  return (
                    <tr key={r.key}>
                      <td className="rk-name" title={r.sub}>{r.label}{r.sub && <span className="muted small"> {r.sub}</span>}</td>
                      {cols.map(({ x, side }, j) => (
                        <td key={`${x.key}-${side}`} className={`num${cols.length > 1 && vs[j] === mx && mx > 0 ? ' cmp-best' : ''}`}>
                          {vs[j] ? fmtInt(vs[j]) : <span className="rk-zero">۰</span>} <span className="muted small">{tot(x, side) ? fmtPct(vs[j] / tot(x, side)) : ''}</span>
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {bdRows.length > 25 && <button className="link" onClick={() => setBdAll(!bdAll)}>{bdAll ? 'نمایش ۲۵ ردیف اول' : `نمایش همه ${fmtInt(bdRows.length)} ردیف`}</button>}
        </Card>
      </>}
    </>
  )
}
