import { useMemo, useState } from 'react'
import { useApp, useFetch, fetchJson, sendJson, fmtInt, fmtPct, fmtMoney, faDigits, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Empty, Kpi, MultiSelect } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { MONTH_NAMES, addDays, parseDate, toJdn, weekIndex } from '../jalali.js'
import { achPill } from './Commission.jsx'

// صفحه «مسابقه»: مسابقه‌های فروش (بازه، کالاها، تارگت ویزیتورها، گروه A/B شعب) در data/contests.json تعریف می‌شوند
// (بیرون از صفحه، با contest.save)؛ این صفحه فقط نمایش و حذف پس از پایان مسابقه را دارد.
// ریز درخواست‌ها (فروشنده × کالا؛ نه فاکتور) یک بار از سرور می‌آید و همه فیلترها و تجمیع‌ها همین‌جا انجام می‌شود.

const FILTERS = [
  ['tier', 'گروه هیبرید'], ['branch', 'هیبرید'], ['supervisor', 'سرپرست'], ['seller_key', 'ویزیتور'],
  ['category', 'گروه کالا'], ['brand', 'برند'], ['product_code', 'کالا (SKU)'],
]
const PERSON_KEYS = ['tier', 'branch', 'supervisor', 'seller_key']
const sum = (rows, k) => rows.reduce((a, r) => a + (r[k] || 0), 0)

export default function Contest() {
  const { unit, vat } = useApp()
  const list = useFetch('/api/contest')
  const [sel, setSel] = useState(null)
  const contests = list.data?.contests || []
  const cur = contests.find((c) => c.id === sel) || contests[0]

  const reload = (id) => fetchJson('/api/contest').then((d) => { list.setData(d); if (id !== undefined) setSel(id) })
  const remove = async (c) => {
    if (!window.confirm(`مسابقه «${c.name}» و تارگت‌هایش برای همیشه حذف شود؟`)) return
    try {
      await sendJson(`/api/contest/${c.id}`, 'DELETE')
      reload(null)
    } catch (e) { window.alert(e.message) }
  }

  if (list.loading && !list.data) return <Loading />
  if (list.error) return <ErrorBox error={list.error} />
  return (
    <>
      <PageHead title="مسابقه" desc="مسابقه‌های فروش بر اساس درخواست: تعداد و مبلغ درخواست کالاهای مسابقه به تفکیک هیبرید، ویزیتور و SKU، تحقق تارگت و نفرات برتر">
        <div className="pill-row">
          {cur && <button className="btn ghost" onClick={() => remove(cur)}>حذف مسابقه</button>}
        </div>
      </PageHead>
      {contests.length > 1 && (
        <div style={{ marginBottom: 12 }}>
          <Tabs value={cur?.id} onChange={setSel} tabs={contests.map((c) => ({ value: c.id, label: c.name }))} />
        </div>
      )}
      {!cur ? (
        <Card><Empty text="مسابقه فعالی تعریف نشده است." /></Card>
      ) : <ContestView key={cur.id + (cur.updated || '')} contest={cur} unit={unit} vat={vat} />}
    </>
  )
}

// ---------------------------------------------------------------- نمایش یک مسابقه
function ContestView({ contest, unit, vat }) {
  const { meta } = useApp()
  // بازه تاریخ داخل مسابقه؛ خالی = کل بازه مسابقه (سرور بیرون از بازه مسابقه را می‌بُرد)
  // پیش‌فرض: روز شروع شمارش تعریف‌شده در مسابقه (default_from، مثلاً ۱۰ آبان)
  const dr0 = { date_from: contest.default_from && contest.default_from > contest.date_from ? contest.default_from : '', date_to: '' }
  const [dr, setDr] = useState(dr0)
  const q = `vat=${vat ? 1 : 0}${dr.date_from ? `&date_from=${dr.date_from}` : ''}${dr.date_to ? `&date_to=${dr.date_to}` : ''}`
  const { data, loading, error } = useFetch(`/api/contest/${contest.id}/data?${q}`)
  const [f, setF] = useState({})
  const [topTier, setTopTier] = useState('all')
  const [topBy, setTopBy] = useState('excess')
  const [view, setView] = useState('people')
  const [skuVal, setSkuVal] = useState('qty')
  const [brTier, setBrTier] = useState('all')   // به تفکیک هیبرید: کل / A / B
  const [psTier, setPsTier] = useState('all')   // به تفکیک ویزیتور: کل / A / B
  const byNet = contest.target_unit === 'net'

  const rows = data?.rows || []
  const people = data?.people || []
  // ردیف‌های فیلترشده و فهرست گزینه‌های هر فیلتر (از همه ردیف‌ها)
  const options = useMemo(() => {
    const o = {}
    const src = [...rows, ...people.map((p) => ({ ...p }))]
    for (const [k] of FILTERS) {
      const m = new Map()
      for (const r of src) {
        if (r[k] == null || r[k] === '') continue
        const label = k === 'seller_key' ? `${r.seller}${r.seller_code ? ` (${faDigits(r.seller_code)})` : ''}`
          : k === 'product_code' ? r.product : k === 'tier' ? `هیبرید ${r.tier}` : r[k]
        const group = k === 'seller_key' || k === 'supervisor' ? r.branch : k === 'product_code' ? r.category : undefined
        if (!m.has(r[k])) m.set(r[k], { value: r[k], label, group })
      }
      o[k] = [...m.values()].sort((a, b) => String(a.label).localeCompare(String(b.label), 'fa'))
    }
    return o
  }, [rows, people])
  const pass = (r, keys) => keys.every((k) => !f[k]?.length || f[k].includes(r[k]))
  const allKeys = FILTERS.map(([k]) => k)
  const fr = useMemo(() => rows.filter((r) => pass(r, allKeys)), [rows, f])  // eslint-disable-line react-hooks/exhaustive-deps

  // جمع هر ویزیتور: درخواست فیلترشده + تارگت (ویزیتورهای تارگت‌دار بی‌درخواست هم می‌آیند)
  const persons = useMemo(() => {
    const m = new Map()
    for (const p of people) {
      if (!pass(p, PERSON_KEYS)) continue
      m.set(p.seller_key, { ...p, key: p.seller_key, qty: 0, done_qty: 0, net: 0, customers: 0, skus: 0 })
    }
    for (const r of fr) {
      let p = m.get(r.seller_key)
      if (!p) {
        p = { key: r.seller_key, seller_key: r.seller_key, branch: r.branch, tier: r.tier, seller: r.seller, seller_code: r.seller_code,
          supervisor: r.supervisor, target: null, qty: 0, done_qty: 0, net: 0, customers: 0, skus: 0 }
        m.set(r.seller_key, p)
      }
      p.qty += r.qty; p.done_qty += r.done_qty || 0; p.net += r.net
      p.customers = Math.max(p.customers, r.customers)
      if (r.qty > 0) p.skus += 1
    }
    const out = [...m.values()]
    // ورود به مسابقه: تعداد/مبلغ درخواست همان بازه و کالاهای انتخاب‌شده (همان عددی که در جدول دیده می‌شود) به تارگت برسد
    for (const p of out) {
      const fv = byNet ? p.net : p.qty
      p.full = fv
      p.ach = p.target ? fv / p.target : null
      p.gap = p.target ? Math.max(0, p.target - fv) : null
      p.in = !!p.target && fv >= p.target
      p.excess = p.in ? fv - p.target : null
      p.status = !p.target ? 'بدون تارگت' : p.in ? 'وارد مسابقه شده' : 'هنوز به تارگت نرسیده'
      p.label = p.seller
    }
    return out.sort((a, b) => (b.in - a.in) || (b.in ? b.excess - a.excess : (b.ach ?? -1) - (a.ach ?? -1)) || b.qty - a.qty)
  }, [people, fr, f, byNet])  // eslint-disable-line react-hooks/exhaustive-deps

  const branches = useMemo(() => {
    const m = new Map()
    for (const p of persons) {
      const b = m.get(p.branch) || { key: p.branch, label: p.branch, tier: p.tier, qty: 0, net: 0, full: 0, target: 0, sellers: 0, active: 0, done: 0 }
      b.qty += p.qty; b.net += p.net; b.target += p.target || 0; b.sellers += 1
      if (p.target) b.full += p.full
      if (p.qty > 0) b.active += 1
      if (p.in) b.done += 1
      m.set(p.branch, b)
    }
    const out = [...m.values()]
    for (const b of out) {
      b.ach = b.target ? b.full / b.target : null
      b.per_seller = b.sellers ? b.qty / b.sellers : null
    }
    return out.sort((a, b) => b.qty - a.qty)
  }, [persons, byNet])

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  const totQty = sum(persons, 'qty'), totNet = sum(persons, 'net'), totTarget = sum(persons, 'target')
  const totFull = sum(persons.filter((p) => p.target), 'full')
  const done = persons.filter((p) => p.in).length
  // فقط کسانی که به تارگتشان رسیده‌اند در رتبه‌بندی مسابقه هستند
  const inTier = persons.filter((p) => topTier === 'all' || p.tier === topTier)
  const ranked = inTier.filter((p) => p.in).sort((a, b) => (b[topBy] ?? -1) - (a[topBy] ?? -1)).slice(0, 10)
  const near = inTier.filter((p) => p.target && !p.in).sort((a, b) => b.ach - a.ach).slice(0, 5)
  const unmatched = people.filter((p) => p.unmatched)
  const loose = people.filter((p) => p.loose)
  const auto = people.filter((p) => p.auto)
  const tgt = byNet ? { type: 'money' } : { type: 'int' }
  const active = Object.values(f).some((v) => v?.length) || dr.date_from !== dr0.date_from || !!dr.date_to

  const personCols = [
    { key: 'rank', label: 'رتبه', type: 'int' },
    { key: 'label', label: 'ویزیتور' },
    { key: 'seller_code', label: 'کد', render: (r) => faDigits(r.seller_code) },
    { key: 'branch', label: 'هیبرید' },
    { key: 'tier', label: 'گروه' },
    { key: 'supervisor', label: 'سرپرست' },
    { key: 'qty', label: 'تعداد درخواست', type: 'int' },
    { key: 'done_qty', label: 'فاکتور شده (تعداد)', type: 'int' },
    { key: 'net', label: 'مبلغ درخواست', type: 'money' },
    { key: 'target', label: byNet ? 'تارگت ریالی' : 'تارگت (تعداد)', ...tgt },
    { key: 'ach', label: 'درصد تحقق', type: 'pct', render: (r) => (r.target ? achPill('ach')(r) : '—') },
    { key: 'status', label: 'وضعیت', render: (r) => (r.in ? <b style={{ color: 'var(--good, #16a34a)' }}>✓ وارد مسابقه شده</b> : <span className="muted">{r.status}</span>) },
    { key: 'excess', label: 'مازاد بر تارگت', ...tgt },
    { key: 'gap', label: 'مانده تا ورود', ...tgt },
    { key: 'skus', label: 'تنوع SKU', type: 'int' },
  ]
  const rankedPersons = persons.map((p, i) => ({ ...p, rank: i + 1 }))
  const tierFilter = (v, set) => <Tabs value={v} onChange={set} tabs={[{ value: 'all', label: 'کل' }, { value: 'A', label: 'هیبرید A' }, { value: 'B', label: 'هیبرید B' }]} />
  const ofTier = (t) => (r) => t === 'all' || r.tier === t
  const brRows = branches.filter(ofTier(brTier))
  const psRows = rankedPersons.filter(ofTier(psTier))
  const lineRows = fr.filter(ofTier(psTier))
  const branchCols = [
    { key: 'label', label: 'هیبرید' }, { key: 'tier', label: 'گروه' },
    { key: 'qty', label: 'تعداد درخواست', type: 'int' }, { key: 'net', label: 'مبلغ درخواست', type: 'money' },
    { key: 'target', label: byNet ? 'تارگت ریالی' : 'تارگت (تعداد)', ...tgt },
    { key: 'ach', label: 'درصد تحقق', type: 'pct', render: (r) => (r.target ? achPill('ach')(r) : '—') },
    { key: 'sellers', label: 'ویزیتور', type: 'int' }, { key: 'active', label: 'ویزیتور با درخواست', type: 'int' },
    { key: 'done', label: 'وارد مسابقه شده', type: 'int' },
    { key: 'per_seller', label: 'میانگین تعداد هر ویزیتور', type: 'int' },
  ]
  const lineCols = [
    { key: 'seller', label: 'ویزیتور' }, { key: 'branch', label: 'هیبرید' }, { key: 'tier', label: 'گروه' },
    { key: 'product_code', label: 'کد کالا' }, { key: 'product', label: 'کالا' }, { key: 'category', label: 'گروه کالا' },
    { key: 'brand', label: 'برند' },
    { key: 'qty', label: 'تعداد درخواست', type: 'int' }, { key: 'done_qty', label: 'فاکتور شده (تعداد)', type: 'int' },
    { key: 'net', label: 'مبلغ درخواست', type: 'money' },
    { key: 'customers', label: 'مشتری', type: 'int' }, { key: 'requests', label: 'سند درخواست', type: 'int' },
  ]

  return (
    <>
      <div className="filterbar">
        <DayRange contest={contest} value={dr} onChange={setDr} today={meta?.file?.today} />
        <PeriodNote contest={contest} period={data.period} narrowed={!!(dr.date_from || dr.date_to)} lastDate={data.last_date} />
        {FILTERS.map(([k, label]) => (
          <MultiSelect key={k} label={label} value={f[k] || []} options={options[k] || []} allMode={k === 'product_code'}
            onChange={(v) => setF((x) => ({ ...x, [k]: v }))} />
        ))}
        {active && <button className="btn ghost" onClick={() => { setF({}); setDr(dr0) }}>حذف فیلترها</button>}
      </div>

      <div className="kpis">
        <Kpi label="تعداد درخواست" value={totQty} type="int" hint="تعداد درخواست‌های ثبت‌شده کالاهای مسابقه (بدون باطل‌شده‌ها، فاکتور شده یا نشده)" />
        <Kpi label="مبلغ درخواست" value={totNet} hint={vat ? 'با ارزش افزوده (قابل پرداخت)' : 'پس از پروموشن، بدون ارزش افزوده'} />
        <Kpi label={byNet ? 'تارگت ریالی' : 'تارگت (تعداد)'} value={totTarget} type={byNet ? 'money' : 'int'} />
        <Kpi label="تحقق کل" value={totTarget ? totFull / totTarget : null} type="pct" hint="درخواست بازه و کالاهای انتخاب‌شده نسبت به تارگت" />
        <Kpi label="وارد مسابقه شده" value={done} type="int" hint="ویزیتورهایی که به تارگتشان رسیده‌اند؛ فقط این‌ها در رتبه‌بندی هستند"
          sub={`از ${fmtInt(persons.filter((p) => p.target).length)} ویزیتور تارگت‌دار`} />
      </div>

      {(unmatched.length > 0 || loose.length > 0 || auto.length > 0) && (
        <div className="state" style={{ textAlign: 'start', marginBottom: 12 }}>
          {auto.length > 0 && <div>در فایل تارگت نبودند، تارگت پیش‌فرض گروه شعبه گرفتند ({Object.entries(contest.tier_targets || {}).map(([t, v]) => `${t}: ${fmtInt(v)}`).join('، ')}): {auto.map((p) => `${p.seller} (${p.branch})`).join('، ')}</div>}
          {unmatched.length > 0 && <div>در کارآمد پیدا نشد (با درخواست صفر حساب می‌شوند): {unmatched.map((p) => `${p.seller} (${p.branch})`).join('، ')}</div>}
          {loose.length > 0 && <div>فقط با کد فروشنده تطبیق شد، نامشان با فایل تارگت یکی نیست: {loose.map((p) => `${p.file_name} ← ${p.seller}`).join('، ')}</div>}
        </div>
      )}

      <div className="grid g2">
        <Card title="نفرات برتر" className="span2"
          subtitle={`فقط ویزیتورهایی که به تارگتشان رسیده‌اند وارد مسابقه می‌شوند (${fmtInt(done)} نفر). تارگت، مازاد و درصد تحقق از درخواست‌های همین بازه و کالاهای انتخاب‌شده`}
          actions={<>
            <Tabs value={topBy} onChange={setTopBy} tabs={[{ value: 'excess', label: 'مازاد بر تارگت' }, { value: 'ach', label: 'درصد تحقق' }, { value: 'qty', label: 'تعداد' }, { value: 'net', label: 'مبلغ' }]} />
            <Tabs value={topTier} onChange={setTopTier} tabs={[{ value: 'all', label: 'کل' }, { value: 'A', label: 'هیبرید A' }, { value: 'B', label: 'هیبرید B' }]} />
          </>}>
          {ranked.length ? <Podium rows={ranked} by={topBy} unit={unit} byNet={byNet} />
            : <Empty text="هنوز کسی به تارگتش نرسیده و وارد مسابقه نشده است." />}
          {near.length > 0 && (
            <div className="muted small" style={{ marginTop: 10 }}>
              نزدیک‌ترین‌ها به ورود: {near.map((p) => `${p.seller} (${fmtPct(p.ach, 0)}، مانده ${byNet ? `${fmtMoney(p.gap, unit)} ${UNITS[unit].label}` : `${fmtInt(p.gap)} عدد`})`).join('، ')}
            </div>
          )}
        </Card>

        <Card title="به تفکیک هیبرید" className="span2" actions={tierFilter(brTier, setBrTier)}>
          <DataTable rows={brRows} columns={branchCols} unit={unit} pageSize={30} exportName={`contest-${contest.name}-hybrid`}
            defaultSort={{ key: 'qty', dir: 'desc' }}
            onRowClick={(r) => setF((x) => ({ ...x, branch: [r.key] }))}
            totals={(rs) => ({ label: 'جمع', qty: sum(rs, 'qty'), net: sum(rs, 'net'), target: sum(rs, 'target'),
              sellers: sum(rs, 'sellers'), active: sum(rs, 'active'), done: sum(rs, 'done'),
              ach: sum(rs, 'target') ? sum(rs, 'full') / sum(rs, 'target') : null })} />
        </Card>

        <Card title="به تفکیک ویزیتور" className="span2"
          actions={<>
            {tierFilter(psTier, setPsTier)}
            {view === 'sku' && <Tabs value={skuVal} onChange={setSkuVal} tabs={[{ value: 'qty', label: 'تعداد' }, { value: 'net', label: 'مبلغ' }]} />}
            <Tabs value={view} onChange={setView} tabs={[{ value: 'people', label: 'خلاصه و تارگت' }, { value: 'sku', label: 'ماتریس SKU' }, { value: 'lines', label: 'ریز سطرها' }]} />
          </>}>
          {view === 'people' && (
            <DataTable rows={psRows} columns={personCols} unit={unit} pageSize={30} exportName={`contest-${contest.name}-visitors`}
              totals={(rs) => ({ label: 'جمع', qty: sum(rs, 'qty'), done_qty: sum(rs, 'done_qty'),
                net: sum(rs, 'net'), target: sum(rs, 'target'), excess: sum(rs, 'excess'), gap: sum(rs, 'gap') })} />
          )}
          {view === 'sku' && <SkuMatrix persons={psRows} rows={lineRows} val={skuVal} unit={unit} name={contest.name} />}
          {view === 'lines' && (
            <DataTable rows={lineRows.map((r, i) => ({ ...r, key: i }))} columns={lineCols} unit={unit} pageSize={30}
              exportName={`contest-${contest.name}-lines`} defaultSort={{ key: 'qty', dir: 'desc' }}
              totals={(rs) => ({ seller: 'جمع', qty: sum(rs, 'qty'), done_qty: sum(rs, 'done_qty'), net: sum(rs, 'net'), requests: sum(rs, 'requests') })} />
          )}
        </Card>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- بازه روزانه داخل مسابقه
const WEEK = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
const dayName = (s) => {
  const d = parseDate(s)
  return d ? `${faDigits(d.jd)} ${MONTH_NAMES[d.jm - 1]} · ${WEEK[weekIndex(toJdn(d.jy, d.jm, d.jd))]}` : s
}

/** فقط روز شروع شمارش: از روز انتخاب‌شده تا پایان مسابقه؛ خالی = شروع مسابقه */
function DayRange({ contest, value, onChange, today }) {
  const days = useMemo(() => {
    const out = []
    for (let s = contest.date_from; s <= contest.date_to && out.length < 400; s = addDays(s, 1)) out.push(s)
    return out
  }, [contest.date_from, contest.date_to])
  const from = value.date_from || ''
  return (
    <label className="unit-select">
      <span className="ms-label">شروع از روز</span>
      <select value={from} onChange={(e) => onChange({ date_from: e.target.value, date_to: '' })}>
        <option value="">شروع مسابقه ({dayName(contest.date_from)})</option>
        {days.map((d) => <option key={d} value={d}>{dayName(d)}{d === today ? ' (امروز)' : ''}</option>)}
      </select>
    </label>
  )
}

/** خلاصه بازه به شکل برچسب: «مسابقه: ۱ آبان تا ۳۰ آبان» · «نمایش: فقط ۱۰ آبان · شنبه» · «آخرین درخواست» · «تعداد کالا» */
function PeriodNote({ contest, period, narrowed, lastDate }) {
  const short = (s) => { const d = parseDate(s); return d ? `${faDigits(d.jd)} ${MONTH_NAMES[d.jm - 1]}` : faDigits(s) }
  const span = (a, b) => (a === b ? `فقط ${dayName(a)}` : `${short(a)} تا ${short(b)}`)
  const chip = { padding: '3px 10px', borderRadius: 999, background: 'var(--surface-2)', whiteSpace: 'nowrap' }
  return (
    <span className="small" style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      <span style={chip} className="muted">مسابقه: {span(contest.date_from, contest.date_to)}</span>
      {narrowed && period && <span style={{ ...chip, background: 'var(--accent)', color: '#fff' }}>نمایش: {span(period.from, period.to)}</span>}
      <span style={chip} className="muted">{lastDate ? `آخرین درخواست: ${short(lastDate)}` : 'در این بازه درخواستی نیست'}</span>
      <span style={chip} className="muted">{fmtInt(contest.products.length)} کالا</span>
    </span>
  )
}

function Podium({ rows, by, unit, byNet }) {
  const medal = ['🥇', '🥈', '🥉']
  const max = Math.max(...rows.map((r) => r[by] || 0), 1e-9)
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {rows.map((r, i) => (
        <div key={r.key} style={{ display: 'grid', gridTemplateColumns: '36px minmax(140px, 1.3fr) 2fr auto', alignItems: 'center', gap: 10 }}>
          <b style={{ fontSize: i < 3 ? 20 : 14, textAlign: 'center' }}>{medal[i] || faDigits(i + 1)}</b>
          <div style={{ minWidth: 0 }}>
            <div className="ellipsis"><b>{r.seller}</b></div>
            <div className="muted small ellipsis">{r.branch} · گروه {r.tier}</div>
          </div>
          <div style={{ background: 'var(--surface-2)', borderRadius: 6, height: 12, overflow: 'hidden' }}>
            <div style={{ width: `${Math.max(0, Math.min(1, (r[by] || 0) / max)) * 100}%`, height: '100%', background: 'var(--accent)' }} />
          </div>
          <div className="small" style={{ whiteSpace: 'nowrap', textAlign: 'left' }}>
            {by === 'excess' ? <b>{byNet ? `${fmtMoney(r.excess, unit)} ${UNITS[unit].label}` : `${fmtInt(r.excess)} عدد`} مازاد</b>
              : by === 'ach' ? <b>{fmtPct(r.ach, 0)}</b> : by === 'qty' ? <b>{fmtInt(r.qty)} عدد</b> : <b>{fmtMoney(r.net, unit)} {UNITS[unit].label}</b>}
            <span className="muted"> · {by === 'ach' || by === 'excess' ? `تحقق ${fmtPct(r.ach, 0)}` : by === 'qty' ? `${fmtMoney(r.net, unit)} ${UNITS[unit].label}` : `${fmtInt(r.qty)} عدد`}
              {r.target ? ` · تارگت ${byNet ? fmtMoney(r.target, unit) : fmtInt(r.target)}` : ''}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

/** ویزیتور × SKU: هر کالا یک ستون (تعداد خالص یا مبلغ خالص) */
function SkuMatrix({ persons, rows, val, unit, name }) {
  const { cols, data } = useMemo(() => {
    const prods = new Map()
    for (const r of rows) {
      const p = prods.get(r.product_code) || { code: r.product_code, label: r.product, total: 0 }
      p.total += r.qty
      prods.set(r.product_code, p)
    }
    const list = [...prods.values()].sort((a, b) => b.total - a.total)
    const cell = new Map(rows.map((r) => [`${r.seller_key}|${r.product_code}`, r]))
    const data = persons.map((p) => {
      const o = { key: p.key, rank: p.rank, label: p.seller, branch: p.branch, tier: p.tier, total: val === 'qty' ? p.qty : p.net }
      for (const c of list) o[`p_${c.code}`] = cell.get(`${p.key}|${c.code}`)?.[val] ?? null
      return o
    })
    const type = val === 'qty' ? 'int' : 'money'
    const cols = [
      { key: 'rank', label: 'رتبه', type: 'int', sticky: true }, { key: 'label', label: 'ویزیتور', sticky: true },
      { key: 'branch', label: 'هیبرید' }, { key: 'tier', label: 'گروه' },
      { key: 'total', label: val === 'qty' ? 'جمع تعداد' : 'جمع مبلغ', type },
      ...list.map((c) => ({ key: `p_${c.code}`, label: c.label, type, hint: `کد ${c.code}` })),
    ]
    return { cols, data }
  }, [persons, rows, val])
  if (!data.length) return <Empty />
  return (
    <DataTable rows={data} columns={cols} unit={unit} pageSize={30} dense exportName={`contest-${name}-sku-${val}`}
      totals={(rs) => Object.fromEntries([['label', 'جمع'], ...cols.filter((c) => c.type && c.key !== 'rank').map((c) => [c.key, sum(rs, c.key)])])} />
  )
}
