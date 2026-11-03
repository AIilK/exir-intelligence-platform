import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useApp, useRkFetch, fmtMoney, fmtInt, faDigits, UNITS, fullTitle } from '../lib.jsx'
import { Card, Loading, ErrorBox, MultiSelect } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { buildXlsx } from '../xlsx.js'
import { CustomerDetail, ProductFilter, monthLabel } from './Rahkaran.jsx'

// شیت‌های Customer Brand و Total report فایل B2B-Sales Report با داده لایو راهکاران
const q = (o) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(o)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else if (v) p.set(k, v)
  }
  return p.toString()
}

/** مقدار سلول: صفر کم‌رنگ، مثل خانه‌های خالی اکسل */
function Num({ v, type, unit }) {
  if (!v) return <span className="rk-zero">۰</span>
  return <span title={fullTitle(v, type === 'qty' ? 'int' : 'money')}>{type === 'qty' ? fmtInt(v) : fmtMoney(v, unit)}</span>
}

function download(name, headers, rows) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(buildXlsx(headers, rows, name))
  a.download = `${name}.xlsx`
  a.click()
  URL.revokeObjectURL(a.href)
}

function UnitSelect() {
  const { unit, setUnit } = useApp()
  return (
    <label className="unit-select">
      <span className="ms-label">واحد مبالغ</span>
      <select value={unit} onChange={(e) => setUnit(e.target.value)}>
        {Object.entries(UNITS).map(([k, u]) => <option key={k} value={k}>{u.label}</option>)}
      </select>
    </label>
  )
}

function Live({ data }) {
  return (
    <span className={`rk-live ${data.live ? 'on' : ''}`} title={`خوانده‌شده: ${data.fetched}`}>
      {data.live ? 'لایو' : `بروزرسانی ${faDigits((data.fetched || '').slice(11, 16))}`}
    </span>
  )
}

/** پرونده یک کد مشتری زیر جدول */
function Detail({ code, period, products, onClose }) {
  const nav = useNavigate()
  const ref = useRef(null)
  useEffect(() => { ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [code])
  return (
    <div ref={ref} className="rk-anchor">
      <CustomerDetail key={code} code={code} period={period} products={products} onClose={onClose}
        onProvince={(p) => nav(`/rahkaran?province=${encodeURIComponent(p)}`)} />
    </div>
  )
}

// ---------------------------------------------------------------- Customer Brand
export function CustomerBrand() {
  const { unit } = useApp()
  const [sp, setSp] = useSearchParams()
  const period = sp.get('period') || 'YTD'
  const cat = sp.get('cat') || ''
  const products = sp.getAll('product')
  const [search, setSearch] = useState('')
  const [onlyActive, setOnlyActive] = useState(false)
  const [sel, setSel] = useState(null)
  // مرتب‌سازی با کلیک روی سرستون: col = ستون متنی (province / code / short / brand) یا «برند|معیار» (مثل Total|cash)
  const [sort, setSort] = useState(null)
  const set = (k, v) => {
    const n = new URLSearchParams(sp)
    n.delete(k)
    ;(Array.isArray(v) ? v : [v]).filter(Boolean).forEach((x) => n.append(k, x))
    setSp(n)
  }
  const { data, loading, error } = useRkFetch(`/api/rk_sales/customer_brand?${q({ period, cat, product: products })}`)
  const rows = useMemo(() => {
    const r = (data?.rows || []).filter((x) => (!onlyActive || x.req || x.net || x.qty)
      && (!search || `${x.short} ${x.name} ${x.province} ${x.code} ${x.brand}`.includes(search.trim())))
    if (!sort) return r
    const [b, k] = sort.col.split('|')
    const val = (x) => (k ? (b === 'Total' ? x[k] : x.brands[b]?.[k]) : x[b])
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...r].sort((x, y) => {
      const a = val(x), c = val(y)
      if (a == null || a === '') return 1  // خانه خالی (برند دیگر) همیشه آخر
      if (c == null || c === '') return -1
      return (typeof a === 'number' ? a - c : String(a).localeCompare(String(c), 'fa')) * dir
    })
  }, [data, onlyActive, search, sort])
  // کلیک اول: عددی نزولی، متنی صعودی؛ کلیک دوم برعکس
  const toggleSort = (col, numeric) => setSort((s) => (s?.col === col
    ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: numeric ? 'desc' : 'asc' }))
  const arrow = (col) => (sort?.col === col ? <span className="sort">{sort.dir === 'desc' ? ' ▼' : ' ▲'}</span> : null)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const brands = data.brands
  const open = (r) => setSel(r.code)
  const metrics = [['req', 'ریال ناخالص درخواست'], ['net', 'ریال خالص فاکتور'], ['qty', 'فروش تعدادی']]
  // بلوک «جمع» هر کد مشتری تخفیف نقدی و جمع کل (خالص + تخفیف نقدی) را هم دارد
  const totalMetrics = [metrics[0], metrics[1], ['cash', 'تخفیف نقدی'], ['net_cash', 'جمع کل (خالص + تخفیف نقدی)'], metrics[2]]
  const mfor = (b) => (b === 'Total' ? totalMetrics : metrics)
  const exportXlsx = () => download('Customer Brand',
    [{ label: 'استان', kind: 'text' }, { label: 'کد مشتری', kind: 'text' }, { label: 'نام مشتری', kind: 'text' }, { label: 'برند', kind: 'text' },
      ...['Total', ...brands].flatMap((b) => mfor(b).map(([k, l]) => ({ label: `${b} - ${l}${k === 'qty' ? '' : ` (${UNITS[unit].label})`}`, kind: k === 'qty' ? 'int' : 'dec' })))],
    rows.map((r) => [r.province, r.code, r.short, r.brand, ...[r, ...brands.map((b) => r.brands[b] || {})].flatMap((v, i) =>
      (i ? metrics : totalMetrics).map(([k]) => (k === 'qty' ? v[k] || 0 : Math.round(((v[k] || 0) / UNITS[unit].div) * 10) / 10)))]))
  const periodText = data.period === 'YTD' ? 'از ابتدای سال' : monthLabel(data.period)
  return (
    <>
      <PageHead title="مشتری × برند (Customer Brand)"
        desc="هر کد مشتری در یک سطر (نماینده‌ای که با چند برند کار می‌کند برای هر برند کد و سطر جدا دارد): ناخالص درخواست فروش، خالص فاکتور و فروش تعدادی؛ لایو از راهکاران">
        <div className="rk-controls">
          <label className="unit-select">
            <span className="ms-label">ماه</span>
            <select value={data.period} onChange={(e) => set('period', e.target.value === 'YTD' ? null : e.target.value)}>
              {data.periods.map((p) => <option key={p.value} value={p.value}>{p.value === 'YTD' ? 'YTD (از ابتدای سال)' : monthLabel(p.value)}</option>)}
            </select>
          </label>
          <label className="unit-select">
            <span className="ms-label">گروه کالا</span>
            <select value={cat} onChange={(e) => set('cat', e.target.value)}>
              <option value="">Total (همه)</option>
              {data.cat_list.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <ProductFilter value={products} onChange={(v) => set('product', v)} />
          <UnitSelect />
          <Live data={data} />
        </div>
      </PageHead>
      <Card title={`فروش نمایندگان به تفکیک برند — ${periodText}${cat ? ` — ${cat}` : ''}`}
        subtitle="روی هر سطر کلیک کنید تا پرونده همان کد مشتری (روند، کالاها، فاکتورها و درخواست‌ها) باز شود">
        <div className="report-tools">
          <input className="input" placeholder="جستجوی نام، کد، برند یا استان…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <label className="small"><input type="checkbox" checked={onlyActive} onChange={(e) => setOnlyActive(e.target.checked)} /> فقط نمایندگان دارای فعالیت</label>
          <span className="muted small">{fmtInt(rows.length)} کد مشتری</span>
          <div className="spacer" />
          <button className="btn ghost sm" onClick={exportXlsx}>خروجی اکسل</button>
        </div>
        <div className="tree-scroll">
          <table className="tree dense rk-xtable">
            <thead>
              <tr>
                {[['province', 'استان'], ['code', 'کد مشتری'], ['short', 'نام مشتری'], ['brand', 'برند']].map(([col, l]) => (
                  <th key={col} rowSpan={2} className={col === 'short' ? 'rk-name' : ''} title="برای مرتب‌سازی کلیک کنید"
                    onClick={() => toggleSort(col, false)}>{l}{arrow(col)}</th>
                ))}
                {['Total', ...brands].map((b) => <th key={b} colSpan={mfor(b).length} className="grp">{b === 'Total' ? 'جمع' : b}</th>)}
              </tr>
              <tr>
                {['Total', ...brands].map((b) => mfor(b).map(([k, l]) => (
                  <th key={b + k} className="num" title="برای مرتب‌سازی کلیک کنید" onClick={() => toggleSort(`${b}|${k}`, true)}>
                    {l}{arrow(`${b}|${k}`)}
                  </th>
                )))}
              </tr>
            </thead>
            <tbody>
              <tr className="rk-total">
                <td colSpan={4} className="rk-name">جمع ({UNITS[unit].label})</td>
                {[data.total, ...brands.map((b) => data.brand_totals[b])].map((v, i) => (i ? metrics : totalMetrics).map(([k]) => (
                  <td key={i + k} className="num"><Num v={v[k]} type={k} unit={unit} /></td>
                )))}
              </tr>
              {rows.map((r) => (
                <tr key={r.key} className={`clickable${sel === r.code ? ' active-row' : ''}`} onClick={() => open(r)}>
                  <td>{r.province}</td>
                  <td>{faDigits(r.code)}</td>
                  <td className="rk-name" title={r.name}>{r.short} <span className="muted small">{r.city}</span></td>
                  <td>{r.brand}</td>
                  {totalMetrics.map(([k]) => <td key={k} className="num rk-sum"><Num v={r[k]} type={k} unit={unit} /></td>)}
                  {brands.map((b) => metrics.map(([k]) => (
                    <td key={b + k} className={`num${r.brands[b] ? '' : ' rk-na'}`}>
                      {r.brands[b] ? <Num v={r.brands[b][k]} type={k} unit={unit} /> : ''}
                    </td>
                  )))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {sel && <Detail code={sel} period={data.period} products={products} onClose={() => setSel(null)} />}
    </>
  )
}

// ---------------------------------------------------------------- Total report
const BLOCKS = [['req', 'فروش ریالی ناخالص (درخواست)'], ['gross', 'فروش ریالی ناخالص'], ['net', 'فروش ریالی خالص'], ['qty', 'فروش تعدادی']]

export function TotalReport() {
  const { unit } = useApp()
  const [sp, setSp] = useSearchParams()
  const day = sp.get('day') || ''
  const month = sp.get('month') || ''
  const cats = sp.getAll('cat')
  const products = sp.getAll('product')
  const [closed, setClosed] = useState(() => new Set())
  const [sel, setSel] = useState(null)
  // مرتب‌سازی با کلیک روی سرستون: برندها (بر اساس جمع برند) و نمایندگان داخل هر برند هر دو مرتب می‌شوند
  const [sort, setSort] = useState(null)
  const setParam = (k, v) => {
    const n = new URLSearchParams(sp)
    n.delete(k)
    ;(Array.isArray(v) ? v : [v]).filter(Boolean).forEach((x) => n.append(k, x))
    setSp(n)
  }
  const { data, loading, error } = useRkFetch(`/api/rk_sales/total_report?${q({ day, month, cat: cats, product: products })}`)
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const blocks = [['day', `روز ${faDigits(data.day)}`], ['mtd', `ماه ${monthLabel(data.month)}`], ['ytd', `از ابتدای سال ${faDigits(data.day.slice(0, 4))}`]]
  const toggle = (b) => setClosed((s) => { const n = new Set(s); n.has(b) ? n.delete(b) : n.add(b); return n })
  // col: 'brand' | 'short' | «بلوک|معیار» (مثل ytd|net) | «cat|گروه|معیار»
  const toggleSort = (col, numeric) => setSort((s) => (s?.col === col
    ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: numeric ? 'desc' : 'asc' }))
  const arrow = (col) => (sort?.col === col ? <span className="sort">{sort.dir === 'desc' ? ' ▼' : ' ▲'}</span> : null)
  const sortVal = (v, label) => {
    if (!sort) return null
    const p = sort.col.split('|')
    if (p[0] === 'cat') return v.cats[p[1]]?.[p[2]]
    if (p.length === 2) return v[p[0]][p[1]]
    return p[0] === 'brand' ? label : v.short
  }
  const sorted = (list, label) => {
    if (!sort) return list
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...list].sort((x, y) => {
      const a = sortVal(x, label(x)), c = sortVal(y, label(y))
      if (a == null) return c == null ? 0 : 1
      if (c == null) return -1
      return (typeof a === 'number' ? a - c : String(a).localeCompare(String(c), 'fa')) * dir
    })
  }
  // مرتب‌سازی بر اساس نام مشتری فقط داخل برندهاست؛ ترتیب برندها همان می‌ماند
  const groups = sort?.col === 'short' ? data.groups : sorted(data.groups, (g) => g.brand)
  const sth = (col, numeric) => ({ title: 'برای مرتب‌سازی کلیک کنید', onClick: () => toggleSort(col, numeric) })
  const allClosed = closed.size === data.groups.length
  const cells = (v) => [
    ...blocks.flatMap(([bk]) => BLOCKS.map(([k]) => <td key={bk + k} className={`num${k === 'req' ? ' rk-blk' : ''}`}><Num v={v[bk][k]} type={k} unit={unit} /></td>)),
    ...data.cats.flatMap((c, i) => ['net', 'qty'].map((k) => (
      <td key={c + k} className={`num${i === 0 && k === 'net' ? ' rk-blk' : ''}`}><Num v={v.cats[c][k]} type={k} unit={unit} /></td>
    ))),
  ]
  const exportXlsx = () => {
    const money = (x) => Math.round((x / UNITS[unit].div) * 10) / 10
    const vals = (v) => [...blocks.flatMap(([bk]) => BLOCKS.map(([k]) => (k === 'qty' ? v[bk][k] : money(v[bk][k])))),
      ...data.cats.flatMap((c) => [money(v.cats[c].net), v.cats[c].qty])]
    download('Total report',
      [{ label: 'برند', kind: 'text' }, { label: 'نام مشتری', kind: 'text' },
        ...blocks.flatMap(([, bl]) => BLOCKS.map(([k, l]) => ({ label: `${bl} - ${l}`, kind: k === 'qty' ? 'int' : 'dec' }))),
        ...data.cats.flatMap((c) => [{ label: `${c} - فروش ریالی خالص`, kind: 'dec' }, { label: `${c} - فروش تعدادی`, kind: 'int' }])],
      [...data.groups.flatMap((g) => [[g.brand, '', ...vals(g)], ...g.rows.map((r) => [g.brand, r.short, ...vals(r)])]),
        ['Total', '', ...vals(data.total)]])
  }
  return (
    <>
      <PageHead title="گزارش کل (Total report)"
        desc="برای هر برند جمع برند و نمایندگانش: فروش یک روز، یک ماه و از ابتدای سال، و فروش سال در گروه‌های کالا؛ لایو از راهکاران">
        <div className="rk-controls">
          <label className="unit-select">
            <span className="ms-label">روز</span>
            <select value={data.day} onChange={(e) => setParam('day', e.target.value)}>
              {data.days.map((d) => <option key={d} value={d}>{faDigits(d)}</option>)}
            </select>
          </label>
          <label className="unit-select">
            <span className="ms-label">ماه</span>
            <select value={data.month} onChange={(e) => setParam('month', e.target.value)}>
              {data.months.map((m) => <option key={m.value} value={m.value}>{monthLabel(m.value)}</option>)}
            </select>
          </label>
          <MultiSelect label="گروه‌های کالا" value={cats} onChange={(v) => setParam('cat', v)}
            options={data.cat_list.map((c) => ({ value: c, label: c }))} />
          <ProductFilter value={products} onChange={(v) => setParam('product', v)} />
          <UnitSelect />
          <Live data={data} />
        </div>
      </PageHead>
      <Card title="گزارش فروش برند ← نماینده"
        subtitle={`مبالغ به ${UNITS[unit].label}؛ گروه‌های کالا از ابتدای سال. روی برند برای بستن/باز کردن و روی نماینده برای پرونده‌اش کلیک کنید`}
        actions={<>
          <button className="btn ghost sm" onClick={() => setClosed(allClosed ? new Set() : new Set(data.groups.map((g) => g.brand)))}>
            {allClosed ? 'باز کردن همه برندها' : 'فقط جمع برندها'}
          </button>
          <button className="btn ghost sm" onClick={exportXlsx}>خروجی اکسل</button>
        </>}>
        <div className="tree-scroll">
          <table className="tree dense rk-xtable">
            <thead>
              <tr>
                <th rowSpan={2} {...sth('brand', false)}>برند{arrow('brand')}</th>
                <th rowSpan={2} className="rk-name" {...sth('short', false)}>نام مشتری{arrow('short')}</th>
                {blocks.map(([k, l]) => <th key={k} colSpan={4} className="grp">{l}</th>)}
                {data.cats.map((c) => <th key={c} colSpan={2} className="grp">{c}</th>)}
              </tr>
              <tr>
                {blocks.map(([bk]) => BLOCKS.map(([k, l]) => (
                  <th key={bk + k} className={`num${k === 'req' ? ' rk-blk' : ''}`} {...sth(`${bk}|${k}`, true)}>{l}{arrow(`${bk}|${k}`)}</th>
                )))}
                {data.cats.map((c, i) => [['net', 'فروش ریالی خالص'], ['qty', 'فروش تعدادی']].map(([k, l], j) => (
                  <th key={c + k} className={`num${i === 0 && j === 0 ? ' rk-blk' : ''}`} {...sth(`cat|${c}|${k}`, true)}>{l}{arrow(`cat|${c}|${k}`)}</th>
                )))}
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <Fragment key={g.brand}>
                  <tr className="rk-brand clickable" onClick={() => toggle(g.brand)}>
                    <td><span className="tree-toggle">{closed.has(g.brand) ? '◂' : '▾'}</span>{g.brand}</td>
                    <td className="rk-name muted small">{fmtInt(g.rows.length)} کد مشتری</td>
                    {cells(g)}
                  </tr>
                  {!closed.has(g.brand) && sorted(g.rows, () => g.brand).map((r) => (
                    <tr key={r.code} className={`clickable${sel?.code === r.code ? ' active-row' : ''}`}
                      onClick={() => setSel({ code: r.code, short: r.short })}>
                      <td className="muted small">{g.brand}</td>
                      <td className="rk-name" title={r.name}>{r.short} <span className="muted small">{r.city} · کد {faDigits(r.code)}</span></td>
                      {cells(r)}
                    </tr>
                  ))}
                </Fragment>
              ))}
              <tr className="rk-total">
                <td>Total</td><td className="rk-name" />
                {cells(data.total)}
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
      {sel && <Detail code={sel.code} period="YTD" products={products} onClose={() => setSel(null)} />}
    </>
  )
}
