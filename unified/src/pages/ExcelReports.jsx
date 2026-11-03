// ماژول «گزارش‌ساز اکسل»: کارپوشه‌های چندبرگه ویزیتورها، سرپرست‌ها و هیبریدها با فیلتر نام، شهر و شعبه.
// ساخت فایل در بک‌اند مالی (app/services/excel_reports_service.py)؛ اینجا فقط انتخاب و دانلود.
import { useEffect, useMemo, useState } from 'react'
import { useApp } from '@sales/lib.jsx'
import { qs, faDigits } from '../data.js'

const API = '/api/v1/finance/excel-reports'

const REPORTS = [
  {
    kind: 'visitors', title: 'ویزیتورها', icon: '☺', people: 'visitors', nameLabel: 'نام ویزیتور',
    sheets: ['عملکرد هر ویزیتور: فروش خالص و ناخالص، مشتری خریدار، تعداد SKU و کالا، ویزیت ثبت‌شده، میانگین فروش روزانه، مانده حساب و چک برگشتی، تخفیف‌ها',
      'ریز ۴۰ کالای پرفروش هر ویزیتور', 'جمع به تفکیک شعبه'],
  },
  {
    kind: 'supervisors', title: 'سرپرست‌ها', icon: '♙', people: 'supervisors', nameLabel: 'نام سرپرست',
    sheets: ['عملکرد هر سرپرست (جمع ویزیتورهایش) با درصد تحقق شعبه و تخفیف حجمی/نقدی/مدیریتی',
      'همه ویزیتورهای سرپرستان', 'یک برگه برای هر سرپرست با ریز عملکرد ویزیتورهایش'],
  },
  {
    kind: 'hybrids', title: 'هیبریدها', icon: '⬢', people: 'hybrids', nameLabel: 'نام هیبرید',
    sheets: ['رتبه و درصد تحقق هر هیبرید، فاکتور توزیع‌شده و نشده، مانده حساب و چک برگشتی شعبه',
      'سرپرستان و ویزیتورهای هر هیبرید', 'یک برگه برای هر هیبرید با ریز ویزیتورهایش'],
  },
]

/** دانلود فایل با کوکی ورود (همان مبدأ، از Proxy پورت 5180) */
async function download(url, fallbackName) {
  const r = await fetch(url, { credentials: 'include' })
  if (!r.ok) {
    const j = await r.json().catch(() => ({}))
    throw new Error(j.detail || `خطای ${r.status}`)
  }
  const blob = await r.blob()
  const cd = r.headers.get('content-disposition') || ''
  const m = cd.match(/filename\*=UTF-8''([^;]+)/)
  const name = m ? decodeURIComponent(m[1]) : fallbackName
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 4000)
}

function ReportCard({ r, range, opts, index }) {
  const [name, setName] = useState('')
  const [city, setCity] = useState('')
  const [branch, setBranch] = useState('')
  const [state, setState] = useState({ busy: false, error: '', done: '' })
  const list = (k) => `xr-${r.kind}-${k}`
  const make = async () => {
    setState({ busy: true, error: '', done: '' })
    const started = Date.now()
    try {
      await download(`${API}/${r.kind}.xlsx?${qs({ ...range, name, city, branch })}`, `report-${r.kind}.xlsx`)
      setState({ busy: false, error: '', done: `آماده شد (${faDigits(Math.round((Date.now() - started) / 1000))} ثانیه)` })
    } catch (e) {
      setState({ busy: false, error: e.message || 'خطا', done: '' })
    }
  }
  return (
    <section className="u-card xr-card" style={{ animationDelay: `${index * 80}ms` }}>
      <div className="xr-card-head">
        <i aria-hidden>{r.icon}</i>
        <div><h2>اکسل {r.title}</h2><small>{faDigits(r.sheets.length + 1)}+ برگه با فیلتر اکسل و ردیف جمع</small></div>
      </div>
      <ul className="xr-sheets">{r.sheets.map((s) => <li key={s}>{s}</li>)}</ul>
      <div className="xr-filters">
        <label>{r.nameLabel}
          <input list={list('name')} value={name} onChange={(e) => setName(e.target.value)} placeholder="همه" />
          <datalist id={list('name')}>{(opts?.[r.people] || []).map((x) => <option key={x} value={x} />)}</datalist>
        </label>
        <label>شهر
          <input list={list('city')} value={city} onChange={(e) => setCity(e.target.value)} placeholder="همه" />
          <datalist id={list('city')}>{(opts?.cities || []).map((x) => <option key={x} value={x} />)}</datalist>
        </label>
        {r.kind !== 'hybrids' && <label>شعبه
          <input list={list('branch')} value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="همه" />
          <datalist id={list('branch')}>{(opts?.branches || []).map((x) => <option key={x} value={x} />)}</datalist>
        </label>}
      </div>
      <div className="xr-actions">
        <button type="button" className="u-btn primary" onClick={make} disabled={state.busy}>
          {state.busy ? <><span className="xr-spin" aria-hidden />در حال ساخت…</> : '⬇ ساخت و دانلود اکسل'}
        </button>
        {state.done && <span className="xr-ok">✓ {state.done}</span>}
        {state.error && <span className="xr-err">{state.error}</span>}
      </div>
    </section>
  )
}

export default function ExcelReports() {
  const { meta } = useApp()
  const today = meta?.file?.today
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  useEffect(() => {
    if (today && !to) { setTo(today); setFrom(`${today.slice(0, 7)}/01`) }
  }, [today, to])
  const range = useMemo(() => ({ date_from: from, date_to: to }), [from, to])
  const [opts, setOpts] = useState(null)
  useEffect(() => {
    if (!from || !to) return undefined
    let alive = true
    fetch(`${API}/options?${qs(range)}`, { credentials: 'include' }).then((r) => r.json()).then((j) => alive && setOpts(j)).catch(() => {})
    return () => { alive = false }
  }, [range, from, to])
  const valid = /^\d{4}\/\d{2}\/\d{2}$/.test(from) && /^\d{4}\/\d{2}\/\d{2}$/.test(to)

  return (
    <div className="u-page xr">
      <div className="u-head">
        <div>
          <span className="u-crumb">گزارش‌ها</span>
          <h1>گزارش‌ساز اکسل</h1>
          <p>کارپوشه‌های چندبرگه از فروش، توزیع و مالی؛ با فیلتر نام، شهر و شعبه. مبالغ به تومان.</p>
        </div>
        <div className="xr-range">
          <label>از تاریخ<input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="1405/08/01" dir="ltr" /></label>
          <label>تا تاریخ<input value={to} onChange={(e) => setTo(e.target.value)} placeholder="1405/08/12" dir="ltr" /></label>
        </div>
      </div>
      {!valid && <div className="xr-err">تاریخ را به شکل ۱۴۰۵/۰۸/۰۱ وارد کنید.</div>}
      <div className="xr-grid">
        {REPORTS.map((r, i) => <ReportCard key={r.kind} r={r} range={range} opts={opts} index={i} />)}
      </div>
      <p className="xr-note">
        ویزیت ثبت‌شده = تعداد اسناد درخواست ثبت‌شده در بازه (کارآمد ویزیت بدون سفارش را جدا ثبت نمی‌کند).
        درصد تحقق از تارگت‌های صفحه «تحقق و پورسانت» می‌آید؛ اگر تارگت ماه ثبت نشده باشد خالی می‌ماند.
        اولین ساخت هر روز تا حدود ۳۰ ثانیه طول می‌کشد (مانده حساب ویزیتورها از کارآمد)؛ بعدی‌ها چند ثانیه.
      </p>
    </div>
  )
}
