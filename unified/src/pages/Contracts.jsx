// قراردادهای همکاران (ماژول «contracts»): تاریخ پایان قرارداد هر همکار، روز باقی‌مانده، تمدید و ویرایش.
// الارم: یک هفته مانده به پایان (و قراردادهای تمام‌شده بدون تمدید) — backend/app/agents/page_agents/agents.py: ContractsAgent
import { useEffect, useMemo, useState } from 'react'
import { useSaved } from '@sales/lib.jsx'
import { PageHead, Card, Kpi } from '../ui.jsx'
import { faDigits } from '../data.js'
import PageAlarms from '../PageAlarms.jsx'

const API = '/api/v1/finance/contracts'
const STATUS = {
  ended: { label: 'تمام‌شده', cls: 'bad' },
  week: { label: 'یک هفته مانده', cls: 'bad' },
  month: { label: 'کمتر از یک ماه', cls: 'warn' },
  ok: { label: 'فعال', cls: 'good' },
}
const EMPTY = { name: '', hybrid: '', role: 'مدیر هیبرید', end_date: '', note: '' }

async function call(url, opts = {}) {
  const r = await fetch(url, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...opts })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.detail || `خطای ${r.status}`)
  return j
}

const dayText = (d) => (d < 0 ? `${faDigits(-d)} روز گذشته` : d === 0 ? 'امروز' : `${faDigits(d)} روز مانده`)

/** یک سال بعد از تاریخ پایان (برای دکمه تمدید یک‌ساله)؛ ۳۰ اسفند در سال غیرکبیسه را بک‌اند رد می‌کند، پس ۲۹ */
function nextYear(end) {
  const [y, m, d] = end.split('/').map(Number)
  return `${y + 1}/${String(m).padStart(2, '0')}/${String(m === 12 && d === 30 ? 29 : d).padStart(2, '0')}`
}

export default function Contracts() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [filter, setFilter] = useSaved('filter', '')
  const [q, setQ] = useSaved('q', '')
  const [form, setForm] = useState(EMPTY)
  const [edit, setEdit] = useState(null)   // { id, ...fields }
  const [busy, setBusy] = useState(false)

  const load = () => call(API).then((j) => { setData(j); setError('') }).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const run = async (fn, ok) => {
    setBusy(true); setError(''); setMsg('')
    try { await fn(); await load(); setMsg(ok) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const add = (e) => { e.preventDefault(); run(() => call(API, { method: 'POST', body: JSON.stringify(form) }).then(() => setForm(EMPTY)), 'قرارداد اضافه شد.') }
  const save = () => run(() => call(`${API}/${edit.id}`, { method: 'PUT', body: JSON.stringify(edit) }).then(() => setEdit(null)), 'قرارداد ذخیره شد.')
  const renew = (c) => run(() => call(`${API}/${c.id}`, { method: 'PUT', body: JSON.stringify({ end_date: nextYear(c.end_date) }) }),
    `قرارداد ${c.name} تا ${faDigits(nextYear(c.end_date))} تمدید شد.`)
  const remove = (c) => { if (window.confirm(`قرارداد «${c.name}» حذف شود؟`)) run(() => call(`${API}/${c.id}`, { method: 'DELETE' }), 'قرارداد حذف شد.') }

  const rows = useMemo(() => (data?.contracts || [])
    .filter((c) => !filter || c.status === filter)
    .filter((c) => !q.trim() || `${c.name} ${c.hybrid} ${c.role}`.includes(q.trim())), [data, filter, q])
  const n = data?.counts || {}

  return (
    <div className="u-page u-contracts">
      <PageAlarms modules={['contracts']} title="قراردادهای همکاران" />
      <PageHead crumb="پرونده‌ها / قراردادهای همکاران" title="قراردادهای همکاران"
        desc={`تاریخ پایان قرارداد هر همکار و روزهای باقی‌مانده. ${faDigits(data?.warn_days ?? 7)} روز مانده به پایان هر قرارداد الارم داده می‌شود؛ قرارداد تمام‌شده‌ای که تاریخ تازه ندارد هم در الارم‌ها می‌آید. امروز: ${faDigits(data?.today_jalali || '')}`} />

      <section className="u-kpis" aria-label="خلاصه قراردادها">
        <Kpi label="تمام‌شده، بدون تاریخ تمدید" value={data ? faDigits(n.ended) : '…'} unit="نفر" valueTone={n.ended ? 'bad' : undefined}
          note="اگر تمدید شده، تاریخ تازه را ثبت کنید" onClick={() => setFilter(filter === 'ended' ? '' : 'ended')} />
        <Kpi label="یک هفته یا کمتر مانده" value={data ? faDigits(n.week) : '…'} unit="نفر" valueTone={n.week ? 'bad' : undefined}
          note="برای هرکدام الارم داده می‌شود" onClick={() => setFilter(filter === 'week' ? '' : 'week')} />
        <Kpi label="کمتر از یک ماه" value={data ? faDigits(n.month) : '…'} unit="نفر" valueTone={n.month ? 'warn' : undefined}
          onClick={() => setFilter(filter === 'month' ? '' : 'month')} />
        <Kpi label="فعال" value={data ? faDigits(n.ok) : '…'} unit="نفر" valueTone="good" onClick={() => setFilter(filter === 'ok' ? '' : 'ok')} />
      </section>

      <Card title="افزودن قرارداد" sub="تاریخ به شکل ۱۴۰۵/۰۹/۰۱">
        <form className="u-contract-form" onSubmit={add}>
          <input required placeholder="نام و نام خانوادگی" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="هیبرید / محل" value={form.hybrid} onChange={(e) => setForm({ ...form, hybrid: e.target.value })} />
          <input placeholder="سمت" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
          <input required placeholder="تاریخ پایان قرارداد" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} dir="ltr" />
          <input placeholder="یادداشت" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <button className="u-btn primary" disabled={busy}>افزودن</button>
        </form>
        {msg && <small className="u-note t-good">{msg}</small>}
        {error && <small className="u-note t-bad">{error}</small>}
      </Card>

      <Card title={`همه قراردادها (${faDigits(rows.length)})`} sub="به ترتیب نزدیک‌ترین پایان؛ نوار رنگی روزهای باقی‌مانده تا ۹۰ روز را نشان می‌دهد"
        action={<>
          {filter && <button className="u-btn ghost" onClick={() => setFilter('')}>نمایش همه ({STATUS[filter].label}) ✕</button>}
          <label className="u-search"><span>جستجو</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام یا هیبرید…" /></label>
        </>}>
        {!data ? <p className="u-note">{error || 'در حال دریافت…'}</p> : (
          <div className="u-table-wrap">
            <table className="u-table u-contract-table">
              <thead><tr><th>همکار</th><th>هیبرید / محل</th><th>سمت</th><th>تاریخ پایان</th><th>زمان باقی‌مانده</th><th>وضعیت</th><th>یادداشت</th><th /></tr></thead>
              <tbody>
                {rows.map((c) => edit?.id === c.id ? (
                  <tr key={c.id} className="editing">
                    <td><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></td>
                    <td><input value={edit.hybrid} onChange={(e) => setEdit({ ...edit, hybrid: e.target.value })} /></td>
                    <td><input value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })} /></td>
                    <td><input value={edit.end_date} onChange={(e) => setEdit({ ...edit, end_date: e.target.value })} dir="ltr" /></td>
                    <td colSpan={2} />
                    <td><input value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} /></td>
                    <td className="u-contract-acts">
                      <button className="u-btn primary" disabled={busy} onClick={save}>ذخیره</button>
                      <button className="u-btn ghost" onClick={() => setEdit(null)}>انصراف</button>
                    </td>
                  </tr>
                ) : (
                  <tr key={c.id} className={`st-${c.status}`}>
                    <td><b>{c.name}</b></td>
                    <td>{c.hybrid || '—'}</td>
                    <td className="t-muted">{c.role || '—'}</td>
                    <td>{faDigits(c.end_date)}</td>
                    <td>
                      <span className="u-contract-left"><i style={{ width: `${Math.max(0, Math.min(100, (100 * c.days_left) / 90))}%` }} /></span>
                      <small className={c.days_left < 0 || c.days_left <= 7 ? 't-bad' : c.days_left <= 30 ? 't-warn' : 't-muted'}>{dayText(c.days_left)}</small>
                    </td>
                    <td><span className={`u-pill ${STATUS[c.status].cls}`}>{STATUS[c.status].label}</span></td>
                    <td className="t-muted">{c.note || ''}</td>
                    <td className="u-contract-acts">
                      <button className="u-btn ghost" disabled={busy} onClick={() => renew(c)} title={`پایان جدید: ${faDigits(nextYear(c.end_date))}`}>تمدید یک‌ساله</button>
                      <button className="u-btn" onClick={() => setEdit({ id: c.id, name: c.name, hybrid: c.hybrid, role: c.role, end_date: c.end_date, note: c.note })}>ویرایش</button>
                      <button className="u-btn" onClick={() => remove(c)} aria-label={`حذف ${c.name}`}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
