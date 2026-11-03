import { useEffect, useMemo, useRef, useState } from 'react'
import { useApp, useFetch, sendJson, fetchJson, fmtInt, fmtMoney, fmtPct, faDigits, isNum, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { buildXlsx } from '../xlsx.js'
import { MONTH_NAMES } from '../jalali.js'

const monthName = (m) => `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${faDigits(m.slice(0, 4))}`
const TOMAN_M = 1e7  // یک میلیون تومان به ریال
const pct2 = (key, label, hint) => ({ key, label, type: 'pct', hint, render: (r) => fmtPct(r[key], 2), csv: (r) => (isNum(r[key]) ? Math.round(r[key] * 10000) / 100 : '') })
const achClass = (a) => (!isNum(a) ? 'st-none' : a >= 0.95 ? 'st-green' : a >= 0.7 ? 'st-yellow' : 'st-red')
export const achPill = (key) => (r) => <span className={`pill ${achClass(r[key])}`}>{fmtPct(r[key], 0)}</span>
const rulesetLabel = (rules, rs) => rules.labels[rs] || rs
// کلید مقایسه نام شعبه، مثل bkey بک‌اند («هیبریدی مازندران» = «هیبرید مازندران»)
const bkey = (b) => String(b || '').replace(/^هیبریدی(?= )/, 'هیبرید').replace(/\s+/g, ' ').trim()

function download(blob, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

/** ارسال فایل xlsx به سرور (بدنه درخواست = خود فایل) */
async function uploadXlsx(month, kind, file, branch) {
  const b = branch ? `&branch=${encodeURIComponent(branch)}` : ''
  return fetchJson(`/api/commission/import?month=${encodeURIComponent(month)}&kind=${kind}${b}`, { method: 'POST', body: file })
}

function UploadButton({ label, onFile }) {
  const ref = useRef(null)
  return (
    <>
      <button className="btn ghost sm" onClick={() => ref.current?.click()}>{label}</button>
      <input ref={ref} type="file" accept=".xlsx" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onFile(f) }} />
    </>
  )
}

// ---------------------------------------------------------------- تحقق تارگت تا روز کاری
const reportCols = (first) => [
  first,
  { key: 'req_net', label: 'ریال خالص درخواست', type: 'money', hint: 'قابل پرداخت − ارزش افزوده درخواست‌ها' },
  { key: 'gross', label: 'ریال ناخالص فاکتور', type: 'money', hint: 'جمع قبل تخفیف فاکتورهای فروش؛ برگشتی‌ها کسر شده‌اند' },
  { key: 'xnet', label: 'ریال خالص فاکتور', type: 'money', hint: 'قابل پرداخت − ارزش افزوده؛ برگشتی‌ها کسر شده‌اند' },
  { key: 'qty', label: 'فروش تعدادی فاکتور', type: 'int' },
  { key: 'customers', label: 'مشتری', type: 'int', hint: 'مشتریانی که جمع تعداد خریدشان مثبت است' },
]

/** شعبه پیش‌فرض فایل تارگت از روی نام فایل (طولانی‌ترین نام شعبه‌ای که بدون «هیبرید» در نام فایل آمده) */
const guessBranch = (file, branches) => {
  const n = file.name.replace(/ي/g, 'ی').replace(/ك/g, 'ک')
  const hits = branches.filter((b) => n.includes(b.replace(/^هیبریدی? /, '')))
  return hits.sort((x, y) => y.length - x.length)[0] || ''
}

function TargetUploads({ data, onSaved, setErr }) {
  const branches = [...new Set([...data.visitors.map((v) => v.branch.replace(/^هیبریدی /, 'هیبرید ').trim()), ...data.branches.map((b) => b.branch)])].sort()
  const [branch, setBranch] = useState('')
  const [msg, setMsg] = useState(null)
  const upVisitors = async (f) => {
    const b = branch || guessBranch(f, branches)
    if (!b) { setErr(`شعبه فایل «${f.name}» از روی نامش معلوم نشد؛ اول شعبه را انتخاب کنید.`); return }
    try { onSaved(await uploadXlsx(data.month, 'targets', f, b)); setMsg(`فایل «${f.name}» برای ${b} خوانده شد.`) } catch (e) { setErr(e.message) }
  }
  const upBranches = async (f) => {
    try { onSaved(await uploadXlsx(data.month, 'branch_targets', f)); setMsg(`فایل «${f.name}» (تارگت شعبه‌ها) خوانده شد.`) } catch (e) { setErr(e.message) }
  }
  const notes = Object.entries(data.import_notes || {})
  return (
    <>
      <div className="report-tools">
        <label className="unit-select">
          <span className="ms-label">شعبه فایل ویزیتورها</span>
          <select value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="">از روی نام فایل</option>
            {branches.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <UploadButton label="بارگذاری تارگت ویزیتورهای یک شعبه" onFile={upVisitors} />
        <UploadButton label="بارگذاری «تارگت ناخالص» شعبه‌ها" onFile={upBranches} />
        {msg && <span className="muted small">{msg}</span>}
      </div>
      {notes.length > 0 && (
        <details className="alert-more">
          <summary>نتیجه آخرین بارگذاری‌ها ({faDigits(notes.length)} فایل)</summary>
          <div className="alerts">
            {notes.map(([b, n]) => {
              const toman = n.rial_heads?.some((h) => h.includes('تومان'))
              const bad = n.missing?.length || n.unmapped?.length || toman
              return (
                <div key={b} className={`alert ${bad ? 'warn' : ''}`}><span className="alert-icon" aria-hidden>{bad ? '!' : 'i'}</span><div>
                  <b>{b === '_branches' ? 'تارگت ناخالص شعبه‌ها' : b}</b>: {faDigits(n.matched)} ردیف خوانده شد.
                  {n.missing?.length > 0 && <> وصل‌نشده به ویزیتورهای فهرست: {n.missing.map((m) => m.name).join('، ')}.</>}
                  {n.unmapped?.length > 0 && <> ستون‌های ناشناخته (خوانده نشد): {n.unmapped.join('، ')}.</>}
                  {toman && <> سرستون تارگت «{n.rial_heads.join('، ')}» است ولی عددها به ریال خوانده شدند.</>}
                </div></div>
              )
            })}
          </div>
        </details>
      )}
    </>
  )
}

function Achievement({ data, unit, onSaved, setErr }) {
  const [sel, setSel] = useState(null)
  const [selB, setSelB] = useState(null)
  const cur = data.visitors.find((v) => v.id === sel)
  const curB = data.branches.find((b) => b.branch === selB)
  // جدول شعبه فقط تارگت کل شعبه (فایل «تارگت ناخالص») را دارد؛ خالص درخواست در محاسبه نقشی ندارد
  const bcols = [...reportCols({ key: 'branch', label: 'شعبه', sticky: true }).filter((c) => c.key !== 'req_net'),
    { key: 'target_rial', label: 'تارگت شعبه (فایل ناخالص)', type: 'money' },
    { key: 'target_day', label: 'تارگت شعبه تا روز', type: 'money', hint: 'تارگت ماه ÷ کل روز کاری × روز کاری سپری‌شده' },
    { key: 'ach', label: 'تحقق (تارگت شعبه)', type: 'pct', render: achPill('ach'), hint: 'ریال ناخالص فاکتور ÷ تارگت شعبه تا روز' }]
  const vcols = [...reportCols({ key: 'name', label: 'ویزیتور', sticky: true }),
    { key: 'target_rial', label: 'تارگت ماه', type: 'money' },
    { key: 'target_day', label: 'تارگت تا روز', type: 'money', hint: 'تارگت ماه ÷ کل روز کاری × روز کاری سپری‌شده' },
    { key: 'ach', label: 'تحقق تارگت', type: 'pct', render: achPill('ach'), hint: 'ریال ناخالص فاکتور ÷ تارگت تا روز' }]
  vcols.splice(1, 0, { key: 'branch', label: 'شعبه' }, { key: 'type_label', label: 'نوع' })
  const gcols = reportCols({ key: 'group', label: 'گروه کالا', sticky: true })
  const qtyTable = (groups) => (
    <div className="table-scroll"><table>
      <thead><tr><th>گروه</th><th className="num">تارگت تعدادی ماه</th><th className="num">تارگت تا روز</th><th className="num">فروش تعدادی</th><th className="num">تحقق تعدادی</th>
</tr></thead>
      <tbody>{groups.filter((g) => g.target).map((g) => (
        <tr key={g.key}><td>{g.key}</td><td className="num">{fmtInt(g.target)}</td><td className="num">{fmtInt(g.target_day)}</td><td className="num">{fmtInt(g.qty)}</td>
          <td className="num"><span className={`pill ${achClass(g.ach_day)}`}>{fmtPct(g.ach_day, 0)}</span></td></tr>
      ))}</tbody>
    </table></div>
  )
  return (
    <>
      <TargetUploads data={data} onSaved={onSaved} setErr={setErr} />
      <div className="muted small" style={{ margin: '8px 0' }}>
        روز کاری: {faDigits(data.wd_elapsed)} از {faDigits(data.wd_total)} (همه روزهای ماه به‌جز جمعه{data.month === data.current ? `، تا امروز ${faDigits(data.today)} با خود امروز` : ''}).
        {' '}تارگت تا روز = تارگت ماه ÷ {faDigits(data.wd_total)} × {faDigits(data.wd_elapsed)}؛ تحقق = ریال ناخالص فاکتور ÷ تارگت تا روز (مثل فایل «عملکرد و تحقق تارگت فروشنده»).
      </div>
      <h4>شعبه‌ها</h4>
      <DataTable rows={data.branches.map((b) => ({ ...b, key: b.branch }))} columns={bcols} unit={unit} pageSize={30} search={false}
        exportName={`achievement-branches-${data.month.replace('/', '-')}`} defaultSort={{ key: 'gross', dir: 'desc' }}
        onRowClick={(r) => setSelB(r.branch === selB ? null : r.branch)} />
      {curB && (
        <div className="inactive-hist">
          <div className="report-tools"><b>{curB.branch} — تحقق گروه‌ها تا روز کاری</b>
            <button className="btn ghost sm" onClick={() => setSelB(null)}>بستن</button></div>
          <div className="muted small">تارگت تعدادی = جمع تارگت تعدادی ویزیتورهای این شعبه در «ثبت تارگت».</div>
          {curB.groups.length ? qtyTable(curB.groups) : <div className="muted small">برای ویزیتورهای این شعبه تارگت تعدادی ثبت نشده است.</div>}
        </div>
      )}
      <h4>ویزیتورها</h4>
      <DataTable rows={data.visitors.map((r) => ({ ...r, key: r.id }))} columns={vcols} unit={unit} pageSize={25}
        exportName={`achievement-visitors-${data.month.replace('/', '-')}`} defaultSort={{ key: 'gross', dir: 'desc' }}
        onRowClick={(r) => setSel(r.id === sel ? null : r.id)} />
      {cur && (
        <div className="inactive-hist">
          <div className="report-tools">
            <b>{cur.name} — {cur.branch}</b>
            <span className="muted small">تحقق ریالی تا روز {fmtPct(cur.ach, 1)}</span>
            <button className="btn ghost sm" onClick={() => setSel(null)}>بستن</button>
          </div>
          {cur.groups.some((g) => g.target) ? qtyTable(cur.groups) : <div className="muted small">تارگت تعدادی ثبت نشده است.</div>}
          <h4>به تفکیک گروه کالا − برند</h4>
          <DataTable rows={cur.groups2.map((g) => ({ ...g, key: g.group }))} columns={gcols} unit={unit} pageSize={50}
            search={false} exportName={`achievement-groups-${cur.code || cur.name}`} />
        </div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- گروه‌های کالا
// جدول گروه‌های کالا: تارگت تعدادی، فروش، تحقق و نرخ تکمیلی هر گروه
function GroupTable({ v, rules, unit }) {
  const E = rules.employed
  const shown = v.groups.filter((g) => g.target || g.qty)
  return (
      <div className="table-scroll">
        <table>
          <thead><tr>
            <th>گروه کالا</th><th className="num">نرخ تکمیلی</th><th className="num">تارگت تعدادی</th><th className="num">فروش تعدادی</th>
            <th className="num">تحقق</th>
            <th className="num">فروش خالص <span className="th-unit">({UNITS[unit].label})</span></th><th>وضعیت</th>
          </tr></thead>
          <tbody>
            {shown.map((g) => {
              const def = rules.groups.find((x) => x.key === g.key)
              const hit = isNum(g.ach) && g.ach >= E.group_min
              return (
                <tr key={g.key} className={hit ? 'active-row' : ''}>
                  <td>{g.key}{def?.alt && <span className="tag">جایگزین</span>}{def?.extra && <span className="tag">خارج از سقف</span>}</td>
                  <td className="num">{fmtPct(def?.rate, 2)}</td>
                  <td className="num">{fmtInt(g.target)}</td>
                  <td className="num">{fmtInt(g.qty)}</td>
                  <td className="num">{g.target ? <span className={`pill ${hit ? 'st-green' : isNum(g.ach) && g.ach >= 0.6 ? 'st-yellow' : 'st-red'}`}>{fmtPct(g.ach, 0)}</span> : '—'}</td>
                  <td className="num">{fmtMoney(g.net, unit)}</td>
                  <td>{def?.info ? <span className="muted">فقط نمایش</span> : !g.target ? <span className="muted">بدون تارگت</span> : hit ? 'محقق' : 'محقق نشده'}</td>
                </tr>
              )
            })}
            {!shown.length && <tr><td colSpan={8} className="muted center">فروش یا تارگتی در گروه‌های پورسانت تکمیلی ندارد</td></tr>}
          </tbody>
        </table>
      </div>
  )
}

// ---------------------------------------------------------------- جدول پورسانت (مثل فایل پورسانت ماهانه)
// فقط ستون‌هایی که از داده کارآمد ساخته می‌شوند؛ حقوق و پاداش نمی‌آیند (تصمیم کاربر).
// مانده بدهی و چک برگشتی از بخش مالی داشبورد یکپارچه (همان اعداد پرونده ویزیتور)؛ اتصال با seller_key.
// مبالغ این تب همیشه کامل به تومان است (جدول، جمع، توضیح و خروجی اکسل)، مستقل از واحد انتخاب‌شده در داشبورد.
const VISITOR_FINANCE_URL = '/api/v1/finance/sales-network/visitor-finance'

/** مانده بدهی و چک برگشتی هر ویزیتور از بک‌اند مالی؛ در داشبورد فروش تنها (بدون بخش مالی) خالی می‌ماند. */
function useVisitorFinance() {
  const [state, setState] = useState({ map: null, loading: true, error: null, from: '' })
  useEffect(() => {
    let alive = true
    fetchJson(VISITOR_FINANCE_URL)
      .then((d) => alive && setState({ map: new Map(d.visitors.map((v) => [v.seller_key, v])), loading: false, error: null, from: d.returned_from_jalali }))
      .catch((e) => alive && setState({ map: null, loading: false, error: e.message, from: '' }))
    return () => { alive = false }
  }, [])
  return state
}

function Sheet({ data }) {
  const unit = 'toman'
  const fin = useVisitorFinance()
  const [who, setWho] = useState('visitors')
  const [f, setF] = useState({ branch: '', supervisor: '', type: '', group: '' })
  const [sel, setSel] = useState(null)
  const [selS, setSelS] = useState(null)
  // ستون‌های مالی: ویزیتور از پرونده خودش، سرپرست = جمع ویزیتورهای همان شعبه و سرپرست
  const visitors = useMemo(() => data.visitors.map((v) => {
    const x = fin.map?.get(v.seller_key)
    return x ? { ...v, debt: x.open_account_receivable_rial, debtors: x.debtor_customer_count,
      returned: x.returned_cheque_rial, returned_n: x.returned_cheque_count } : v
  }), [data.visitors, fin.map])
  const supervisors = useMemo(() => data.supervisors.map((s) => {
    const team = visitors.filter((v) => v.supervisor === s.name && bkey(v.branch) === bkey(s.branch) && isNum(v.debt))
    if (!team.length) return s
    const add = (k) => team.reduce((a, v) => a + (v[k] || 0), 0)
    return { ...s, debt: add('debt'), returned: add('returned'), returned_n: add('returned_n') }
  }), [data.supervisors, visitors])
  const uniq = (k) => [...new Set(visitors.map((v) => v[k]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fa'))
  const opts = { branch: uniq('branch'), supervisor: uniq('supervisor').filter((s) => !f.branch || visitors.some((v) => v.branch === f.branch && v.supervisor === s)) }
  const vrows = visitors.filter((v) => (!f.branch || v.branch === f.branch) && (!f.supervisor || v.supervisor === f.supervisor)
    && (!f.type || v.type === f.type) && (!f.group || v.group_ab === f.group))
  const srows = supervisors.filter((s) => (!f.branch || bkey(s.branch) === bkey(f.branch)) && (!f.supervisor || s.name === f.supervisor)
    && (!f.group || s.group_ab === f.group))
  const finCols = (team) => [
    { key: 'debt', label: team ? 'مانده بدهی تیم' : 'مانده بدهی', type: 'money',
      hint: `مانده بدهی مشتریان ${team ? 'ویزیتورهای این سرپرست' : 'این ویزیتور'} از بخش مالی (همان عدد پرونده ویزیتور)` },
    { key: 'returned', label: team ? 'چک برگشتی تیم' : 'چک برگشتی', type: 'money',
      hint: `مبلغ چک‌های برگشتی تسویه‌نشده فاکتورهای ${team ? 'تیم' : 'این ویزیتور'} از بخش مالی${fin.from ? ` (سررسید از ${faDigits(fin.from)})` : ''}` },
    { key: 'returned_n', label: 'تعداد چک برگشتی', type: 'int' },
  ]
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value, ...(k === 'branch' ? { supervisor: '' } : {}) }); setSel(null); setSelS(null) }
  const vcols = [
    // شعبه و نام فروشنده هنگام اسکرول افقی ثابت می‌مانند
    { key: 'branch', label: 'نام شعبه', sticky: true }, { key: 'name', label: 'نام فروشنده', sticky: true },
    { key: 'code', label: 'کد فروشنده' }, { key: 'supervisor', label: 'نام سرپرست' }, { key: 'type_label', label: 'نوع' },
    { key: 'group_ab', label: 'گروه' },
    { key: 'target_rial', label: 'تارگت', type: 'money' },
    { key: 'ach', label: 'تحقق', type: 'pct', render: achPill('ach'), hint: 'فروش ناخالص ÷ تارگت (ماه جاری: تارگت تا روز)' },
    { key: 'gross', label: 'فروش ناخالص', type: 'money', hint: 'جمع قبل تخفیف فاکتورها؛ برگشتی‌ها کسر شده‌اند' },
    { key: 'net', label: 'فروش خالص', type: 'money', hint: 'پس از کسر برگشتی و همه تخفیفات، بدون ارزش افزوده' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی', type: 'money', hint: 'فروش خالص به‌اضافه تخفیف نقدی (برگشتی‌ها کسر شده)' },
    ...(data.pace ? [{ key: 'forecast', label: 'پیش‌بینی ماه', type: 'money', hint: 'فروش خالص ÷ روز کاری سپری‌شده × کل روز کاری ماه' }] : []),
    { key: 'wholesale_n', label: 'تعداد فاکتور بالای ۷۰۰', type: 'int', hint: 'فاکتورهای فروشی که مبلغ ناخالص (جمع قبل تخفیف) هر کدام بیش از ۷۰۰ میلیون تومان است' },
    { key: 'wholesale_gross', label: 'مبلغ عمده‌فروشی', type: 'money', hint: 'جمع مبلغ ناخالص همان فاکتورهای بالای ۷۰۰ میلیون تومان' },
    pct2('wholesale_share', 'درصد عمده‌فروشی', 'مبلغ عمده‌فروشی ÷ مبلغ ناخالص همه فاکتورهای فروش (بدون برگشتی)'),
    { key: 'customers', label: 'تعداد مشتری', type: 'int', hint: 'مشتریانی که جمع تعداد خریدشان مثبت است' },
    // فاکتورهای فروش دارای تخفیف مدیریتی (از کارآمد: انواع تخفیفی که نامشان «مدیریت» دارد)
    { key: 'mgmt_n', label: 'تعداد فاکتور با تخفیف مدیریتی', type: 'int', hint: 'فاکتورهای فروشی که تخفیف مدیریتی دارند' },
    { key: 'mgmt_inv_gross', label: 'مبلغ فاکتورهای با تخفیف مدیریتی', type: 'money', hint: 'جمع مبلغ ناخالص (قبل تخفیف) همان فاکتورها' },
    pct2('mgmt_inv_share', 'سهم از فروش ناخالص', 'مبلغ فاکتورهای با تخفیف مدیریتی ÷ مبلغ ناخالص همه فاکتورهای فروش (بدون برگشتی)'),
    { key: 'mgmt_disc', label: 'مبلغ تخفیف مدیریتی', type: 'money' },
    pct2('mgmt_rate', 'نرخ تخفیف مدیریتی', 'مبلغ تخفیف مدیریتی ÷ مبلغ ناخالص همان فاکتورها'),
    { key: 'status', label: 'وضعیت' },
    pct2('rate', 'درصد پورسانت', 'پورسانتی: نرخ سطح (با فروش ناخالص)؛ استخدامی: نرخ نهایی (پایه + تکمیلی)'),
    pct2('eff_rate', 'نرخ مؤثر', 'پورسانت محاسبه‌شده ÷ فروش خالص؛ با فاکتورهای ویژه (عمده / تخفیف مدیریتی) که نرخ پایه می‌گیرند، کمتر از درصد پورسانت می‌شود'),
    { key: 'commission', label: 'پورسانت محاسبه‌شده', type: 'money' },
    { key: 'reserve', label: 'ذخیره پورسانت', type: 'money', hint: `پورسانتی ${fmtPct(data.rules.commission.reserve, 0)}، استخدامی ${fmtPct(data.rules.employed.reserve, 0)}` },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره' },
    ...finCols(false),
  ]
  const scols = [
    { key: 'branch', label: 'نام شعبه', sticky: true }, { key: 'name', label: 'نام سرپرست', sticky: true }, { key: 'group_ab', label: 'گروه' },
    { key: 'visitors', label: 'ویزیتور', type: 'int' },
    { key: 'gross', label: 'فروش ناخالص تیم', type: 'money' }, { key: 'net', label: 'فروش خالص تیم', type: 'money' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی تیم', type: 'money' },
    ...(data.pace ? [{ key: 'forecast', label: 'پیش‌بینی ماه', type: 'money' }] : []),
    { key: 't1', label: 'تارگت اول', type: 'money' }, { key: 't2', label: 'تارگت دوم', type: 'money' },
    { key: 'ach_t1', label: 'تحقق تارگت اول', type: 'pct', render: achPill('ach_t1'), hint: 'فروش ناخالص تیم ÷ تارگت اول' },
    { key: 'status', label: 'وضعیت' },
    pct2('eff_rate', 'درصد پورسانت', 'پورسانت محاسبه‌شده ÷ فروش خالص تیم'),
    { key: 'commission', label: 'پورسانت محاسبه‌شده', type: 'money', hint: 'پلکانی روی فروش خالص تیم طبق جدول سرپرستی همان ماه؛ اگر فروش ناخالص تیم به تارگت اول نرسد صفر' },
    ...(data.pace ? [{ key: 'forecast_commission', label: 'پورسانت با پیش‌بینی', type: 'money' }] : []),
    { key: 'reserve', label: 'ذخیره پورسانت', type: 'money', hint: `${fmtPct(data.rules.supervisor.reserve, 0)} پورسانت` },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره' },
    ...finCols(true),
  ]
  const sum = (rows, k) => rows.reduce((s, r) => s + (r[k] || 0), 0)
  const ratio = (a, b) => (b > 0 ? a / b : null)
  // ردیف «جمع کل»: مبالغ و تعدادها جمع می‌شوند؛ درصدها از جمع‌ها دوباره حساب می‌شوند (نه جمع درصدها)
  const vTotals = (rs) => {
    const t = Object.fromEntries(vcols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, sum(rs, c.key)]))
    return { ...t, branch: 'جمع کل', key: '__total',
      eff_rate: ratio(t.commission, sum(rs, 'base')), wholesale_share: ratio(t.wholesale_gross, sum(rs, 'sales_gross')),
      mgmt_inv_share: ratio(t.mgmt_inv_gross, sum(rs, 'sales_gross')), mgmt_rate: ratio(t.mgmt_disc, t.mgmt_inv_gross) }
  }
  const sTotals = (rs) => {
    const t = Object.fromEntries(scols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, sum(rs, c.key)]))
    return { ...t, t1: null, t2: null, branch: 'جمع کل', key: '__total', eff_rate: ratio(t.commission, sum(rs, 'base')) }
  }
  const tag = data.month.replace('/', '-')
  const select = (k, label, list) => (
    <label className="unit-select"><span className="ms-label">{label}</span>
      <select value={f[k]} onChange={set(k)}>
        <option value="">همه</option>
        {list.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </label>
  )
  const rows = who === 'visitors' ? vrows : srows
  return (
    <>
      <div className="report-tools">
        <Tabs value={who} onChange={(w) => { setWho(w); setSel(null); setSelS(null) }} tabs={[
          { value: 'visitors', label: `فروشندگان (${fmtInt(vrows.length)})` }, { value: 'supervisors', label: `سرپرستان (${fmtInt(srows.length)})` }]} />
        <span className="muted small">
          پورسانت {money(sum(rows, 'commission'), unit)}، ذخیره {money(sum(rows, 'reserve'), unit)}، قابل پرداخت {money(sum(rows, 'payable'), unit)}
        </span>
        {fin.loading && <span className="muted small">در حال خواندن مانده بدهی و چک برگشتی از بخش مالی…</span>}
        {fin.error && <span className="muted small">مانده بدهی و چک برگشتی از بخش مالی خوانده نشد: {fin.error}</span>}
      </div>
      <div className="filter-bar">
        {select('branch', 'شعبه', opts.branch.map((b) => [b, b]))}
        {select('supervisor', 'سرپرست', opts.supervisor.map((s) => [s, s]))}
        {who === 'visitors' && select('type', 'نوع', Object.entries(data.types))}
        {select('group', 'گروه', [['A', 'گروه A'], ['B', 'گروه B']])}
        <span className="muted small">روی هر ردیف کلیک کنید تا توضیح محاسبه پورسانت زیر همان ردیف باز شود.</span>
      </div>
      {who === 'visitors' ? (
        <DataTable rows={vrows.map((r) => ({ ...r, key: r.id }))} columns={vcols} unit={unit} pageSize={100}
          exportName={`commission-visitors-${tag}`} defaultSort={{ key: 'branch', dir: 'asc' }}
          onRowClick={(r) => setSel(r.key === sel ? null : r.key)} expandedKey={sel}
          renderExpanded={(r) => <VisitorCalc v={r} data={data} unit={unit} />} totals={vTotals} />
      ) : (
        <DataTable rows={srows.map((s) => ({ ...s, key: s.id }))} columns={scols} unit={unit} pageSize={50}
          search={false} exportName={`commission-supervisors-${tag}`} defaultSort={{ key: 'branch', dir: 'asc' }}
          onRowClick={(r) => setSelS(r.key === selS ? null : r.key)} expandedKey={selS}
          renderExpanded={(r) => <SupervisorCalc s={r} data={data} unit={unit} />} totals={sTotals} />
      )}
    </>
  )
}

// ---------------------------------------------------------------- توضیح ساده محاسبه (زیر ردیف جدول پورسانت)
const fa = (n) => faDigits(n)
const money = (v, unit) => `${fmtMoney(v, unit)} ${UNITS[unit].label}`
// متن بازه هر سطح (حدود جدول‌ها به میلیون ریال‌اند)
const tierRange = (tiers, i, unit) => {
  const lo = i ? tiers[i - 1][0] : null, up = tiers[i][0]
  return lo == null ? `کمتر از ${money(up * 1e6, unit)}` : up == null ? `بیش از ${money(lo * 1e6, unit)}` : `${money(lo * 1e6, unit)} تا ${money(up * 1e6, unit)}`
}

function VisitorCalc({ v, data, unit }) {
  const r = data.rules
  const head = <p><b>{v.name}</b> — {v.type_label}، {v.branch}. محاسبه طبق {r.title}.</p>
  const cashBase = r.comm_base === 'net_cash'
  const B = cashBase ? 'فروش خالص + درصد نقدی' : 'فروش خالص'  // نام مبنای پورسانت این ماه
  const netLine = (
    <li>فروش خالص {monthName(data.month)}: {money(v.net, unit)} (فروش {money(v.sales_net, unit)} منهای برگشتی {money(v.returns_net, unit)}). فروش خالص یعنی بعد از کسر برگشتی و همه تخفیف‌ها، بدون ارزش افزوده.
      {cashBase && <> تخفیف نقدی به آن برمی‌گردد: <b>فروش خالص + درصد نقدی = {money(v.net_cash, unit)}</b> ← مبنای پورسانت این ماه.</>}
    </li>)
  // «فاکتور ویژه»: عمده و/یا با تخفیف مدیریتی (طبق قاعده همان ماه) که نرخ ثابت پایه می‌گیرد، نه نرخ سطح
  const spRate = v.type === 'commission' ? r.commission.wholesale_rate : r.employed.wholesale_rate
  const kinds = [(r.special || []).includes('wholesale') && 'عمده باشد (مبلغ ناخالص فاکتور بیش از ۷۰۰ میلیون تومان)',
    (r.special || []).includes('mgmt') && 'تخفیف مدیریتی داشته باشد'].filter(Boolean).join(' یا ')
  const rateText = v.type === 'commission' ? `نرخ سطح (${fmtPct(v.rate, 2)})` : `نرخ نهایی (${fmtPct(v.rate, 2)})`
  const wsLine = v.wholesale_n > 0 && (
    <li>{fa(v.wholesale_n)} فاکتور عمده (مبلغ ناخالص بالای ۷۰۰ میلیون تومان) داشته: {money(v.wholesale_gross, unit)} ناخالص، {fmtPct(v.wholesale_share, 1)} فروش ناخالص.</li>)
  const mgLine = v.mgmt_n > 0 && (
    <li>{fa(v.mgmt_n)} فاکتور با تخفیف مدیریتی داشته: مبلغ ناخالص {money(v.mgmt_inv_gross, unit)} ({fmtPct(v.mgmt_inv_share, 1)} فروش ناخالص)،
      {' '}تخفیف مدیریتی {money(v.mgmt_disc, unit)} یعنی نرخ {fmtPct(v.mgmt_rate, 2)} روی همان فاکتورها.</li>)
  const specialRule = isNum(spRate) && (
    <li><b>قاعده فاکتورهای ویژه این ماه:</b> هر فاکتوری که {kinds}، پورسانتش با نرخ پایه <b>{fmtPct(spRate, 0)}</b> حساب می‌شود، نه {rateText}.
      {' '}بقیه فروش با {rateText} حساب می‌شود.
      {v.special_n > 0 ? (
        <>
          {' '}این فرد <b>{fa(v.special_n)} فاکتور ویژه</b> داشته ({B} {money(v.special_base, unit)}):
          <div className="table-scroll"><table>
            <thead><tr><th>شماره فاکتور</th><th>تاریخ</th><th>مشتری</th><th>دلیل</th>
              <th className="num">مبلغ ناخالص</th><th className="num">تخفیف مدیریتی</th><th className="num">فروش خالص</th>{cashBase && <th className="num">خالص + نقدی</th>}</tr></thead>
            <tbody>{v.special_invoices.map((x, i) => (
              <tr key={i}><td>{fa(x.inv_no)}</td><td>{fa(x.date)}</td><td>{x.customer}</td>
                <td>{[x.wholesale && 'عمده', x.mgmt_inv && 'تخفیف مدیریتی'].filter(Boolean).join(' و ')}</td>
                <td className="num">{money(x.gross, unit)}</td><td className="num">{x.mgmt ? `${money(x.mgmt, unit)} (${fmtPct(x.mgmt / x.gross, 1)})` : '—'}</td>
                <td className="num">{money(x.net, unit)}</td>{cashBase && <td className="num">{money(x.net_cash, unit)}</td>}</tr>))}
            </tbody>
          </table></div>
        </>
      ) : ' این فرد فاکتور ویژه‌ای نداشته؛ کل فروش با همان نرخ حساب می‌شود.'}
    </li>)
  // فرمول پورسانت: با فاکتور ویژه دو بخش است، بدون آن یک بخش
  const commLine = isNum(spRate) && v.special_n > 0 ? (
    <li>پورسانت دو بخش دارد:
      <ul>
        <li>بقیه فروش = {B} کل {money(v.base, unit)} − {B} فاکتورهای ویژه {money(v.special_base, unit)} = {money(v.rest_net, unit)}؛
          {' '}پورسانتش: {money(v.rest_net, unit)} × {fmtPct(v.rate, 2)} = {money(v.rest_commission, unit)}</li>
        <li>فاکتورهای ویژه: {money(v.special_base, unit)} × {fmtPct(spRate, 0)} = {money(v.special_commission, unit)}</li>
        <li>جمع پورسانت: {money(v.rest_commission, unit)} + {money(v.special_commission, unit)} = <b>{money(v.commission, unit)}</b>
          {' '}(نرخ مؤثر روی کل {B}: {fmtPct(v.eff_rate, 2)}){v.rest_commission + v.special_commission < 0 ? '؛ منفی بود و صفر شد' : ''}.</li>
      </ul>
    </li>
  ) : (
    <li>پورسانت = {B} {money(v.base, unit)} × {fmtPct(v.rate, 2)} = <b>{money(v.commission, unit)}</b>{v.base < 0 ? ' (منفی: پورسانت صفر)' : ''}.</li>
  )
  if (v.type === 'commission') {
    const tiers = r.rulesets[v.ruleset].visitor
    const res = r.commission.reserve
    return (
      <div>{head}
        <ol className="calc-steps">
          <li>شعبه {v.branch} در «{rulesetLabel(r, v.ruleset)}» است. سطح ویزیتور پورسانتی با <b>فروش ناخالص</b> ماه تعیین می‌شود و نرخ همان سطح روی <b>فروش خالص</b> اعمال می‌شود.</li>
          <li>فروش ناخالص {monthName(data.month)} (جمع قبل از تخفیف، برگشتی‌ها کسر شده): <b>{money(v.gross, unit)}</b> ← ملاک تعیین سطح.</li>
          {netLine}
          <li>جدول سطوح (بر اساس فروش ناخالص):
            <ul>{tiers.map(([, rate], i) => (
              <li key={i} className={i + 1 === v.tier ? 'hit' : ''}>سطح {fa(i + 1)}: {tierRange(tiers, i, unit)} ← {fmtPct(rate, 0)}{i + 1 === v.tier ? ' (سطح این فرد)' : ''}</li>))}
            </ul>
          </li>
          {wsLine}
          {mgLine}
          {specialRule}
          {commLine}
          <li>{fmtPct(res, 0)} پورسانت ذخیره می‌شود ({money(v.reserve, unit)}) و هر ۶ ماه تسویه می‌شود؛ قابل پرداخت این ماه: <b>{money(v.payable, unit)}</b>.</li>
          {isNum(v.next_tier) && <li className="muted">برای رسیدن به سطح بعد ({fmtPct(tiers[v.tier][1], 0)}) {money(v.next_tier, unit)} فروش ناخالص بیشتر لازم بود.</li>}
        </ol>
      </div>
    )
  }
  const E = r.employed
  const baseIdx = isNum(v.ach) ? E.base.findIndex(([u]) => u == null || v.ach < u) : -1
  const bands = ['کمتر از ۷۰٪', '۷۰٪ تا ۹۵٪', '۹۵٪ و بیشتر']
  return (
    <div>{head}
      <ol className="calc-steps">
        {netLine}
        <li>شرط کف: اگر {B} کمتر از {money(E.floor, unit)} باشد پورسانتی تعلق نمی‌گیرد.
          {' '}{B} این فرد {money(v.base, unit)} است؛ {v.base < E.floor ? <b>کمتر است؛ پورسانت صفر.</b> : 'از کف بیشتر است.'}</li>
        {!v.target_rial ? <li><b>تارگت ریالی برای این فرد ثبت نشده؛ پورسانت محاسبه نمی‌شود.</b></li> : (
          <>
            <li>پورسانت پایه از درصد تحقق تارگت ریالی: فروش ناخالص {money(v.gross, unit)} ÷ تارگت {money(v.target_day, unit)} = <b>{fmtPct(v.ach, 1)}</b>
              <ul>{E.base.map(([, rate], i) => <li key={i} className={i === baseIdx ? 'hit' : ''}>تحقق {bands[i]} ← {fmtPct(rate, 1)}{i === baseIdx ? ' (این فرد)' : ''}</li>)}</ul>
            </li>
            <li>پورسانت تکمیلی: هر گروه کالایی که دست‌کم {fmtPct(E.group_min, 0)} تارگت تعدادی‌اش محقق شود، نرخ خودش را اضافه می‌کند (جمعاً حداکثر {fmtPct(E.group_cap, 0)}؛ رزتی خارج از این سقف).
              {' '}این فرد در {fa(v.groups_hit || 0)} گروه به حد لازم رسیده: تکمیلی {fmtPct(v.bonus_rate, 2)}{v.extra_rate > 0 ? ` + رزتی ${fmtPct(v.extra_rate, 2)}` : ''}.
              <GroupTable v={v} rules={r} unit={unit} />
            </li>
            <li>نرخ نهایی = پایه {fmtPct(v.base_rate, 2)} + تکمیلی {fmtPct(v.bonus_rate, 2)} (سقف {fmtPct(E.max_rate, 0)}){v.extra_rate > 0 ? ` + رزتی ${fmtPct(v.extra_rate, 2)}` : ''} = <b>{fmtPct(v.rate, 2)}</b>.</li>
            {wsLine}
            {mgLine}
            {v.base >= E.floor && specialRule}
            {v.base >= E.floor && commLine}
            <li>{fmtPct(E.reserve, 0)} پورسانت ذخیره می‌شود ({money(v.reserve, unit)})؛ قابل پرداخت این ماه: <b>{money(v.payable, unit)}</b>.</li>
          </>
        )}
      </ol>
    </div>
  )
}

function SupervisorCalc({ s, data, unit }) {
  const r = data.rules
  const rule = r.rulesets[s.ruleset]?.supervisor
  const [r1, r2, r3] = r.sup_rates
  const team = data.visitors.filter((v) => bkey(v.branch) === bkey(s.branch) && v.supervisor === s.name)
  if (!rule) return <p>برای {rulesetLabel(r, s.ruleset)} در {r.title} جدول سرپرستی تعریف نشده است.</p>
  const B = r.comm_base === 'net_cash' ? 'فروش خالص + درصد نقدی' : 'فروش خالص'
  const b = Math.max(s.base, 0)
  const p1 = Math.min(b, s.t1) * r1, p2 = Math.max(Math.min(b, s.t2) - s.t1, 0) * r2, p3 = Math.max(b - s.t2, 0) * r3
  return (
    <div>
      <p><b>{s.name}</b> — سرپرست {s.branch}، «{rulesetLabel(r, s.ruleset)}». محاسبه طبق {r.title}.</p>
      <ol className="calc-steps">
        <li>تیم: {fa(team.length)} ویزیتور{team.length > 0 && <span className="muted"> ({team.map((v) => v.name).join('، ')})</span>}.
          {' '}فروش ناخالص تیم <b>{money(s.gross, unit)}</b> (ملاک رسیدن به تارگت) و {B} تیم <b>{money(s.base, unit)}</b> (مبنای پورسانت).</li>
        <li>رسیدن به تارگت با فروش ناخالص سنجیده می‌شود. پورسانت پلکانی روی {B} است: تا تارگت اول ({money(s.t1, unit)}) {fmtPct(r1, 2)}، از تارگت اول تا دوم ({money(s.t2, unit)}) {fmtPct(r2, 0)}، بیش از تارگت دوم {fmtPct(r3, 1)}. اگر فروش ناخالص تیم به تارگت اول نرسد پورسانتی تعلق نمی‌گیرد.</li>
        {s.gross < s.t1
          ? <li><b>فروش ناخالص تیم {fmtPct(s.ach_t1, 0)} تارگت اول است و به آن نرسیده؛ پورسانت صفر.</b> {money(s.t1 - s.gross, unit)} تا تارگت اول مانده بود.</li>
          : <li>فروش ناخالص تیم به {s.gross >= s.t2 ? 'تارگت دوم' : 'تارگت اول'} رسیده ({fmtPct(s.ach_t1, 0)} تارگت اول). پورسانت روی {B} = {money(Math.min(b, s.t1), unit)} × {fmtPct(r1, 2)} ({money(p1, unit)})
            {p2 > 0 && <> + {money(Math.min(b, s.t2) - s.t1, unit)} × {fmtPct(r2, 0)} ({money(p2, unit)})</>}
            {p3 > 0 && <> + {money(b - s.t2, unit)} × {fmtPct(r3, 1)} ({money(p3, unit)})</>} = <b>{money(s.commission, unit)}</b>.</li>}
        <li>{fmtPct(r.supervisor.reserve, 0)} پورسانت ذخیره می‌شود ({money(s.reserve, unit)})؛ قابل پرداخت این ماه: <b>{money(s.payable, unit)}</b>.</li>
      </ol>
    </div>
  )
}

// ---------------------------------------------------------------- ثبت تارگت
function Targets({ data, onSaved, setErr }) {
  const groups = data.rules.groups.filter((g) => !g.info).map((g) => g.key)
  const [type, setType] = useState('employed')
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState({})
  useEffect(() => { setDraft({}) }, [data.month])
  const val = (id) => draft[id] ?? data.targets[id] ?? { groups: {} }
  const set = (id, patch) => setDraft((d) => {
    const cur = d[id] ?? data.targets[id] ?? { groups: {} }
    return { ...d, [id]: { ...cur, ...patch, groups: { ...(cur.groups || {}), ...(patch.groups || {}) } } }
  })
  const rows = data.visitors.filter((v) => (type === 'all' || v.type === type)
    && (!q || `${v.name} ${v.branch} ${v.code} ${v.supervisor}`.includes(q.trim())))
  const dirty = Object.keys(draft).length
  const save = async () => {
    try { onSaved(await sendJson('/api/commission', 'PUT', { month: data.month, targets: draft })); setDraft({}) } catch (e) { setErr(e.message) }
  }
  const template = () => {
    const headers = [{ label: 'شناسه', kind: 'text' }, { label: 'شعبه', kind: 'text' }, { label: 'سرپرست', kind: 'text' }, { label: 'کد', kind: 'text' },
      { label: 'نام', kind: 'text' }, { label: 'نوع', kind: 'text' }, { label: 'تارگت ریالی (میلیون تومان)', kind: 'dec' },
      ...groups.map((g) => ({ label: `${g} (تعداد)`, kind: 'int' }))]
    const body = data.visitors.map((v) => {
      const t = val(v.id)
      return [v.id, v.branch, v.supervisor, v.code, v.name, v.type_label, t.rial ? t.rial / TOMAN_M : '', ...groups.map((g) => t.groups?.[g] || '')]
    })
    download(buildXlsx(headers, body, `تارگت ${data.month}`), `commission-targets-${data.month.replace('/', '-')}.xlsx`)
  }
  const num = (v) => (v === '' ? null : Math.max(0, +v))
  return (
    <>
      <div className="report-tools">
        <Tabs value={type} onChange={setType} tabs={[
          { value: 'employed', label: 'استخدامی' }, { value: 'commission', label: 'پورسانتی' }, { value: 'all', label: 'همه' }]} />
        <input className="input" placeholder="جستجو…" value={q} onChange={(e) => setQ(e.target.value)} />
        <button className="btn" disabled={!dirty} onClick={save}>ذخیره{dirty ? ` (${faDigits(dirty)} ردیف)` : ''}</button>
        {dirty > 0 && <button className="btn ghost sm" onClick={() => setDraft({})}>لغو تغییرات</button>}
        <span className="spacer" />
        <button className="btn ghost sm" onClick={template}>دریافت جدول به اکسل</button>
      </div>
      <TargetUploads data={data} onSaved={onSaved} setErr={setErr} />
      <div className="muted small" style={{ marginBottom: 8 }}>
        فایل تارگت هر استان (ویزیتور، تارگت ریالی به ریال، تارگت تعدادی گروه‌ها) را بارگذاری کنید؛ ردیف‌ها با نام ویزیتور در همان شعبه وصل می‌شوند.
        در جدول زیر تارگت ریالی به میلیون تومان است؛ گروه‌ها تعدادی (عدد). پورسانت تکمیلی هر گروه فقط برای ویزیتوری حساب می‌شود که برایش تارگت آن گروه ثبت شده است؛
        برای فروشندگانی که مولهنس ندارند تارگت گروه‌های «جایگزین» را بنویسید. پورسانتی‌ها تارگت لازم ندارند و تارگت ریالی‌شان فقط برای درصد تحقق است.
      </div>
      <div className="table-scroll">
        <table className="matrix">
          <thead><tr>
            <th>ویزیتور</th><th>شعبه</th><th>نوع</th><th className="num">تارگت ریالی (میلیون تومان)</th>
            {groups.map((g) => <th key={g} className="num">{g}</th>)}
          </tr></thead>
          <tbody>
            {rows.map((v) => {
              const t = val(v.id)
              const ch = !!draft[v.id]
              return (
                <tr key={v.id}>
                  <td>{v.name}{v.code ? <span className="muted small"> ({faDigits(v.code)})</span> : null}</td>
                  <td>{v.branch}</td><td>{v.type_label}</td>
                  <td className="num"><input className={`input cell-in ${ch ? 'ov' : ''}`} type="number" min="0" step="10"
                    value={t.rial ? Math.round((t.rial / TOMAN_M) * 100) / 100 : ''}
                    onChange={(e) => set(v.id, { rial: num(e.target.value) ? num(e.target.value) * TOMAN_M : null })} /></td>
                  {groups.map((g) => (
                    <td key={g} className="num"><input className={`input cell-in ${ch ? 'ov' : ''}`} style={{ width: 80 }} type="number" min="0"
                      value={t.groups?.[g] || ''} onChange={(e) => set(v.id, { groups: { [g]: num(e.target.value) } })} /></td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- فهرست ویزیتورها
function Roster({ data, onSaved, setErr }) {
  const [draft, setDraft] = useState(null)
  useEffect(() => { setDraft(null) }, [data.month, data.updated_at])
  const list = draft ?? data.visitors.map(({ id, branch, supervisor, code, name, phone, phone_from, karamad_name, type, note }) => ({ id, branch, supervisor, code, name, phone, phone_from, karamad_name, type, note }))
  const byId = Object.fromEntries(data.visitors.map((v) => [v.id, v]))
  const setType = (id, type) => setDraft(list.map((v) => (v.id === id ? { ...v, type } : v)))
  const save = async () => {
    try { onSaved(await sendJson('/api/commission', 'PUT', { month: data.month, visitors: list })) } catch (e) { setErr(e.message) }
  }
  const upload = async (f) => { try { onSaved(await uploadXlsx(data.month, 'roster', f)) } catch (e) { setErr(e.message) } }
  const enrich = async () => { try { onSaved(await fetchJson(`/api/commission/enrich?month=${encodeURIComponent(data.month)}`, { method: 'POST' })) } catch (e) { setErr(e.message) } }
  const missing = data.visitors.filter((v) => !v.seller_key)
  const log = data.enrich_log || []
  const flag = (id, kind) => log.some((l) => l.id === id && l.kind === kind)
  const noPhone = list.filter((v) => !v.phone)
  return (
    <>
      <div className="report-tools">
        <UploadButton label="بارگذاری فایل «لیست ویزیتور و سرپرست»" onFile={upload} />
        <button className="btn ghost sm" onClick={enrich}>تکمیل تلفن و کد از کارآمد</button>
        <button className="btn" disabled={!draft} onClick={save}>ذخیره نوع ویزیتورها</button>
        {draft && <button className="btn ghost sm" onClick={() => setDraft(null)}>لغو</button>}
        <span className="muted small">
          {fmtInt(list.length)} ویزیتور ({fmtInt(list.filter((v) => v.type === 'commission').length)} پورسانتی)،
          {' '}{fmtInt(data.supervisors.length)} سرپرست. در فایل اکسل، خانه نام با هاشور آبی = پورسانتی؛ بقیه استخدامی.
          {data.roster_from && ` این ماه هنوز ذخیره نشده و فهرست ${monthName(data.roster_from)} نمایش داده می‌شود.`}
        </span>
      </div>
      {(missing.length > 0 || data.unmatched.length > 0 || log.length > 0 || data.enrich_error) && (
        <div className="alerts">
          {data.enrich_error && <div className="alert danger"><span className="alert-icon" aria-hidden>!</span><div>{data.enrich_error}</div></div>}
          {log.filter((l) => l.kind === 'mismatch' || l.kind === 'ambiguous' || l.kind === 'notfound').map((l) => (
            <div key={l.id + l.kind} className="alert warn"><span className="alert-icon" aria-hidden>!</span><div><b>{l.name}</b>: {l.text}</div></div>
          ))}
          {log.some((l) => l.kind === 'phone' || l.kind === 'code') && <div className="alert"><span className="alert-icon" aria-hidden>i</span><div>
            از کارآمد تکمیل شد: {log.filter((l) => l.kind === 'phone' || l.kind === 'code').map((l) => `${l.name} (${l.text})`).join('، ')}
          </div></div>}
          {noPhone.length > 0 && <div className="alert warn"><span className="alert-icon" aria-hidden>!</span><div>
            {fmtInt(noPhone.length)} نفر نه در فایل لیست و نه در کارآمد شماره ندارند: {noPhone.map((v) => v.name).join('، ')}
          </div></div>}
          {missing.length > 0 && <div className="alert warn"><span className="alert-icon" aria-hidden>!</span><div>
            {fmtInt(missing.length)} ویزیتور فهرست در داده کارآمد پیدا نشد (فروش صفر حساب می‌شود): {missing.map((v) => `${v.name} (${v.branch}${v.code ? `، ${faDigits(v.code)}` : ''})`).join('، ')}
          </div></div>}
          {data.unmatched.length > 0 && <div className="alert warn"><span className="alert-icon" aria-hidden>!</span><div>
            {fmtInt(data.unmatched.length)} فروشنده هیبرید در این ماه فروش دارند ولی در فهرست پورسانت نیستند: {data.unmatched.map((u) => `${u.name} (${u.branch}، ${faDigits(u.code)})`).join('، ')}
          </div></div>}
        </div>
      )}
      <div className="table-scroll">
        <table>
          <thead><tr><th>شعبه</th><th>سرپرست</th><th>کد</th><th>نام</th><th>تلفن</th><th>نام در کارآمد</th><th>نوع</th><th>در فروش کارآمد</th><th>یادداشت</th></tr></thead>
          <tbody>
            {list.map((v) => {
              const m = byId[v.id]
              return (
                <tr key={v.id}>
                  <td>{v.branch}</td><td>{v.supervisor || <span className="muted">—</span>}</td><td>{faDigits(v.code) || '—'}</td><td>{v.name}</td>
                  <td className="ltr">{v.phone ? <>{faDigits(v.phone)}{v.phone_from === 'کارآمد' && <span className="tag">کارآمد</span>}</> : <span className="muted">—</span>}</td>
                  <td>{v.karamad_name ? <span className={flag(v.id, 'mismatch') ? 'pill st-red' : ''}>{v.karamad_name}</span> : <span className="muted">—</span>}</td>
                  <td>
                    <select value={v.type} onChange={(e) => setType(v.id, e.target.value)}>
                      {Object.entries(data.types).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                    </select>
                  </td>
                  <td>{!m?.seller_key ? <span className="pill st-red">پیدا نشد</span> : m.match === 'name'
                    ? <span className="pill st-yellow">با نام (کد {faDigits(m.seller_key.split('-')[1])})</span> : <span className="pill st-green">با کد</span>}</td>
                  <td className="muted">{v.note}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- دستورالعمل
// متن فاکتورهای ویژه هر ماه (عمده و/یا با تخفیف مدیریتی) برای کارت‌های دستورالعمل
const specialText = (r) => ['فاکتورهای عمده (مبلغ ناخالص بیش از ۷۰۰ میلیون تومان)', 'فاکتورهای با تخفیف مدیریتی']
  .filter((_, i) => (r.special || []).includes(['wholesale', 'mgmt'][i])).join(' و ')

function Rules({ data }) {
  const r = data.rules
  const mr = (v) => (v == null ? '—' : `${faDigits((v / 1000).toLocaleString('en'))} میلیارد ریال`)
  const tierText = (tiers) => tiers.map(([u, rate], i) => {
    const lo = i ? tiers[i - 1][0] : null
    return `${lo == null ? `کمتر از ${mr(u)}` : u == null ? `بیش از ${mr(lo)}` : `${mr(lo)} تا ${mr(u)}`}: ${fmtPct(rate, 0)}`
  })
  return (
    <div className="grid g2">
      <Card title="ویزیتور پورسانتی" subtitle={`سطح با فروش ناخالص ماه تعیین می‌شود و نرخ آن روی کل ${r.comm_base === 'net_cash' ? 'فروش خالص + درصد نقدی' : 'فروش خالص'} ماه اعمال می‌شود؛ ${isNum(r.commission.wholesale_rate) ? `${specialText(r)}: نرخ پایه ${fmtPct(r.commission.wholesale_rate, 0)}` : 'فاکتور عمده و تخفیف مدیریتی قاعده جدا ندارند'}؛ ${fmtPct(r.commission.reserve, 0)} ذخیره، هر ۶ ماه تسویه.`}>
        <div className="table-scroll"><table>
          <thead><tr><th>جدول</th><th>سطوح فروش ماهانه و نرخ</th></tr></thead>
          <tbody>{Object.entries(r.rulesets).map(([k, v]) => (
            <tr key={k}><td>{rulesetLabel(r, k)}</td><td>{tierText(v.visitor).join(' | ')}</td></tr>
          ))}</tbody>
        </table></div>
      </Card>
      <Card title="سرپرست" subtitle={`پلکانی روی فروش خالص ویزیتورهای تیم: تا تارگت اول ${fmtPct(r.sup_rates[0], 2)}، تا تارگت دوم ${fmtPct(r.sup_rates[1], 0)}، مازاد ${fmtPct(r.sup_rates[2], 1)}؛ زیر تارگت اول صفر؛ ${fmtPct(r.supervisor.reserve, 0)} ذخیره.`}>
        <div className="table-scroll"><table>
          <thead><tr><th>جدول</th><th className="num">تارگت اول</th><th className="num">تارگت دوم</th></tr></thead>
          <tbody>{Object.entries(r.rulesets).map(([k, v]) => (
            <tr key={k}><td>{rulesetLabel(r, k)}</td><td className="num">{v.supervisor ? mr(v.supervisor.t1) : 'بدون سرپرست'}</td><td className="num">{v.supervisor ? mr(v.supervisor.t2) : '—'}</td></tr>
          ))}</tbody>
        </table></div>
      </Card>
      <Card title="ویزیتور استخدامی" className="span2"
        subtitle={`فروش خالص کمتر از ۷۰۰ میلیون تومان: صفر. پایه: تحقق ریالی کمتر از ۷۰٪ ${fmtPct(r.employed.base[0][1], 1)}، ۷۰ تا ۹۵٪ ${fmtPct(r.employed.base[1][1], 1)}، ۹۵٪ و بیشتر ${fmtPct(r.employed.base[2][1], 1)}. تکمیلی: هر گروه با دست‌کم ${fmtPct(r.employed.group_min, 0)} تحقق تعدادی (سقف ${fmtPct(r.employed.group_cap, 0)})؛ سقف نرخ ${fmtPct(r.employed.max_rate, 0)}، با رزتی ۵.۲٪. ${isNum(r.employed.wholesale_rate) ? `${specialText(r)}: نرخ پایه ${fmtPct(r.employed.wholesale_rate, 0)}.` : 'فاکتور عمده و تخفیف مدیریتی قاعده جدا ندارند.'} ذخیره ${fmtPct(r.employed.reserve, 0)}.`}>
        <div className="table-scroll"><table>
          <thead><tr><th>گروه</th><th className="num">نرخ تکمیلی</th><th>تعریف در داده</th><th>توضیح</th></tr></thead>
          <tbody>{r.groups.map((g) => (
            <tr key={g.key}><td>{g.key}</td><td className="num">{fmtPct(g.rate, 2)}</td>
              <td className="muted">{[g.category && `گروه کالا: ${g.category.join('، ')}`, g.brand && `برند: ${g.brand.join('، ')}`, g.product_like && `نام کالا شامل «${g.product_like}»`].filter(Boolean).join(' — ')}</td>
              <td>{g.info ? 'فقط نمایش؛ بدون تارگت و پورسانت' : g.extra ? 'خارج از سقف ۲٪' : g.alt ? 'جایگزین برای فروشندگان بدون مولهنس' : ''}</td></tr>
          ))}</tbody>
        </table></div>
      </Card>
      <Card title="اعمال‌نشده‌ها" className="span2"
        subtitle="این شرط‌ها در داده کارآمد نیستند و در محاسبه اعمال نمی‌شوند: فقط فروش وصول‌شده؛ مانده حساب و چک برگشتی بیش از ۶۵٪ فروش (حذف پورسانت)؛ حداکثر ۲۰٪ فروش عمده و ۲۰٪ مانده پایان ماه." />
    </div>
  )
}

// ---------------------------------------------------------------- صفحه
export default function Commission() {
  const { unit } = useApp()
  const [month, setMonth] = useState('')
  const [view, setView] = useState('achievement')
  const [setup, setSetup] = useState('targets')  // زیربخش «تارگت و فهرست»
  const [err, setErr] = useState(null)
  const { data, error, setData } = useFetch(`/api/commission${month ? `?month=${encodeURIComponent(month)}` : ''}`)
  const onSaved = (d) => { setErr(null); setData(d) }
  const k = useMemo(() => {
    if (!data) return null
    return { noTarget: data.visitors.filter((r) => r.type === 'employed' && !r.target_rial).length }
  }, [data])
  if (error) return <ErrorBox error={error} />
  if (!data) return <Loading />
  const picker = (
    <label className="unit-select">
      <span className="ms-label">ماه</span>
      <select value={data.month} onChange={(e) => setMonth(e.target.value)}>
        {data.months.map((m) => <option key={m} value={m}>{monthName(m)}{m === data.current ? ' (جاری)' : ''}</option>)}
      </select>
    </label>
  )
  return (
    <>
      <PageHead title="درصد تحقق و پورسانت" desc={`ویزیتورها و سرپرستان هیبرید، طبق ${data.rules.title}${data.pace ? ` — ماه جاری: ${faDigits(data.wd_elapsed)} از ${faDigits(data.wd_total)} روز کاری` : ''}`}>
        {picker}
      </PageHead>
      {err && <ErrorBox error={err} />}
      {k.noTarget > 0 && !(view === 'setup' && setup === 'targets') && (
        <div className="alerts"><div className="alert warn"><span className="alert-icon" aria-hidden>!</span><div>
          برای {fmtInt(k.noTarget)} ویزیتور استخدامی تارگت ریالی ثبت نشده و پورسانتشان محاسبه نمی‌شود.
          {' '}<button className="btn ghost sm" onClick={() => { setView('setup'); setSetup('targets') }}>ثبت تارگت</button>
        </div></div></div>
      )}
      <Card actions={<Tabs value={view} onChange={setView} tabs={[
        { value: 'achievement', label: 'تحقق تارگت' }, { value: 'sheet', label: 'پورسانت' },
        { value: 'setup', label: 'تارگت و فهرست' }, { value: 'rules', label: 'دستورالعمل' }]} />}
        title={{ achievement: `عملکرد و تحقق تارگت ${monthName(data.month)}`, sheet: `پورسانت ${monthName(data.month)}`,
          setup: setup === 'targets' ? `تارگت ${monthName(data.month)}` : 'فهرست ویزیتورها و نوع همکاری', rules: 'قواعد محاسبه' }[view]}
        subtitle={data.updated_at ? `آخرین ذخیره: ${faDigits(data.updated_at)}` : 'برای این ماه هنوز چیزی ذخیره نشده است.'}>
        {view === 'achievement' && <Achievement data={data} unit={unit} onSaved={onSaved} setErr={setErr} />}
        {view === 'sheet' && <Sheet data={data} />}
        {view === 'setup' && (
          <>
            <div className="report-tools">
              <Tabs value={setup} onChange={setSetup} tabs={[{ value: 'targets', label: 'ثبت تارگت' }, { value: 'roster', label: 'فهرست ویزیتورها' }]} />
            </div>
            {setup === 'targets' ? <Targets data={data} onSaved={onSaved} setErr={setErr} /> : <Roster data={data} onSaved={onSaved} setErr={setErr} />}
          </>
        )}
        {view === 'rules' && <Rules data={data} />}
      </Card>
    </>
  )
}
