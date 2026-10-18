import { useEffect, useMemo, useRef, useState } from 'react'
import { faDigits } from '../lib.jsx'
import { MONTH_NAMES, WEEK_DAYS, addDays, fmtDate, monthEnd, monthLength, parseDate, toJdn, weekIndex } from '../jalali.js'

const monthLabel = (m) => { const [y, mm] = m.split('/'); return `${MONTH_NAMES[+mm - 1]} ${faDigits(y)}` }
const dayLabel = (s, withYear = true) => {
  const d = parseDate(s)
  return d ? `${faDigits(d.jd)} ${MONTH_NAMES[d.jm - 1]}${withYear ? ` ${faDigits(d.jy)}` : ''}` : ''
}

/** متن دکمه: «ماه جاری · مهر ۱۴۰۵»، «شهریور ۱۴۰۵»، «سال ۱۴۰۴» یا «۱ شهریور تا ۱۵ مهر ۱۴۰۵» */
function summary(from, to, months, cur) {
  if (!from && !to) return `ماه جاری · ${monthLabel(cur)}`
  const m = months.find((x) => x.from === from && x.to === to)
  if (m) return monthLabel(m.month)
  const f = parseDate(from), t = parseDate(to)
  if (f && t && f.jy === t.jy && from === `${f.jy}/01/01` && to === monthEnd(t.jy, 12)) return `سال ${faDigits(f.jy)}`
  if (f && t) {
    if (from === to) return dayLabel(from)
    if (f.jd === 1 && to === monthEnd(t.jy, t.jm)) {
      // بازه چندماهه کامل: «تیر تا شهریور ۱۴۰۵»
      const a = f.jy === t.jy ? MONTH_NAMES[f.jm - 1] : `${MONTH_NAMES[f.jm - 1]} ${faDigits(f.jy)}`
      return `${a} تا ${MONTH_NAMES[t.jm - 1]} ${faDigits(t.jy)}`
    }
    return `${dayLabel(from, f.jy !== t.jy)} تا ${dayLabel(to)}`
  }
  return f ? `از ${dayLabel(from)}` : `تا ${dayLabel(to)}`
}

export default function DateRange({ filters, setFilters, meta }) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('month')
  const [pending, setPending] = useState(null)   // روز شروع انتخاب‌شده در تقویم، منتظر روز پایان
  const [hover, setHover] = useState(null)
  const [anchor, setAnchor] = useState(null)     // ماه شروع برای بازه چندماهه (Shift + کلیک)
  const ref = useRef(null)

  const cur = meta.file.month
  const today = meta.file.today || meta.file.month_to
  const months = useMemo(() => (meta.file.months || []).filter((m) => m.loaded), [meta])
  const minDate = months.length ? months[months.length - 1].from : `${cur}/01`
  const maxDate = meta.file.month_to
  const dataDays = useMemo(() => new Set(meta.dates), [meta])
  const { date_from: from, date_to: to } = filters
  const startView = () => { const d = parseDate(to || from || today); return { jy: d.jy, jm: d.jm } }
  const [view, setView] = useState(startView)

  useEffect(() => {
    if (!open) return
    setView(startView()); setPending(null); setAnchor(null)
    const out = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', out)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc) }
  }, [open])  // eslint-disable-line react-hooks/exhaustive-deps

  const apply = (f, t, close = true) => {
    // ماه جاری کامل = بدون فیلتر تاریخ، تا پیش‌بینی پایان ماه محاسبه شود
    const curM = months.find((m) => m.month === cur)
    const isCur = curM && f === curM.from && t === curM.to
    setFilters({ ...filters, date_from: isCur ? '' : f, date_to: isCur ? '' : t })
    if (close) setOpen(false)
  }
  const clamp = (s) => (s < minDate ? minDate : s > maxDate ? maxDate : s)

  // ---------------- میانبرها
  const cy = parseDate(today).jy
  const presets = [
    { label: 'ماه جاری', hint: 'با پیش‌بینی پایان ماه', f: '', t: '' },
    months[1] && { label: 'ماه قبل', f: months[1].from, t: months[1].to },
    { label: '۷ روز اخیر', f: clamp(addDays(today, -6)), t: today },
    { label: '۳۰ روز اخیر', f: clamp(addDays(today, -29)), t: today },
    months[2] && { label: '۳ ماه اخیر', hint: 'دو ماه قبل + ماه جاری', f: months[2].from, t: maxDate },
    { label: `از ابتدای ${faDigits(cy)}`, f: clamp(`${cy}/01/01`), t: today },
    `${cy - 1}/01/01` >= minDate && { label: `سال ${faDigits(cy - 1)}`, f: `${cy - 1}/01/01`, t: monthEnd(cy - 1, 12) },
    { label: 'کل تاریخچه', hint: `از ${dayLabel(minDate)}`, f: minDate, t: maxDate },
  ].filter(Boolean)
  const isActive = (p) => (p.f || '') === (from || '') && (p.t || '') === (to || '')

  // ---------------- ماه‌ها به تفکیک سال (جدیدترین بالا)
  const loaded = new Map(months.map((m) => [m.month, m]))
  const years = [...new Set(months.map((m) => +m.month.slice(0, 4)))].sort((a, b) => b - a)
  const inRange = (s) => from && to && s >= from && s <= to
  const pickMonth = (m, e) => {
    if (e.shiftKey && anchor) {
      const [a, b] = [anchor, m].sort((x, y) => x.from.localeCompare(y.from))
      apply(a.from, b.to)
      return
    }
    setAnchor(m)
    apply(m.from, m.to, false)  // باز می‌ماند تا با Shift بازه چندماهه انتخاب شود
  }

  // ---------------- تقویم روزانه
  const first = toJdn(view.jy, view.jm, 1)
  const len = monthLength(view.jy, view.jm)
  const cells = [...Array(weekIndex(first)).fill(null), ...Array.from({ length: len }, (_, i) => fmtDate({ ...view, jd: i + 1 }))]
  const move = (n) => setView(({ jy, jm }) => {
    const k = jy * 12 + (jm - 1) + n
    return { jy: Math.floor(k / 12), jm: (k % 12) + 1 }
  })
  const viewKey = `${view.jy}/${String(view.jm).padStart(2, '0')}`
  const canPrev = viewKey > minDate.slice(0, 7)
  const canNext = viewKey < maxDate.slice(0, 7)
  const [selA, selB] = pending ? [pending, hover || pending].sort() : [from, to]
  const pickDay = (s) => {
    if (!pending) { setPending(s); return }
    const [a, b] = [pending, s].sort()
    setPending(null)
    apply(a, b)
  }

  return (
    <div className={`ms dr ${from || to ? 'on' : ''}`} ref={ref}>
      <button className="ms-btn dr-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="ms-label">تاریخ:</span> <span className="ms-val">{summary(from, to, months, cur)}</span> <span className="caret">▾</span>
      </button>
      {open && (
        <div className="ms-pop dr-pop" role="dialog" aria-label="انتخاب بازه تاریخ">
          <div className="dr-presets">
            {presets.map((p) => (
              <button key={p.label} className={`dr-preset ${isActive(p) ? 'active' : ''}`} onClick={() => apply(p.f, p.t)}>
                {p.label}{p.hint && <span className="muted small">{p.hint}</span>}
              </button>
            ))}
          </div>
          <div className="dr-main">
            <div className="tabs dr-tabs" role="tablist">
              {[['month', 'انتخاب ماه'], ['day', 'انتخاب روز']].map(([k, l]) => (
                <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'active' : ''}
                  onClick={() => { setTab(k); setPending(null) }}>{l}</button>
              ))}
            </div>
            {tab === 'month' ? (
              <>
                {years.map((y) => (
                  <div key={y} className="dr-year">
                    <div className="dr-year-label">{faDigits(y)}</div>
                    <div className="dr-months">
                      {MONTH_NAMES.map((n, i) => {
                        const m = loaded.get(`${y}/${String(i + 1).padStart(2, '0')}`)
                        const sel = m && ((!from && !to && m.month === cur) || (inRange(m.from) && inRange(m.to)))
                        return (
                          <button key={n} disabled={!m} className={`dr-month ${sel ? 'sel' : ''} ${m?.month === cur ? 'cur' : ''}`}
                            onClick={(e) => m && pickMonth(m, e)}>{n}</button>
                        )
                      })}
                    </div>
                  </div>
                ))}
                <div className="muted small dr-hint">
                  {anchor ? `برای بازه چندماهه: Shift را نگه دارید و ماه پایان را بزنید (از ${monthLabel(anchor.month)}).`
                    : 'روی ماه کلیک کنید. برای بازه چندماهه، ماه شروع و بعد با Shift ماه پایان را بزنید.'}
                </div>
              </>
            ) : (
              <>
                <div className="dr-cal-head">
                  <button className="dr-nav" disabled={!canPrev} onClick={() => move(-1)} aria-label="ماه قبل">›</button>
                  <b>{MONTH_NAMES[view.jm - 1]} {faDigits(view.jy)}</b>
                  <button className="dr-nav" disabled={!canNext} onClick={() => move(1)} aria-label="ماه بعد">‹</button>
                </div>
                <div className="dr-grid" onMouseLeave={() => setHover(null)}>
                  {WEEK_DAYS.map((w) => <div key={w} className="dr-wd">{w}</div>)}
                  {cells.map((s, i) => {
                    if (!s) return <div key={`e${i}`} />
                    const off = s < minDate || s > maxDate
                    const cls = [
                      'dr-day',
                      !dataDays.has(s) && 'nodata',
                      s === today && 'today',
                      selA && selB && s >= selA && s <= selB && 'in',
                      (s === selA || s === selB) && 'edge',
                    ].filter(Boolean).join(' ')
                    return (
                      <button key={s} className={cls} disabled={off} onClick={() => pickDay(s)}
                        onMouseEnter={() => pending && setHover(s)} title={dataDays.has(s) ? '' : 'بدون فاکتور و درخواست'}>
                        {faDigits(+s.slice(8))}
                      </button>
                    )
                  })}
                </div>
                <div className="muted small dr-hint">
                  {pending ? `از ${dayLabel(pending)} — روز پایان را انتخاب کنید (برای یک روز، همان روز را دوباره بزنید).`
                    : 'روز شروع و بعد روز پایان را بزنید. روزهای کم‌رنگ فاکتور یا درخواستی ندارند.'}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
