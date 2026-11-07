import { Component, Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { fmtCompact, fmtInt, fmtMoney, fmtPct, fmtNum1, faDigits, UNITS, fullTitle } from '../lib.jsx'
import { buildXlsx, colName } from '../xlsx.js'

export function Kpi({ label, value, type = 'money', sub, hint, onClick, active, more }) {
  let main, unit = ''
  if (type === 'money') ({ value: main, unit } = fmtCompact(value))
  else if (type === 'pct') main = fmtPct(value)
  else if (type === 'num1') main = fmtNum1(value)
  else main = fmtInt(value)
  // کارت قابل کلیک (مثلاً برای باز کردن فهرست جزئیات)
  const click = onClick ? {
    role: 'button', tabIndex: 0, 'aria-pressed': !!active, onClick,
    onKeyDown: (e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick()),
  } : {}
  return (
    <div className={`kpi${onClick ? ' clickable' : ''}${active ? ' active' : ''}`} title={hint} {...click}>
      <div className="kpi-label">{label}{hint && <span className="hint-dot">؟</span>}</div>
      <div className="kpi-value" title={fullTitle(value, type === 'money' ? 'money' : type === 'pct' ? null : 'int')}>{main}<span className="kpi-unit">{unit}</span></div>
      {sub && <div className="kpi-sub">{sub}</div>}
      {onClick && <div className="kpi-more">{more ?? (active ? 'بستن فهرست ▲' : 'نمایش فهرست ▼')}</div>}
    </div>
  )
}

export function Card({ title, subtitle, children, actions, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Loading() {
  return <div className="state">در حال بارگذاری…</div>
}
export function ErrorBox({ error }) {
  return <div className="state error">{error}</div>
}
export function Empty({ text = 'داده‌ای در محدوده فیلتر وجود ندارد.' }) {
  return <div className="state">{text}</div>
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} role="tab" aria-selected={value === t.value}
          className={value === t.value ? 'active' : ''} onClick={() => onChange(t.value)}>
          {t.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- data table
function cell(v, type, unit) {
  switch (type) {
    case 'money': return fmtMoney(v, unit)
    case 'int': return fmtInt(v)
    case 'pct': return fmtPct(v)
    case 'num1': return fmtNum1(v)
    case 'date': return v ? faDigits(v) : '—'
    default: return v ?? '—'
  }
}
const NUMERIC = new Set(['money', 'int', 'pct', 'num1'])

// مقدار هر خانه در اکسل: عدد (نه متن)، درصد به‌صورت کسر با قالب ٪، مبلغ به واحد انتخاب‌شده
function csvValue(v, type, unit) {
  if (v == null || (typeof v === 'number' && !Number.isFinite(v))) return ''
  switch (type) {
    case 'int': return Math.round(v)
    case 'num1': return Math.round(v * 10) / 10
    case 'pct': return Math.round(v * 100000) / 100000
    case 'money': return wholeUnit(unit) ? Math.round(v / UNITS[unit].div) : Math.round((v / UNITS[unit].div) * 10) / 10
    default: return typeof v === 'boolean' ? (v ? 'بله' : 'خیر') : v
  }
}
const wholeUnit = (unit) => unit === 'rial' || unit === 'toman'

// خروجی اکسل واقعی (xlsx): CSV در اکسل فارسی ستون‌ها را جدا نمی‌کند و چپ‌به‌راست باز می‌شود
// ستون با فرمول در اکسل: xf(ref) متن فرمول (بدون =) با ref(key) = خانه همان سطر در ستون key؛
// ratio: [صورت, مخرج] برای ستون درصد (÷، مخرج صفر = خالی). اگر ستونی که فرمول لازم دارد در خروجی نباشد، مقدار عددی می‌آید.
// exportOnly: ستونی که فقط در اکسل می‌آید (مثلاً ورودی‌های فرمول پورسانت)؛ pctDigits: 2 = درصد با دو رقم اعشار.
// total: ردیف جمع پایین جدول؛ مبلغ و تعداد با SUM، درصدها و متن‌های فرمولی با همان فرمول روی خانه‌های جمع؛
// noTotal: ستونی که در ردیف جمع خالی می‌ماند (مثلاً نرخ سطح که جمع آن معنی ندارد).
// extras: {extraSheets, names} برگه‌ها و نام‌های تعریف‌شده‌ای که فرمول‌ها به آن‌ها ارجاع می‌دهند (مثل برگه «قواعد»).
function toXlsx(rows, allColumns, unit, title, total, extras = {}) {
  // ستون‌های تصویری (csv: false) نمی‌آیند؛ csv می‌تواند تابعی برای متن خوانای ستون‌های نمایشی باشد (مثل وضعیت)
  const columns = allColumns.filter((c) => c.csv !== false)
  const label = (c) => c.label + (c.type === 'money' ? ` (${UNITS[unit].label})` : '')
  const kind = (c) => (c.type === 'int' ? 'int' : c.type === 'pct' ? (c.pctDigits === 2 ? 'pct2' : 'pct')
    : c.type === 'money' ? (wholeUnit(unit) ? 'money' : 'dec') : c.type === 'num1' ? 'dec' : 'text')
  const headers = columns.map((c) => ({ label: label(c), kind: kind(c) }))
  const letter = Object.fromEntries(columns.map((c, i) => [c.key, colName(i)]))
  const formula = (c, row) => {
    const ref = (k) => {
      if (!letter[k]) throw new Error(k)
      return `${letter[k]}${row}`
    }
    try {
      if (c.ratio) return { f: `IF(N(${ref(c.ratio[1])})=0,"",N(${ref(c.ratio[0])})/${ref(c.ratio[1])})` }
      if (c.xf) return { f: c.xf(ref), ...(c.type ? {} : { k: 'text' }) }
    } catch { /* ستون لازم در خروجی نیست */ }
    return null
  }
  const value = (c, r) => (typeof c.csv === 'function' ? c.csv(r) : csvValue(r[c.key], c.type, unit))
  // فرمول + مقدار فعلی همان خانه (برای نمایش پیش از محاسبه مجدد)
  const withValue = (fx, c, r) => fx && { ...fx, v: value(c, r) }
  const body = rows.map((r, i) => columns.map((c) => withValue(formula(c, i + 2), c, r) || value(c, r)))
  if (total) {
    const t = rows.length + 2
    const sum = (c) => ({ f: `SUM(${letter[c.key]}2:${letter[c.key]}${t - 1})` })
    body.push(columns.map((c) => {
      if (c.noTotal) return ''
      if (c.type === 'money' || c.type === 'int') return total[c.key] != null && rows.length ? { ...sum(c), v: value(c, total) } : value(c, total)
      return withValue(formula(c, t), c, total) || value(c, total)
    }))
  }
  // ستون‌های sticky اول جدول (مثل نام شعبه و نام فروشنده) در اکسل هم فریز می‌شوند
  const freezeCol = columns.findIndex((c) => !c.sticky)
  return buildXlsx(headers, body, title, { filterRows: rows.length, freezeCol: freezeCol > 0 ? freezeCol : 0, ...extras })
}

/** نوار اسکرول افقی بالای جدول، هم‌گام با نوار پایین؛ فقط وقتی جدول از عرض صفحه پهن‌تر است دیده می‌شود. */
function TopScroll({ target }) {
  const barRef = useRef(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = target.current
    if (!el) return
    const measure = () => setWidth(el.scrollWidth > el.clientWidth + 1 ? el.scrollWidth : 0)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => ro.disconnect()
  }, [target])
  useEffect(() => {
    const el = target.current, bar = barRef.current
    if (!el || !bar || !width) return
    // فقط اگر فرق دارد: رویداد برگشتی از طرف دیگر کاری نمی‌کند
    const sync = (from, to) => () => { if (to.scrollLeft !== from.scrollLeft) to.scrollLeft = from.scrollLeft }
    const a = sync(bar, el), b = sync(el, bar)
    bar.scrollLeft = el.scrollLeft
    bar.addEventListener('scroll', a)
    el.addEventListener('scroll', b)
    return () => { bar.removeEventListener('scroll', a); el.removeEventListener('scroll', b) }
  }, [target, width])
  if (!width) return null
  return <div className="table-scroll-top" ref={barRef}><div style={{ width }} /></div>
}

// expandedKey / renderExpanded: یک ردیف باز زیر همان ردیف (مثلاً توضیح محاسبه)
// totals(filteredRows): ردیف «جمع کل» پایین جدول از ردیف‌های فیلترشده (همه صفحه‌ها)؛ در خروجی اکسل هم می‌آید
// exportExtras(): {extraSheets, names} برای خروجی اکسل (برگه‌های کمکی مثل «قواعد» که فرمول‌ها به آن ارجاع می‌دهند)
export function DataTable({ rows, columns: allColumns, unit, onRowClick, pageSize = 15, search = true, defaultSort, exportName, dense,
  expandedKey, renderExpanded, totals, exportExtras }) {
  // ستون‌های exportOnly فقط در اکسل می‌آیند
  const columns = useMemo(() => allColumns.filter((c) => !c.exportOnly), [allColumns])
  const [q, setQ] = useState('')
  const [sort, setSort] = useState(defaultSort || null)
  const [page, setPage] = useState(0)
  useEffect(() => { setPage(0) }, [q, rows])

  const filtered = useMemo(() => {
    let r = rows || []
    if (q) {
      const s = q.trim().toLowerCase()
      r = r.filter((x) => columns.some((c) => !NUMERIC.has(c.type) && String(x[c.key] ?? '').toLowerCase().includes(s)))
    }
    if (sort) {
      const { key, dir } = sort
      r = [...r].sort((a, b) => {
        const va = a[key], vb = b[key]
        if (va == null) return 1
        if (vb == null) return -1
        return (typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb), 'fa')) * (dir === 'asc' ? 1 : -1)
      })
    }
    return r
  }, [rows, q, sort, columns])

  // ستون اصلی (نام) هنگام اسکرول افقی ثابت می‌ماند: ستون(های) sticky، وگرنه label / product، وگرنه ستون اول.
  // چند ستون sticky کنار هم ثابت می‌مانند: فاصله هر کدام از لبه راست = جمع پهنای ستون‌های sticky قبلی (اندازه‌گیری‌شده).
  const stickyKeys = columns.some((c) => c.sticky) ? columns.filter((c) => c.sticky).map((c) => c.key)
    : [(columns.find((c) => c.key === 'label' || c.key === 'product') || columns[0])?.key]
  const headRef = useRef(null)
  const scrollRef = useRef(null)
  const [offs, setOffs] = useState({})
  useLayoutEffect(() => {
    if (stickyKeys.length < 2 || !headRef.current) return
    const ths = [...headRef.current.children]
    const o = {}
    let acc = 0
    columns.forEach((c, i) => { if (stickyKeys.includes(c.key)) { o[c.key] = acc; acc += ths[i]?.offsetWidth || 0 } })
    setOffs((prev) => (JSON.stringify(prev) === JSON.stringify(o) ? prev : o))
  })
  const sc = (c) => (stickyKeys.includes(c.key) ? ' sticky-col' : '')
  const ss = (c) => (offs[c.key] ? { right: offs[c.key] } : undefined)

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const view = filtered.slice(page * pageSize, page * pageSize + pageSize)
  const total = totals && filtered.length ? totals(filtered) : null
  const toggle = (key) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  const download = () => {
    const blob = toXlsx(filtered, allColumns, unit || 'million', exportName || 'export', total, exportExtras ? exportExtras() : {})
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${exportName || 'export'}.xlsx`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className={`table-wrap ${dense ? 'dense' : ''}`}>
      {(search || exportName) && (
        <div className="table-tools">
          {search && <input className="input" placeholder="جستجو…" value={q} onChange={(e) => setQ(e.target.value)} />}
          <span className="muted">{fmtInt(filtered.length)} ردیف</span>
          {exportName && <button className="btn ghost" onClick={download}>خروجی اکسل</button>}
        </div>
      )}
      <TopScroll target={scrollRef} />
      <div className="table-scroll" ref={scrollRef}>
        <table className="dt">
          <thead>
            <tr ref={headRef}>
              {columns.map((c) => (
                <th key={c.key} className={(NUMERIC.has(c.type) ? 'num' : '') + sc(c)} style={ss(c)} onClick={() => toggle(c.key)} title={c.hint}>
                  {c.label}
                  {c.type === 'money' && <span className="th-unit"> ({UNITS[unit].label})</span>}
                  {sort?.key === c.key && <span className="sort">{sort.dir === 'desc' ? ' ▼' : ' ▲'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <Fragment key={r.key ?? i}>
                <tr onClick={onRowClick ? () => onRowClick(r) : undefined}
                  className={(onRowClick ? 'clickable' : '') + (expandedKey != null && r.key === expandedKey ? ' active-row' : '')}>
                  {columns.map((c) => (
                    <td key={c.key} className={`${NUMERIC.has(c.type) ? 'num' : ''} ${isNeg(r[c.key], c.type) ? 'neg' : ''}${sc(c)}`} style={ss(c)}
                      title={c.render ? undefined : fullTitle(r[c.key], c.type)}>
                      {c.render ? c.render(r) : cell(r[c.key], c.type, unit)}
                    </td>
                  ))}
                </tr>
                {renderExpanded && expandedKey != null && r.key === expandedKey && (
                  <tr className="expand-row"><td colSpan={columns.length}><div className="expand-panel">{renderExpanded(r)}</div></td></tr>
                )}
              </Fragment>
            ))}
            {!view.length && (
              <tr><td colSpan={columns.length} className="muted center">موردی یافت نشد</td></tr>
            )}
          </tbody>
          {total && (
            <tfoot>
              <tr className="total-row">
                {columns.map((c) => (
                  <td key={c.key} className={`${NUMERIC.has(c.type) ? 'num' : ''} ${isNeg(total[c.key], c.type) ? 'neg' : ''}${sc(c)}`} style={ss(c)}
                    title={c.render ? undefined : fullTitle(total[c.key], c.type)}>
                    {total[c.key] == null ? '' : c.render ? c.render(total) : cell(total[c.key], c.type, unit)}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {pages > 1 && (
        <div className="pager">
          <button className="btn ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>قبلی</button>
          <span>{fmtInt(page + 1)} از {fmtInt(pages)}</span>
          <button className="btn ghost" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>بعدی</button>
        </div>
      )}
    </div>
  )
}
const isNeg = (v, type) => NUMERIC.has(type) && typeof v === 'number' && v < 0

// ---------------------------------------------------------------- multi select
export function MultiSelect({ label, options, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const sel = new Set(value)
  const shown = options.filter((o) => !q || o.label.includes(q) || (o.group || '').includes(q))
  const toggle = (v) => onChange(sel.has(v) ? value.filter((x) => x !== v) : [...value, v])
  const summary = value.length === 0 ? 'همه'
    : value.length === 1 ? (options.find((o) => o.value === value[0])?.label ?? value[0])
    : `${fmtInt(value.length)} مورد`
  return (
    <div className={`ms ${value.length ? 'on' : ''}`} ref={ref}>
      <button className="ms-btn" onClick={() => setOpen(!open)}>
        <span className="ms-label">{label}:</span> <span className="ms-val">{summary}</span> <span className="caret">▾</span>
      </button>
      {open && (
        <div className="ms-pop">
          <input className="input" autoFocus placeholder="جستجو…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="ms-actions">
            <button className="link" onClick={() => onChange([])}>پاک کردن</button>
            {q && <button className="link" onClick={() => onChange([...new Set([...value, ...shown.map((o) => o.value)])])}>انتخاب نتایج</button>}
          </div>
          <div className="ms-list">
            {shown.map((o) => (
              <label key={o.value} className="ms-opt">
                <input type="checkbox" checked={sel.has(o.value)} onChange={() => toggle(o.value)} />
                <span>{o.label}</span>
                {o.group && <span className="muted small">{o.group}</span>}
              </label>
            ))}
            {!shown.length && <div className="muted small center">موردی نیست</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// خطای رندر یک صفحه نباید کل برنامه را سفید کند؛ با تغییر مسیر (resetKey) دوباره تلاش می‌شود
export class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }
  componentDidCatch(error, info) {
    console.error('Dashboard render error:', error, info?.componentStack)
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="state error">
        نمایش این صفحه با خطا مواجه شد: {String(this.state.error.message || this.state.error)}
        <div>
          <button className="btn" onClick={() => this.setState({ error: null })}>تلاش دوباره</button>
        </div>
      </div>
    )
  }
}
