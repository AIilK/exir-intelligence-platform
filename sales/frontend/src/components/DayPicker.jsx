import { useEffect, useMemo, useRef, useState } from 'react'
import { faDigits, fmtInt } from '../lib.jsx'
import { MONTH_NAMES, WEEK_DAYS, addDays, fmtDate, monthLength, parseDate, toJdn, weekIndex } from '../jalali.js'

export const DAYS_RE = /^\d{4}\/\d{2}\/\d{2}(,\d{4}\/\d{2}\/\d{2})*$/
/** آیا مقدار دوره، فهرست روزهای انتخابی است («1405/08/01,1405/08/03») */
export const isDays = (p) => DAYS_RE.test(p || '')
export const parseDays = (p) => (isDays(p) ? p.split(',') : [])

const dayLabel = (s, withYear = true) => {
  const d = parseDate(s)
  return d ? `${faDigits(d.jd)} ${MONTH_NAMES[d.jm - 1]}${withYear ? ` ${faDigits(d.jy)}` : ''}` : ''
}

/** متن روزهای انتخابی: «۳ آبان ۱۴۰۵»، «۱ تا ۷ آبان ۱۴۰۵» (روزهای پیوسته) یا «۵ روز (۱ آبان … ۹ آبان)» */
export function daysLabel(days) {
  const ds = [...days].sort()
  if (!ds.length) return 'همه روزها'
  if (ds.length === 1) return dayLabel(ds[0])
  const a = ds[0], b = ds[ds.length - 1]
  const contiguous = ds.every((s, i) => i === 0 || addDays(ds[i - 1], 1) === s)
  const sameMonth = a.slice(0, 7) === b.slice(0, 7)
  if (contiguous) {
    return sameMonth ? `${faDigits(+a.slice(8))} تا ${dayLabel(b)}` : `${dayLabel(a, a.slice(0, 4) !== b.slice(0, 4))} تا ${dayLabel(b)}`
  }
  return `${fmtInt(ds.length)} روز (${dayLabel(a, false)} … ${dayLabel(b)})`
}

/** فیلتر روزانه: یک روز یا چند روز دلخواه (کلیک = افزودن/حذف روز، Shift + کلیک = بازه از روز قبلی).
 * value: آرایه روزها «1405/08/01»؛ onChange(آرایه مرتب؛ خالی = بدون فیلتر روز)
 * today: امروز؛ dataDays: روزهای دارای فروش (بقیه کم‌رنگ)؛ minDate: اولین روز قابل انتخاب */
export default function DayPicker({ value, onChange, today, dataDays = [], minDate, label = 'روز' }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const [last, setLast] = useState(null)
  const ref = useRef(null)
  const has = useMemo(() => new Set(dataDays), [dataDays])
  const startView = () => { const d = parseDate([...value].sort().pop() || today); return { jy: d.jy, jm: d.jm } }
  const [view, setView] = useState(startView)

  useEffect(() => {
    if (!open) return
    setDraft(value); setLast(null); setView(startView())
    const out = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', out)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc) }
  }, [open])  // eslint-disable-line react-hooks/exhaustive-deps

  const min = minDate || dataDays[0] || `${today.slice(0, 4)}/01/01`
  const apply = (ds) => { onChange([...new Set(ds)].sort()); setOpen(false) }
  const range = (a, b) => {
    const [f, t] = [a, b].sort()
    const out = []
    for (let s = f; s <= t; s = addDays(s, 1)) out.push(s)
    return out
  }
  const sel = new Set(draft)
  const pick = (s, e) => {
    if (e.shiftKey && last) {
      const n = new Set(draft)
      range(last, s).forEach((d) => n.add(d))
      setDraft([...n].sort())
    } else {
      setDraft(sel.has(s) ? draft.filter((d) => d !== s) : [...draft, s].sort())
    }
    setLast(s)
  }

  const presets = [
    { label: 'امروز', ds: [today] },
    { label: 'دیروز', ds: [addDays(today, -1)] },
    { label: '۷ روز اخیر', ds: range(addDays(today, -6), today) },
    { label: '۱۴ روز اخیر', ds: range(addDays(today, -13), today) },
    { label: '۳۰ روز اخیر', ds: range(addDays(today, -29), today) },
  ]

  const first = toJdn(view.jy, view.jm, 1)
  const len = monthLength(view.jy, view.jm)
  const cells = [...Array(weekIndex(first)).fill(null), ...Array.from({ length: len }, (_, i) => fmtDate({ ...view, jd: i + 1 }))]
  const move = (n) => setView(({ jy, jm }) => {
    const k = jy * 12 + (jm - 1) + n
    return { jy: Math.floor(k / 12), jm: (k % 12) + 1 }
  })
  const viewKey = `${view.jy}/${String(view.jm).padStart(2, '0')}`
  const monthDays = cells.filter((s) => s && s >= min && s <= today)

  return (
    <div className={`ms dr ${value.length ? 'on' : ''}`} ref={ref}>
      <button className="ms-btn dr-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="ms-label">{label}:</span> <span className="ms-val">{value.length ? daysLabel(value) : 'همه'}</span> <span className="caret">▾</span>
      </button>
      {open && (
        <div className="ms-pop dr-pop" role="dialog" aria-label="انتخاب روز">
          <div className="dr-presets">
            {presets.map((p) => (
              <button key={p.label} className="dr-preset" onClick={() => apply(p.ds)}>{p.label}</button>
            ))}
            <button className="dr-preset" onClick={() => apply([])}>همه روزها<span className="muted small">بدون فیلتر روز</span></button>
          </div>
          <div className="dr-main">
            <div className="dr-cal-head">
              <button className="dr-nav" disabled={viewKey <= min.slice(0, 7)} onClick={() => move(-1)} aria-label="ماه قبل">›</button>
              <b>{MONTH_NAMES[view.jm - 1]} {faDigits(view.jy)}</b>
              <button className="dr-nav" disabled={viewKey >= today.slice(0, 7)} onClick={() => move(1)} aria-label="ماه بعد">‹</button>
            </div>
            <div className="dr-grid">
              {WEEK_DAYS.map((w) => <div key={w} className="dr-wd">{w}</div>)}
              {cells.map((s, i) => {
                if (!s) return <div key={`e${i}`} />
                const cls = ['dr-day', !has.has(s) && 'nodata', s === today && 'today', sel.has(s) && 'in edge'].filter(Boolean).join(' ')
                return (
                  <button key={s} className={cls} disabled={s < min || s > today} onClick={(e) => pick(s, e)}
                    title={has.has(s) ? '' : 'بدون فروش'}>{faDigits(+s.slice(8))}</button>
                )
              })}
            </div>
            <div className="ms-actions">
              <button className="link" onClick={() => setDraft([...new Set([...draft, ...monthDays])].sort())}>کل این ماه</button>
              <button className="link" onClick={() => setDraft([])}>پاک کردن</button>
            </div>
            <div className="muted small dr-hint">
              {draft.length ? `${daysLabel(draft)} انتخاب شده. ` : ''}
              روی هر روز کلیک کنید تا اضافه یا حذف شود؛ Shift + کلیک بازه را از روز قبلی پر می‌کند. روزهای کم‌رنگ فروش ندارند.
            </div>
            <div className="ms-actions">
              <button className="btn sm" onClick={() => apply(draft)}>اعمال</button>
              <button className="btn ghost sm" onClick={() => setOpen(false)}>انصراف</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
