import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp, useBusy, fetchJson } from '@sales/lib.jsx'
import { useJson, faDigits } from './data.js'

const GROUPS = [
  { id: 'home', items: [{ to: '/', label: 'نمای مدیر', icon: '✦', end: true }] },
  {
    id: 'sales', label: 'فروش کارآمد (هیبرید)', dot: 'var(--u-sales)', items: [
      { to: '/sales', label: 'نمای کلی فروش', icon: '◱' },
      { to: '/hybrid', label: 'عملکرد هیبرید', icon: '⌂' },
      { to: '/team', label: 'تیم فروش', icon: '☺' },
      { to: '/products', label: 'محصولات و گروه‌ها', icon: '▦' },
      { to: '/customers', label: 'مشتریان (فروش)', icon: '◎' },
      { to: '/analysis', label: 'تحلیل فروش', icon: '◔' },
    ],
  },
  {
    id: 'rahkaran', label: 'فروش راهکاران (B2B)', dot: 'var(--u-sales)', items: [
      { to: '/rahkaran', label: 'نمایندگان B2B', icon: '◉', end: true },
      { to: '/rahkaran/customer-brand', label: 'مشتری × برند', icon: '▦' },
      { to: '/rahkaran/total-report', label: 'گزارش کل (Total)', icon: '☰' },
      { to: '/rahkaran/export', label: 'فروش صادراتی', icon: '✈' },
    ],
  },
  {
    id: 'finance', label: 'مالی و خزانه', dot: 'var(--u-fin)', items: [
      { to: '/finance/management', label: 'خلاصه مدیریتی مالی', icon: '✧' },
      { to: '/finance/cheques', label: 'چک و سررسید', icon: '◷' },
      { to: '/finance/cashBank', label: 'نقد و حواله', icon: '⇄' },
      { to: '/finance/companyPayments', label: 'حواله‌های پرداختی شرکت', icon: '↗' },
      { to: '/finance/b2bRemittances', label: 'حواله‌های مشتریان B2B', icon: '⇢' },
      { to: '/finance/liquidity', label: 'نقدینگی', icon: '₪' },
      { to: '/finance/cashflow', label: 'پیش‌بینی نقدینگی', icon: '⌁' },
      { to: '/finance/monthlyExcel', label: 'Cash Flow روزانه', icon: '▥' },
      { to: '/finance/collections', label: 'مرکز عملیات وصول', icon: '✓' },
      { to: '/finance/distribution', label: 'توزیع بار', icon: '⛟' },
      { to: '/finance/simulator', label: 'سناریوساز نقدینگی', icon: '◫' },
    ],
  },
  {
    id: 'files', label: 'پرونده‌ها', dot: 'var(--u-text)', items: [
      { to: '/files/hybrids', label: 'هیبریدها', icon: '⬢' },
      { to: '/finance/customers', label: 'پرونده مشتری', icon: '◎' },
      { to: '/finance/representatives', label: 'نمایندگان', icon: '♙' },
    ],
  },
  {
    id: 'system', label: 'سیستم و Agentها', dot: 'var(--u-muted)', collapsible: true, items: [
      { to: '/finance/alerts', label: 'هشدارها', icon: '!' },
      { to: '/finance/agents', label: 'تیم Agentها', icon: '⬡' },
      { to: '/finance/history', label: 'تاریخچه و مقایسه', icon: '↺' },
      { to: '/finance/performance', label: 'دقت پیش‌بینی', icon: '◉' },
      { to: '/finance/settings', label: 'قوانین و اتوماسیون', icon: '⚙' },
      { to: '/data', label: 'منبع داده فروش', icon: '⇪' },
    ],
  },
]

/** sales backend live check (sql_source.live_step): true while it is reading Karamad every few seconds */
function useSalesLive() {
  const [live, setLive] = useState(null)
  useEffect(() => {
    const check = () => fetchJson('/api/stamp').then((s) => setLive(!!s.live)).catch(() => setLive(false))
    check()
    const id = setInterval(check, 10000)
    return () => clearInterval(id)
  }, [])
  return live
}

function SourceStatus() {
  const { meta, metaError } = useApp()
  const live = useSalesLive()
  const fin = useJson('/api/v1/liquidity/categories')
  const salesAt = meta?.file?.months?.find((m) => m.month === meta?.file?.month)?.fetched
  const salesSub = metaError ? 'قطع'
    : live ? 'متصل'
      : salesAt ? faDigits(salesAt.slice(11, 16)) // live off or stalled: show when the data is from
        : '…'
  const rows = [
    { label: 'فروش (کارآمد)', ok: !!meta && !metaError, sub: salesSub },
    { label: 'مالی (راهکاران و کارآمد)', ok: !!fin.data, sub: fin.error ? 'قطع' : fin.data ? 'متصل' : '…' },
  ]
  return (
    <div className="u-sources">
      {rows.map((r) => (
        <div key={r.label}>
          <i className={r.ok ? 'ok' : 'off'} />
          <span>{r.label}</span>
          <small>{r.sub}</small>
        </div>
      ))}
    </div>
  )
}

export default function Shell() {
  const { pathname } = useLocation()
  const busy = useBusy()
  const [menuOpen, setMenuOpen] = useState(false)
  const [sysOpen, setSysOpen] = useState(() => pathname.startsWith('/finance/') && GROUPS.find((g) => g.collapsible).items.some((i) => i.to === pathname))
  useEffect(() => { window.scrollTo(0, 0); setMenuOpen(false) }, [pathname])
  return (
    <div className="u-app">
      <aside className={`u-side ${menuOpen ? 'open' : ''}`}>
        <div className="u-brand">
          <i>ا</i>
          <div><b>اکسیر کادوس</b><small>Management Command Center</small></div>
        </div>
        {GROUPS.map((g) => {
          const open = !g.collapsible || sysOpen
          return (
            <nav key={g.id} aria-label={g.label || 'اصلی'} className="u-nav">
              {g.label && (g.collapsible
                ? <button className="u-nav-head" onClick={() => setSysOpen(!sysOpen)} aria-expanded={sysOpen}>
                    <span style={{ background: g.dot }} />{g.label}<em>{sysOpen ? '▴' : '▾'}</em>
                  </button>
                : <div className="u-nav-head"><span style={{ background: g.dot }} />{g.label}</div>)}
              {open && g.items.map((it) => (
                <NavLink key={it.to} to={it.to} end={it.end}>
                  <i aria-hidden>{it.icon}</i>{it.label}
                </NavLink>
              ))}
            </nav>
          )
        })}
        <SourceStatus />
      </aside>
      <main className={`u-main ${busy ? 'busy' : ''}`}>
        {busy && <div className="u-loadbar" role="progressbar" aria-label="در حال بروزرسانی" />}
        <button className="u-menu-btn" onClick={() => setMenuOpen(!menuOpen)} aria-label="منو">☰</button>
        <Outlet />
      </main>
    </div>
  )
}
