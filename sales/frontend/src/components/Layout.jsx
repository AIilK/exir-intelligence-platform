import { NavLink, Outlet, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useApp, useBusy, EMPTY_FILTERS, FILTER_LABELS, UNITS, faDigits } from '../lib.jsx'
import { MultiSelect, ErrorBoundary } from './ui.jsx'
import DateRange from './DateRange.jsx'

// فروش در دو بخش: کارآمد (شعب هیبرید) و راهکاران (فروش کارخانه به نمایندگان B2B)
const NAV = [
  { section: 'فروش کارآمد (هیبرید)' },
  { to: '/', label: 'نمای کلی', icon: '◱' },
  { to: '/hybrid', label: 'عملکرد هیبرید', icon: '⌂' },  { to: '/team', label: 'تیم فروش', icon: '☺' },
  { to: '/products', label: 'محصولات و گروه‌ها', icon: '▦' },
  { to: '/customers', label: 'مشتریان', icon: '◎' },
  { to: '/analysis', label: 'تحلیل فروش', icon: '◔' },
  { to: '/plan', label: 'برنامه‌ریزی و تارگت', icon: '◇' },
  { to: '/inventory', label: 'موجودی و سفارش', icon: '▤' },
  { section: 'فروش راهکاران (B2B)' },
  { to: '/rahkaran', label: 'نمایندگان B2B', icon: '◉' },
  { to: '/rahkaran/customer-brand', label: 'مشتری × برند', icon: '▦' },
  { to: '/rahkaran/total-report', label: 'گزارش کل (Total)', icon: '☰' },
  { to: '/rahkaran/compare', label: 'مقایسه', icon: '⇄' },
  { to: '/rahkaran/export', label: 'فروش صادراتی', icon: '✈' },
]

function FilterBar() {
  const { filters, setFilters, meta, unit, setUnit, vat, setVat } = useApp()
  if (!meta) return null
  // فهرست‌های وابسته: شعبه ← سرپرست ← فروشنده، و گروه کالا ← زیرگروه
  const has = (sel, v) => !sel?.length || sel.includes(v)
  const supOptsFor = (f) => meta.options.supervisor.filter((o) => has(f.branch, o.group))
  const sellerOptsFor = (f) => meta.options.seller.filter((o) => has(f.branch, o.group)
    && (!f.supervisor?.length || (o.supervisors || []).some((s) => f.supervisor.includes(s))))
  const groupOptsFor = (f) => (meta.options.group || []).filter((o) => has(f.category, o.group))
  const set = (k, v) => {
    const next = { ...filters, [k]: v }
    // انتخاب‌هایی که با تغییر والد دیگر در فهرست نیستند حذف شوند (وگرنه پنهان می‌مانند و داده را خالی می‌کنند)
    const keep = (key, opts) => {
      const ok = new Set(opts.map((o) => o.value))
      next[key] = (next[key] || []).filter((x) => ok.has(x))
    }
    if (k === 'branch') keep('supervisor', supOptsFor(next))
    if (k === 'branch' || k === 'supervisor') keep('seller', sellerOptsFor(next))
    if (k === 'category') keep('group', groupOptsFor(next))
    setFilters(next)
  }
  const active = Object.entries(filters).some(([, v]) => (Array.isArray(v) ? v.length : v))
  const supOpts = supOptsFor(filters)
  const sellerOpts = sellerOptsFor(filters)
  const groupOpts = groupOptsFor(filters)
  return (
    <div className="filterbar">
      {/* بدون فیلتر تاریخ = ماه جاری (با پیش‌بینی پایان ماه) */}
      <DateRange filters={filters} setFilters={setFilters} meta={meta} />
      {['branch', 'supervisor', 'seller', 'brand', 'category', 'group', 'city', 'payment', 'inv_type'].map((k) => (
        <MultiSelect key={k} label={FILTER_LABELS[k]} value={filters[k] || []} onChange={(v) => set(k, v)}
          options={{ supervisor: supOpts, seller: sellerOpts, group: groupOpts }[k] || meta.options[k]} />
      ))}
      {active && <button className="btn ghost" onClick={() => setFilters(EMPTY_FILTERS)}>حذف فیلترها</button>}
      <div className="spacer" />
      <label className="unit-select" title="با ارزش افزوده: مبالغ خالص (فروش، برگشتی، درخواست) برابر «مبلغ کل» و «قابل پرداخت» گزارش‌های کارآمد. ناخالص و نرخ تخفیف تغییر نمی‌کنند.">
        <span className="ms-label">ارزش افزوده</span>
        <select value={vat ? '1' : '0'} onChange={(e) => setVat(e.target.value === '1')}>
          <option value="1">با ارزش افزوده</option>
          <option value="0">بدون ارزش افزوده</option>
        </select>
      </label>
      <label className="unit-select">
        <span className="ms-label">واحد مبالغ</span>
        <select value={unit} onChange={(e) => setUnit(e.target.value)}>
          {Object.entries(UNITS).map(([k, u]) => <option key={k} value={k}>{u.label}</option>)}
        </select>
      </label>
    </div>
  )
}

export default function Layout() {
  const { meta, metaError } = useApp()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const isData = pathname === '/data'
  // صفحه‌های برنامه‌ریزی و موجودی کنترل‌های خودشان را دارند و فیلترهای سراسری روی آن‌ها اثر ندارند
  const isRahkaran = pathname.startsWith('/rahkaran')  // راهکاران کنترل‌های خودش را دارد و به داده کارآمد وابسته نیست
  const noFilters = pathname === '/plan' || pathname === '/inventory' || isRahkaran
  const busy = useBusy()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return (
    <div className="shell">
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <div className="logo">▲</div>
          <div>
            <div className="brand-title">داشبورد فروش</div>
            <div className="brand-sub">Hybrid Sales</div>
          </div>
        </div>
        <nav>
          {NAV.map((n) => n.section ? <div key={n.section} className="nav-section">{n.section}</div> : (
            <NavLink key={n.to} to={n.to} end={n.to === '/' || n.to === '/rahkaran'} onClick={() => setOpen(false)}>
              <span className="nav-icon" aria-hidden>{n.icon}</span>{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/data" onClick={() => setOpen(false)}><span className="nav-icon" aria-hidden>⇪</span>منبع داده</NavLink>
          {meta && (
            <div className="file-info" title={meta.file.file}>
              <div className="muted small">اتصال لایو</div>
              <div className="small ellipsis">{meta.file.file_name}</div>
              <div className="muted small">
                {faDigits(meta.dates[0])} تا {faDigits(meta.dates[meta.dates.length - 1])}
              </div>
              {meta.file.loaded_at && (
                <div className="muted small">بروزرسانی: {faDigits(meta.file.loaded_at.slice(11, 16))}</div>
              )}
            </div>
          )}
        </div>
      </aside>
      <main className={`main ${busy ? 'busy' : ''}`} aria-busy={busy}>
        {busy && <div className="loadbar" role="progressbar" aria-label="در حال بروزرسانی" />}
        <button className="menu-btn" onClick={() => setOpen(!open)} aria-label="منو">☰</button>
        <ErrorBoundary resetKey={pathname}>
        {isData || isRahkaran ? <Outlet /> : metaError ? (
          <div className="state error">
            {metaError}
            <div><Link to="/data" className="btn">رفتن به مدیریت منبع داده</Link></div>
          </div>
        ) : (
          <>
            {!noFilters && <FilterBar />}
            <Outlet />
          </>
        )}
        </ErrorBoundary>
      </main>
    </div>
  )
}

export function PageHead({ title, desc, children }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {desc && <p className="muted">{desc}</p>}
      </div>
      {children}
    </div>
  )
}
