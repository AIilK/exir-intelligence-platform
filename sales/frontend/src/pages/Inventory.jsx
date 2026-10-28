import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApp, useFetch, sendJson, fetchJson, fmtCompact, fmtInt, fmtMoney, fmtPct, fmtNum1, faDigits, isNum, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, Tabs, Kpi, DataTable, MultiSelect } from '../components/ui.jsx'
import { Chart, HBar, baseOption, useTheme } from '../components/Chart.jsx'
import { brandColor } from '../brands.js'
import { Spark } from '../components/TreeTable.jsx'
import { PageHead } from '../components/Layout.jsx'
import { Alerts } from './Plan.jsx'

const TABS = [
  { value: 'summary', label: 'خلاصه مدیریتی' },
  { value: 'order', label: 'سفارش و هشدارها' },
  { value: 'items', label: 'کالاها' },
  { value: 'remit', label: 'حواله‌های فروش' },
  { value: 'factory', label: 'انبار کارخانه' },
  { value: 'settings', label: 'تنظیمات' },
]
// زیرنمای تب «کالاها»
const ITEM_VIEWS = [
  { value: 'all', label: 'همه کالاها' },
  { value: 'idle', label: 'راکد و مازاد (برگشتی)' },
  { value: 'supplier', label: 'تأمین‌کنندگان' },
]
// پیوندهای قدیمی (تب‌های ادغام‌شده) به تب جدید
const OLD_TABS = { branches: ['summary'], all: ['items', 'all'], supplier: ['items', 'supplier'], idle: ['items', 'idle'] }
// تب‌های سطح شرکت (همه شعب)؛ بقیه تب‌ها برای شعبه انتخاب‌شده‌اند
const GLOBAL_TABS = new Set(['factory', 'remit'])
const BRANCH_KEY = 'sd.invBranch'
const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const monthName = (m) => (m ? `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}` : '—')
const dayName = (d) => (d ? `${faDigits(Number(d.slice(8, 10)))} ${MONTHS[Number(d.slice(5, 7)) - 1]}` : '—')
// رنگ وضعیت: قرمز و نارنجی نیاز به اقدام؛ بقیه خنثی
const ST_CLASS = { red: 'st-red', orange: 'st-yellow', ok: 'st-green', excess: 'st-none', dead: 'st-none', c: 'st-none', nodata: 'st-none' }


// برچسب وضعیت؛ «فوری» جدا نیست: سفارش بعدی با تگ فوری (متن کامل در tooltip)
function StatusPill({ s, labels, low }) {
  const st = s === 'red' ? 'orange' : s
  return (
    <span className="pill-row" title={low ? 'کالای کم‌فروش ولی منظم: موجودی به فروش تا رسیدن بار رسیده؛ به اندازه فروش چند هفته سفارش داده می‌شود' : labels[s]}>
      <span className={`pill ${ST_CLASS[st] || 'st-none'}`}>{ST_SHORT[st] || labels[s] || s}</span>
      {low ? <span className="pill st-none">کم‌فروش</span> : s === 'red' && <span className="pill st-red">فوری</span>}
    </span>
  )
}

export default function Inventory() {
  const [sp, setSp] = useSearchParams()
  const old = OLD_TABS[sp.get('tab')]
  const tab = old ? old[0] : TABS.some((t) => t.value === sp.get('tab')) ? sp.get('tab') : 'summary'
  const [view, setView] = useState(old?.[1] || 'all')
  // شعب انتخابی (یک یا چند شعبه که با هم محاسبه می‌شوند) و انبارهای انتخابی (خالی = همه انبارهای آن شعب)
  const [sel, setSelState] = useState(() => {
    if (sp.getAll('branch').length) return sp.getAll('branch')
    try {
      const v = localStorage.getItem(BRANCH_KEY) || ''
      return v.startsWith('[') ? JSON.parse(v) : v ? [v] : []
    } catch { return [] }
  })
  const [stores, setStores] = useState([])
  const q = sel.length || stores.length
    ? `?${[...sel.map((b) => `branch=${encodeURIComponent(b)}`), ...stores.map((x) => `store=${x}`)].join('&')}` : ''
  // داده شعبه همیشه خوانده می‌شود تا فیلتر شعبه در همه زیرتب‌ها (حتی نمای کلی و انبار کارخانه) در دسترس باشد
  const { data, error, setData } = useFetch(`/api/inventory${q}`)
  // فهرست شعب جدا خوانده می‌شود تا اگر محاسبه شعبه انتخابی خطا داد (مثلاً سابقه ناکافی)، فیلتر قفل نشود
  const { data: brList } = useFetch('/api/inventory/branches')
  const branches = brList?.branches || data?.branches || []
  // نام نمایشی شعبه (مثلاً «زنجیره ای» کارآمد → «هیبرید زنجیره‌ای»)؛ مقدار همان نام کارآمد می‌ماند
  const labels = brList?.labels || data?.labels || {}
  const lbl = (b) => labels[b] || b
  // شعبه انتخابی کاربر؛ تا اولین انتخاب، شعبه پیش‌فرض سرور
  const cur = sel.length ? sel : data?.selected || (brList?.default ? [brList.default] : [])
  const curLabel = cur.map(lbl).join('، ')
  // داده رسیده مربوط به همین انتخاب است؟ (تا رسیدن پاسخ جدید، داده قبلی می‌ماند)
  const dataStores = data?.store_filtered ? data.stores.filter((x) => x.selected).map((x) => x.id) : []
  const sameSel = !!data && (!sel.length || data.selected?.join('|') === sel.join('|'))
  const loadingBranch = !!data && !error && (!sameSel || dataStores.join('|') !== [...stores].sort((a, b) => a - b).join('|'))
  // انبارهای شعب انتخابی (از پاسخ همین انتخاب)؛ ضایعات و مغایرت جدا علامت می‌خورند
  const storeOpts = sameSel ? (data.stores || []).map((x) => ({
    value: x.id, label: `${x.name}${x.wastage ? ' (ضایعات)' : ''}`, group: cur.length > 1 ? lbl(x.branch) : '',
  })) : []
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  // فیلتر وضعیت جدول سفارش و نوع فهرست راکد/مازاد؛ کارت‌ها با کلیک آن‌ها را تنظیم می‌کنند
  const [status, setStatus] = useState('all')
  const [idle, setIdle] = useState('all')
  // انتخاب خالی شعبه = شعبه پیش‌فرض؛ با عوض شدن شعب، فیلتر انبار پاک می‌شود (انبارها مال شعب قبلی‌اند)
  const setSel = (v) => {
    const b = v.length ? v : (brList?.default ? [brList.default] : [])
    setSelState(b)
    setStores([])
    try { localStorage.setItem(BRANCH_KEY, JSON.stringify(b)) } catch { /* ignore */ }
  }
  const setBranch = (b) => setSel([b])
  const go = (t, extra) => {
    if (t === 'all') { setStatus(extra || 'all'); setView('all'); t = 'items' }
    if (t === 'idle') { setIdle(extra); setView('idle'); t = 'items' }
    setSp({ tab: t })
  }
  // انتخاب شعبه از جدول همه شعب: بخش «شعبه انتخاب‌شده» همان پایین صفحه عوض می‌شود
  const branchRef = useRef(null)
  const openBranch = (b) => {
    setBranch(b)
    setTimeout(() => branchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
  }
  const refresh = async () => {
    setBusy(true); setErr(null)
    try { setData(await fetchJson(`/api/inventory${q ? `${q}&` : '?'}refresh=true`)) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const global = GLOBAL_TABS.has(tab)
  return (
    <>
      <PageHead title="موجودی و سفارش"
        desc={tab === 'factory' ? 'موجودی انبارهای کارخانه از راهکاران، کنار جمع موجودی شعب هیبرید از کارآمد. فقط خوانده می‌شود.'
          : tab === 'remit' ? 'حواله‌های فروش ثبت‌شده زنجیره‌ای و اینترنتی در راهکاران، با پیشنهاد تأیید هر کالا از موجودی و فروش همان شعبه در کارآمد. فقط خوانده می‌شود.'
          : tab === 'summary' ? 'وضعیت انبار و سفارش همه شعب هیبرید و، پایین‌تر، شعبه انتخاب‌شده. موجودی و ارزش انبار از کارآمد.'
          : data ? `${(data.selected || []).map(lbl).join('، ')} — هشدار کمبود، پیشنهاد سفارش (حداکثر دو سفارش در ماه) و کالاهای راکد. موجودی از کارآمد فقط خوانده می‌شود${data.rahkaran?.ok ? '؛ سفارش و بار در راه کارخانه از راهکاران' : ''}.`
            : 'هشدار کمبود، پیشنهاد سفارش و کالاهای راکد'}>
        <Tabs tabs={TABS} value={tab} onChange={(v) => setSp({ tab: v })} />
      </PageHead>
      {/* فیلتر شعبه برای کل صفحه: در همه زیرتب‌ها دیده می‌شود و انتخاب آن همه را تغییر می‌دهد */}
      {tab !== 'remit' && <div className="plan-bar">
        {/* مقدار = انتخاب کاربر (نه شعبه داده قبلی)، تا تا رسیدن داده شعبه جدید به عقب برنگردد */}
        <MultiSelect label="شعبه" value={cur} onChange={setSel}
          options={(branches.length ? branches : cur).map((b) => ({ value: b, label: lbl(b) }))} />
        {!global && <MultiSelect label="انبار" value={stores} onChange={setStores} options={storeOpts} />}
        {loadingBranch && <span className="pill st-none">در حال خواندن {curLabel}…</span>}
        {!global && cur.length > 1 && <span className="muted small">{faDigits(cur.length)} شعبه با هم محاسبه می‌شوند (موجودی، فروش و سفارش جمع شعب).</span>}
        {!global && stores.length > 0 && <span className="muted small">فیلتر انبار فقط موجودی را محدود می‌کند؛ فروش و پیش‌بینی همان کل شعبه است.</span>}
        {global && <span className="muted small">موجودی و فروش این شعبه کنار جمع همه هیبریدها در جدول کالاها آمده است.</span>}
        {tab === 'summary' && <span className="muted small">یا در جدول «وضعیت شعب» روی ردیف شعبه کلیک کنید.</span>}
        {!global && data && (
            <>
              {data.inactive && <span className="pill st-red">شعبه غیرفعال</span>}
              {data.data_issue && <span className="pill st-yellow">داده خرید ناقص</span>}
              {data.break_month && <span className="pill st-yellow">پایه از {faDigits(data.break_month)} (تغییر ساختاری فروش)</span>}
              {data.rahkaran?.ok
                ? <span className="pill st-green" title={`مشتریان این شعبه در راهکاران: ${data.rahkaran.customers.join('، ') || '—'}`}>
                    راهکاران: {fmtInt(data.kpis.rk_open)} سفارش باز · {fmtInt(data.kpis.rk_transit)} در راه</span>
                : data.rahkaran?.error && <span className="pill st-yellow" title={data.rahkaran.error}>راهکاران در دسترس نیست</span>}
            </>
        )}
      </div>}
      {tab === 'summary' && <BranchesTab onOpen={openBranch} current={cur} />}
      {tab === 'factory' && <FactoryTab />}
      {tab === 'remit' && <RemitTab />}
      {!global && (
        <>
          {tab === 'summary' && <h3 ref={branchRef} className="section-title">{cur.length > 1 ? 'شعب انتخاب‌شده' : 'شعبه انتخاب‌شده'}: {curLabel || '—'}</h3>}
          {(error || err) && <ErrorBox error={error || err} />}
          {!data ? (!error && <Loading />) : (
            <>
              {tab !== 'settings' && <OrderBar data={data} onRefresh={refresh} busy={busy} />}
              {tab === 'summary' && <SummaryTab data={data} go={go} />}
              {tab === 'order' && <OrderTab data={data} />}
              {tab === 'items' && (
                <>
                  <div className="inv-summary-head"><Tabs tabs={ITEM_VIEWS} value={view} onChange={setView} /></div>
                  {view === 'all' && <AllTab data={data} status={status} setStatus={setStatus} />}
                  {view === 'supplier' && <SupplierTab data={data} />}
                  {view === 'idle' && <IdleTab data={data} kind={idle} setKind={setIdle} />}
                </>
              )}
              {tab === 'settings' && <SettingsTab data={data} setData={setData} />}
            </>
          )}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- خلاصه مدیریتی: همه شعب
const money = (v) => { const c = fmtCompact(v); return `${c.value} ${c.unit}`.trim() }
// وضعیت ساده هر شعبه برای مدیر: یک برچسب رنگی
const branchState = (r) => (r.error ? ['st-none', 'سابقه ناکافی', r.error]
  : r.inactive ? ['st-red', 'غیرفعال']
    : r.days_to_deadline === 0 ? ['st-red', 'سفارش امروز']
      : r.order_lines > 0 ? ['st-yellow', 'سفارش بعدی دارد']
        : r.data_issue ? ['st-yellow', 'داده خرید ناقص', r.data_issue]
          : ['st-green', 'عادی'])

function BranchesTab({ onOpen, current }) {
  const { unit } = useApp()
  const { data, error } = useFetch('/api/inventory/overview')
  if (error) return <ErrorBox error={error} />
  if (!data) return <div className="state">در حال محاسبه برای همه شعب… (بار اول ممکن است تا یک دقیقه طول بکشد)</div>
  const lbl = (b) => data.labels?.[b] || b
  const byLabel = Object.fromEntries(data.branches.map((r) => [lbl(r.branch), r.branch]))
  const all = data.branches
  const act = all.filter((r) => !r.error && !r.inactive)
  const sum = (k, rs = all) => rs.reduce((a, r) => a + (r[k] || 0), 0)
  const total = sum('total_value')
  const idle = sum('dead_value') + sum('excess_value')
  const issues = all.filter((r) => r.data_issue)
  const noHist = all.filter((r) => r.error)
  return (
    <>
      <h3 className="section-title">همه شعب هیبرید</h3>
      <div className="kpis">
        <Kpi label="ارزش کل موجودی" value={total}
          sub={`انبار اصلی ${money(sum('main_value'))} · ضایعات ${money(sum('waste_value'))} · ${fmtInt(sum('total_units'))} عدد`}
          hint="همان «ارزش انبار» گزارش کارآمد: هر شعبه با میانگین قیمت خرید خودش" />
        <Kpi label="ضایعات" value={sum('waste_value')} sub={`${fmtPct(sum('waste_value') / Math.max(total, 1), 1)} ارزش موجودی · ${fmtInt(sum('waste_units'))} عدد`} />
        <Kpi label="راکد + مازاد" value={idle} sub={`${fmtPct(idle / Math.max(sum('main_value'), 1), 0)} انبار اصلی؛ پول خوابیده`} />
        <Kpi label="سفارش بعدی همه شعب" value={sum('order_value', act)} sub={`${fmtInt(sum('order_lines', act))} قلم · ${fmtInt(sum('order_units', act))} عدد`} />
      </div>
      {(issues.length > 0 || noHist.length > 0) && (
        <div className="alerts">
          {noHist.length > 0 && <div className="alert warn"><span className="alert-icon">!</span>
            <span>بدون سابقه کافی برای پیشنهاد سفارش (فقط موجودی نمایش داده می‌شود): {noHist.map((r) => lbl(r.branch)).join('، ')}</span></div>}
          {issues.length > 0 && <div className="alert warn"><span className="alert-icon">!</span>
            <span>داده خرید ناقص (موجودی کارآمد ممکن است دقیق نباشد): {issues.map((r) => lbl(r.branch)).join('، ')} — برای جزئیات نشانگر را روی وضعیت ببرید.</span></div>}
        </div>
      )}
      <Card title="وضعیت شعب"
        subtitle={`موجودی خوانده‌شده ${faDigits(data.fetched.slice(11))} · روی هر شعبه کلیک کنید تا جزئیات آن پایین همین صفحه بیاید`}>
        <DataTable rows={all.map((r) => ({ ...r, key: r.branch }))} unit={unit} pageSize={25} dense search={false}
          exportName="inventory-branches" defaultSort={{ key: 'total_value', dir: 'desc' }} onRowClick={(r) => onOpen(r.branch)}
          columns={[
            { key: 'branch', label: 'شعبه', csv: (r) => lbl(r.branch), render: (r) => <>{lbl(r.branch)}{current.includes(r.branch) && <span className="tag">انتخاب‌شده</span>}</> },
            { key: 'state', label: 'وضعیت', csv: (r) => branchState(r)[1], render: (r) => { const [c, l, t] = branchState(r); return <span className={`pill ${c}`} title={t}>{l}</span> } },
            { key: 'main_units', label: 'انبار اصلی (تعداد)', type: 'int', hint: 'جمع موجودی انبارهای قابل فروش شعبه در کارآمد؛ موجودی منفی صفر حساب شده' },
            { key: 'main_value', label: 'انبار اصلی (ارزش)', type: 'money', hint: 'همان «ارزش انبار» گزارش کارآمد: موجودی × میانگین قیمت خرید این شعبه' },
            { key: 'waste_units', label: 'ضایعات (تعداد)', type: 'int', hint: 'انبارهایی که نامشان «ضایعات» یا «مغایرت» دارد' },
            { key: 'waste_value', label: 'ضایعات (ارزش)', type: 'money' },
            { key: 'total_units', label: 'جمع (تعداد)', type: 'int' },
            { key: 'total_value', label: 'جمع (ارزش)', type: 'money' },
            { key: 'deadline', label: 'مهلت سفارش', type: 'date' },
            { key: 'order_value', label: 'ارزش سفارش بعدی', type: 'money' },
          ]} />
      </Card>
      <Card title="ترکیب ارزش موجودی هر شعبه" subtitle="انبار اصلی به سالم، مازاد (بیش از ۶ ماه پوشش) و راکد (بدون فروش ۹۰ روز)، به‌علاوه ضایعات؛ روی هر شعبه کلیک کنید">
        <Chart height={Math.max(260, all.length * 26)} onClick={(p) => p?.name && onOpen(byLabel[p.name] || p.name)} option={(t) => {
          const rs = [...all].sort((a, b) => (a.total_value || 0) - (b.total_value || 0))
          const ok = (r) => Math.max((r.main_value || 0) - (r.dead_value || 0) - (r.excess_value || 0), 0)
          const s = (name, data, color) => ({ name, type: 'bar', stack: 's', data, itemStyle: { color }, cursor: 'pointer' })
          return {
            grid: { left: 12, right: 24, top: 30, bottom: 8, containLabel: true },
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => money(v) },
            legend: { top: 0, textStyle: { color: t.text } },
            xAxis: { type: 'value', axisLabel: { color: t.text, formatter: (v) => fmtCompact(v).value }, splitLine: { lineStyle: { color: t.grid } } },
            yAxis: { type: 'category', data: rs.map((r) => lbl(r.branch)), axisLabel: { color: t.text } },
            series: [
              s('سالم', rs.map(ok), t.series[2]),
              s('مازاد', rs.map((r) => r.excess_value || 0), t.series[3]),
              s('راکد', rs.map((r) => r.dead_value || 0), t.series[7]),
              s('ضایعات', rs.map((r) => r.waste_value || 0), t.dark ? '#8a8984' : '#8f8e88'),
            ],
          }
        }} />
      </Card>
    </>
  )
}

// ---------------------------------------------------------------- انبار کارخانه (راهکاران)
// فقط نمایش؛ در محاسبه سفارش شعب اثری ندارد. گزارش کلی است و به شعبه انتخاب‌شده بستگی ندارد
function FactoryTab() {
  const { unit, rkVersion } = useApp()
  // با هر تغییر در راهکاران (rkVersion) جدول دوباره گرفته می‌شود؛ داده قبلی تا رسیدن پاسخ می‌ماند
  const { data, error, setData } = useFetch(`/api/inventory/factory?v=${rkVersion}`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [brand, setBrand] = useState('')
  const [group, setGroup] = useState('')
  const [store, setStore] = useState('')
  const brands = useMemo(() => (data ? [...new Set(data.rows.map((r) => r.brand))].sort() : []), [data])
  const groups = useMemo(() => (data ? [...new Set(data.rows.map((r) => r.category))].sort() : []), [data])
  const rows = useMemo(() => (!data ? [] : data.rows.filter((r) => (!brand || r.brand === brand) && (!group || r.category === group)
    && (!store || r[`s_${store}`] > 0)).map((r) => ({ ...r, key: r.code }))), [data, brand, group, store])
  // یک ستون برای هر نوع انبار (جمع انبارهای همان نوع)؛ نام انبارها در راهنمای ستون
  const kindCols = useMemo(() => (!data ? [] : Object.entries(data.kinds).map(([k, label]) => ({
    key: `t_${k}`, label, type: 'int',
    hint: data.store_cols.filter((c) => c.kind === k).map((c) => c.store_name).join('، '),
  }))), [data])
  const byBrand = useMemo(() => {
    if (!data) return []
    const m = {}
    for (const r of data.rows) {
      const b = (m[r.brand] ||= { brand: r.brand, f: 0, h: 0 })
      b.f += r.k_product || 0
      b.h += r.hybrid_stock || 0
    }
    return Object.values(m).filter((b) => b.f + b.h > 0).sort((a, b) => b.f - a.f).slice(0, 15)
  }, [data])
  const refresh = async () => {
    setBusy(true); setErr(null)
    try { setData(await fetchJson('/api/inventory/factory?refresh=true')) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (error) return <ErrorBox error={error} />
  if (!data) return <div className="state">در حال خواندن انبارهای کارخانه از راهکاران…</div>
  const k = data.kpis
  return (
    <>
      {err && <ErrorBox error={err} />}
      <div className="plan-bar">
        <span className="muted">موجودی کارخانه از راهکاران (سال مالی جاری) · {data.live ? 'لایو · ' : ''}خوانده‌شده {faDigits(data.fetched.slice(11))} · فقط نمایش؛ در محاسبه سفارش شعب نیست</span>
        <div className="spacer" />
        <button className="btn ghost" onClick={refresh} disabled={busy}>{busy ? 'در حال خواندن…' : 'خواندن دوباره'}</button>
      </div>
      <div className="kpis">
        <Kpi label="موجودی انبار محصول" value={k.product_value} sub={`${fmtInt(k.product_units)} عدد · ${fmtInt(k.product_skus)} کالا`}
          hint={`انبارهای کد ${data.sellable_stores.join('، ')}؛ ارزش به آخرین قیمت خرید شعب در کارآمد`} />
        <Kpi label="سفارش باز کارخانه" value={k.open_all} type="int" sub={`${fmtInt(k.open_hybrid)} عدد آن برای هیبریدها · ${fmtInt(data.open_days)} روز اخیر`}
          hint="سفارش‌های ثبت‌شده/تأییدشده همه مشتریان که هنوز از انبار خارج نشده" />
        <Kpi label="آزاد کارخانه" value={k.free_value} sub={`${fmtInt(k.free_units)} عدد · موجودی منهای سفارش باز`} />
        <Kpi label="کالای کم برای سفارش‌ها" value={k.short_skus} type="int" sub="سفارش باز بیشتر از موجودی انبار محصول" />
        <Kpi label="موجودی کل شعب هیبرید (کارآمد)" value={k.hybrid_value} sub={`${fmtInt(k.hybrid_units)} عدد · برای مقایسه`}
          hint="انبار اصلی شعب (بدون ضایعات)؛ ارزش همان «ارزش انبار» گزارش کارآمد: هر شعبه با میانگین قیمت خرید خودش" />
        <Kpi label="زنجیره‌ای، نمونه و راکد" value={k.other_units} type="int" sub="عدد کالای ساخته‌شده در انبارهای دیگر کارخانه" />
      </div>
      {k.no_price > 0 && <div className="alerts"><div className="alert info"><span className="alert-icon">i</span>
        <span>{fmtInt(k.no_price)} کالای موجود در کارخانه در یک سال اخیر خرید کارآمد نداشته و قیمتش معلوم نیست؛ ارزش آن‌ها صفر حساب شده (تعدادشان درست است).</span></div></div>}
      <div className="grid g2">
        <Card title="موجودی هر برند (تعداد): کارخانه در برابر جمع شعب هیبرید" subtitle="۱۵ برند اول بر اساس تعداد در انبار محصول کارخانه؛ روی میله کلیک کنید تا جدول کالاها روی آن برند فیلتر شود" className="span2">
          <Chart height={Math.max(260, byBrand.length * 30)} option={(t) => {
            const rs = [...byBrand].reverse()
            return {
              grid: { left: 110, right: 30, top: 30, bottom: 30 },
              tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${fmtInt(v)} عدد` },
              legend: { top: 0, textStyle: { color: t.text } },
              xAxis: { type: 'value', axisLabel: { color: t.text, formatter: (v) => fmtInt(v) }, splitLine: { lineStyle: { color: t.grid } } },
              yAxis: { type: 'category', data: rs.map((r) => r.brand), axisLabel: { color: t.text } },
              series: [
                { name: 'انبار محصول کارخانه', type: 'bar', data: rs.map((r) => r.f), itemStyle: { color: t.series[0] } },
                { name: 'جمع شعب هیبرید', type: 'bar', data: rs.map((r) => r.h), itemStyle: { color: t.series[2] } },
              ],
            }
          }} onClick={(p) => p?.name && setBrand(p.name)} />
        </Card>
        <Card title="انبارهای کارخانه" className="span2"
          subtitle="همه انبارهای راهکاران. «کالای قابل فروش» یعنی کالایی که در فروش راهکاران تعریف شده. واحد انبارهای مواد اولیه و توزین گرم و کیلو هم هست، پس تعدادشان با بقیه قابل مقایسه نیست.">
          <DataTable rows={data.stores.map((r) => ({ ...r, key: r.store }))} unit={unit} pageSize={25} dense search={false}
            exportName="factory-stores" defaultSort={{ key: 'value', dir: 'desc' }}
            columns={[
              { key: 'store', label: 'کد' },
              { key: 'store_name', label: 'انبار' },
              { key: 'kind_label', label: 'نوع' },
              { key: 'items', label: 'اقلام موجود', type: 'int' },
              { key: 'product_items', label: 'کالای قابل فروش', type: 'int' },
              { key: 'product_units', label: 'تعداد کالای قابل فروش', type: 'int' },
              { key: 'value', label: 'ارزش', type: 'money' },
              { key: 'negative', label: 'مانده منفی', type: 'int', hint: 'اقلامی که مانده منفی دارند (صفر حساب شده‌اند)' },
            ]} />
        </Card>
        <Card title="موجودی هر کالا در انبارهای کارخانه" className="span2"
          subtitle={`گزارش کلی همه شعب هیبرید و همه انبارهای راهکاران؛ گروه کالا از نگاشت category_map؛ فروش ماهانه میانگین ${data.last3.map(monthName).join('، ')}`}>
          <div className="plan-bar">
            <label className="inline-field">
              <span>انبار</span>
              <select value={store} onChange={(e) => setStore(e.target.value)}>
                <option value="">همه انبارها</option>
                {data.store_cols.map((c) => <option key={c.store} value={c.store}>{c.store_name}</option>)}
              </select>
            </label>
            <label className="inline-field">
              <span>گروه</span>
              <select value={group} onChange={(e) => setGroup(e.target.value)}>
                <option value="">همه</option>
                {groups.map((g) => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <label className="inline-field">
              <span>برند</span>
              <select value={brand} onChange={(e) => setBrand(e.target.value)}>
                <option value="">همه</option>
                {brands.map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
            <div className="spacer" />
            <span className="muted">{fmtInt(rows.length)} کالا</span>
          </div>
          <DataTable rows={rows} unit={unit} pageSize={25} dense exportName="factory-items" defaultSort={{ key: 'value', dir: 'desc' }}
            columns={[
              { key: 'code', label: 'کد' },
              { key: 'product', label: 'کالا' },
              { key: 'brand', label: 'برند' },
              { key: 'category', label: 'گروه کالا' },
              { key: 'unit', label: 'واحد' },
              { key: 'hybrid_stock', label: 'موجودی انبار هیبرید', type: 'int', hint: 'جمع موجودی همه شعب هیبرید در کارآمد (بدون ضایعات)' },
              { key: 'total', label: 'موجودی همه انبارهای راهکاران', type: 'int', hint: 'جمع مانده کالا در همه انبارهای کارخانه در راهکاران' },
              { key: 'grand_total', label: 'موجودی کل', type: 'int', hint: 'انبارهای راهکاران + شعب هیبرید؛ کالای در راه (فاکتورشده و هنوز رسید نشده) در هیچ‌کدام نیست' },
              ...kindCols,
              { key: 'open_all', label: 'سفارش باز', type: 'int', hint: 'سفارش همه مشتریان که هنوز از انبار خارج نشده' },
              { key: 'open_hybrid', label: 'سفارش باز هیبرید', type: 'int', hint: 'بخشی از سفارش باز که مشتری‌اش هیبرید است' },
              { key: 'hybrid_monthly', label: 'فروش ماهانه هیبریدها', type: 'int', hint: 'میانگین فروش خالص ماهانه همه شعب هیبرید در ۳ ماه بسته اخیر' },
              { key: 'value', label: 'ارزش انبار محصول', type: 'money' },
            ]} />
        </Card>
      </div>
    </>
  )
}

function OrderBar({ data, onRefresh, busy }) {
  const o = data.orders
  const late = o.days_to_deadline === 0
  const steps = [
    { label: 'امروز', d: data.today },
    { label: 'آخرین مهلت سفارش بعدی', d: o.deadline, now: true,
      sub: o.deadline ? `${late ? 'همین امروز' : `${fmtInt(o.days_to_deadline)} روز دیگر`} · اولین کالا: ${o.deadline_items[0] || ''}` : 'فعلاً کالای A یا B در خطر نیست' },
    { label: 'اگر امروز سفارش دهید، بار می‌رسد', d: o.arr0, sub: `زمان رسیدن بار: ${fmtInt(o.lead)} روز (ثابت)` },
    { label: 'هر سفارش باید دوام بیاورد تا', d: o.arr1,
      sub: `حداکثر ${fmtInt(o.per_month)} سفارش در ماه: ${fmtInt(o.review)} روز تا سفارش بعد + ${fmtInt(o.lead)} روز رسیدن` },
  ]
  return (
    <div className="inv-bar">
      <ol className="inv-steps">
        {steps.map((s, i) => (
          <li key={i} className={s.now ? `now${late ? ' late' : ''}` : ''}>
            <span className="muted small">{s.label}</span>
            <strong>{s.d ? dayName(s.d) : '—'}</strong>
            {s.sub && <span className="muted small">{s.sub}</span>}
          </li>
        ))}
      </ol>
      <div className="inv-bar-side">
        <span className="muted small">موجودی خوانده‌شده: {faDigits(data.fetched.slice(11))}</span>
        <button className="btn ghost" disabled={busy} onClick={onRefresh}>{busy ? 'در حال خواندن…' : 'خواندن دوباره موجودی'}</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- خلاصه مدیریتی
// برچسب کوتاه و رنگ هر وضعیت برای نمودارها (هم‌معنی با رنگ pillها)
// «سابقه ناکافی» در نمودارها با «نامنظم» یکی می‌شود (هر دو بدون هشدار خودکار)
const ST_SHORT = { red: 'سفارش بعدی', orange: 'سفارش بعدی', ok: 'کافی', excess: 'مازاد', dead: 'راکد', c: 'نامنظم / بدون سابقه', nodata: 'نامنظم / بدون سابقه' }
const ST_ORDER = ['orange', 'ok', 'excess', 'dead', 'c']
// «فوری» جزو «سفارش بعدی» است و «سابقه ناکافی» جزو «نامنظم»
const stOf = (r) => (r.status === 'nodata' ? 'c' : r.status === 'red' ? 'orange' : r.status)
const stColor = (s, t) => ({ red: t.series[7], orange: t.series[3], ok: t.series[2], excess: t.series[0],
  dead: t.dark ? '#8a8984' : '#8f8e88', c: t.dark ? '#4a4a46' : '#dddcd6' })[s === 'nodata' ? 'c' : s === 'red' ? 'orange' : s]
const NO_BRAND = 'بدون برند'
const brandOf = (r) => r.brand || NO_BRAND

/** جمع val بر اساس کلید؛ خروجی مرتب نزولی [{label, v}] */
function groupSum(rows, keyOf, val) {
  const m = new Map()
  rows.forEach((r) => { const k = keyOf(r) || '—'; m.set(k, (m.get(k) || 0) + (val(r) || 0)) })
  return [...m].map(([label, v]) => ({ key: label, label, v })).filter((x) => x.v > 0).sort((a, b) => b.v - a.v)
}

// همه نمودارهای موجودی و سفارش تعدادی‌اند (عدد یا کارتن)؛ کلیک روی هر نمودار، کالاهای همان بخش را همان‌جا باز می‌کند
// و کلیک روی هر کالا جزئیات و دلیل پیشنهاد آن را نشان می‌دهد
function SummaryTab({ data, go }) {
  const need = useMemo(() => data.rows.filter((r) => r.status === 'red' || r.status === 'orange'), [data])
  const k = data.kpis
  return (
    <>
      <div className="kpis">
        <Kpi label="ارزش موجودی انبار اصلی" value={k.stock_value} sub="به میانگین قیمت خرید شعبه"
          hint="همان «ارزش انبار» گزارش کارآمد" />
        <Kpi label="موجودی انبار اصلی (تعداد)" value={k.stock_units} type="int" sub={`${fmtInt(k.stock_skus)} کالای موجود`} />
        <Kpi label="سفارش بعدی" value={k.order_value} sub={`${fmtInt(k.order_lines)} قلم · ${fmtInt(k.order_units)} عدد · ${fmtInt(k.red)} فوری`} onClick={() => go('order')} />
        <Kpi label="راکد" value={k.dead_value} sub={`${fmtInt(k.dead_skus)} کالا`} onClick={() => go('idle', 'dead')} />
        <Kpi label="مازاد" value={k.excess_value} sub={`${fmtInt(k.excess_skus)} کالا`} onClick={() => go('idle', 'excess')} />
      </div>
      <div className="grid g2">
        <StockTreemap data={data} />
        <StockHealth data={data} />
      </div>
      <OrderSummary data={data} rows={need} title="سفارش بعدی" link={() => go('order')}
        empty="فعلاً کالایی برای سفارش نیست." />
    </>
  )
}

/** باز شدن نرم کارت جزئیات زیر نمودار */
function useReveal(dep) {
  const ref = useRef(null)
  useEffect(() => { dep && ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [dep])
  return ref
}

/** موجودی شعبه: برند ← گروه کالا ← کالا؛ اندازه = تعداد، رنگ = برند یا وضعیت؛ کلیک روی کالا جزئیات آن را باز می‌کند */
function StockTreemap({ data }) {
  const [color, setColor] = useState('brand')
  const [sel, setSel] = useState(null)
  const selRef = useReveal(sel)
  const theme = useTheme()
  const rows = useMemo(() => data.rows.filter((r) => r.stock > 0), [data])
  const val = (r) => r.stock
  const total = rows.reduce((a, r) => a + val(r), 0)
  const tree = (t) => groupSum(rows, brandOf, val).map((b) => {
    const br = rows.filter((r) => brandOf(r) === b.label)
    return {
      name: b.label, value: b.v, itemStyle: { color: brandColor(b.label, t) },
      children: groupSum(br, (r) => r.category, val).map((c) => ({
        name: c.label, value: c.v,
        children: br.filter((r) => r.category === c.label && val(r) > 0).sort((x, y) => val(y) - val(x)).map((r) => ({
          name: r.product, value: val(r), row: r,
          ...(color === 'status' ? { itemStyle: { color: stColor(r.status, t) } } : {}),
        })),
      })),
    }
  })
  return (
    <>
      <Card title="موجودی انبار: برند ← گروه کالا ← کالا" className="span2"
        subtitle={`${fmtInt(rows.length)} کالای موجود · جمع ${fmtInt(total)} عدد · اندازه هر خانه = تعداد؛ روی هر گروه کلیک کنید تا کالاهایش باز شود و روی هر کالا تا جزئیاتش زیر نمودار بیاید (برگشت از نوار پایین)`}
        actions={<Tabs value={color} onChange={setColor} tabs={[{ value: 'brand', label: 'رنگ برند' }, { value: 'status', label: 'رنگ وضعیت' }]} />}>
        {color === 'status' && (
          <div className="legend-row">
            {ST_ORDER.map((s) => (
              <span key={s}><i className="legend-dot" style={{ background: stColor(s, theme) }} />{ST_SHORT[s]}</span>
            ))}
          </div>
        )}
        <Chart height={520} onClick={(p) => p?.data?.row && setSel(p.data.row)} option={(t) => ({
          tooltip: { ...baseOption(t).tooltip, formatter: (p) => {
            const r = p.data?.row
            const path = p.treePathInfo.slice(1).map((x) => x.name).join(' / ')
            const share = total ? ` (${fmtPct(p.value / total, 1)} کل)` : ''
            if (!r) return `${path}<br/><b>${fmtInt(p.value)} عدد</b>${share}`
            return `${path}<br/>موجودی: <b>${fmtInt(r.stock)}</b> عدد${r.unity > 1 ? ` (${fmtNum1(r.stock / r.unity)} کارتن)` : ''}${share}`
              + `<br/>وضعیت: ${ST_SHORT[r.status] || r.status} · گروه ${r.abc}`
              + (isNum(r.cover_days) ? `<br/>روز باقی‌مانده: ${fmtInt(r.cover_days)}` : '')
              + (r.order > 0 ? `<br/>سفارش پیشنهادی: <b>${fmtInt(r.order)}</b> عدد` : '')
              + DETAIL
          } },
          series: [{
            // نمای اول: برند ← گروه؛ کلیک روی گروه، کالاهای آن را نشان می‌دهد
            type: 'treemap', roam: false, nodeClick: 'zoomToNode', leafDepth: color === 'status' ? null : 2, left: 0, right: 0, top: 0, bottom: 28,
            breadcrumb: { show: true, bottom: 0, left: 'center', itemStyle: { color: t.surface, borderColor: t.axis, textStyle: { color: t.text } } },
            label: { show: true, formatter: '{b}', color: '#fff', fontFamily: 'Vazirmatn', overflow: 'truncate' },
            upperLabel: { show: true, height: 22, color: '#fff', fontFamily: 'Vazirmatn' },
            itemStyle: { borderColor: t.surface, borderWidth: 2, gapWidth: 2 },
            levels: [
              { itemStyle: { borderWidth: 0, gapWidth: 3 } },
              { itemStyle: { gapWidth: 2, borderColorSaturation: 0.6 } },
              { itemStyle: { gapWidth: 1, borderWidth: 1, borderColorSaturation: 0.5 } },
              { itemStyle: { borderWidth: 1 }, upperLabel: { show: false } },
            ],
            data: tree(t),
          }],
        })} />
      </Card>
      {sel && <div ref={selRef} className="span2"><ItemDetail data={data} row={sel} onClose={() => setSel(null)} /></div>}
    </>
  )
}

/** سلامت موجودی هر برند: تعداد موجودی به تفکیک وضعیت؛ کلیک روی میله، کالاهای همان برند و وضعیت را باز می‌کند */
function StockHealth({ data }) {
  const [pick, setPick] = useState(null)
  const pickRef = useReveal(pick)
  const rows = data.rows.filter((r) => r.stock > 0)
  const brands = groupSum(rows, brandOf, (r) => r.stock).reverse()
  const sts = ST_ORDER.filter((s) => rows.some((r) => stOf(r) === s))
  const cell = (b, s) => rows.reduce((a, r) => a + (brandOf(r) === b && stOf(r) === s ? r.stock : 0), 0)
  const tot = rows.reduce((a, r) => a + r.stock, 0)
  const by = Object.fromEntries(sts.map((s) => [s, rows.reduce((a, r) => a + (stOf(r) === s ? r.stock : 0), 0)]))
  const idle = (by.dead || 0) + (by.excess || 0)
  return (
    <>
      <Card title="سلامت موجودی هر برند" className="span2"
        subtitle={<>تعداد موجودی به تفکیک وضعیت کالا · {fmtPct(idle / Math.max(tot, 1), 0)} موجودی ({fmtInt(idle)} عدد) راکد یا مازاد است · روی هر بخش میله کلیک کنید تا کالاهایش همین‌جا باز شود</>}>
        <Chart height={Math.max(240, brands.length * 30 + 60)}
          onClick={(p) => p?.name && setPick({ brand: p.name, status: sts[p.seriesIndex] })}
          option={(t) => ({
            grid: { left: 12, right: 12, top: 32, bottom: 8, containLabel: true },
            legend: { top: 0, right: 0, textStyle: { color: t.text } },
            tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
              formatter: (ps) => {
                const sum = ps.reduce((a, p) => a + (p.value || 0), 0)
                return `${ps[0].name} — ${fmtInt(sum)} عدد<br/>` + ps.filter((p) => p.value > 0)
                  .map((p) => `${p.marker} ${p.seriesName}: <b>${fmtInt(p.value)}</b> (${fmtPct(p.value / sum, 0)})`).join('<br/>') + CLICK
              } },
            xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtInt(v) }, splitLine: { lineStyle: { color: t.grid } } },
            yAxis: { type: 'category', position: 'right', data: brands.map((b) => b.label), axisLabel: { color: t.text },
              axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
            series: sts.map((s) => ({
              name: ST_SHORT[s], type: 'bar', stack: 'v', barMaxWidth: 18, cursor: 'pointer',
              itemStyle: { color: stColor(s, t), borderColor: t.surface, borderWidth: 1 },
              data: brands.map((b) => cell(b.label, s)),
            })),
          })} />
      </Card>
      {pick && <div ref={pickRef} className="span2">
        <ItemList data={data} title={`موجودی برند ${pick.brand} — ${ST_SHORT[pick.status]}`}
          rows={rows.filter((r) => brandOf(r) === pick.brand && stOf(r) === pick.status)}
          val={(r) => r.stock} unitLabel="عدد موجودی" exportName="stock-brand-status" onClose={() => setPick(null)} />
      </div>}
    </>
  )
}

/** نمای کلی سفارش: سهم برند، فوریت، تأمین‌کننده و گروه کالا (فقط کالاهای دارای مقدار سفارش)؛ تعداد یا کارتن */
function OrderSummary({ data, rows: all, title, empty, link }) {
  const [metric, setMetric] = useState('units')
  const rows = useMemo(() => all.filter((r) => r.order > 0), [all])
  // انتخاب با کلیک روی نمودار: {kind, label, status?} ← فهرست کالاهای همان بخش زیر نمودارها
  const [pick, setPick] = useState(null)
  const pickRef = useReveal(pick)
  const open = (kind, label, status) => label && setPick({ kind, label, status })
  if (!rows.length) return <div className="alert"><span>{empty}</span></div>
  const val = (r) => (metric === 'cartons' ? (r.unity > 0 ? r.order / r.unity : 0) : r.order)
  const fmtV = (v) => (metric === 'cartons' ? `${fmtNum1(v)} کارتن` : `${fmtInt(v)} عدد`)
  const total = rows.reduce((a, r) => a + val(r), 0)
  const brands = groupSum(rows, brandOf, val)
  const cats = groupSum(rows, (r) => r.category, val)
  const aV = rows.filter((r) => r.abc === 'A').reduce((a, r) => a + val(r), 0)
  const top = brands[0]
  const top3 = brands.slice(0, 3).reduce((a, b) => a + b.v, 0)
  const short = (n) => n.slice(0, 12).map((x) => ({ ...x, v: metric === 'cartons' ? Math.round(x.v * 10) / 10 : x.v }))
  const picked = pick ? rows.filter((r) => (PICK_KEY[pick.kind](r) || '—') === pick.label && (!pick.status || stOf(r) === pick.status)) : []
  return (
    <>
      <div className="inv-summary-head">
        <h3>{title}</h3>
        <span className="muted">
          {fmtInt(rows.length)} قلم · {fmtInt(rows.reduce((a, r) => a + r.order, 0))} عدد · {fmtNum1(rows.reduce((a, r) => a + (r.unity > 0 ? r.order / r.unity : 0), 0))} کارتن
          {' — '}<b>{top.label}</b> {fmtPct(top.v / total, 0)} سفارش؛ سه برند اول {fmtPct(top3 / total, 0)}
          {' · '}کالاهای A {fmtPct(aV / total, 0)}
        </span>
        <div className="spacer" />
        {link && <button className="btn ghost" onClick={link}>فهرست کامل ◀</button>}
        <span className="muted small">روی هر برند یا گروه کلیک کنید تا کالاهایش همین‌جا باز شود</span>
        <Tabs value={metric} onChange={setMetric} tabs={[{ value: 'units', label: 'تعداد' }, { value: 'cartons', label: 'کارتن' }]} />
      </div>
      <div className="grid g2">
        <Card title="سهم هر برند از سفارش" subtitle={`جمع ${fmtV(total)}`}>
          <Chart height={320} onClick={(p) => open('brand', p.name)} option={(t) => ({
            tooltip: { ...baseOption(t).tooltip, formatter: (p) => `${p.name}<br/><b>${fmtV(p.value)}</b> (${fmtPct(p.percent / 100, 1)})${CLICK}` },
            legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle', textStyle: { color: t.text } },
            series: [{
              type: 'pie', radius: ['45%', '72%'], center: ['40%', '50%'], avoidLabelOverlap: true, cursor: 'pointer',
              itemStyle: { borderColor: t.surface, borderWidth: 2 },
              label: { color: t.text, formatter: (p) => (p.percent >= 4 ? `${p.name}\n${fmtPct(p.percent / 100, 0)}` : '') },
              labelLine: { lineStyle: { color: t.axis } },
              data: brands.map((b) => ({ name: b.label, value: b.v, itemStyle: { color: brandColor(b.label, t) } })),
            }],
          })} />
        </Card>
        <Card title="سفارش به تفکیک گروه کالا" subtitle={cats.length > 12 ? `۱۲ گروه اول از ${fmtInt(cats.length)}` : `${fmtInt(cats.length)} گروه`}>
          <HBar rows={short(cats)} value="v" valueType="int" colorIndex={6} onClick={(r) => open('category', r.label)} />
        </Card>
        {pick && <div ref={pickRef} className="span2">
          <ItemList data={data} rows={picked} val={val} unitLabel={metric === 'cartons' ? 'کارتن سفارش' : 'عدد سفارش'}
            title={`کالاهای سفارش — ${PICK_NAME[pick.kind]}: ${pick.label}${pick.status ? ` (${ST_SHORT[pick.status]})` : ''}`}
            hide={pick.kind} exportName={`order-${pick.kind}`} onClose={() => setPick(null)} />
        </div>}
      </div>
    </>
  )
}

const CLICK = '<br/><span style="opacity:.7">برای دیدن کالاها کلیک کنید</span>'
const DETAIL = '<br/><span style="opacity:.7">برای جزئیات کالا کلیک کنید</span>'
const PICK_KEY = { brand: brandOf, supplier: (r) => r.supplier, category: (r) => r.category }
const PICK_NAME = { brand: 'برند', supplier: 'تأمین‌کننده', category: 'گروه کالا' }

/** ریز کالاهای یک بخش نمودار (تعدادی)؛ کلیک روی هر کالا، جزئیات و دلیل پیشنهادش را زیر فهرست باز می‌کند */
function ItemList({ data, rows: all, val, unitLabel, title, hide, exportName, onClose }) {
  const { unit } = useApp()
  const theme = useTheme()
  const [sel, setSel] = useState(null)
  const selRef = useReveal(sel)
  useEffect(() => { setSel(null) }, [title])
  const rows = all.map((r) => ({ ...r, key: r.code, label: r.product, v: val(r) })).sort((a, b) => b.v - a.v)
  const total = rows.reduce((a, r) => a + r.v, 0)
  const nRed = rows.filter((r) => r.status === 'red').length
  const sts = ST_ORDER.filter((s) => rows.some((r) => stOf(r) === s))
  const MAX = 40
  const labels = data.status_label
  return (
    <>
      <Card title={title}
        subtitle={`${fmtInt(rows.length)} قلم · جمع ${fmtInt(total)} ${unitLabel} · ${fmtInt(nRed)} قلم فوری · روی هر کالا (نمودار یا جدول) کلیک کنید تا جزئیاتش باز شود${rows.length > MAX ? ` · نمودار ${fmtInt(MAX)} قلم اول؛ همه در جدول` : ''}`}
        actions={<button className="btn ghost" onClick={onClose}>بستن</button>}>
        {!rows.length ? <div className="state">کالایی نیست.</div> : (
          <>
            <div className="legend-row">
              {sts.map((s) => <span key={s}><i className="legend-dot" style={{ background: stColor(s, theme) }} />{ST_SHORT[s]}</span>)}
            </div>
            <HBar rows={rows.slice(0, MAX)} value="v" valueType="int" labelWidth={260} colorOf={(r, t) => stColor(r.status, t)}
              onClick={(r) => setSel(rows.find((x) => x.label === r.label) || null)} />
            <DataTable rows={rows} unit={unit} pageSize={15} dense search={false} exportName={exportName}
              defaultSort={{ key: 'v', dir: 'desc' }} onRowClick={setSel}
              columns={[
                { key: 'status', label: 'وضعیت', csv: (r) => labels[r.status] || r.status, render: (r) => <StatusPill s={r.status} labels={labels} low={r.c_low} /> },
                { key: 'code', label: 'کد کالا' },
                { key: 'product', label: 'کالا' },
                ...(hide !== 'brand' ? [{ key: 'brand', label: 'برند' }] : []),
                ...(hide !== 'category' ? [{ key: 'category', label: 'گروه کالا' }] : []),
                ...(hide !== 'supplier' ? [{ key: 'supplier', label: 'تأمین‌کننده' }] : []),
                { key: 'abc', label: 'ABC' },
                { key: 'stock', label: 'موجودی', type: 'int' },
                { key: 'open_req', label: 'درخواست باز', type: 'int' },
                { key: 'fc_now', label: 'فروش پیش‌بینی این ماه', type: 'int' },
                { key: 'cover_days', label: 'روز باقی‌مانده', type: 'int' },
                { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
                { key: 'order', label: 'سفارش (عدد)', type: 'int' },
                { key: 'cartons', label: 'کارتن', type: 'num1' },
              ]} />
          </>
        )}
      </Card>
      {sel && <div ref={selRef}><ItemDetail data={data} row={sel} onClose={() => setSel(null)} /></div>}
    </>
  )
}

// ---------------------------------------------------------------- پیشنهاد سفارش
// ستون‌های راهکاران (کارخانه): فقط وقتی داده راهکاران خوانده شده
function OrderTab({ data }) {
  const { unit } = useApp()
  const [sel, setSel] = useState(null)
  const labels = data.status_label
  // این نوبت: کالاهایی که پیشنهاد سفارش دارند (فوری یا برای دوام تا سفارش بعد)
  const rows = useMemo(() => data.rows.filter((r) => (r.status === 'red' || r.status === 'orange') && r.order > 0), [data])
  // نامنظم: سفارش خودکار ندارند؛ با درخواست مشتری سفارش داده می‌شوند
  const irregular = useMemo(() => data.rows.filter((r) => r.status === 'c' || r.status === 'nodata'), [data])
  const nLow = rows.filter((r) => r.c_low).length
  const units = rows.reduce((a, r) => a + (r.order || 0), 0)
  const value = rows.reduce((a, r) => a + (r.order_value || 0), 0)
  const cartons = rows.reduce((a, r) => a + (r.unity > 1 ? r.order / r.unity : 0), 0)
  const incoming = data.rahkaran?.ok ? [{ key: 'incoming', label: 'در راه + سفارش باز کارخانه', type: 'int', hint: 'از راهکاران؛ در محاسبه سفارش کم شده است' }] : []
  return (
    <>
      {/* فقط هشدارهای مهم؛ توضیحات روش در تب تنظیمات است */}
      <Alerts items={(data.warnings || []).filter((w) => w.level !== 'info')} />
      <div className="kpis">
        <Kpi label="اقلام سفارش بعدی" value={rows.length} type="int" sub={`${fmtInt(rows.filter((r) => r.status === 'red' && !r.c_low).length)} فوری · ${fmtInt(nLow)} کم‌فروش`} />
        <Kpi label="تعداد سفارش" value={units} type="int" sub={`${fmtNum1(cartons)} کارتن`} />
        <Kpi label="ارزش سفارش" value={value} sub="به آخرین قیمت خرید" />
        <Kpi label="کالاهای نامنظم" value={irregular.length} type="int" sub="سفارش فقط با درخواست مشتری" />
      </div>
      <Card title="سفارش بعدی"
        subtitle={`همه این کالاها در همین نوبت سفارش داده می‌شوند تا ${dayName(data.orders.arr1)} دوام بیاورند · تگ «فوری»: حتی با سفارش امروز تا رسیدن بار کم می‌آید · تگ «کم‌فروش»: کالای کم‌فروش ولی منظم که موجودی‌اش ته کشیده · روی هر ردیف کلیک کنید تا دلیل پیشنهاد بیاید`}>
        {rows.length ? (
          <DataTable rows={rows} unit={unit} pageSize={25} dense exportName={`order-${data.today.replace(/\//g, '-')}`}
            defaultSort={{ key: 'cover_days', dir: 'asc' }} onRowClick={setSel}
            columns={[
              { key: 'status', label: 'وضعیت', csv: (r) => labels[r.status] || r.status, render: (r) => <StatusPill s={r.status} labels={labels} low={r.c_low} /> },
              { key: 'code', label: 'کد کالا' },
              { key: 'product', label: 'کالا' },
              { key: 'brand', label: 'برند' },
              { key: 'category', label: 'گروه کالا' },
              { key: 'abc', label: 'ABC', hint: 'A: کالاهای ۸۰٪ اول فروش تعدادی؛ B: ۱۵٪ بعدی؛ C: ۵٪ آخر (نامنظم)' },
              { key: 'cv', label: 'نوسان', type: 'num1', hint: 'ضریب تغییرات فروش ماهانه (انحراف معیار ÷ میانگین)؛ بیشتر یعنی فروش نامنظم‌تر' },
              { key: 'safety_pct', label: 'safety', type: 'pct', hint: 'ذخیره اطمینان به نسبت تقاضا؛ A از نوسان فروش، B درصد ثابت' },
              { key: 'stock', label: 'موجودی', type: 'int' },
              { key: 'min', label: 'کمترین فروش ماهانه', type: 'int', hint: 'کمترین فروش خالص یک ماه در ماه‌های پایه' },
              { key: 'mean', label: 'فروش ماهانه', type: 'int', hint: 'میانگین فروش خالص ماهانه در ماه‌های پایه' },
              { key: 'max', label: 'بیشترین فروش ماهانه', type: 'int', hint: 'بیشترین فروش خالص یک ماه در ماه‌های پایه' },
              ytdCol(data),
              { key: 'cover_days', label: 'روز باقی‌مانده', type: 'int', hint: 'موجودی ÷ فروش روزانه (با ضریب فصل)' },
              ...incoming,
              { key: 'order', label: 'سفارش (عدد)', type: 'int' },
              { key: 'cartons', label: 'کارتن', type: 'num1' },
              { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
            ]} />
        ) : <div className="state">فعلاً کالایی برای سفارش بعدی نیست.</div>}
      </Card>
      {sel && <ItemDetail data={data} row={sel} onClose={() => setSel(null)} />}
      <Card title="کالاهای نامنظم"
        subtitle={`فروش پراکنده (کمتر از ${fmtInt(data.settings.c_regular_months)} ماه از ۶ ماه)، وابسته به یک مشتری یا سابقه کوتاه؛ فقط با درخواست مشتری سفارش داده می‌شوند. کالاهای کم‌فروشِ منظم این‌جا هستند تا وقتی موجودی‌شان به فروش تا رسیدن بار برسد؛ آن وقت با تگ «کم‌فروش» به سفارش بعدی می‌روند`}>
        <DataTable rows={irregular} unit={unit} pageSize={15} dense exportName="inventory-irregular"
          defaultSort={{ key: 'open_req', dir: 'desc' }} onRowClick={setSel}
          columns={[
            { key: 'code', label: 'کد کالا' },
            { key: 'product', label: 'کالا' },
            { key: 'brand', label: 'برند' },
            { key: 'category', label: 'گروه کالا' },
            { key: 'stock', label: 'موجودی', type: 'int' },
            { key: 'open_req', label: 'درخواست باز', type: 'int' },
            { key: 'months_sold', label: 'ماه با فروش', type: 'int' },
            { key: 'mean', label: 'فروش ماهانه', type: 'int' },
            { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
          ]} />
      </Card>
    </>
  )
}

// هر عدد، درصد یا تاریخ جدا (bdi) نمایش داده می‌شود تا در متن فارسی با + و = جابه‌جا نشود
const NUM_RE = /([0-9۰-۹][0-9۰-۹,./٫٬]*)/
function BidiText({ text }) {
  return text.replace(/%/g, '٪').split(NUM_RE).map((p, i) => (i % 2 ? <bdi key={i} dir="ltr">{faDigits(p)}</bdi> : faDigits(p)))
}

function ItemDetail({ data, row, onClose }) {
  const hist = data.hist[row.code] || []
  const abn = new Set(data.abnormal)
  const base = new Set(data.base_months)
  const facts = [
    ['میانگین / میانه ماهانه', `${fmtInt(row.mean)} / ${fmtInt(row.median)}`],
    ['کمترین / بیشترین ماه', `${fmtInt(row.min)} / ${fmtInt(row.max)}`],
    ['ماه‌های دارای فروش', `${fmtInt(row.months_sold)} از ${fmtInt(data.base_months.length)}`],
    ['درخواست باز / کسری', `${fmtInt(row.open_req)} / ${fmtInt(row.req_short)}`],
    ...(data.rahkaran?.ok ? [
      ['در راه / سفارش باز کارخانه', `${fmtInt(row.rk_transit)} / ${fmtInt(row.rk_open)}${row.open_since ? ` (از ${faDigits(row.open_since)})` : ''}`],
      ['موجودی / آزاد کارخانه', `${fmtInt(row.factory_stock)} / ${fmtInt(row.factory_free)}`],
    ] : []),
    ['نوسان (CV)', fmtNum1(row.cv)],
    ['روند ۳ ماه اخیر', isNum(row.trend) ? fmtPct(row.trend, 0) : '—'],
    ['برگشتی از فروش', fmtPct(row.ret_rate, 0)],
    ['تعداد مشتری', fmtInt(row.n_cust)],
    ['سهم بزرگ‌ترین مشتری', isNum(row.top_share) ? `${fmtPct(row.top_share, 0)} — ${row.top_cust || ''}` : '—'],
    [`همین ماه سال قبل`, fmtInt(row.ly_cur)],
    [`ماه بعد در سال قبل`, fmtInt(row.ly_next)],
    ['فروش این ماه تا امروز', fmtInt(row.cur_month)],
    ['آخرین فروش', row.last_sale ? faDigits(row.last_sale) : '—'],
    ['تعداد در کارتن', fmtInt(row.unity)],
    ['تاریخ تقریبی اتمام', row.runout ? faDigits(row.runout) : '—'],
  ]
  return (
    <Card title={row.product} subtitle={`${row.supplier} · ${row.brand} · ${row.category} · کد ${faDigits(row.code)}`} className="span2"
      actions={<button className="btn ghost" onClick={onClose}>بستن</button>}>
      <div className="inv-why">
        <StatusPill s={row.status} labels={data.status_label} />
        {Array.isArray(row.why) ? (
          <dl className="inv-why-steps">
            {row.why.map(([k, v], i) => <div key={i}><dt><BidiText text={k} /></dt><dd><BidiText text={v} /></dd></div>)}
          </dl>
        ) : <> <BidiText text={row.why || ''} /></>}
      </div>
      <div className="grid g2">
        <dl className="inv-facts">
          {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
        <Chart height={240} option={(t) => ({
          grid: { left: 40, right: 10, top: 20, bottom: 40 },
          tooltip: { trigger: 'axis', valueFormatter: (v) => fmtInt(v) },
          xAxis: { type: 'category', inverse: true, data: data.hist_months.map(monthName), axisLabel: { color: t.text, rotate: 45 } },
          yAxis: { type: 'value', axisLabel: { color: t.text, formatter: (v) => fmtInt(v) }, splitLine: { lineStyle: { color: t.grid } } },
          series: [{
            type: 'bar', name: 'فروش خالص',
            data: hist.map((v, i) => ({
              value: v,
              itemStyle: { color: abn.has(data.hist_months[i]) ? t.axis : base.has(data.hist_months[i]) ? t.series[0] : t.series[0] + '88' },
            })),
          }],
        })} />
      </div>
      <p className="muted small">میله‌های خاکستری: ماه‌های غیرعادی (در محاسبه نیستند). میله‌های پررنگ: ماه‌های پایه محاسبه.</p>
    </Card>
  )
}

// ستون فروش تعدادی از ابتدای سال جاری؛ کنار کمترین / میانگین / بیشترین فروش ماهانه
const ytdCol = (data) => ({
  key: 'ytd', label: `فروش از ابتدای ${data.ytd_from ? faDigits(data.ytd_from.slice(0, 4)) : 'سال'}`, type: 'int',
  hint: 'فروش خالص تعدادی (فروش منهای برگشتی) از ابتدای سال تا امروز، با همه ماه‌ها حتی ماه جاری',
})

// ---------------------------------------------------------------- همه کالاها
// فیلتر وضعیت در «همه کالاها»: «نامنظم» و «سابقه ناکافی» یکی است
const ALL_FILTERS = [['all', 'همه'], ['orange', 'سفارش بعدی'], ['ok', 'کافی'], ['excess', 'مازاد'], ['dead', 'راکد'], ['c', 'نامنظم']]
function AllTab({ data, status, setStatus }) {
  const { unit } = useApp()
  const [sel, setSel] = useState(null)
  const labels = data.status_label
  const counts = useMemo(() => data.rows.reduce((a, r) => ({ ...a, [stOf(r)]: (a[stOf(r)] || 0) + 1 }), {}), [data])
  const rows = useMemo(() => (status === 'all' ? data.rows : data.rows.filter((r) => stOf(r) === (status === 'red' ? 'orange' : status))), [data, status])
  return (
    <>
      <div className="plan-bar">
        <div className="seg" role="group" aria-label="وضعیت">
          {ALL_FILTERS.map(([v, l]) => (
            <button key={v} className={status === v ? 'active' : ''} onClick={() => setStatus(v)}>
              {l} <span className="tag">{fmtInt(v === 'all' ? data.rows.length : counts[v] || 0)}</span>
            </button>
          ))}
        </div>
      </div>
      <Card title="همه کالاها" subtitle={`ماه‌های پایه: ${faDigits(data.base_months.join('، '))} · اعداد تعدادی و خالص (فروش منهای برگشتی) · روی هر ردیف کلیک کنید تا جزئیات کالا بیاید`}>
        <DataTable rows={rows} unit={unit} pageSize={25} dense exportName="inventory-items" defaultSort={{ key: 'value', dir: 'desc' }} onRowClick={setSel}
          columns={[
            { key: 'status', label: 'وضعیت', csv: (r) => labels[r.status] || r.status, render: (r) => <StatusPill s={r.status} labels={labels} low={r.c_low} /> },
            { key: 'code', label: 'کد کالا' },
            { key: 'product', label: 'کالا' },
            { key: 'brand', label: 'برند' },
            { key: 'category', label: 'گروه کالا' },
            { key: 'abc', label: 'ABC', hint: 'A: کالاهای ۸۰٪ اول فروش تعدادی؛ B: ۱۵٪ بعدی؛ C: ۵٪ آخر (نامنظم)' },
            { key: 'cv', label: 'نوسان', type: 'num1', hint: 'ضریب تغییرات فروش ماهانه (انحراف معیار ÷ میانگین)؛ بیشتر یعنی فروش نامنظم‌تر' },
            { key: 'safety_pct', label: 'safety', type: 'pct', hint: 'ذخیره اطمینان به نسبت تقاضا؛ A از نوسان فروش، B درصد ثابت' },
            { key: 'stock', label: 'موجودی', type: 'int' },
            { key: 'value', label: 'ارزش موجودی', type: 'money', hint: 'همان «ارزش انبار» گزارش کارآمد' },
            { key: 'min', label: 'کمترین فروش ماهانه', type: 'int', hint: 'کمترین فروش خالص یک ماه در ماه‌های پایه' },
            { key: 'mean', label: 'فروش ماهانه', type: 'int', hint: 'میانگین فروش خالص ماهانه در ماه‌های پایه' },
            { key: 'max', label: 'بیشترین فروش ماهانه', type: 'int', hint: 'بیشترین فروش خالص یک ماه در ماه‌های پایه' },
            ytdCol(data),
            { key: 'cover_months', label: 'پوشش (ماه)', type: 'num1' },
            { key: 'cover_days', label: 'روز باقی‌مانده', type: 'int' },
            { key: 'order', label: 'سفارش پیشنهادی', type: 'int' },
            { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
            { key: 'open_req', label: 'درخواست باز', type: 'int' },
            { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
            { key: 'trend', label: 'روند ۳ ماه', type: 'pct' },
          ]} />
      </Card>
      {sel && <ItemDetail data={data} row={sel} onClose={() => setSel(null)} />}
    </>
  )
}

// ---------------------------------------------------------------- تأمین‌کنندگان
function SupplierTab({ data }) {
  const { unit } = useApp()
  return (
    <Card title="خلاصه تأمین‌کنندگان" subtitle="نسبت خرید به فروش ۹۰ روز اخیر نزدیک ۱ یعنی خرید متناسب با فروش؛ بالاتر یعنی انباشت موجودی.">
      <DataTable rows={data.suppliers.map((r) => ({ ...r, need: (r.red || 0) + (r.orange || 0) }))} unit={unit} pageSize={20} dense exportName="inventory-suppliers" defaultSort={{ key: 'value', dir: 'desc' }}
        columns={[
          { key: 'supplier', label: 'تأمین‌کننده' },
          { key: 'skus', label: 'تعداد کالا', type: 'int' },
          { key: 'stock', label: 'موجودی', type: 'int' },
          { key: 'value', label: 'ارزش موجودی', type: 'money' },
          { key: 'monthly', label: 'فروش ماهانه (با فصل)', type: 'int' },
          { key: 'cover_months', label: 'پوشش (ماه)', type: 'num1' },
          { key: 'need', label: 'اقلام سفارش بعدی', type: 'int' },
          { key: 'order', label: 'سفارش پیشنهادی', type: 'int' },
          { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
          { key: 'bought_90', label: 'خرید ۹۰ روز', type: 'int' },
          { key: 'sold_90', label: 'فروش خالص ۹۰ روز', type: 'int' },
          { key: 'buy_sell', label: 'خرید ÷ فروش', type: 'num1', render: (r) => <span className={r.buy_sell > 1.5 ? 'neg-text' : ''}>{fmtNum1(r.buy_sell)}</span> },
        ]} />
    </Card>
  )
}

// ---------------------------------------------------------------- راکد و مازاد: پیشنهاد برگشت
function IdleTab({ data, kind, setKind }) {
  const { unit } = useApp()
  const [sel, setSel] = useState(null)
  const s = data.settings
  const all = useMemo(() => data.rows.filter((r) => r.status === 'dead' || r.status === 'excess'), [data])
  const rows = useMemo(() => (kind === 'all' ? all : all.filter((r) => r.status === kind)), [all, kind])
  const sum = (k, rs = rows) => rs.reduce((a, r) => a + (r[k] || 0), 0)
  const cnt = (st) => all.filter((r) => r.status === st).length
  return (
    <>
      <div className="kpis">
        <Kpi label="ارزش موجودی این فهرست" value={sum('value')} sub={`${fmtInt(rows.length)} کالا · ${fmtInt(sum('stock'))} عدد`} />
        <Kpi label="می‌ماند" value={sum('value') - sum('ret_value')} sub="برای فروش پیش‌بینی‌شده تا نوبت‌های بعد" />
      </div>
      <Card title="راکد و مازاد — پیشنهاد برگشت"
        subtitle={`راکد: ${fmtInt(s.dead_days)} روز نه فروش داشته نه خرید؛ ${fmtInt(s.return_keep_dead)} عدد برای قفسه می‌ماند. مازاد: بیش از ${faDigits(s.excess_months)} ماه پوشش؛ پیش‌بینی فروش ${faDigits(s.return_keep_months)} ماه آینده (A و B) یا ${faDigits(s.return_keep_months_c)} ماه (C) می‌ماند و برگشت به کارتن کامل رو به پایین گرد می‌شود. درخواست باز همیشه می‌ماند. قبل از برگشت، موجودی را شمارش کنید.`}
        actions={<Tabs tabs={[{ value: 'all', label: `همه (${fmtInt(all.length)})` }, { value: 'dead', label: `راکد (${fmtInt(cnt('dead'))})` }, { value: 'excess', label: `مازاد (${fmtInt(cnt('excess'))})` }]} value={kind} onChange={setKind} />}>
        <DataTable rows={rows} unit={unit} pageSize={25} dense exportName={`inventory-return-${kind}`} defaultSort={{ key: 'ret_qty', dir: 'desc' }} onRowClick={setSel}
          columns={[
            { key: 'status', label: 'وضعیت', csv: (r) => data.status_label[r.status], render: (r) => <StatusPill s={r.status} labels={data.status_label} /> },
            { key: 'code', label: 'کد کالا' },
            { key: 'product', label: 'کالا' },
            { key: 'category', label: 'گروه کالا' },
            { key: 'abc', label: 'ABC' },
            { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
            { key: 'idle_days', label: 'روز بدون فروش', type: 'int' },
            { key: 'last_buy', label: 'آخرین خرید', type: 'date', hint: 'در ۱۸۰ روز اخیر؛ خالی یعنی خرید اخیر ندارد' },
            { key: 'mean', label: 'فروش ماهانه', type: 'int' },
            { key: 'stock', label: 'موجودی', type: 'int' },
            { key: 'ret_keep', label: 'نگه‌داشت', type: 'int', hint: 'مازاد: پیش‌بینی فروش ماه‌های نگه‌داشت + درخواست باز؛ راکد: تعداد ثابت برای قفسه + درخواست باز' },
            { key: 'ret_qty', label: 'برگشت (عدد)', type: 'int' },
            { key: 'ret_cartons', label: 'برگشت (کارتن)', type: 'num1' },
            { key: 'bought_90', label: 'خرید ۹۰ روز', type: 'int', hint: 'اگر تازه خریده شده، علت سفارش زیاد بررسی شود' },
          ]} />
      </Card>
      {sel && <ItemDetail data={data} row={sel} onClose={() => setSel(null)} />}
    </>
  )
}

// ---------------------------------------------------------------- تنظیمات
function SettingsTab({ data, setData }) {
  const s = data.settings
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState(null)
  useEffect(() => {
    setF({
      lead_days: s.lead_days, orders_per_month: s.orders_per_month,
      break_detect: !!s.break_detect, inactive_days: s.inactive_days,
      min_order_cartons: s.min_order_cartons, min_gap_pct: Math.round(s.min_gap_pct * 100),
      a_safety: s.a_safety, z_a: s.z_a, b_pct: Math.round(s.b_pct * 100),
      br0: Math.round(s.breadth[0] * 100), br1: Math.round(s.breadth[1] * 100), br2: Math.round(s.breadth[2] * 100),
      base_months: s.base_months, dead_days: s.dead_days, excess_months: s.excess_months,
      min_months_sold: s.min_months_sold, ly_weight: Math.round(s.ly_weight * 100),
      c_regular_months: s.c_regular_months, c_order_months: s.c_order_months,
      return_keep_months: s.return_keep_months, return_keep_months_c: s.return_keep_months_c, return_keep_dead: s.return_keep_dead,
    })
  }, [s])
  if (!f) return null
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async () => {
    setMsg(null)
    try {
      setData(await sendJson('/api/inventory/settings', 'PUT', {
        branch: data.selected, store: data.store_filtered ? data.stores.filter((x) => x.selected).map((x) => x.id) : null, lead_days: Number(f.lead_days), orders_per_month: Number(f.orders_per_month),
        break_detect: f.break_detect, inactive_days: Number(f.inactive_days),
        min_order_cartons: Number(f.min_order_cartons), min_gap_pct: Number(f.min_gap_pct) / 100,
        a_safety: f.a_safety, z_a: Number(f.z_a), b_pct: Number(f.b_pct) / 100,
        breadth: [Number(f.br0) / 100, Number(f.br1) / 100, Number(f.br2) / 100],
        base_months: Number(f.base_months), dead_days: Number(f.dead_days), excess_months: Number(f.excess_months),
        min_months_sold: Number(f.min_months_sold), ly_weight: Number(f.ly_weight) / 100,
        c_regular_months: Number(f.c_regular_months), c_order_months: Number(f.c_order_months),
        return_keep_months: Number(f.return_keep_months), return_keep_months_c: Number(f.return_keep_months_c),
        return_keep_dead: Number(f.return_keep_dead),
      }))
      setMsg({ ok: true, text: 'ذخیره شد و محاسبات به‌روز شد.' })
    } catch (e) { setMsg({ ok: false, text: e.message }) }
  }
  const num = (k, label, props = {}) => (
    <label className="inline-field"><span>{label}</span>
      <input className="input num-in" type="number" value={f[k]} onChange={set(k)} {...props} /></label>
  )
  return (
    <div className="grid g2">
      <Card title="تنظیمات" subtitle="برای همه شعب یکسان است">
        <div className="inv-form">
          <div className="inv-row">
            {num('lead_days', 'زمان رسیدن بار (روز، ثابت)', { min: 0, max: 60 })}
            {num('orders_per_month', 'حداکثر سفارش در ماه', { min: 1, max: 8 })}
          </div>
          <div className="inv-row">
            {num('min_order_cartons', 'هشدار نارنجی از سفارش حداقل (کارتن)', { min: 0, max: 10, step: 0.25 })}
            {num('min_gap_pct', 'و کمبود حداقل (٪ سطح هدف)', { min: 0, max: 90 })}
          </div>
          <div className="inv-row">
            <label className="inline-field"><span>safety کالاهای A</span>
              <select value={f.a_safety} onChange={set('a_safety')}>
                <option value="data">بر اساس نوسان واقعی فروش (امن‌تر)</option>
                <option value="breadth">بر اساس تعداد مشتری (سفارش کمتر)</option>
              </select>
            </label>
            {f.a_safety === 'data' ? num('z_a', 'ضریب z (۱٫۶۵ ≈ ۹۵٪)', { step: 0.05, min: 0, max: 3 }) : (
              <>
                {num('br0', 'مشتری زیاد (٪)')}
                {num('br1', 'مشتری متوسط (٪)')}
                {num('br2', 'وابسته به یک مشتری (٪)')}
              </>
            )}
          </div>
          <div className="inv-row">
            {num('b_pct', 'safety کالاهای B (٪)', { min: 0, max: 200 })}
            {num('base_months', 'ماه‌های پایه', { min: 2, max: 12 })}
          </div>
          <div className="inv-row">
            {num('ly_weight', 'وزن فروش همان ماه سال قبل (٪)', { min: 0, max: 100 })}
            {num('min_months_sold', 'حداقل ماه با فروش برای A و B', { min: 1, max: 6 })}
          </div>
          <div className="inv-row">
            <label className="inline-check"><input type="checkbox" checked={f.break_detect} onChange={set('break_detect')} /> تشخیص خودکار تغییر ساختاری فروش شعبه</label>
            {num('inactive_days', 'غیرفعال بعد از (روز بدون فروش)', { min: 3, max: 120 })}
          </div>
          <div className="inv-row">
            {num('dead_days', 'راکد بعد از (روز بدون فروش)', { min: 15, max: 720 })}
            {num('excess_months', 'مازاد بالای (ماه پوشش)', { min: 1, max: 36, step: 0.5 })}
          </div>
          <div className="inv-row">
            {num('c_regular_months', 'کم‌فروش منظم: حداقل ماه با فروش از ۶ ماه', { min: 1, max: 6 })}
            {num('c_order_months', 'مقدار سفارش کم‌فروش (ماه فروش)', { min: 0.25, max: 6, step: 0.25 })}
          </div>
          <div className="inv-row">
            {num('return_keep_months', 'برگشتی: نگه‌داشت A و B (ماه فروش)', { min: 0, max: 12, step: 0.25 })}
            {num('return_keep_months_c', 'نگه‌داشت C (ماه فروش)', { min: 0, max: 12, step: 0.25 })}
            {num('return_keep_dead', 'نگه‌داشت راکد (عدد)', { min: 0, max: 1000 })}
          </div>
          <div className="inv-row">
            <button className="btn" onClick={save}>ذخیره و محاسبه دوباره</button>
            {msg && <span className={msg.ok ? 'pos-text' : 'neg-text'}>{msg.text}</span>}
          </div>
        </div>
      </Card>
      <Card title="روش محاسبه" subtitle="هر عدد با یک فرمول ثابت و قابل بازبینی محاسبه می‌شود">
        <ol className="inv-method">
          <li><strong>پایه ماهانه:</strong> میانگین فروش خالص (فروش منهای برگشتی) ماه‌های سالم اخیر، پس از حذف اثر فصل. ماه‌های غیرعادی و ماه اول شعبه کنار گذاشته می‌شوند.</li>
          <li><strong>ضریب فصلی:</strong> از تاریخچه چندساله همه شعب (همان ضریب صفحه برنامه‌ریزی)؛ مثلاً شهریور بالا، مهر پایین، دی و بهمن اوج.</li>
          <li><strong>پیش‌بینی هر ماه:</strong> پایه × ضریب فصل آن ماه. اگر همان ماه سال قبل در این شعبه عادی بوده و کالا آن زمان فروخته می‌شده، با فروش آن ماه (تعدیل‌شده با رشد شعبه) با وزن تنظیم‌شده ترکیب می‌شود.</li>
          <li><strong>زمان سفارش:</strong> تاریخ ثابت ندارد؛ فقط حداکثر {faDigits(s.orders_per_month)} سفارش در ماه. زمان رسیدن بار ثابت {faDigits(s.lead_days)} روز فرض می‌شود.</li>
          <li><strong>لازم تا رسیدن بار:</strong> تقاضای پیش‌بینی‌شده در {faDigits(s.lead_days)} روز آینده (اگر همین امروز سفارش داده شود). موجودی قابل فروش (منهای درخواست‌های باز) کمتر از آن ← <span className="pill st-red">قرمز</span></li>
          <li><strong>سطح هدف:</strong> هر سفارش باید تا سفارش بعدی ({faDigits(data.orders.review)} روز) و رسیدن بار آن دوام بیاورد: تقاضای {faDigits(data.orders.review + s.lead_days)} روز آینده + safety. موجودی کمتر از آن ← <span className="pill st-yellow">نارنجی</span> و باید در سفارش بعدی باشد؛ به شرطی که سفارش لازم حداقل {faDigits(s.min_order_cartons)} کارتن و کمبود حداقل {faDigits(Math.round(s.min_gap_pct * 100))}٪ سطح هدف باشد (کمبودهای کوچک‌تر در بررسی بعدی دوباره سنجیده می‌شوند).</li>
          <li><strong>مهلت سفارش:</strong> برای هر کالا، تاریخ اتمام منهای زمان رسیدن بار. «آخرین مهلت سفارش بعدی» زودترین مهلت بین کالاهای A و B است.</li>
          <li><strong>گروه A، B و C:</strong> کالاها از پرفروش به کم‌فروش (فروش خالص ماهانه، تعدادی) مرتب می‌شوند. کالاهایی که روی هم ۸۰٪ اول فروش را می‌سازند A، ۱۵٪ بعدی B و ۵٪ آخر C هستند. کالای B که در کمتر از {faDigits(s.min_months_sold)} ماه از ماه‌های پایه فروش داشته، نامنظم (C) حساب می‌شود؛ کالاهای A از این قاعده معاف‌اند.</li>
          <li><strong>safety:</strong> A از نوسان واقعی فروش یا تعداد مشتری؛ B درصد ثابت؛ C بدون هشدار خودکار (سفارش با درخواست).</li>
          <li><strong>راکد:</strong> موجودی دارد ولی {faDigits(s.dead_days)} روز نه فروش داشته و نه خرید؛ کالایی که تازه رسیده تا {faDigits(s.dead_days)} روز فرصت فروش دارد. برگشت: همه به‌جز {faDigits(s.return_keep_dead)} عدد برای قفسه و درخواست باز.</li>
          <li><strong>مازاد:</strong> کالای A یا B با پوشش بیش از {faDigits(s.excess_months)} ماه فروش. برگشت: موجودی منهای (پیش‌بینی فروش {faDigits(s.return_keep_months)} ماه آینده با ضریب فصل + درخواست باز)، رو به پایین به کارتن کامل.</li>
          <li><strong>کم‌فروش منظم:</strong> کالای C که در حداقل {faDigits(s.c_regular_months)} ماه از ۶ ماه پایه فروش داشته و بیش از نیم فروشش به یک مشتری نیست. وقتی موجودی آزاد (منهای درخواست باز) به فروش تا رسیدن بار برسد، با تگ «کم‌فروش» به سفارش بعدی می‌رود: فروش تا رسیدن بار + {faDigits(s.c_order_months)} ماه فروش − موجودی آزاد، حداقل ۱ عدد و بدون گرد کردن به کارتن. بقیه کالاهای C فقط با درخواست مشتری سفارش داده می‌شوند.</li>
          <li><strong>مقدار سفارش:</strong> سطح هدف منهای موجودی قابل فروش، به‌اضافه کسری درخواست‌های باز مشتری (اگر درخواست از موجودی بیشتر باشد)؛ از نیم کارتن به بالا گرد به کارتن کامل، کمتر از آن به عدد.</li>
        </ol>
        <p className="muted small">آزمون روی همه شعب هیبرید (اردیبهشت تا شهریور ۱۴۰۵، هر بار فقط با داده قبل از همان تاریخ): از هر ۱۰ کمبود واقعی کالاهای A حدود ۸ تا از قبل هشدار گرفتند و با سفارش پیشنهادی، تأمین فروش از ۸۴٪ به ۹۲٪ رسید؛ حجم سفارش تقریباً به اندازه نیاز بود.</p>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- حواله‌های فروش زنجیره‌ای و اینترنتی (راهکاران)
const VERDICT_CLASS = { approve: 'st-green', reduce: 'st-yellow', reject: 'st-red', review: 'st-none' }
const REMIT_CHANNELS = [{ value: '', label: 'همه' }, { value: 'chain', label: 'زنجیره‌ای' }, { value: 'online', label: 'اینترنتی' }]
const faDate = (d) => { try { return new Intl.DateTimeFormat('fa-IR-u-ca-persian', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(d)) } catch { return d } }
const days1 = (v) => (isNum(v) ? `${fmtInt(v)} روز` : '—')

function RemitTab() {
  const { unit, rkVersion } = useApp()
  const [all, setAll] = useState(false)
  const [channel, setChannel] = useState('')
  const [verdict, setVerdict] = useState('')
  const { data, error, setData } = useFetch(`/api/inventory/remittances?all_states=${all}&v=${rkVersion}`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const refresh = async () => {
    setBusy(true); setErr(null)
    try { setData(await fetchJson(`/api/inventory/remittances?all_states=${all}&refresh=true`)) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const lines = useMemo(() => (data ? data.lines.filter((r) => !channel || r.channel === channel) : []), [data, channel])
  const orders = useMemo(() => (data ? data.orders.filter((o) => (!channel || o.channel === channel) && (!verdict || o.counts[verdict] > 0)) : []), [data, channel, verdict])
  const byOrder = useMemo(() => {
    const m = {}
    for (const r of lines) (m[r.oid] ||= []).push({ ...r, key: `${r.oid}-${r.code}` })
    return m
  }, [lines])
  if (error) return <ErrorBox error={error} />
  if (!data) return <div className="state">در حال خواندن حواله‌های فروش از راهکاران…</div>
  const V = data.verdicts
  const cnt = (k) => lines.filter((r) => r.verdict === k).length
  const chLabel = Object.fromEntries(data.channels.map((c) => [c.key, c.label]))
  const cols = [
    { key: 'code', label: 'کد کالا', render: (r) => faDigits(r.code) },
    { key: 'product', label: 'کالا', sticky: true },
    { key: 'verdict', label: 'پیشنهاد', csv: (r) => V[r.verdict], render: (r) => (
      <span className={`pill ${VERDICT_CLASS[r.verdict]}`} title={faDigits(r.why)}>{V[r.verdict]}</span>) },
    { key: 'qty', label: 'مانده حواله', type: 'int', hint: 'مقدار حواله منهای خارج‌شده از انبار کارخانه' },
    { key: 'suggested', label: 'مقدار پیشنهادی', type: 'int', hint: 'از نیم کارتن به بالا به کارتن کامل گرد می‌شود' },
    { key: 'stock', label: 'موجودی شعبه', type: 'int', hint: 'موجودی همین کالا در شعبه زنجیره‌ای / اینترنتی کارآمد (بدون ضایعات)' },
    { key: 'monthly', label: 'فروش ماهانه (پیش‌بینی)', type: 'int', hint: 'پیش‌بینی فروش این ماه شعبه در کنترل موجودی (پایه ماه‌های سالم × فصل)' },
    { key: 'sold_90', label: 'فروش ۹۰ روز', type: 'int' },
    { key: 'ytd', label: `فروش از ابتدای ${faDigits((data.today || '').slice(0, 4))}`, type: 'int', hint: 'فروش خالص (فروش منهای برگشتی) شعبه از ابتدای سال جاری تا امروز' },
    { key: 'target', label: 'سطح هدف', type: 'int', hint: 'فروش تا رسیدن سفارش بعدی + زمان رسیدن بار + ذخیره اطمینان' },
    { key: 'cover_now', label: 'پوشش فعلی', csv: (r) => r.cover_now, render: (r) => days1(r.cover_now), hint: 'موجودی شعبه منهای درخواست باز ÷ فروش روزانه' },
    { key: 'cover_after', label: 'پوشش پس از تأیید', csv: (r) => r.cover_after, render: (r) => days1(r.cover_after), hint: 'با مقدار پیشنهادی' },
    { key: 'why', label: 'دلیل', render: (r) => <span className="small">{faDigits(r.why)}</span> },
  ]
  return (
    <>
      {err && <ErrorBox error={err} />}
      <div className="plan-bar">
        <Tabs tabs={REMIT_CHANNELS} value={channel} onChange={setChannel} />
        <label className="muted small"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> تأییدشده و در حال استفاده هم (بررسی حواله‌های قبلی)</label>
        <span className="muted small">{data.live ? 'لایو · ' : ''}خوانده‌شده {faDigits((data.fetched || '').slice(11))}</span>
        <div className="spacer" />
        <button className="btn ghost" onClick={refresh} disabled={busy}>{busy ? 'در حال خواندن…' : 'خواندن دوباره'}</button>
      </div>
      {data.channels.filter((c) => c.error).map((c) => (
        <div key={c.key} className="alert warn"><span>{c.simple ? `شعبه «${c.branch}»: کنترل موجودی کامل ممکن نبود (${c.error})؛ معیار، میانگین فروش ۳ ماه اخیر است.` : `شعبه «${c.branch}» در کارآمد: ${c.error}`}</span></div>
      ))}
      <div className="kpis">
        <Kpi label={all ? 'حواله‌های باز' : 'حواله ثبت‌شده منتظر تأیید'} value={orders.length} type="int" sub={`${fmtInt(lines.length)} ردیف کالا`}
          onClick={() => setVerdict('')} active={!verdict} />
        {['approve', 'reduce', 'reject', 'review'].map((k) => (
          <Kpi key={k} label={V[k]} value={cnt(k)} type="int" sub="ردیف کالا" onClick={() => setVerdict(verdict === k ? '' : k)} active={verdict === k} />
        ))}
      </div>
      {!orders.length && (
        <div className="state">{all ? 'حواله بازی برای زنجیره‌ای و اینترنتی نیست.'
          : 'فعلاً حواله ثبت‌شده‌ای برای زنجیره‌ای و اینترنتی نیست. با ثبت حواله در راهکاران، همین‌جا (لایو) می‌آید.'}</div>
      )}
      {orders.map((o) => (
        <Card key={o.oid} className="span2"
          title={<>حواله {faDigits(o.number)} · {o.cust} <span className={`pill ${VERDICT_CLASS[o.verdict]}`}>{V[o.verdict]}</span></>}
          subtitle={`${chLabel[o.channel] || ''} · ${faDate(o.d)} · ${o.state_label} · انبار ${o.store_name || '—'} · ${fmtInt(o.lines)} کالا، ${fmtInt(o.qty)} عدد`
            + (o.suggested !== o.qty ? ` · پیشنهاد ${fmtInt(o.suggested)} عدد` : '') + (o.descr ? ` · ${o.descr}` : '')}>
          <div className="remit-table">
            <DataTable rows={(byOrder[o.oid] || []).filter((r) => !verdict || r.verdict === verdict)}
              unit={unit} pageSize={50} dense search={false} exportName={`remittance-${o.number}`} columns={cols} />
          </div>
        </Card>
      ))}
      <p className="muted small">انبارهای حساب‌شده در موجودی (همه انبارهای همان شعبه در کارآمد): {data.channels.map((c) => `${c.label}: ${(c.stores || []).join('، ') || '—'}`).join(' · ')}</p>
      <p className="muted small">معیار: موجودی و فروش شعبه «زنجیره ای» (برای زنجیره‌ای‌ها) و «اینترنتی» (برای فروش اینترنتی) در کارآمد. تأیید وقتی است که
        موجودی شعبه + حواله از سطح هدف کنترل موجودی بیشتر از {fmtInt(data.settings.tolerance * 100)}٪ یا یک کارتن جلو نزند.</p>
    </>
  )
}
