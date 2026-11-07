// ماژول «گزارش‌ساز اکسل»: قدم‌به‌قدم پیشنهاد می‌دهد — اول هیبرید (شعبه)، بعد سرپرست‌های آن هیبرید، بعد ویزیتورهای آن سرپرست —
// و در آخر می‌پرسد کدام اکسل ساخته شود (ویزیتور، سرپرست یا هیبرید). ساخت فایل: app/services/excel_reports_service.py
import { useEffect, useMemo, useState } from 'react'
import { useApp } from '@sales/lib.jsx'
import { qs, faDigits, n0 } from '../data.js'

/** همه مبالغ این صفحه به ریال (عدد کامل) */
const rial = (v) => `${n0(Math.round(Number(v || 0)))} ریال`

const API = '/api/v1/finance/excel-reports'
const STEPS = [
  { key: 'branch', label: 'هیبرید', ask: 'از کدام هیبرید شروع کنیم؟' },
  { key: 'supervisor', label: 'سرپرست', ask: 'کدام سرپرست؟' },
  { key: 'visitor', label: 'ویزیتور', ask: 'کدام ویزیتور؟' },
  { key: 'kind', label: 'کدام اکسل؟', ask: 'کدام را برایتان اکسل کنم؟' },
]

/** دانلود فایل با کوکی ورود (همان مبدأ، از Proxy پورت 5180) */
async function download(url, fallbackName) {
  const r = await fetch(url, { credentials: 'include' })
  if (!r.ok) {
    const j = await r.json().catch(() => ({}))
    throw new Error(j.detail || `خطای ${r.status}`)
  }
  const blob = await r.blob()
  const m = (r.headers.get('content-disposition') || '').match(/filename\*=UTF-8''([^;]+)/)
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = m ? decodeURIComponent(m[1]) : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 4000)
}

/** گروه‌بندی ویزیتورها: هر گزینه با تعداد ویزیتور و جمع فروش، پرفروش‌ترها اول (پیشنهاد) */
function groupBy(rows, key, extra) {
  const m = new Map()
  for (const r of rows) {
    const g = m.get(r[key]) || { value: r[key], count: 0, net: 0, ...(extra ? extra(r) : {}) }
    g.count += 1
    g.net += r.net_rial
    m.set(r[key], g)
  }
  return [...m.values()].sort((a, b) => b.net - a.net)
}

function Chips({ items, all, onPick, sub, search }) {
  const shown = items.filter((x) => !search || String(x.value).includes(search))
  return (
    <div className="xr-chips">
      <button type="button" className="xr-chip all" onClick={() => onPick('')} style={{ '--i': 0 }}>
        <b>{all.label}</b><small>{all.sub}</small>
      </button>
      {shown.map((x, i) => (
        <button type="button" key={x.value} className={`xr-chip ${i < 3 && !search ? 'top' : ''}`} onClick={() => onPick(x.value)} style={{ '--i': Math.min(i + 1, 24) }}>
          {i < 3 && !search && <em>پیشنهاد</em>}
          <b>{x.value}</b>
          <small>{sub(x)}</small>
        </button>
      ))}
      {!shown.length && <p className="xr-empty">موردی پیدا نشد.</p>}
    </div>
  )
}

// همان ستون‌های برگه «عملکرد ویزیتورها» در اکسل
const pctf = (v) => (v == null ? '—' : `${faDigits((v * 100).toFixed(1))}٪`)
const COLS = [
  { key: 'visitor', label: 'ویزیتور', text: true },
  { key: 'branch', label: 'شعبه', text: true },
  { key: 'supervisor', label: 'سرپرست', text: true },
  { key: 'city', label: 'شهر', text: true },
  { key: 'net', label: 'فروش خالص', money: true },
  { key: 'gross', label: 'فروش ناخالص', money: true },
  { key: 'returns_net', label: 'برگشت از فروش', money: true },
  { key: 'customers', label: 'مشتری خریدار' },
  { key: 'sku', label: 'SKU' },
  { key: 'qty', label: 'تعداد کالا' },
  { key: 'req_docs', label: 'ویزیت ثبت‌شده' },
  { key: 'daily_avg', label: 'میانگین روزانه', money: true },
  { key: 'ar_rial', label: 'مانده حساب', money: true },
  { key: 'ret_cheque_rial', label: 'چک برگشتی', money: true },
  { key: 'vol_disc_rate', label: 'تخفیف حجمی', pct: true },
  { key: 'cash_disc_rate', label: 'تخفیف نقدی', pct: true },
  { key: 'mgmt_disc_rate', label: 'تخفیف مدیریتی', pct: true },
]
const cell = (c, v) => (c.text ? v || '—' : c.pct ? pctf(v) : c.money ? n0(Math.round(Number(v || 0))) : n0(Number(v || 0)))

/** جدول همه ویزیتورهای انتخاب (شهر/سرپرست) با همه شاخص‌ها؛ مرتب‌سازی با کلیک روی سرستون و ردیف جمع */
function VisitorTable({ rows, title, onPick, picked }) {
  const [sort, setSort] = useState({ key: 'net', dir: -1 })
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key]
    return (typeof x === 'string' || typeof y === 'string' ? String(x || '').localeCompare(String(y || ''), 'fa') : Number(x || 0) - Number(y || 0)) * sort.dir
  }), [rows, sort])
  const sum = (k) => rows.reduce((t, r) => t + Number(r[k] || 0), 0)
  return (
    <section className="u-card xr-table-card">
      <div className="xr-stage-head">
        <div><h2>{title}</h2><small>{n0(rows.length)} ویزیتور · همان ستون‌های اکسل ویزیتور · روی ردیف بزنید تا همان ویزیتور انتخاب شود</small></div>
      </div>
      <div className="xr-table-wrap">
        <table className="xr-table">
          <thead>
            <tr>{COLS.map((c) => (
              <th key={c.key} onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? -s.dir : c.text ? 1 : -1 }))}
                aria-sort={sort.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                {c.label}{c.money && <small> (ریال)</small>}{sort.key === c.key && <i>{sort.dir > 0 ? '▲' : '▼'}</i>}
              </th>
            ))}</tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={`${r.visitor}-${r.branch}`} style={{ '--i': Math.min(i, 30) }} className={picked === r.visitor ? 'on' : ''}
                onClick={onPick ? () => onPick(r) : undefined}>
                {COLS.map((c) => <td key={c.key} className={c.text ? 't' : ''}>{cell(c, r[c.key])}</td>)}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>{COLS.map((c, i) => <td key={c.key} className={c.text ? 't' : ''}>
              {i === 0 ? 'جمع' : c.text || c.pct ? '' : c.money ? n0(Math.round(sum(c.key))) : n0(sum(c.key))}</td>)}</tr>
          </tfoot>
        </table>
      </div>
    </section>
  )
}

function KindCard({ kind, icon, title, desc, href, index, team }) {
  const [state, setState] = useState({ busy: false, error: '', done: '' })
  const make = async () => {
    setState({ busy: true, error: '', done: '' })
    const t = Date.now()
    try {
      await download(href, `report-${kind}.xlsx`)
      setState({ busy: false, error: '', done: `دانلود شد (${faDigits(Math.round((Date.now() - t) / 1000))} ثانیه)` })
    } catch (e) {
      setState({ busy: false, error: e.message || 'خطا', done: '' })
    }
  }
  return (
    <section className="u-card xr-kind" style={{ '--i': index }}>
      <div className="xr-card-head"><i aria-hidden>{icon}</i><div><h2>{title}</h2></div></div>
      <ul className="xr-sheets">{desc.map((d) => <li key={d}>{d}</li>)}</ul>
      {team && (
        <div className="xr-team">
          <b>{team.title}</b>
          <ol>{team.rows.map((r) => <li key={r.name}><span>{r.name}</span><small>{r.sub ? `${r.sub} · ` : ''}{rial(r.net)}</small></li>)}</ol>
          <p>{team.total}: <b>{rial(team.rows.reduce((t, r) => t + r.net, 0))}</b></p>
        </div>
      )}
      <div className="xr-actions">
        <button type="button" className="u-btn primary" onClick={make} disabled={state.busy}>
          {state.busy ? <><span className="xr-spin" aria-hidden />در حال ساخت…</> : '⬇ بساز و دانلود کن'}
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
  const valid = /^\d{4}\/\d{2}\/\d{2}$/.test(from) && /^\d{4}\/\d{2}\/\d{2}$/.test(to)

  const [opts, setOpts] = useState({ people: null, error: '' })
  useEffect(() => {
    if (!valid) return undefined
    let alive = true
    setOpts({ people: null, error: '' })
    fetch(`${API}/options?${qs({ date_from: from, date_to: to })}`, { credentials: 'include' })
      .then((r) => r.json()).then((j) => alive && setOpts({ people: j.people || [], error: j.error || j.detail || '' }))
      .catch((e) => alive && setOpts({ people: [], error: e.message }))
    return () => { alive = false }
  }, [from, to, valid])

  // انتخاب‌ها؛ undefined = هنوز انتخاب نشده، '' = «همه»
  const [pick, setPick] = useState({ branch: undefined, supervisor: undefined, visitor: undefined })
  const [search, setSearch] = useState('')
  const step = pick.branch === undefined ? 0 : pick.supervisor === undefined ? 1 : pick.visitor === undefined ? 2 : 3
  const choose = (key, value) => { setSearch(''); setPick((p) => ({ ...p, [key]: value })) }
  const back = (i) => {
    setSearch('')
    setPick((p) => ({ branch: i <= 0 ? undefined : p.branch, supervisor: i <= 1 ? undefined : p.supervisor, visitor: i <= 2 ? undefined : p.visitor }))
  }

  const people = opts.people || []
  const inBranch = useMemo(() => people.filter((r) => !pick.branch || r.branch === pick.branch), [people, pick.branch])
  // با انتخاب سرپرست، همه ویزیتورهایش (در هر هیبریدی) — نه فقط ویزیتورهای همان هیبرید
  const inSup = useMemo(() => (pick.supervisor ? people.filter((r) => r.supervisor === pick.supervisor) : inBranch), [people, inBranch, pick.supervisor])
  const chosen = useMemo(() => inSup.filter((r) => !pick.visitor || r.visitor === pick.visitor), [inSup, pick.visitor])
  const branches = [...new Set(chosen.map((r) => r.branch))]
  const sups = [...new Set(chosen.map((r) => r.supervisor))]
  // زیرمجموعه کامل سرپرست(ها) و کل ویزیتورهای هیبرید(ها) — اکسل سرپرست و هیبرید بر همین اساس ساخته می‌شود
  const team = useMemo(() => people.filter((r) => sups.includes(r.supervisor)), [people, sups.join('|')])
  const branchAll = useMemo(() => people.filter((r) => branches.includes(r.branch)), [people, branches.join('|')])
  const branchSups = new Set(branchAll.map((r) => r.supervisor)).size

  const where = [pick.branch, pick.supervisor && `سرپرست ${pick.supervisor}`, pick.visitor && `ویزیتور ${pick.visitor}`].filter(Boolean)
  const scopeText = where.length ? where.join(' › ') : 'همه هیبریدها، سرپرست‌ها و ویزیتورها'
  const href = (kind) => `${API}/${kind}.xlsx?${qs({ date_from: from, date_to: to, branch: pick.branch, supervisor: pick.supervisor, visitor: pick.visitor })}`

  const kinds = [
    { kind: 'visitors', icon: '☺', title: pick.visitor ? `اکسل ویزیتور: ${pick.visitor}` : `اکسل ${n0(chosen.length)} ویزیتور`,
      desc: ['عملکرد: فروش خالص و ناخالص، مشتری خریدار، تعداد SKU و کالا، ویزیت ثبت‌شده، میانگین فروش روزانه',
        'مانده حساب مشتریان و چک برگشتی، تخفیف حجمی/نقدی/مدیریتی', '۴۰ کالای پرفروش هر ویزیتور', 'مانده مطالبات و چک‌های برگشتی هر ویزیتور به تفکیک مشتری', 'جمع به تفکیک شعبه',
        chosen.length <= 40 ? 'یک برگه کارت برای هر ویزیتور با همه شاخص‌ها و کالاهایش' : 'برای برگه جدای هر ویزیتور، هیبرید یا سرپرست را محدود کنید (تا ۴۰ ویزیتور)'] },
    { kind: 'supervisors', icon: '♙', title: sups.length === 1 ? `اکسل سرپرست: ${sups[0]}` : `اکسل ${n0(sups.length)} سرپرست`,
      desc: ['برگه اول کارت سرپرست؛ بعد کارت همه ویزیتورهایش (در هر هیبرید، حتی بدون فروش در ۳ ماه اخیر)',
        'عملکرد سرپرست، درصد تحقق شعبه و تخفیف حجمی/نقدی/مدیریتی',
        pick.visitor ? `کل ویزیتورهای ${sups[0] || 'سرپرستش'} (نه فقط ${pick.visitor})، هرکدام با کارت جدا` : 'یک برگه برای هر سرپرست با ریز همه ویزیتورهایش',
        'همه اعداد کارت سرپرست = جمع ویزیتورهای زیرمجموعه‌اش',
        'ریز کالاها، مانده مطالبات و چک‌های برگشتی هر ویزیتور به تفکیک مشتری' + (sups.length === 1 ? ' و یک برگه کارت برای هر ویزیتورش' : '')],
      team: sups.length === 1 ? { title: `ویزیتورهای زیر ${sups[0]}`, total: `جمع ${n0(team.length)} ویزیتور`,
        rows: team.map((r) => ({ name: r.visitor, net: r.net_rial })) } : null },
    { kind: 'hybrids', icon: '⬢', title: branches.length === 1 ? `اکسل هیبرید: ${branches[0]}` : `اکسل ${n0(branches.length)} شعبه / هیبرید`,
      desc: ['رتبه و درصد تحقق، فاکتور توزیع‌شده و نشده، مانده حساب و چک برگشتی شعبه',
        `اطلاعات کل شعبه، نه فقط این انتخاب: ${n0(branchSups)} سرپرست و ${n0(branchAll.length)} ویزیتور، جمع فروش خالص ${rial(branchAll.reduce((t, r) => t + r.net_rial, 0))}`,
        'کارت هر هیبرید: همه سرپرستانش (هرکدام جمع زیرمجموعه) و همه ویزیتورهایش؛ به‌علاوه ریز کالاها، مطالبات و چک‌های برگشتی به تفکیک مشتری'],
      team: branches.length === 1 ? { title: `سرپرستان ${branches[0]}`, total: `جمع ${n0(branchSups)} سرپرست`,
        rows: [...branchAll.reduce((m, r) => m.set(r.supervisor, { name: r.supervisor, net: (m.get(r.supervisor)?.net || 0) + r.net_rial,
          n: (m.get(r.supervisor)?.n || 0) + 1 }), new Map()).values()].sort((a, b) => b.net - a.net)
          .map((x) => ({ ...x, sub: `${n0(x.n)} ویزیتور` })) } : null },
  ]

  return (
    <div className="u-page xr">
      <div className="u-head">
        <div>
          <span className="u-crumb">گزارش‌ها</span>
          <h1>گزارش‌ساز اکسل</h1>
          <p>قدم‌به‌قدم انتخاب کنید؛ پیشنهادها بر اساس فروش همین بازه مرتب شده‌اند. مبالغ به ریال.</p>
        </div>
        <div className="xr-range">
          <label>از تاریخ<input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="1405/08/01" dir="ltr" /></label>
          <label>تا تاریخ<input value={to} onChange={(e) => setTo(e.target.value)} placeholder="1405/08/12" dir="ltr" /></label>
        </div>
      </div>

      <ol className="xr-steps">
        {STEPS.map((s, i) => {
          const val = i < 3 ? pick[s.key] : null
          return (
            <li key={s.key} className={i === step ? 'on' : i < step ? 'done' : ''}>
              <button type="button" onClick={() => i < step && back(i)} disabled={i >= step}>
                <i>{i < step ? '✓' : faDigits(i + 1)}</i>
                <span>{s.label}<small>{i < step ? (val || 'همه') : i === step ? 'در حال انتخاب' : ''}</small></span>
              </button>
            </li>
          )
        })}
      </ol>

      {!valid && <div className="xr-err">تاریخ را به شکل ۱۴۰۵/۰۸/۰۱ وارد کنید.</div>}
      {opts.error && <div className="xr-err">{opts.error}</div>}

      <section className="u-card xr-stage" key={step}>
        <div className="xr-stage-head">
          <div>
            <h2>{STEPS[step].ask}</h2>
            <small>{step === 3 ? scopeText : where.length ? `${scopeText} — ${n0(step === 1 ? inBranch.length : inSup.length)} ویزیتور` : 'پرفروش‌ترها اول آمده‌اند'}</small>
          </div>
          {step < 3 && <input className="xr-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="جستجو…" />}
          {step > 0 && <button type="button" className="u-btn ghost" onClick={() => back(step - 1)}>→ قدم قبل</button>}
        </div>

        {opts.people === null && valid ? <div className="xr-loading"><span className="xr-spin dark" />در حال آماده کردن پیشنهادها…</div>
          : step === 0 ? <Chips items={groupBy(people, 'branch').map((g) => ({ ...g, sups: new Set(people.filter((r) => r.branch === g.value).map((r) => r.supervisor)).size }))}
            search={search} onPick={(v) => choose('branch', v)}
            all={{ label: 'همه هیبریدها', sub: `${n0(people.length)} ویزیتور` }}
            sub={(x) => `${n0(x.sups)} سرپرست · ${n0(x.count)} ویزیتور · ${rial(x.net)}`} />
            : step === 1 ? <Chips items={groupBy(inBranch, 'supervisor', (r) => ({ branch: r.branch }))} search={search} onPick={(v) => choose('supervisor', v)}
              all={{ label: `همه سرپرستان${pick.branch ? ` ${pick.branch}` : ''}`, sub: `${n0(inBranch.length)} ویزیتور` }}
              sub={(x) => `${x.branch} · ${n0(x.count)} ویزیتور · ${rial(x.net)}`} />
              : step === 2 ? <Chips items={inSup.map((r) => ({ value: r.visitor, ...r }))} search={search} onPick={(v) => choose('visitor', v)}
                all={{ label: `همه ویزیتورهای${pick.supervisor ? ` ${pick.supervisor}` : ' این انتخاب'}`, sub: `${n0(inSup.length)} ویزیتور` }}
                sub={(x) => `${x.branch} · ${n0(x.customers)} مشتری · ${rial(x.net_rial)}`} />
                : <div className="xr-grid">{kinds.map((k, i) => <KindCard key={k.kind} {...k} href={href(k.kind)} index={i} />)}</div>}
      </section>

      {/* با انتخاب هیبرید یا سرپرست، همه ویزیتورهایش با همه شاخص‌های اکسل ویزیتور */}
      {step > 0 && opts.people !== null && (
        <VisitorTable rows={step >= 3 ? chosen : inSup} picked={pick.visitor}
          title={`ویزیتورهای ${where.length ? scopeText : 'همه هیبریدها'}`}
          onPick={step >= 3 && pick.visitor ? undefined : (r) => {
            setSearch('')
            setPick({ branch: pick.branch ?? '', supervisor: pick.supervisor ?? '', visitor: r.visitor })
          }} />
      )}

      <p className="xr-note">
        هیبرید هر ویزیتور = شعبه فاکتورهایش در کارآمد. ویزیت ثبت‌شده = تعداد اسناد درخواست در بازه.
        درصد تحقق از تارگت‌های صفحه «تحقق و پورسانت» می‌آید؛ اگر تارگت ماه ثبت نشده باشد خالی می‌ماند.
        اولین ساخت هر روز تا حدود ۳۰ ثانیه طول می‌کشد؛ بعدی‌ها چند ثانیه.
      </p>
    </div>
  )
}
