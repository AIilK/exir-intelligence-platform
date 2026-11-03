import { useEffect, useMemo, useState } from 'react'
import { fmtInt, fmtMoney, fmtPct, fmtNum1, faDigits, UNITS, useApp, fullTitle } from '../lib.jsx'
import { buildXlsx } from '../xlsx.js'

const NUMERIC = new Set(['money', 'int', 'pct', 'num1', 'spark'])

function cell(v, type, unit) {
  switch (type) {
    case 'money': return fmtMoney(v, unit)
    case 'int': return fmtInt(v)
    case 'pct': return fmtPct(v)
    case 'num1': return fmtNum1(v)
    case 'date': return faDigits(v)
    default: return v ?? '—'
  }
}

/** نمودار کوچک روند؛ زمان از راست به چپ (مثل sparkline شیت Trend). */
export function Spark({ values, width = 90, height = 22 }) {
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  const n = values.length
  if (n < 2) return null
  const pts = values.map((v, i) => {
    const x = width - (i / (n - 1)) * width
    const y = height - 2 - ((v - min) / span) * (height - 4)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const zeroY = height - 2 - ((0 - min) / span) * (height - 4)
  return (
    <svg width={width} height={height} className="spark" aria-hidden>
      {min < 0 && <line x1="0" x2={width} y1={zeroY} y2={zeroY} className="spark-zero" />}
      <polyline points={pts.join(' ')} fill="none" strokeWidth="1.5" />
    </svg>
  )
}

// خروجی اکسل: سطح درخت با تورفتگی نام نشان داده می‌شود؛ عددها مثل جدول (مبلغ به واحد انتخاب‌شده، درصد × ۱۰۰)
function toXlsx(rows, columns, unit, firstLabel, title) {
  const cols = columns.filter((c) => c.type !== 'spark')
  const val = (v, t) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) return v ?? ''
    if (t === 'money') return Math.round((v / UNITS[unit].div) * 10) / 10
    if (t === 'pct') return Math.round(v * 1000) / 10
    if (t === 'num1') return Math.round(v * 10) / 10
    return Math.round(v)
  }
  const headers = [{ label: 'سطح', kind: 'int' }, ...cols.map((c) => ({
    label: (c.key === 'label' ? firstLabel : (c.group ? `${c.group} - ${c.label}` : c.label))
      + (c.type === 'money' ? ` (${UNITS[unit].label})` : c.type === 'pct' ? ' (٪)' : ''),
    kind: c.key === 'label' || !NUMERIC.has(c.type) ? 'text' : c.type === 'int' ? 'int' : 'dec',
  }))]
  const body = rows.map((r) => [r.level ?? '', ...cols.map((c) => (c.key === 'label'
    ? '   '.repeat(r.level || 0) + (r.label ?? '') : val(r[c.key], c.type)))])
  return buildXlsx(headers, body, title)
}

/**
 * جدول درختی با جمع جزء در هر سطح (مشابه شیت‌های گزارشی اکسل).
 * nodes: [{id, parent, level, label, ...metrics}] ؛ total: ردیف «کل».
 */
export function TreeTable({ nodes, total, columns, sortKey = 'net', levelNames = [], onRowClick, exportName,
  defaultDepth = 0, cellStyle, firstLabel = 'نام' }) {
  const { unit } = useApp()
  const defaultOpen = () => new Set(nodes.filter((n) => n.level < defaultDepth).map((n) => n.id))
  const [open, setOpen] = useState(defaultOpen)
  // با تغییر داده (فیلتر، روز گزارش) وضعیت باز/بسته به پیش‌فرض برمی‌گردد
  useEffect(() => { setOpen(defaultOpen()) }, [nodes, defaultDepth])
  const [q, setQ] = useState('')
  const [sort, setSort] = useState({ key: sortKey, dir: 'desc' })
  const maxLevel = Math.max(0, ...nodes.map((n) => n.level))

  const children = useMemo(() => {
    const m = new Map()
    for (const n of nodes) {
      if (!m.has(n.parent)) m.set(n.parent, [])
      m.get(n.parent).push(n)
    }
    const cmp = (a, b) => {
      const va = a[sort.key], vb = b[sort.key]
      const r = typeof va === 'number' || typeof vb === 'number'
        ? (va ?? -Infinity) - (vb ?? -Infinity)
        : String(va ?? '').localeCompare(String(vb ?? ''), 'fa')
      return sort.dir === 'desc' ? -r : r
    }
    for (const arr of m.values()) arr.sort(cmp)
    return m
  }, [nodes, sort])

  // جستجو: گره‌های منطبق و همه اجدادشان نمایش داده و باز می‌شوند
  const match = useMemo(() => {
    if (!q.trim()) return null
    const s = q.trim().toLowerCase()
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const keep = new Set()
    for (const n of nodes) {
      if (String(n.label).toLowerCase().includes(s) || String(n.key).includes(s)) {
        let cur = n
        while (cur) { keep.add(cur.id); cur = byId.get(cur.parent) }
      }
    }
    return keep
  }, [q, nodes])

  const isOpen = (n) => (match ? true : open.has(n.id))
  const visible = []
  const walk = (pid) => {
    for (const n of children.get(pid) || []) {
      if (match && !match.has(n.id)) continue
      visible.push(n)
      if (n.level < maxLevel && isOpen(n)) walk(n.id)
    }
  }
  walk('')

  const toggle = (n) => setOpen((s) => {
    const x = new Set(s)
    if (x.has(n.id)) x.delete(n.id)
    else x.add(n.id)
    return x
  })
  const expandAll = () => setOpen(new Set(nodes.filter((n) => n.level < maxLevel).map((n) => n.id)))
  const collapseAll = () => setOpen(new Set())

  const groups = []
  for (const c of columns) {
    const g = c.group || null
    // فقط ستون‌های گروه‌دار ادغام می‌شوند؛ هر ستون بدون گروه سرستون دوطبقه خودش را دارد
    if (g && groups.length && groups[groups.length - 1].g === g) groups[groups.length - 1].span++
    else groups.push({ g, span: 1, col: c })
  }
  const hasGroups = groups.some((g) => g.g)

  const download = () => {
    const ordered = []
    const all = (pid) => (children.get(pid) || []).forEach((n) => { ordered.push(n); all(n.id) })
    all('')
    const blob = toXlsx(total ? [{ ...total, label: 'کل' }, ...ordered] : ordered, columns, unit, firstLabel, exportName || 'report')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${exportName || 'report'}.xlsx`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const header = (c, rowSpan) => (
    <th key={c.key} rowSpan={rowSpan} className={NUMERIC.has(c.type) ? 'num' : ''} title={c.hint}
      onClick={() => c.type !== 'spark' && setSort((s) => (s.key === c.key ? { key: c.key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key: c.key, dir: 'desc' }))}>
      {c.key === 'label' ? firstLabel : c.label}
      {c.type === 'money' && <span className="th-unit"> ({UNITS[unit].label})</span>}
      {sort.key === c.key && <span className="sort">{sort.dir === 'desc' ? ' ▼' : ' ▲'}</span>}
    </th>
  )

  const renderCell = (n, c, isTotal) => {
    if (c.key === 'label') {
      if (isTotal) return <td key="label" className="tree-label total-label">کل</td>
      const hasKids = n.level < maxLevel && (children.get(n.id) || []).length > 0
      const opened = hasKids && isOpen(n)
      return (
        <td key="label" className="tree-label" style={{ paddingRight: 10 + n.level * 18 }}>
          {hasKids
            ? <button className="tree-toggle" onClick={(e) => { e.stopPropagation(); toggle(n) }} aria-label={opened ? 'بستن' : 'باز کردن'}>{opened ? '▾' : '◂'}</button>
            : <span className="tree-toggle placeholder" />}
          <span className={`lvl lvl${n.level}`}>{n.label}</span>
        </td>
      )
    }
    const v = n[c.key]
    return (
      <td key={c.key} className={`${NUMERIC.has(c.type) ? 'num' : ''} ${typeof v === 'number' && v < 0 && c.type !== 'spark' ? 'neg' : ''}`}
        style={cellStyle ? cellStyle(n, c) : undefined} title={c.render ? undefined : fullTitle(v, c.type)}>
        {c.render ? c.render(n) : cell(v, c.type, unit)}
      </td>
    )
  }

  const shown = visible

  return (
    <div className="table-wrap">
      <div className="table-tools">
        <input className="input" placeholder="جستجو…" value={q} onChange={(e) => setQ(e.target.value)} />
        {maxLevel > 0 && <button className="btn ghost" onClick={expandAll}>باز کردن همه</button>}
        {maxLevel > 0 && <button className="btn ghost" onClick={collapseAll}>بستن همه</button>}
        {exportName && <button className="btn ghost" onClick={download}>خروجی اکسل</button>}
      </div>
      <div className="table-scroll tree-scroll">
        <table className="tree">
          <thead>
            {hasGroups ? (
              <>
                <tr>
                  {groups.map((g, i) => (g.g
                    ? <th key={i} colSpan={g.span} className="grp">{g.g}</th>
                    : header(g.col, 2)))}
                </tr>
                <tr>{columns.filter((c) => c.group).map((c) => header(c, 1))}</tr>
              </>
            ) : <tr>{columns.map((c) => header(c, 1))}</tr>}
          </thead>
          <tbody>
            {total && <tr className="total-row">{columns.map((c) => renderCell(total, c, true))}</tr>}
            {shown.map((n) => (
              <tr key={n.id} className={`lvl-row lvl-row${n.level} ${onRowClick ? 'clickable' : ''}`}
                onClick={onRowClick ? () => onRowClick(n) : undefined}>
                {columns.map((c) => renderCell(n, c, false))}
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={columns.length} className="muted center">موردی یافت نشد</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** انتخاب «روز گزارش» (مشترک بین صفحات). */
export function ReportDayPicker({ value }) {
  const { meta, reportDay, setReportDay } = useApp()
  if (!meta) return null
  return (
    <label className="unit-select">
      <span className="ms-label">روز گزارش</span>
      <select value={reportDay || value || ''} onChange={(e) => setReportDay(e.target.value)}>
        {meta.sales_dates.map((d) => <option key={d} value={d}>{faDigits(d)}</option>)}
      </select>
    </label>
  )
}
