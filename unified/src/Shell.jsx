import { useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useApp, useBusy, fetchJson } from '@sales/lib.jsx'
import { useAuth } from '@finance/auth/auth.tsx'
import ThemePicker from '@finance/theme/theme-picker.tsx'
import { AlarmBell, AlarmToasts, startAlarms, stopAlarms } from '@finance/alarms/alarms.tsx'
import ChatWidget from '@finance/chatbot/chat-widget.tsx'
import Pet from '@finance/pet/pet.tsx'
import { useJson, faDigits } from './data.js'
import TopBar from './TopBar.jsx'
import { getMoneyUnit, setMoneyUnit } from '@finance/money-unit.ts'

const GROUPS = [
  { id: 'home', items: [{ to: '/', label: 'نمای مدیر', icon: '✦', end: true }] },
  {
    id: 'sales', label: 'فروش کارآمد (هیبرید)', dot: 'var(--u-sales)', items: [
      { to: '/finance/sales', label: 'خلاصه مدیریتی فروش', icon: '◈' },
      { to: '/sales', label: 'نمای کلی فروش', icon: '◱' },
      { to: '/hybrid', label: 'عملکرد هیبرید', icon: '⌂' },
      { to: '/team', label: 'تیم فروش', icon: '☺' },
      { to: '/products', label: 'محصولات و گروه‌ها', icon: '▦' },
      { to: '/customers', label: 'مشتریان (فروش)', icon: '◎' },
      { to: '/analysis', label: 'تحلیل فروش', icon: '◔' },
      { to: '/inventory', label: 'موجودی و سفارش', icon: '▤' },
      { to: '/commission', label: 'تحقق و پورسانت', icon: '٪' },
      { to: '/contest', label: 'مسابقه', icon: '★' },
    ],
  },
  {
    id: 'rahkaran', label: 'فروش راهکاران (B2B)', dot: 'var(--u-sales)', items: [
      { to: '/rahkaran', label: 'نمایندگان B2B', icon: '◉', end: true },
      { to: '/rahkaran/customer-brand', label: 'مشتری × برند', icon: '▦' },
      { to: '/rahkaran/total-report', label: 'گزارش کل (Total)', icon: '☰' },
      { to: '/rahkaran/compare', label: 'مقایسه', icon: '⇄' },
      { to: '/rahkaran/reorder', label: 'پیشنهاد سفارش', icon: '⟳' },
      { to: '/rahkaran/export', label: 'فروش صادراتی', icon: '✈' },
      { to: '/rahkaran/commission', label: 'پورسانت نمایندگان و صادرات', icon: '٪' },
    ],
  },
  {
    id: 'finance', label: 'مالی و خزانه', dot: 'var(--u-fin)', items: [
      { to: '/finance/management', label: 'خلاصه مدیریتی مالی', icon: '✧' },
      { to: '/finance/cheques', label: 'چک و سررسید', icon: '◷' },
      { to: '/finance/cashBank', label: 'نقد و حواله', icon: '⇄' },
      { to: '/finance/companyPayments', label: 'حواله‌های پرداختی شرکت', icon: '↗' },
      { to: '/finance/payables', label: 'پرداخت تجاری', icon: '◧' },
      { to: '/finance/liquidity', label: 'نقدینگی', icon: '₪' },
      { to: '/finance/inventoryPricing', label: 'قیمت‌گذاری انبار', icon: '▦' },
      { to: '/finance/purchaseDocs', label: 'اسناد خرید', icon: '▤' },
      { to: '/finance/pnl', label: 'سود و زیان (P&L)', icon: '∑' },
      { to: '/finance/collections', label: 'مرکز عملیات وصول', icon: '✓' },
      { to: '/finance/distribution', label: 'توزیع بار', icon: '⛟' },
      { to: '/reconciliation', label: 'مغایرت‌گیری بانک', icon: '⚖' },
    ],
  },
  {
    id: 'files', label: 'پرونده‌ها', dot: 'var(--u-text)', items: [
      { to: '/files/hybrids', label: 'هیبریدها', icon: '⬢' },
      { to: '/files/rahkaran', label: 'نمایندگان راهکاران', icon: '◉' },
      { to: '/finance/customers', label: 'پرونده مشتری', icon: '◎' },
      { to: '/finance/representatives', label: 'تحلیل نماینده (مالی)', icon: '♙' },
      { to: '/contracts', label: 'قراردادهای همکاران', icon: '✎' },
    ],
  },
  {
    id: 'reports', label: 'گزارش‌ها', dot: 'var(--u-warn)', items: [
      { to: '/reports', label: 'گزارش‌ساز اکسل', icon: '▦' },
    ],
  },
  {
    id: 'system', label: 'سیستم و الارم‌ها', dot: 'var(--u-muted)', items: [
      { to: '/finance/alerts', label: 'مرکز الارم‌ها', icon: '🔔' },
      { to: '/finance/users', label: 'مدیریت کاربران', icon: '👥' },
      { to: '/finance/history', label: 'تاریخچه و مقایسه', icon: '↺' },
      { to: '/finance/performance', label: 'دقت پیش‌بینی', icon: '◉' },
      { to: '/finance/settings', label: 'قوانین و اتوماسیون', icon: '⚙' },
      { to: '/finance/whatsapp', label: 'ارسال واتساپ', icon: '✆' },
      { to: '/data', label: 'منبع داده فروش', icon: '⇪' },
    ],
  },
]

// مسیرهای فروش ← ماژول‌های مجاز (کلیدها: backend/app/auth/modules.py؛ API همین صفحه‌ها: sales/backend/exir_auth.py).
// اولین تطابق اعمال می‌شود؛ پس مسیر دقیق‌تر بالاتر است.
const SALES_ALL = ['sales', 'salesOverview', 'salesHybrid', 'salesTeam', 'salesProducts', 'salesCustomers', 'salesAnalysis', 'salesInventory', 'salesB2B', 'salesExport', 'salesCommission']
const ROUTE_MODULES = [
  ['/', ['management', 'sales'], true],
  ['/sales', ['salesOverview']],
  ['/hybrid', ['salesHybrid']],
  ['/files/hybrids', ['salesHybrid']],
  ['/files/visitors', ['salesHybrid', 'salesTeam']],
  ['/team', ['salesTeam']],
  ['/products', ['salesProducts']],
  ['/customers', ['salesCustomers']],
  ['/analysis', ['salesAnalysis']],
  ['/inventory', ['salesInventory']],
  ['/commission', ['salesCommission']],
  ['/rahkaran/export', ['salesExport']],
  ['/rahkaran/commission', ['salesCommission', 'salesB2B', 'salesExport']],
  ['/rahkaran', ['salesB2B']],
  ['/files/rahkaran', ['salesB2B', 'customers']],
  ['/reconciliation', ['reconciliation']],
  ['/reports', ['excelReports']],
  ['/contracts', ['contracts']],
  ['/detail', SALES_ALL],
]

/** سطح دسترسی هر مسیر بر اساس ماژول‌های کاربر. */
function canOpen(path, { can, hasModule, profile }) {
  if (profile.user.is_admin) return true
  if (path.startsWith('/finance/')) return can(path.split('/')[2] || '')
  if (path === '/data') return false
  const hit = ROUTE_MODULES.find(([r, , exact]) => path === r || (!exact && path.startsWith(`${r}/`)))
  return (hit ? hit[1] : SALES_ALL).some((m) => hasModule(m))
}

/** کاربر فعلی، زنگوله الارم، تم و خروج — پایین منوی کناری (استایل‌هایش زیر .fin-scope است). */
function UserBox() {
  const { profile, logout } = useAuth()
  const nav = useNavigate()
  const look = profile.user.preferences || {}
  useEffect(() => { startAlarms(profile.user.username); return () => stopAlarms() }, [profile.user.username])
  const go = (v) => nav(`/finance/${v}`)
  return (
    <div className="fin-scope u-userbox" data-theme={look.theme || 'teal'} data-wallpaper={look.wallpaper || 'none'}>
      <div className="fd-head-tools">
        {!profile.alarms_hidden && <AlarmBell onGo={go} />}
        <ThemePicker />
      </div>
      <span className="user-chip">
        <i>{profile.user.full_name.slice(0, 1)}</i>
        <span>{profile.user.full_name}<small>{profile.user.is_admin ? 'مدیر سیستم' : profile.user.username}</small></span>
        <button type="button" onClick={() => void logout()}>خروج</button>
      </span>
      {!profile.alarms_hidden && <AlarmToasts onGo={go} />}
    </div>
  )
}

/** یک چت‌بات برای همه صفحه‌ها: صفحه مالی ← همان view؛ صفحه‌های فروش و پرونده‌ها ← «sales»؛ نمای مدیر ← «management». */
function ShellChat({ pathname }) {
  const nav = useNavigate()
  const { can, hasModule } = useAuth()
  if (!hasModule('chatbot')) return null
  const view = pathname.startsWith('/finance/') ? pathname.split('/')[2] : pathname === '/' && can('management') ? 'management' : 'sales'
  return <div className="fin-scope u-chat"><ChatWidget view={view} go={(v) => nav(`/finance/${v}`)} /></div>
}

/** حیوان خانگی کاربر روی همه صفحه‌ها؛ رفتن به صفحه: view مالی یا مسیر یکپارچه */
function ShellPet() {
  const nav = useNavigate()
  return <div className="fin-scope u-chat"><Pet onGo={(v) => nav(v.startsWith('/') ? v : `/finance/${v}`)} /></div>
}

/** sales backend live check (sql_source.live_step): true while it is reading Karamad every few seconds */
function useSalesLive() {
  const [live, setLive] = useState(null)
  useEffect(() => {
    // تب پنهان نمی‌پرسد؛ پس اگر هیچ تب بازی نباشد، بک‌اند فروش بررسی‌های لایو SQL را متوقف می‌کند (viewers_idle)
    const check = () => { if (!document.hidden) fetchJson('/api/stamp').then((s) => setLive(!!s.live)).catch(() => setLive(false)) }
    check()
    const id = setInterval(check, 10000)
    document.addEventListener('visibilitychange', check)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', check) }
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

/** سرفصلی که صفحه فعلی زیر آن است (دقیق‌ترین تطابق مسیر) */
function groupOf(pathname) {
  let best = null
  for (const g of GROUPS) {
    for (const it of g.items) {
      const hit = it.to === pathname || (it.to !== '/' && pathname.startsWith(`${it.to}/`))
      if (hit && (!best || it.to.length > best.len)) best = { id: g.id, len: it.to.length }
    }
  }
  return best?.id
}

/** مورد منویی که صفحه فعلی زیر آن است (دقیق‌ترین تطابق مسیر) */
function itemOf(pathname) {
  let best = null
  for (const g of GROUPS) {
    for (const it of g.items) {
      const hit = it.to === pathname || (it.to !== '/' && pathname.startsWith(`${it.to}/`))
      if (hit && (!best || it.to.length > best.to.length)) best = it
    }
  }
  return best
}

const FREQUENT_MIN_VISITS = 3   // صفحه‌ای که دست‌کم این‌قدر باز شده در «پرکاربردها» می‌آید
const FREQUENT_MAX = 5

export default function Shell() {
  const auth = useAuth()
  const { pathname } = useLocation()
  const busy = useBusy()
  const { setUnit: setSalesUnit } = useApp()
  // واحد پول کل برنامه؛ جدول‌های فروش واحد خودشان (useApp) را دارند که با همین کلید هم‌گام می‌شود («خودکار» ← میلیون)
  const [unit, setUnit] = useState(getMoneyUnit)
  useEffect(() => { if (unit !== 'auto') setSalesUnit(unit) }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const changeUnit = (u) => { setMoneyUnit(u); setUnit(u); setSalesUnit(u === 'auto' ? 'million' : u) }
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((it) => canOpen(it.to, auth) && !(it.to === '/finance/alerts' && auth.profile.alarms_hidden)) })).filter((g) => g.items.length)
  const pages = groups.flatMap((g) => g.items.map((it) => ({ to: it.to, label: it.label, group: g.label || '' })))
  // شمارنده بازدید هر صفحه برای همین کاربر (فقط در همین مرورگر) ← بخش «پرکاربردها» بالای منو
  const visitKey = `exir.visits:${auth.profile.user.username}`
  const [visits, setVisits] = useState(() => { try { return JSON.parse(localStorage.getItem(visitKey) || '{}') } catch { return {} } })
  useEffect(() => {
    const it = itemOf(pathname)
    if (!it || it.to === '/') return
    setVisits((v) => {
      const next = { ...v, [it.to]: (v[it.to] || 0) + 1 }
      try { localStorage.setItem(visitKey, JSON.stringify(next)) } catch { /* حالت خصوصی */ }
      return next
    })
  }, [pathname, visitKey])
  const frequent = groups.flatMap((g) => g.items).filter((it) => it.to !== '/' && (visits[it.to] || 0) >= FREQUENT_MIN_VISITS)
    .sort((a, b) => visits[b.to] - visits[a.to]).slice(0, FREQUENT_MAX)
  const [menuOpen, setMenuOpen] = useState(false)
  // منوی آکاردئونی: با کلیک روی هر سرفصل ماژول‌های ریزش باز می‌شود و بقیه جمع می‌شوند
  const [openGroup, setOpenGroup] = useState(() => groupOf(pathname))
  useEffect(() => { window.scrollTo(0, 0); setMenuOpen(false) }, [pathname])
  useEffect(() => { const g = groupOf(pathname); if (g) setOpenGroup(g) }, [pathname])
  return (
    <div className="u-app">
      <aside className={`u-side ${menuOpen ? 'open' : ''}`}>
        <div className="u-brand">
          <i>ا</i>
          <div><b>اکسیر کادوس</b><small>Management Command Center</small></div>
        </div>
        {groups.map((g, gi) => {
          const open = !g.label || openGroup === g.id
          const links = g.items.map((it, i) => (
            <NavLink key={it.to} to={it.to} end={it.end} style={{ '--i': i }} tabIndex={open ? undefined : -1}>
              <i aria-hidden>{it.icon}</i>{it.label}
            </NavLink>
          ))
          return (
            <nav key={g.id} aria-label={g.label || 'اصلی'} className={`u-nav ${open ? 'open' : ''}`} style={{ '--g': gi }}>
              {g.label ? <>
                <button className="u-nav-head" onClick={() => setOpenGroup(open ? null : g.id)} aria-expanded={open}>
                  <span style={{ background: g.dot }} />{g.label}
                  <b className="u-nav-count">{faDigits(g.items.length)}</b>
                  <em aria-hidden>▾</em>
                </button>
                <div className="u-nav-body"><div>{links}</div></div>
              </> : links}
              {g.id === 'home' && frequent.length >= 2 && (
                <div className="u-nav-frequent" aria-label="پرکاربردها">
                  <small>پرکاربردهای شما</small>
                  {frequent.map((it) => <NavLink key={`f:${it.to}`} to={it.to} end={it.end}><i aria-hidden>{it.icon}</i>{it.label}</NavLink>)}
                </div>
              )}
            </nav>
          )
        })}
        <SourceStatus />
        <UserBox />
      </aside>
      <main className={`u-main ${busy ? 'busy' : ''}`}>
        {busy && <div className="u-loadbar" role="progressbar" aria-label="در حال بروزرسانی" />}
        <button className="u-menu-btn" onClick={() => setMenuOpen(!menuOpen)} aria-label="منو">☰</button>
        <TopBar pages={pages} unit={unit} onUnit={changeUnit} />
        {/* key = واحد پول: با عوض شدن واحد، صفحه از نو ساخته می‌شود تا همه مبالغ با واحد تازه نوشته شوند */}
        {canOpen(pathname, auth) ? <div key={unit} className="u-unit-scope"><Outlet /></div>
          : pathname === '/' ? <Navigate to={GROUPS.flatMap((g) => g.items).find((it) => canOpen(it.to, auth))?.to || '/finance/alerts'} replace />
            : <div className="u-noaccess"><b>به این بخش دسترسی ندارید</b><span>برای دسترسی با مدیر سیستم هماهنگ کنید.</span><Link className="u-btn" to="/">بازگشت</Link></div>}
        <ShellChat pathname={pathname} />
        <ShellPet />
      </main>
    </div>
  )
}
