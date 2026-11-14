// نوار بالای همه صفحه‌ها: جستجوی سراسری، کلید واحد پول و خروجی اکسل جدول‌های همین صفحه.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { buildWorkbook, tableSheet } from '@sales/xlsx.js'
import { MONEY_UNITS } from '@finance/money-unit.ts'
import { faDigits } from './data.js'

const norm = (s) => String(s || '').replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/[آأإ]/g, 'ا').replace(/‌/g, ' ').toLowerCase().trim()

/** جستجوی سراسری: صفحه‌های منو (همین‌جا) + مشتری، نماینده، شعبه، تأمین‌کننده و شماره چک (backend: /api/v1/search) */
function GlobalSearch({ pages }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [server, setServer] = useState({ q: '', results: [], loading: false, error: '' })
  const [active, setActive] = useState(0)
  const box = useRef(null)
  const input = useRef(null)

  useEffect(() => {
    const text = q.trim()
    if (text.length < 2) { setServer({ q: '', results: [], loading: false, error: '' }); return }
    setServer((s) => ({ ...s, loading: true }))
    const ctl = new AbortController()
    const timer = setTimeout(() => {
      fetch(`/api/v1/search?q=${encodeURIComponent(text)}`, { credentials: 'include', signal: ctl.signal })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`خطای ${r.status}`))))
        .then((j) => setServer({ q: text, results: j.results || [], loading: false, error: (j.errors || []).join('، ') }))
        .catch((e) => { if (e.name !== 'AbortError') setServer({ q: text, results: [], loading: false, error: e.message }) })
    }, 280)
    return () => { clearTimeout(timer); ctl.abort() }
  }, [q])

  useEffect(() => {
    const key = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.current?.focus() } }
    const out = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    window.addEventListener('keydown', key)
    document.addEventListener('mousedown', out)
    return () => { window.removeEventListener('keydown', key); document.removeEventListener('mousedown', out) }
  }, [])

  const items = useMemo(() => {
    const n = norm(q)
    if (n.length < 2) return []
    const menu = pages.filter((p) => norm(p.label).includes(n)).slice(0, 5).map((p) => ({ kind: 'صفحه', title: p.label, sub: p.group || '', to: p.to }))
    return [...menu, ...server.results]
  }, [q, pages, server.results])
  useEffect(() => { setActive(0) }, [items.length, q])

  const go = (it) => { setOpen(false); setQ(''); input.current?.blur(); nav(it.to) }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)) }
    else if (e.key === 'Enter' && items[active]) go(items[active])
    else if (e.key === 'Escape') { setOpen(false); input.current?.blur() }
  }
  const show = open && q.trim().length >= 2

  return (
    <div className="u-gsearch" ref={box}>
      <span aria-hidden>⌕</span>
      <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)} onKeyDown={onKey}
        placeholder="جستجوی مشتری، نماینده، شعبه، شماره چک یا صفحه…" aria-label="جستجوی سراسری" role="combobox" aria-expanded={show} aria-controls="u-gsearch-list" />
      <kbd>Ctrl K</kbd>
      {show && (
        <div className="u-gsearch-list" id="u-gsearch-list" role="listbox">
          {items.map((it, i) => (
            <button key={`${it.kind}:${it.to}:${it.title}:${i}`} type="button" role="option" aria-selected={i === active}
              className={i === active ? 'on' : ''} onMouseEnter={() => setActive(i)} onClick={() => go(it)}>
              <em>{it.kind}</em>
              <span><b>{it.title}</b>{it.sub && <small>{faDigits(it.sub)}</small>}</span>
              <i aria-hidden>←</i>
            </button>
          ))}
          {server.loading && <p>در حال جستجو…</p>}
          {!server.loading && !items.length && <p>چیزی برای «{q.trim()}» پیدا نشد. شماره چک فقط بین چک‌های باز جستجو می‌شود.</p>}
          {server.error && <p className="t-bad">بخشی از جستجو در دسترس نبود: {server.error}</p>}
        </div>
      )}
    </div>
  )
}

/** متن یک خانه جدول ← عدد (اگر فقط عدد باشد) یا متن */
function cellValue(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim()
  const ascii = t.replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٬,]/g, '').replace('٫', '.').replace('−', '-')
  return /^-?\d+(\.\d+)?$/.test(ascii) ? Number(ascii) : t
}

/** همه جدول‌های دیده‌شدنی صفحه فعلی ← یک فایل اکسل، هر جدول یک برگه (همان ردیف‌هایی که الان روی صفحه است) */
function exportPageTables() {
  const tables = [...document.querySelectorAll('.u-main table')].filter((t) => t.offsetParent !== null && t.rows.length > 1)
  if (!tables.length) return 0
  const used = new Set()
  const sheets = tables.map((table, n) => {
    const headRow = table.tHead?.rows[table.tHead.rows.length - 1] || table.rows[0]
    const labels = [...headRow.cells].map((c) => c.innerText.replace(/\s+/g, ' ').replace(/[↕▴▾]/g, '').trim())
    const body = [...table.tBodies].flatMap((b) => [...b.rows]).concat(table.tFoot ? [...table.tFoot.rows] : [])
      .filter((r) => r.cells.length > 1)
      .map((r) => labels.map((_, i) => (r.cells[i] ? cellValue(r.cells[i].innerText) : '')))
    const headers = labels.map((label, i) => ({ label: label || `ستون ${i + 1}`,
      kind: body.length && body.every((r) => r[i] === '' || typeof r[i] === 'number') && body.some((r) => typeof r[i] === 'number') ? 'dec' : 'text' }))
    const rows = body.map((r) => r.map((v, i) => (headers[i].kind === 'dec' ? (v === '' ? null : v) : String(v))))
    const card = table.closest('section, article, .u-card, .card, .panel')
    let name = (card?.querySelector('h2, h3, h4')?.innerText || `جدول ${n + 1}`).replace(/\s+/g, ' ').replace(/[\\/?*[\]:]/g, ' ').trim().slice(0, 28) || `جدول ${n + 1}`
    while (used.has(name)) name = `${name.slice(0, 25)} ${n + 1}`
    used.add(name)
    return tableSheet(headers, rows, name, { freezeCol: 1 })
  })
  const blob = buildWorkbook(sheets)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  const page = (document.querySelector('.u-main h1, .u-main h2')?.innerText || 'صفحه').replace(/\s+/g, ' ').trim().slice(0, 40)
  a.download = `${page}.xlsx`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  return tables.length
}

export default function TopBar({ pages, unit, onUnit }) {
  const [note, setNote] = useState('')
  const xl = () => {
    const n = exportPageTables()
    setNote(n ? `${faDigits(n)} جدول در اکسل` : 'این صفحه جدولی ندارد')
    setTimeout(() => setNote(''), 2600)
  }
  return (
    <div className="u-topbar">
      <GlobalSearch pages={pages} />
      <div className="u-unit" role="group" aria-label="واحد نمایش مبلغ">
        <small>واحد پول</small>
        {MONEY_UNITS.map((u) => (
          <button key={u.key} type="button" className={unit === u.key ? 'on' : ''} aria-pressed={unit === u.key} onClick={() => onUnit(u.key)}>{u.label}</button>
        ))}
      </div>
      <button type="button" className="u-btn u-xl-btn" onClick={xl} title="همه جدول‌های همین صفحه، با همین فیلتر و ترتیب، در یک فایل اکسل (هر جدول یک برگه)">
        {note || 'خروجی اکسل صفحه'}
      </button>
    </div>
  )
}
