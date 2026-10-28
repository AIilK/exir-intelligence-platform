import { Component, useEffect, useMemo, useRef, useState } from 'react'
import { fmtCompact, fmtInt, fmtMoney, fmtPct, fmtNum1, faDigits, UNITS, fullTitle } from '../lib.jsx'
import { buildXlsx } from '../xlsx.js'

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

// مقدار هر خانه در CSV مثل نمایش جدول: عدد گرد، درصد، مبلغ به واحد انتخاب‌شده (ارقام لاتین برای اکسل)
function csvValue(v, type, unit) {
  if (v == null || (typeof v === 'number' && !Number.isFinite(v))) return ''
  switch (type) {
    case 'int': return Math.round(v)
    case 'num1': return Math.round(v * 10) / 10
    case 'pct': return Math.round(v * 1000) / 10
    case 'money': return Math.round((v / UNITS[unit].div) * 10) / 10
    default: return typeof v === 'boolean' ? (v ? 'بله' : 'خیر') : v
  }
}

// خروجی اکسل واقعی (xlsx): CSV در اکسل فارسی ستون‌ها را جدا نمی‌کند و چپ‌به‌راست باز می‌شود
function toXlsx(rows, allColumns, unit, title) {
  // ستون‌های تصویری (csv: false) نمی‌آیند؛ csv می‌تواند تابعی برای متن خوانای ستون‌های نمایشی باشد (مثل وضعیت)
  const columns = allColumns.filter((c) => c.csv !== false)
  const label = (c) => c.label + (c.type === 'money' ? ` (${UNITS[unit].label})` : c.type === 'pct' ? ' (٪)' : '')
  const kind = (c) => (c.type === 'int' ? 'int' : ['num1', 'pct', 'money'].includes(c.type) ? 'dec' : 'text')
  const headers = columns.map((c) => ({ label: label(c), kind: kind(c) }))
  const body = rows.map((r) => columns.map((c) => (typeof c.csv === 'function' ? c.csv(r) : csvValue(r[c.key], c.type, unit))))
  return buildXlsx(headers, body, title)
}

export function DataTable({ rows, columns, unit, onRowClick, pageSize = 15, search = true, defaultSort, exportName, dense }) {
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

  // ستون اصلی (نام) هنگام اسکرول افقی ثابت می‌ماند: ستون sticky، وگرنه label / product، وگرنه ستون اول
  const stickyKey = (columns.find((c) => c.sticky) || columns.find((c) => c.key === 'label' || c.key === 'product') || columns[0])?.key
  const sc = (c) => (c.key === stickyKey ? ' sticky-col' : '')

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const view = filtered.slice(page * pageSize, page * pageSize + pageSize)
  const toggle = (key) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  const download = () => {
    const blob = toXlsx(filtered, columns, unit || 'million', exportName || 'export')
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
      <div className="table-scroll">
        <table className="dt">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={(NUMERIC.has(c.type) ? 'num' : '') + sc(c)} onClick={() => toggle(c.key)} title={c.hint}>
                  {c.label}
                  {c.type === 'money' && <span className="th-unit"> ({UNITS[unit].label})</span>}
                  {sort?.key === c.key && <span className="sort">{sort.dir === 'desc' ? ' ▼' : ' ▲'}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <tr key={r.key ?? i} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? 'clickable' : ''}>
                {columns.map((c) => (
                  <td key={c.key} className={`${NUMERIC.has(c.type) ? 'num' : ''} ${isNeg(r[c.key], c.type) ? 'neg' : ''}${sc(c)}`}
                    title={c.render ? undefined : fullTitle(r[c.key], c.type)}>
                    {c.render ? c.render(r) : cell(r[c.key], c.type, unit)}
                  </td>
                ))}
              </tr>
            ))}
            {!view.length && (
              <tr><td colSpan={columns.length} className="muted center">موردی یافت نشد</td></tr>
            )}
          </tbody>
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
