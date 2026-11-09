import { useEffect, useMemo, useRef, useState } from 'react'
import { useApp, useFetch, sendJson, fetchJson, fmtInt, fmtMoney, fmtPct, faDigits, isNum, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { buildXlsx, colName } from '../xlsx.js'
import { MONTH_NAMES } from '../jalali.js'

const monthName = (m) => `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${faDigits(m.slice(0, 4))}`
const TOMAN_M = 1e7  // یک میلیون تومان به ریال
// ratio: [صورت, مخرج] تا خروجی اکسل همین درصد را با فرمول بسازد
const pct2 = (key, label, hint, ratio) => ({ key, label, type: 'pct', pctDigits: 2, hint, ratio, render: (r) => fmtPct(r[key], 2) })
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
// تفکیک برگشتی با ستون «خروجی» فاکتور فروش مرجع در کارآمد؛ جمع دو ستون = کل برگشتی که از فروش خالص کم شده
const retCols = (team) => [
  { key: 'ret_sale', label: team ? 'برگشت از فروش تیم' : 'برگشت از فروش', type: 'money',
    hint: 'مبلغ خالص برگشتی‌هایی که فاکتور فروش مرجعشان در کارآمد «خروجی» ندارد (برگشتی بدون فاکتور مرجع هم همین‌جاست)' },
  { key: 'ret_dist', label: team ? 'برگشت از توزیع تیم' : 'برگشت از توزیع', type: 'money',
    hint: 'مبلغ خالص برگشتی‌هایی که فاکتور فروش مرجعشان در کارآمد «خروجی» دارد' },
]
const reportCols = (first, ret = []) => [
  first,
  { key: 'req_net', label: 'ریال خالص درخواست', type: 'money', hint: 'قابل پرداخت − ارزش افزوده درخواست‌ها' },
  { key: 'gross', label: 'ریال ناخالص فاکتور', type: 'money', hint: 'جمع قبل تخفیف فاکتورهای فروش؛ برگشتی‌ها کسر شده‌اند' },
  { key: 'xnet', label: 'ریال خالص فاکتور', type: 'money', hint: 'قابل پرداخت − ارزش افزوده؛ برگشتی‌ها کسر شده‌اند' },
  ...ret,
  { key: 'qty', label: 'فروش تعدادی فاکتور', type: 'int' },
  { key: 'customers', label: 'مشتری', type: 'int', hint: 'مشتریانی که جمع تعداد خریدشان مثبت است' },
]

/** شعبه پیش‌فرض فایل تارگت از روی نام فایل (طولانی‌ترین نام شعبه‌ای که بدون «هیبرید» در نام فایل آمده) */
const guessBranch = (file, branches) => {
  const n = file.name.replace(/ي/g, 'ی').replace(/ك/g, 'ک')
  const hits = branches.filter((b) => n.includes(b.replace(/^هیبریدی? /, '')))
  return hits.sort((x, y) => y.length - x.length)[0] || ''
}

// ویزیتورهای فهرست (بدون فروشندگان زنجیره‌ای که خودکار در جدول پورسانت می‌آیند)
const rosterOf = (data) => data.visitors.filter((v) => !v.auto)

function TargetUploads({ data, onSaved, setErr }) {
  const branches = [...new Set([...rosterOf(data).map((v) => v.branch.replace(/^هیبریدی /, 'هیبرید ').trim()), ...data.branches.map((b) => b.branch)])].sort()
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
  const bcols = [...reportCols({ key: 'branch', label: 'شعبه', sticky: true }, retCols()).filter((c) => c.key !== 'req_net'),
    { key: 'target_rial', label: 'تارگت شعبه (فایل ناخالص)', type: 'money' },
    { key: 'target_day', label: 'تارگت شعبه تا روز', type: 'money', hint: 'تارگت ماه ÷ کل روز کاری × روز کاری سپری‌شده' },
    { key: 'ach', label: 'تحقق (تارگت شعبه)', type: 'pct', render: achPill('ach'), hint: 'ریال ناخالص فاکتور ÷ تارگت شعبه تا روز' }]
  const vcols = [...reportCols({ key: 'name', label: 'ویزیتور', sticky: true }, retCols()),
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
// مبالغ این تب همیشه کامل به ریال است (جدول، جمع، توضیح و خروجی اکسل)، مستقل از واحد انتخاب‌شده در داشبورد.
const VISITOR_FINANCE_URL = '/api/v1/finance/sales-network/visitor-finance'

// تایید اعتباری: (مانده بدهی + چک برگشتی) کمتر از ۲۰٪ فروش خالص از ابتدای سال
const APPROVAL_LIMIT = 0.2
const OK = 'تایید', NOT_OK = 'عدم تایید'
/** ok_net را اضافه می‌کند؛ تا مانده بدهی از بخش مالی نیامده خالی می‌ماند. */
function withApproval(r) {
  if (!isNum(r.debt)) return { ...r, ok_net: null }
  const exposure = (r.debt || 0) + (r.returned || 0)
  return { ...r, ok_net: exposure < APPROVAL_LIMIT * (r.net_ytd || 0) ? OK : NOT_OK }
}
const approvalPill = (key) => (r) => (r[key] == null ? ''
  : <span className={`pill ${r[key] === OK ? 'st-green' : 'st-red'}`}>{r[key]}</span>)
// حقوق ثابت: از جدول حقوق ثابت ماه (اکسل پورسانت)؛ راهنمای موس = منبع و عدد حقوق و دستمزد کارآمد برای مقایسه
const salaryCell = (r) => {
  const db = isNum(r.salary_db) ? [`کارآمد (${r.salary_db_source === 'فیش حقوق' ? 'فیش همین ماه' : 'حکم فعال، ۳۰ روز'}): ${fmtMoney(r.salary_db, 'rial')}`,
    ...(r.salary_db_parts || []).map((p) => `   ${p.label}: ${fmtMoney(p.value, 'rial')}`)] : []
  const who = r.salary_emp ? [`${r.salary_emp}${r.salary_job ? ` — ${r.salary_job}` : ''}`] : []
  if (isNum(r.salary)) {
    const tip = [r.salary_from && `از جدول حقوق ثابت (${r.salary_from})`, ...who, ...db].filter(Boolean).join('\n')
    return <span title={tip || undefined}>{fmtMoney(r.salary, 'rial')}</span>
  }
  return r.salary_note ? <span className="muted" title={[r.salary_note, ...who, ...db].join('\n')}>—</span> : ''
}

// ---------------------------------------------------------------- خروجی اکسل با فرمول
// برگه «قواعد»: پارامترها و جدول‌های دستورالعمل همان ماه؛ ستون‌های محاسبه‌ای برگه اصلی با فرمول به این خانه‌ها
// (با نام تعریف‌شده، مثل R_COMM_RES) ارجاع می‌دهند. خانه‌های زرد ورودی‌اند و با تغییرشان همه‌چیز دوباره حساب می‌شود.
const RULES_SHEET = 'قواعد'
const abs = (c, r) => `'${RULES_SHEET}'!$${colName(c)}$${r}`
const absRange = (c1, r1, c2, r2) => `'${RULES_SHEET}'!$${colName(c1)}$${r1}:$${colName(c2)}$${r2}`

function rulesSheet(data) {
  const R = data.rules
  const rows = []
  const names = []
  const put = (cells) => { rows.push(cells); return rows.length }
  const input = (v, k) => ({ v: v ?? '', k, st: 'input' })
  put([{ v: `قواعد محاسبه پورسانت — ${R.title} (${data.month})`, st: 'title' }])
  put([{ v: 'خانه‌های زرد ورودی‌اند؛ با تغییر هر کدام، همه ستون‌های فرمولی برگه اصلی دوباره حساب می‌شوند. مبالغ به ریال‌اند.', st: 'note' }])
  put([])
  put([{ v: 'پارامتر', st: 'head' }, { v: 'مقدار', st: 'head' }, { v: 'توضیح', st: 'head' }])
  const param = (name, label, cell, note = '') => {
    const r = put([{ v: label, st: 'label' }, cell, { v: note, st: 'body' }])
    names.push({ name, ref: abs(1, r) })
  }
  param('R_WD_E', 'روز کاری سپری‌شده', input(data.wd_elapsed, 'int'), 'برای تارگت تا روز و پیش‌بینی ماه')
  param('R_WD_T', 'کل روز کاری ماه', input(data.wd_total, 'int'))
  param('R_DAY_SHARE', 'سهم روز سپری‌شده', { f: 'IF(N(R_WD_T)=0,1,R_WD_E/R_WD_T)', k: 'pct' }, 'تارگت تا روز = تارگت × این سهم')
  param('R_PACE', 'ضریب پیش‌بینی ماه', data.pace ? { f: 'IF(N(R_WD_E)=0,"",R_WD_T/R_WD_E)', k: 'dec' } : { v: '' },
    data.pace ? 'پیش‌بینی = مبلغ تا امروز × این ضریب (فقط ماه جاری)' : 'ماه بسته؛ پیش‌بینی ندارد')
  param('R_BASE_CASH', 'مبنای پورسانت', input(R.comm_base === 'net_cash' ? 1 : 0, 'int'), '۱ = فروش خالص + تخفیف نقدی، ۰ = فروش خالص')
  param('R_COMM_WS', 'نرخ فاکتورهای ویژه (پورسانتی)', input(R.commission.wholesale_rate, 'pct2'), 'فاکتورهای عمده / با تخفیف مدیریتی به‌جای نرخ سطح؛ خالی = فاکتور ویژه ندارد')
  param('R_COMM_RES', 'ذخیره پورسانت (پورسانتی)', input(R.commission.reserve, 'pct'))
  param('R_EMP_WS', 'نرخ فاکتورهای ویژه (استخدامی)', input(R.employed.wholesale_rate, 'pct2'))
  param('R_EMP_RES', 'ذخیره پورسانت (استخدامی)', input(R.employed.reserve, 'pct'))
  param('R_EMP_FLOOR', 'کف پورسانت استخدامی', input(R.employed.floor, 'money'), 'مبنای پورسانت کمتر از این مبلغ: بدون پورسانت')
  param('R_EMP_MAX', 'سقف نرخ استخدامی', input(R.employed.max_rate, 'pct2'), 'نرخ پایه + تکمیلی حداکثر این نرخ (رزتی خارج از سقف)')
  R.sup_rates.forEach((x, i) => param(`R_SUP${i + 1}`, `نرخ سرپرست — ${['تا تارگت اول', 'تارگت اول تا دوم', 'مازاد تارگت دوم'][i]}`, input(x, 'pct2')))
  param('R_SUP_RES', 'ذخیره پورسانت سرپرست', input(R.supervisor.reserve, 'pct'))
  param('R_APPROVAL', 'حد تایید (مانده بدهی + چک برگشتی)', input(APPROVAL_LIMIT, 'pct'), 'کمتر از این سهم فروش از ابتدای سال = تایید')
  put([])

  // نرخ پایه استخدامی بر اساس تحقق ریالی: [حد پایین، نرخ]
  put([{ v: 'نرخ پایه استخدامی (بر اساس تحقق تارگت ریالی)', st: 'title' }])
  put([{ v: 'از تحقق', st: 'head' }, { v: 'نرخ پایه', st: 'head' }])
  const empStart = rows.length + 1
  let lo = 0
  for (const [upper, rate] of R.employed.base) {
    put([input(lo, 'pct'), input(rate, 'pct2')])
    lo = upper
  }
  names.push({ name: 'R_EMP_LOW', ref: absRange(0, empStart, 0, rows.length) },
    { name: 'R_EMP_RATE', ref: absRange(1, empStart, 1, rows.length) })
  put([])

  // سطح‌های ویزیتور و تارگت سرپرست هر قاعده: حد پایین هر سطح (ریال، از فروش ناخالص) و نرخ آن
  const sets = Object.entries(R.rulesets)
  const nTier = Math.max(...sets.map(([, s]) => s.visitor.length))
  put([{ v: 'سطح‌های پورسانت ویزیتور و تارگت سرپرست هر قاعده', st: 'title' }])
  put([{ v: 'سطح با فروش ناخالص تعیین می‌شود و نرخ آن روی مبنای پورسانت اعمال می‌شود. «از فروش» حد پایین هر سطح است.', st: 'note' }])
  put([{ v: 'کد قاعده', st: 'head' }, { v: 'عنوان', st: 'head' }, { v: 'تارگت اول سرپرست', st: 'head' }, { v: 'تارگت دوم سرپرست', st: 'head' },
    ...Array.from({ length: nTier }, (_, i) => ({ v: `از فروش سطح ${fa(i + 1)}`, st: 'head' })),
    ...Array.from({ length: nTier }, (_, i) => ({ v: `نرخ سطح ${fa(i + 1)}`, st: 'head' }))])
  const setStart = rows.length + 1
  for (const [code, s] of sets) {
    const lows = [0, ...s.visitor.slice(0, -1).map(([u]) => u * 1e6)]
    const rates = s.visitor.map(([, r]) => r)
    // سطح‌های کمتر: آخرین سطح تکرار می‌شود تا جستجو درست بماند
    while (lows.length < nTier) { lows.push(lows[lows.length - 1]); rates.push(rates[rates.length - 1]) }
    put([{ v: code, st: 'label' }, { v: R.labels[code] || code }, input(s.supervisor ? s.supervisor.t1 * 1e6 : '', 'money'),
      input(s.supervisor ? s.supervisor.t2 * 1e6 : '', 'money'), ...lows.map((x) => input(x, 'money')), ...rates.map((x) => input(x, 'pct'))])
  }
  const setEnd = rows.length
  names.push({ name: 'R_NAMES', ref: absRange(0, setStart, 0, setEnd) }, { name: 'R_T1', ref: absRange(2, setStart, 2, setEnd) },
    { name: 'R_T2', ref: absRange(3, setStart, 3, setEnd) },
    { name: 'R_LOW', ref: absRange(4, setStart, 3 + nTier, setEnd) }, { name: 'R_RATE', ref: absRange(4 + nTier, setStart, 3 + 2 * nTier, setEnd) })
  put([])

  // گروه‌های پورسانت تکمیلی استخدامی (فقط برای اطلاع؛ نرخ تکمیلی هر ویزیتور در برگه اصلی آمده است)
  put([{ v: 'گروه‌های پورسانت تکمیلی استخدامی (فقط اطلاع)', st: 'title' }])
  put([{ v: `هر گروهی که تحقق تعدادی‌اش حداقل ${fa(Math.round(R.employed.group_min * 100))}٪ باشد نرخش اضافه می‌شود؛ جمع گروه‌ها حداکثر ${fa(R.employed.group_cap * 100)}٪ (به‌جز گروه‌های خارج از سقف).`, st: 'note' }])
  put([{ v: 'گروه', st: 'head' }, { v: 'نرخ', st: 'head' }, { v: 'خارج از سقف', st: 'head' }])
  for (const g of R.groups.filter((x) => !x.info)) put([{ v: g.key }, { v: g.rate, k: 'pct2' }, { v: g.extra ? 'بله' : '' }])

  const widths = [34, 20, 20, 20, ...Array(2 * nTier).fill(17)]
  return { sheet: { name: RULES_SHEET, rows, widths, merges: ['A1:F1', 'A2:F2'], heights: { 1: 26, 2: 30 } }, names }
}

/** برگه «راهنمای ستون‌ها»: عنوان، توضیح و فرمولی بودن هر ستون خروجی. */
function guideSheet(columns) {
  const rows = [[{ v: 'راهنمای ستون‌ها', st: 'title' }], [],
    [{ v: 'ستون', st: 'head' }, { v: 'نوع مقدار', st: 'head' }, { v: 'توضیح', st: 'head' }]]
  for (const c of columns.filter((x) => x.csv !== false)) {
    rows.push([{ v: c.label, st: 'label' }, { v: c.xf || c.ratio ? 'فرمول' : 'داده کارآمد / بخش مالی' }, { v: c.hint || '' }])
  }
  return { name: 'راهنمای ستون‌ها', rows, widths: [42, 22, 100], heights: { 1: 26 } }
}

const commissionExtras = (data, columns) => () => {
  const { sheet, names } = rulesSheet(data)
  return { extraSheets: [sheet, guideSheet(columns)], names }
}

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

// ---------------------------------------------------------------- گزارش کلی پورسانت (هیبرید، زنجیره‌ای، B2B)
const PORTFOLIO_URL = '/api/v1/finance/customer-collection-portfolio?limit=1000'

/** مانده بدهی و چک برگشتی نمایندگان B2B از پرتفوی مطالبات داشبورد مالی (کلید = کد مشتری راهکاران). */
function usePortfolioMap() {
  const [state, setState] = useState({ map: null, loading: true, error: null })
  useEffect(() => {
    let alive = true
    fetchJson(PORTFOLIO_URL)
      .then((d) => alive && setState({ map: new Map((d.customers || []).map((f) => [String(f.counterpart_code), f])), loading: false, error: null }))
      .catch((e) => alive && setState({ map: null, loading: false, error: e.message }))
    return () => { alive = false }
  }, [])
  return state
}

/** سه ردیف هیبرید، زنجیره‌ای و نمایندگان B2B برای همان ماه: جمع ستون‌های کلی جدول‌های پورسانت هر بخش. */
function Summary({ data }) {
  const fin = useVisitorFinance()
  const port = usePortfolioMap()
  const [b2b, setB2b] = useState({ data: null, error: null })
  useEffect(() => {
    let alive = true
    setB2b({ data: null, error: null })
    fetchJson(`/api/rk_commission?channel=b2b&month=${encodeURIComponent(data.month)}`)
      .then((d) => alive && setB2b({ data: d, error: null }))
      .catch((e) => alive && setB2b({ data: null, error: e.message }))
    return () => { alive = false }
  }, [data.month])
  const year = faDigits(data.month.slice(0, 4))
  const add = (rs, k) => rs.reduce((a, r) => a + (r[k] || 0), 0)
  const addFin = (rs, get) => {  // تا بخش مالی نیامده خالی
    const xs = rs.map(get).filter(Boolean)
    if (!xs.length) return { debt: null, returned: null, returned_n: null }
    return { debt: add(xs, 'debt'), returned: add(xs, 'returned'), returned_n: add(xs, 'returned_n') }
  }
  const visitorFin = (v) => {
    const x = fin.map?.get(v.seller_key)
    return x && { debt: x.open_account_receivable_rial, returned: x.returned_cheque_rial, returned_n: x.returned_cheque_count }
  }
  const sales = (rs) => ({ gross: add(rs, 'gross'), net: add(rs, 'net'), net_cash: add(rs, 'net_cash'), mgmt_n: add(rs, 'mgmt_n'),
    gross_ytd: add(rs, 'gross_ytd'), net_ytd: add(rs, 'net_ytd'), people: rs.length })
  const hyb = data.visitors.filter((v) => v.type !== 'channel')
  const chain = data.visitors.filter((v) => v.type === 'channel')
  // ماهی که در داده راهکاران نیست (پیش از سال قبل) را بک‌اند به ماه جاری برمی‌گرداند؛ آن ماه اینجا خالی می‌ماند
  const b2bOk = b2b.data && b2b.data.month === data.month
  const b2bRows = b2bOk ? b2b.data.rows : []
  const rows = [
    { key: 'hybrid', channel: 'هیبرید', ...sales(hyb), payable: add(hyb, 'payable') + add(data.supervisors, 'payable'), ...addFin(hyb, visitorFin),
      note: `${fmtInt(hyb.length)} ویزیتور و ${fmtInt(data.supervisors.length)} سرپرست؛ قابل پرداخت = ویزیتورها + سرپرستان` },
    { key: 'chain', channel: 'زنجیره‌ای', ...sales(chain), payable: chain.some((v) => isNum(v.payable)) ? add(chain, 'payable') : null,
      ...addFin(chain, visitorFin), note: 'هنوز دستورالعمل پورسانت ندارد' },
    b2bOk ? {
      key: 'b2b', channel: 'نمایندگان B2B', ...sales(b2bRows), payable: add(b2bRows, 'payable'),
      ...addFin(b2bRows, (r) => {
        const f = port.map?.get(String(r.code))
        if (!f) return null
        const cp = f.collection_position || {}
        return { debt: cp.open_account_receivable_rial ?? f.account_position?.balance_rial ?? 0, returned: cp.returned_account_rial ?? 0,
          returned_n: f.returned_cheque_count ?? 0 }
      }),
      note: `${fmtInt(b2bRows.length)} نماینده؛ فروش از راهکاران (خالص با مالیات)؛ پورسانت ۰٫۲٪ خالص + نقدی`,
    } : { key: 'b2b', channel: 'نمایندگان B2B', note: b2b.error ? `خوانده نشد: ${b2b.error}` : b2b.data ? 'این ماه در داده فروش راهکاران نیست' : 'در حال خواندن از راهکاران…' },
  ]
  const cols = [
    { key: 'channel', label: 'بخش', sticky: true },
    { key: 'people', label: 'تعداد فروشنده / نماینده', type: 'int' },
    { key: 'gross', label: 'فروش ناخالص', type: 'money' },
    { key: 'net', label: 'فروش خالص', type: 'money', hint: 'پس از کسر برگشتی و تخفیف‌ها؛ هیبرید و زنجیره‌ای بدون ارزش افزوده (کارآمد)، B2B خالص راهکاران (با مالیات)' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی', type: 'money' },
    { key: 'mgmt_n', label: 'تعداد فاکتور با تخفیف مدیریتی', type: 'int' },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره؛ هیبرید = ویزیتورها + سرپرستان' },
    { key: 'gross_ytd', label: `فروش ناخالص از ابتدای ${year}`, type: 'money' },
    { key: 'net_ytd', label: `فروش خالص از ابتدای ${year}`, type: 'money' },
    { key: 'debt', label: 'مانده بدهی', type: 'money', hint: 'هیبرید و زنجیره‌ای: مانده مشتریان هر ویزیتور (همان جدول پورسانت)؛ B2B: مانده حساب نماینده از پرتفوی مطالبات' },
    { key: 'returned', label: 'چک برگشتی', type: 'money', hint: 'مانده چک‌های برگشتی تسویه‌نشده' },
    { key: 'returned_n', label: 'تعداد چک برگشتی', type: 'int' },
    { key: 'note', label: 'توضیح' },
  ]
  const totals = (rs) => {
    const t = Object.fromEntries(cols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, rs.some((r) => isNum(r[c.key])) ? add(rs, c.key) : null]))
    return { ...t, key: '__total', channel: 'جمع کل', note: '' }
  }
  return (
    <>
      <div className="report-tools">
        <span className="muted small">جمع ستون‌های کلی جدول‌های پورسانت هیبرید، زنجیره‌ای (همین صفحه) و نمایندگان B2B (صفحه «پورسانت نمایندگان و صادرات») برای {monthName(data.month)}.</span>
        {(fin.loading || port.loading) && <span className="muted small">در حال خواندن مطالبات از بخش مالی…</span>}
        {fin.error && <span className="muted small">مانده ویزیتورها از بخش مالی خوانده نشد: {fin.error}</span>}
        {port.error && <span className="muted small">مانده نمایندگان B2B از بخش مالی خوانده نشد: {port.error}</span>}
      </div>
      <DataTable rows={rows} columns={cols} unit="rial" search={false} pageSize={10} totals={totals}
        exportName={`commission-summary-${data.month.replace('/', '-')}`} />
    </>
  )
}

function Sheet({ data }) {
  const unit = 'rial'
  const year = faDigits(data.month.slice(0, 4))
  const fin = useVisitorFinance()
  const [who, setWho] = useState('visitors')
  const [f, setF] = useState({ branch: '', supervisor: '', type: '', group: '' })
  const [sel, setSel] = useState(null)
  const [selS, setSelS] = useState(null)
  // ستون‌های مالی: ویزیتور از پرونده خودش، سرپرست = جمع ویزیتورهای همان شعبه و سرپرست
  // درصد پورسانت = پورسانت محاسبه‌شده ÷ (فروش خالص + درصد نقدی)
  // درصد مدیریتی = تخفیف مدیریتی ÷ فروش ناخالص؛ درصد عمده‌فروشی = مبلغ فاکتورهای عمده ÷ فروش ناخالص
  const ratio = (a, b) => (b > 0 ? a / b : null)
  // درصد هزینه فروش = (حقوق ثابت + پورسانت) ÷ (فروش خالص + درصد نقدی)
  const costPct = (r) => (isNum(r.salary) || isNum(r.commission) ? ratio((r.salary || 0) + (r.commission || 0), r.net_cash) : null)
  const costCol = (team) => ({ key: 'cost_pct', label: 'درصد هزینه فروش', type: 'pct', pctDigits: 2, render: (r) => fmtPct(r.cost_pct, 2),
    hint: `(حقوق ثابت + پورسانت محاسبه‌شده) ÷ (فروش خالص + درصد نقدی${team ? ' تیم' : ''})`,
    xf: (ref) => `IF(OR(N(${ref('net_cash')})<=0,AND(${ref('salary')}="",${ref('commission')}="")),"",(N(${ref('salary')})+N(${ref('commission')}))/N(${ref('net_cash')}))` })
  const visitors = useMemo(() => data.visitors.map((v) => {
    const x = fin.map?.get(v.seller_key)
    const row = { ...v, cash_disc: (v.net_cash || 0) - (v.net || 0), comm_pct: isNum(v.commission) ? ratio(v.commission, v.net_cash) : null, cost_pct: costPct(v),
      mgmt_pct: ratio(v.mgmt_disc, v.gross), wholesale_pct: ratio(v.wholesale_gross, v.gross) }
    // توزیع‌نشده = فاکتورهای بدون حواله خروج (همان تب «توزیع بار»)؛ بدهی نهایی = مانده بدهی − توزیع‌نشده
    return x ? withApproval({ ...row, debt: x.open_account_receivable_rial, debtors: x.debtor_customer_count,
      returned: x.returned_cheque_rial, returned_n: x.returned_cheque_count,
      undist: x.undistributed_rial ?? 0, undist_n: x.undistributed_count ?? 0,
      debt_final: (x.open_account_receivable_rial || 0) - (x.undistributed_rial || 0), fin: x }) : row
  }), [data.visitors, fin.map])
  const supervisors = useMemo(() => data.supervisors.map((s0) => {
    const mates = visitors.filter((v) => v.supervisor === s0.name && bkey(v.branch) === bkey(s0.branch))
    const s = { ...s0, comm_pct: ratio(s0.commission, s0.net_cash), cost_pct: costPct(s0), gross_ytd: mates.reduce((a, v) => a + (v.gross_ytd || 0), 0),
      net_ytd: mates.reduce((a, v) => a + (v.net_ytd || 0), 0) }
    const team = visitors.filter((v) => v.supervisor === s.name && bkey(v.branch) === bkey(s.branch) && isNum(v.debt))
    if (!team.length) return s
    const add = (k) => team.reduce((a, v) => a + (v[k] || 0), 0)
    return withApproval({ ...s, debt: add('debt'), returned: add('returned'), returned_n: add('returned_n'),
      undist: add('undist'), undist_n: add('undist_n'), debt_final: add('debt_final') })
  }), [data.supervisors, visitors])
  const uniq = (k) => [...new Set(visitors.map((v) => v[k]).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fa'))
  const opts = { branch: uniq('branch'), supervisor: uniq('supervisor').filter((s) => !f.branch || visitors.some((v) => v.branch === f.branch && v.supervisor === s)) }
  const vrows = visitors.filter((v) => (!f.branch || v.branch === f.branch) && (!f.supervisor || v.supervisor === f.supervisor)
    && (!f.type || v.type === f.type) && (!f.group || v.group_ab === f.group))
  const srows = supervisors.filter((s) => (!f.branch || bkey(s.branch) === bkey(f.branch)) && (!f.supervisor || s.name === f.supervisor)
    && (!f.group || s.group_ab === f.group))
  const T = team => (team ? ' تیم' : '')
  const approvalHint = (base, team) => `اگر مانده بدهی${T(team)} + چک برگشتی${T(team)} کمتر از ${fa(Math.round(APPROVAL_LIMIT * 100))}٪ فروش ${base}${T(team)} از ابتدای ${year} باشد «تایید»، وگرنه «عدم تایید»؛ تا مانده بدهی از بخش مالی نیامده خالی است`
  // فرمول‌های اکسل (ref(key) = خانه همان سطر در ستون key؛ R_… = خانه‌های برگه «قواعد»)
  const approvalXf = (base) => (ref) => `IF(${ref('debt')}="","",IF(N(${ref('debt')})+N(${ref('returned')})<R_APPROVAL*N(${ref(base)}),"${OK}","${NOT_OK}"))`
  const COMM_T = data.types.commission  // «پورسانتی»
  const baseXf = (ref) => `IF(R_BASE_CASH=1,N(${ref('net_cash')}),N(${ref('net')}))`
  const tierRate = (ref) => `LOOKUP(MAX(N(${ref('gross')}),0),INDEX(R_LOW,MATCH(${ref('ruleset')},R_NAMES,0),0),INDEX(R_RATE,MATCH(${ref('ruleset')},R_NAMES,0),0))`
  // پورسانتی: نرخ سطح؛ استخدامی: بدون تارگت ریالی خالی، زیر کف صفر، وگرنه min(نرخ پایه + تکمیلی، سقف) + خارج از سقف
  const rateXf = (ref) => `IF(${ref('type_label')}="${COMM_T}",${tierRate(ref)},IF(${ref('target_rial')}="","",IF(N(${ref('base')})<R_EMP_FLOOR,0,`
    + `MIN(LOOKUP(MAX(N(${ref('ach')}),0),R_EMP_LOW,R_EMP_RATE)+N(${ref('bonus_rate')}),R_EMP_MAX)+N(${ref('extra_rate')}))))`
  // پورسانت = نرخ × (مبنا − مبنای فاکتورهای ویژه) + نرخ ویژه × مبنای فاکتورهای ویژه (حداقل صفر)
  const split = (ref, ws) => `MAX(N(${ref('rate')})*(N(${ref('base')})-IF(${ws}="",0,N(${ref('special_base')})))+N(${ws})*IF(${ws}="",0,N(${ref('special_base')})),0)`
  const commXf = (ref) => `IF(${ref('rate')}="","",IF(${ref('type_label')}="${COMM_T}",${split(ref, 'R_COMM_WS')},IF(N(${ref('base')})<R_EMP_FLOOR,0,${split(ref, 'R_EMP_WS')})))`
  // اکسل: «درصد پورسانت» از قواعد حساب می‌شود و «پورسانت» = درصد پورسانت × (فروش خالص + درصد نقدی)؛
  // اگر درصد پورسانت ردیفی دستی عوض شود، پورسانت، ذخیره، قابل پرداخت و درصد هزینه با همان درصد حساب می‌شوند
  const pctFrom = (comm) => (ref) => `IF(${comm(ref)}="","",IF(N(${ref('net_cash')})<=0,0,${comm(ref)}/N(${ref('net_cash')})))`
  const commFromPct = (ref) => `IF(${ref('comm_pct')}="","",N(${ref('comm_pct')})*N(${ref('net_cash')}))`
  const commPctCol = (hint, comm) => ({ key: 'comm_pct', label: 'درصد پورسانت', type: 'pct', pctDigits: 2, render: (r) => fmtPct(r.comm_pct, 2),
    hint, ratio: ['commission', 'net_cash'], xf: pctFrom(comm) })
  const reserveXf = (ref) => `IF(${ref('commission')}="",0,N(${ref('commission')})*IF(${ref('type_label')}="${COMM_T}",R_COMM_RES,R_EMP_RES))`
  const payXf = (ref) => `IF(${ref('commission')}="","",N(${ref('commission')})-N(${ref('reserve')}))`
  // سرپرست: پلکانی روی مبنای تیم؛ اگر فروش ناخالص تیم (reach) به تارگت اول نرسد صفر
  const supComm = (ref, b, reach) => `IF(${ref('t1')}="","",IF(${reach}<N(${ref('t1')}),0,MIN(MAX(${b},0),N(${ref('t1')}))*R_SUP1`
    + `+MAX(MIN(MAX(${b},0),N(${ref('t2')}))-N(${ref('t1')}),0)*R_SUP2+MAX(MAX(${b},0)-N(${ref('t2')}),0)*R_SUP3))`
  const supTarget = (name) => (ref) => `IF(N(INDEX(${name},MATCH(${ref('ruleset')},R_NAMES,0)))=0,"",INDEX(${name},MATCH(${ref('ruleset')},R_NAMES,0)))`
  const finCols = (team) => [
    { key: 'gross_ytd', label: `فروش ناخالص${T(team)} از ابتدای ${year}`, type: 'money',
      hint: team ? 'جمع ستون «فروش ناخالص از ابتدای سال» ویزیتورهای همین سرپرست'
        : `جمع قبل تخفیف فاکتورها از ۱ فروردین ${year} تا پایان همین ماه؛ برگشتی‌ها کسر شده‌اند` },
    { key: 'net_ytd', label: `فروش خالص${T(team)} از ابتدای ${year}`, type: 'money',
      hint: team ? 'جمع ستون «فروش خالص از ابتدای سال» ویزیتورهای همین سرپرست'
        : `فروش خالص (پس از کسر برگشتی و همه تخفیفات، بدون ارزش افزوده) از ۱ فروردین ${year} تا پایان همین ماه` },
    { key: 'debt', label: team ? 'مانده بدهی تیم' : 'مانده بدهی', type: 'money',
      hint: `مانده بدهی مشتریان ${team ? 'ویزیتورهای این سرپرست' : 'این ویزیتور'} از بخش مالی (همان عدد پرونده ویزیتور)` },
    { key: 'undist', label: team ? 'توزیع‌نشده تیم' : 'توزیع‌نشده', type: 'money',
      hint: `جمع مبلغ فاکتورهای ${team ? 'ویزیتورهای این سرپرست' : 'این ویزیتور'} که هنوز حواله خروج ندارند (سال مالی جاری؛ همان تب «توزیع بار» داشبورد مالی)` },
    { key: 'debt_final', label: team ? 'بدهی نهایی تیم' : 'بدهی نهایی', type: 'money',
      hint: 'مانده بدهی − توزیع‌نشده', xf: (ref) => `IF(${ref('debt')}="","",N(${ref('debt')})-N(${ref('undist')}))` },
    { key: 'returned', label: team ? 'چک برگشتی تیم' : 'چک برگشتی', type: 'money',
      hint: `مبلغ چک‌های برگشتی تسویه‌نشده فاکتورهای ${team ? 'تیم' : 'این ویزیتور'} از بخش مالی${fin.from ? ` (سررسید از ${faDigits(fin.from)})` : ''}` },
    { key: 'returned_n', label: 'تعداد چک برگشتی', type: 'int' },
    // تایید فقط بر اساس فروش خالص از ابتدای سال (اعلام کاربر)
    { key: 'ok_net', label: `تایید (${fa(Math.round(APPROVAL_LIMIT * 100))}٪ خالص ${year})`, render: approvalPill('ok_net'),
      hint: approvalHint('خالص', team), xf: approvalXf('net_ytd') },
  ]
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value, ...(k === 'branch' ? { supervisor: '' } : {}) }); setSel(null); setSelS(null) }
  const vcols = [
    // شعبه و نام فروشنده هنگام اسکرول افقی ثابت می‌مانند
    { key: 'branch', label: 'نام شعبه', sticky: true }, { key: 'name', label: 'نام فروشنده', sticky: true },
    { key: 'code', label: 'کد فروشنده' }, { key: 'supervisor', label: 'نام سرپرست' }, { key: 'type_label', label: 'نوع' },
    { key: 'group_ab', label: 'گروه' },
    { key: 'ruleset', label: 'کد قاعده', exportOnly: true, hint: 'ردیف همین قاعده در جدول سطح‌های برگه «قواعد»' },
    { key: 'target_rial', label: 'تارگت', type: 'money' },
    { key: 'target_day', label: 'تارگت تا روز', type: 'money', exportOnly: true, noTotal: true,
      hint: 'تارگت × سهم روز سپری‌شده (برگه قواعد)', xf: (ref) => `IF(${ref('target_rial')}="","",N(${ref('target_rial')})*R_DAY_SHARE)` },
    { key: 'ach', label: 'تحقق', type: 'pct', render: achPill('ach'), noTotal: true, hint: 'فروش ناخالص ÷ تارگت (ماه جاری: تارگت تا روز)',
      xf: (ref) => `IF(N(${ref('target_day')})=0,"",N(${ref('gross')})/N(${ref('target_day')}))` },
    { key: 'gross', label: 'فروش ناخالص', type: 'money', hint: 'جمع قبل تخفیف فاکتورها؛ برگشتی‌ها کسر شده‌اند' },
    { key: 'net', label: 'فروش خالص', type: 'money', hint: 'پس از کسر برگشتی و همه تخفیفات، بدون ارزش افزوده' },
    { key: 'cash_disc', label: 'تخفیف نقدی', type: 'money', exportOnly: true, hint: 'تخفیف نقدی فاکتورها (برگشتی‌ها کسر شده)' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی', type: 'money', hint: 'فروش خالص به‌اضافه تخفیف نقدی (برگشتی‌ها کسر شده)',
      xf: (ref) => `N(${ref('net')})+N(${ref('cash_disc')})` },
    { key: 'base', label: 'مبنای پورسانت', type: 'money', exportOnly: true, hint: 'فروش خالص یا فروش خالص + نقدی، طبق «مبنای پورسانت» برگه قواعد', xf: baseXf },
    { key: 'special_base', label: 'مبنای فاکتورهای ویژه', type: 'money', exportOnly: true,
      hint: `مبنای پورسانت فاکتورهای ویژه (${(data.rules.special || []).map((k) => ({ wholesale: 'عمده', mgmt: 'با تخفیف مدیریتی' }[k] || k)).join(' و ') || 'ندارد'}) که نرخ ثابت می‌گیرند` },
    ...(data.pace ? [{ key: 'forecast', label: 'پیش‌بینی ماه', type: 'money', hint: 'فروش خالص ÷ روز کاری سپری‌شده × کل روز کاری ماه',
      xf: (ref) => `N(${ref('net')})*R_PACE` }] : []),
    { key: 'wholesale_n', label: 'تعداد فاکتور بالای ۷۰۰', type: 'int', hint: 'فاکتورهای فروشی که مبلغ ناخالص (جمع قبل تخفیف) هر کدام بیش از ۷۰۰ میلیون تومان است' },
    { key: 'wholesale_gross', label: 'مبلغ عمده‌فروشی', type: 'money', hint: 'جمع مبلغ ناخالص همان فاکتورهای بالای ۷۰۰ میلیون تومان؛ برگشتی از آن کم نمی‌شود' },
    pct2('wholesale_pct', 'درصد عمده‌فروشی', 'مبلغ عمده‌فروشی ÷ فروش ناخالص (همان ستون «فروش ناخالص» که برگشتی از آن کم شده؛ اگر برگشتی زیاد باشد ممکن است از ۱۰۰٪ بیشتر شود)',
      ['wholesale_gross', 'gross']),
    { key: 'customers', label: 'تعداد مشتری', type: 'int', hint: 'مشتریانی که جمع تعداد خریدشان مثبت است' },
    // فاکتورهای فروش دارای تخفیف مدیریتی (از کارآمد: انواع تخفیفی که نامشان «مدیریت» دارد)
    { key: 'mgmt_n', label: 'تعداد فاکتور با تخفیف مدیریتی', type: 'int', hint: 'فاکتورهای فروشی که تخفیف مدیریتی دارند' },
    { key: 'mgmt_inv_gross', label: 'ناخالص فاکتورهای با تخفیف مدیریتی', type: 'money', hint: 'جمع مبلغ ناخالص (قبل تخفیف) فاکتورهای فروشی که تخفیف مدیریتی دارند' },
    { key: 'mgmt_inv_net_cash', label: 'خالص + نقدی فاکتورهای با تخفیف مدیریتی', type: 'money',
      hint: 'فروش خالص به‌اضافه تخفیف نقدی همان فاکتورها؛ مبنای پورسانت فاکتورهای ویژه (همان عددهای ستون «خالص + نقدی» در توضیح محاسبه)' },
    { key: 'mgmt_disc', label: 'مبلغ تخفیف مدیریتی', type: 'money' },
    pct2('mgmt_rate', 'نرخ تخفیف مدیریتی', 'مبلغ تخفیف مدیریتی ÷ مبلغ ناخالص همان فاکتورها', ['mgmt_disc', 'mgmt_inv_gross']),
    pct2('mgmt_pct', 'درصد فروش مدیریتی', 'مجموع تخفیف مدیریتی ÷ فروش ناخالص', ['mgmt_disc', 'gross']),
    { key: 'status', label: 'وضعیت', noTotal: true },
    { key: 'bonus_rate', label: 'نرخ تکمیلی گروه‌ها', type: 'pct', pctDigits: 2, exportOnly: true, noTotal: true,
      hint: 'فقط استخدامی: جمع نرخ گروه‌هایی که تحقق تعدادی‌شان به حد رسیده (با سقف)، از تارگت‌های تعدادی هر گروه' },
    { key: 'extra_rate', label: 'نرخ خارج از سقف', type: 'pct', pctDigits: 2, exportOnly: true, noTotal: true, hint: 'فقط استخدامی: گروه‌های خارج از سقف (رزتی)' },
    { key: 'rate', label: 'نرخ پورسانت', type: 'pct', pctDigits: 2, exportOnly: true, noTotal: true,
      hint: 'پورسانتی: نرخ سطح فروش ناخالص از جدول قاعده؛ استخدامی: min(نرخ پایه تحقق + تکمیلی، سقف) + خارج از سقف، زیر کف صفر', xf: rateXf },
    commPctCol('پورسانت محاسبه‌شده ÷ (فروش خالص + درصد نقدی). در اکسل ورودی پورسانت است: اگر دستی عوض شود پورسانت با همین درصد حساب می‌شود', commXf),
    { key: 'commission', label: 'پورسانت محاسبه‌شده', type: 'money', xf: commFromPct,
      hint: 'نرخ پورسانت × (مبنای پورسانت − مبنای فاکتورهای ویژه) + نرخ فاکتورهای ویژه × مبنای فاکتورهای ویژه' },
    { key: 'reserve', label: 'ذخیره پورسانت', type: 'money', xf: reserveXf,
      hint: `پورسانتی ${fmtPct(data.rules.commission.reserve, 0)}، استخدامی ${fmtPct(data.rules.employed.reserve, 0)}` },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره', xf: payXf },
    { key: 'salary', label: 'حقوق ثابت', type: 'money', render: salaryCell,
      hint: 'فقط استخدامی: مبلغ ثابت ماهانه از جدول حقوق ثابت (اکسل پورسانت شهریور؛ هر ماه از ماه قبل می‌آید). '
        + 'موس روی عدد = منبع و برای مقایسه عدد حقوق و دستمزد کارآمد' },
    costCol(false),
    ...finCols(false),
  ]
  const scols = [
    { key: 'branch', label: 'نام شعبه', sticky: true }, { key: 'name', label: 'نام سرپرست', sticky: true }, { key: 'group_ab', label: 'گروه' },
    { key: 'ruleset', label: 'کد قاعده', exportOnly: true, hint: 'ردیف همین قاعده در جدول سطح‌های برگه «قواعد»' },
    { key: 'visitors', label: 'ویزیتور', type: 'int' },
    { key: 'gross', label: 'فروش ناخالص تیم', type: 'money', hint: 'جمع فروش ناخالص ویزیتورهای همین سرپرست' },
    { key: 'net', label: 'فروش خالص تیم', type: 'money', hint: 'جمع فروش خالص ویزیتورهای همین سرپرست' },
    { key: 'net_cash', label: 'فروش خالص + درصد نقدی تیم', type: 'money', hint: 'جمع فروش خالص + تخفیف نقدی ویزیتورهای همین سرپرست' },
    { key: 'base', label: 'مبنای پورسانت تیم', type: 'money', exportOnly: true, hint: 'فروش خالص یا فروش خالص + نقدی تیم، طبق «مبنای پورسانت» برگه قواعد', xf: baseXf },
    ...(data.pace ? [{ key: 'forecast', label: 'پیش‌بینی ماه', type: 'money', hint: 'مبنای پورسانت تیم × ضریب پیش‌بینی', xf: (ref) => `N(${ref('base')})*R_PACE` }] : []),
    { key: 't1', label: 'تارگت اول', type: 'money', xf: supTarget('R_T1'), hint: 'از جدول قاعده همین شعبه در برگه قواعد' },
    { key: 't2', label: 'تارگت دوم', type: 'money', xf: supTarget('R_T2'), hint: 'از جدول قاعده همین شعبه در برگه قواعد' },
    { key: 'ach_t1', label: 'تحقق تارگت اول', type: 'pct', render: achPill('ach_t1'), hint: 'فروش ناخالص تیم ÷ تارگت اول',
      xf: (ref) => `IF(N(${ref('t1')})=0,"",N(${ref('gross')})/N(${ref('t1')}))` },
    { key: 'status', label: 'وضعیت', noTotal: true,
      xf: (ref) => `IF(${ref('t1')}="","بدون قاعده سرپرستی",IF(N(${ref('gross')})<N(${ref('t1')}),"زیر تارگت اول",IF(N(${ref('gross')})>=N(${ref('t2')}),"تارگت دوم","تارگت اول")))` },
    commPctCol('پورسانت محاسبه‌شده ÷ (فروش خالص + درصد نقدی تیم). در اکسل ورودی پورسانت است: اگر دستی عوض شود پورسانت با همین درصد حساب می‌شود',
      (ref) => supComm(ref, `N(${ref('base')})`, `N(${ref('gross')})`)),
    { key: 'commission', label: 'پورسانت محاسبه‌شده', type: 'money', xf: commFromPct,
      hint: 'پلکانی روی مبنای پورسانت تیم با نرخ‌های سرپرست برگه قواعد؛ اگر فروش ناخالص تیم به تارگت اول نرسد صفر' },
    ...(data.pace ? [{ key: 'forecast_commission', label: 'پورسانت با پیش‌بینی', type: 'money',
      xf: (ref) => supComm(ref, `N(${ref('forecast')})`, `N(${ref('gross')})*R_PACE`), hint: 'همان محاسبه پورسانت روی پیش‌بینی پایان ماه' }] : []),
    { key: 'reserve', label: 'ذخیره پورسانت', type: 'money', hint: `${fmtPct(data.rules.supervisor.reserve, 0)} پورسانت`,
      xf: (ref) => `IF(${ref('commission')}="",0,N(${ref('commission')})*R_SUP_RES)` },
    { key: 'payable', label: 'قابل پرداخت', type: 'money', hint: 'پورسانت منهای ذخیره', xf: payXf },
    { key: 'salary', label: 'حقوق ثابت', type: 'money', render: salaryCell,
      hint: 'مبلغ ثابت ماهانه سرپرست از جدول حقوق ثابت (اکسل پورسانت شهریور؛ هر ماه از ماه قبل می‌آید). '
        + 'موس روی عدد = منبع و برای مقایسه عدد حقوق و دستمزد کارآمد' },
    costCol(true),
    ...finCols(true),
  ]
  const sum = (rows, k) => rows.reduce((s, r) => s + (r[k] || 0), 0)
  // ردیف «جمع کل»: مبالغ و تعدادها جمع می‌شوند؛ درصدها از جمع‌ها دوباره حساب می‌شوند (نه جمع درصدها)
  const vTotals = (rs) => {
    const t = Object.fromEntries(vcols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, sum(rs, c.key)]))
    const hasFin = rs.some((r) => isNum(r.debt))
    return withApproval({ ...t, ...(hasFin ? {} : { debt: null }), branch: 'جمع کل', key: '__total',
      comm_pct: ratio(t.commission, t.net_cash), cost_pct: ratio((t.salary || 0) + (t.commission || 0), t.net_cash),
      wholesale_pct: ratio(t.wholesale_gross, t.gross),
      mgmt_pct: ratio(t.mgmt_disc, t.gross), mgmt_rate: ratio(t.mgmt_disc, t.mgmt_inv_gross) })
  }
  const sTotals = (rs) => {
    const t = Object.fromEntries(scols.filter((c) => c.type === 'money' || c.type === 'int').map((c) => [c.key, sum(rs, c.key)]))
    const hasFin = rs.some((r) => isNum(r.debt))
    return withApproval({ ...t, ...(hasFin ? {} : { debt: null }), t1: null, t2: null, branch: 'جمع کل', key: '__total',
      comm_pct: ratio(t.commission, t.net_cash), cost_pct: ratio((t.salary || 0) + (t.commission || 0), t.net_cash) })
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
        {data.salary_error && <span className="muted small">{data.salary_error}</span>}
      </div>
      <div className="filter-bar">
        {select('branch', 'شعبه', opts.branch.map((b) => [b, b]))}
        {select('supervisor', 'سرپرست', opts.supervisor.map((s) => [s, s]))}
        {who === 'visitors' && select('type', 'نوع', [...Object.entries(data.types), ['channel', 'زنجیره‌ای']])}
        {select('group', 'گروه', [['A', 'گروه A'], ['B', 'گروه B']])}
        <span className="muted small">روی هر ردیف کلیک کنید تا توضیح محاسبه پورسانت زیر همان ردیف باز شود.</span>
      </div>
      {who === 'visitors' ? (
        <DataTable rows={vrows.map((r) => ({ ...r, key: r.id }))} columns={vcols} unit={unit} pageSize={100}
          exportName={`commission-visitors-${tag}`} exportExtras={commissionExtras(data, vcols)} defaultSort={{ key: 'branch', dir: 'asc' }}
          onRowClick={(r) => setSel(r.key === sel ? null : r.key)} expandedKey={sel}
          renderExpanded={(r) => <VisitorCalc v={r} data={data} unit={unit} />} totals={vTotals} />
      ) : (
        <DataTable rows={srows.map((s) => ({ ...s, key: s.id }))} columns={scols} unit={unit} pageSize={50}
          search={false} exportName={`commission-supervisors-${tag}`} exportExtras={commissionExtras(data, scols)} defaultSort={{ key: 'branch', dir: 'asc' }}
          onRowClick={(r) => setSelS(r.key === selS ? null : r.key)} expandedKey={selS}
          renderExpanded={(r) => <SupervisorCalc s={r} data={data} unit={unit} />} totals={sTotals} />
      )}
      {f.branch && <AccountDetails rows={vrows} branch={f.branch} fin={fin} unit={unit} month={data.month} current={data.current} />}
    </>
  )
}

/** ریز مانده حساب ویزیتورهای یک هیبرید (زیر جدول پورسانت، وقتی فیلتر شعبه انتخاب شده). داده: بخش مالی (visitor-finance). */
function AccountDetails({ rows, branch, fin, unit, month, current }) {
  const list = rows.filter((v) => v.fin)
  const [open, setOpen] = useState(() => new Set())
  const toggle = (id) => setOpen((s) => { const x = new Set(s); if (x.has(id)) x.delete(id); else x.add(id); return x })
  const title = `ریز مانده حساب ویزیتورها — ${branch}`
  if (fin.loading) return <Card title={title}><Loading /></Card>
  if (!list.length) return <Card title={title}><p className="muted">مانده حسابی از بخش مالی برای ویزیتورهای این شعبه نیامد.</p></Card>
  const m = (v) => fmtMoney(v, unit)
  const U = UNITS[unit].label
  // مانده هر مشتری به تفکیک ماه فاکتورها (همان روش «بدهی هر مشتری به تفکیک ماه»): تا پایان ماه پورسانت و بعد از آن تا امروز
  const next = (mm) => { const y = +mm.slice(0, 4), n = +mm.slice(5, 7); return n === 12 ? `${y + 1}/01` : `${y}/${String(n + 1).padStart(2, '0')}` }
  const upLabel = `تا پایان ${monthName(month)}`
  const afterLabel = month >= current ? 'بعد از این ماه' : next(month) === current ? `ماه جاری (${monthName(current)})` : `بعد از ${monthName(month)} تا امروز`
  const split = (byMonth, total) => {
    if (!byMonth || !Object.keys(byMonth).length) return { up: total || 0, after: 0 }
    let up = 0, after = 0
    for (const [mm, a] of Object.entries(byMonth)) { if (mm > month) after += a; else up += a }
    return { up, after }
  }
  const rowsX = list.map((v) => {
    const debtors = [...(v.fin.debtors || [])].sort((a, b) => b.amount_rial - a.amount_rial).map((d) => ({ ...d, ...split(d.by_month, d.amount_rial) }))
    return { v, debtors, up: debtors.reduce((a, d) => a + d.up, 0), after: debtors.reduce((a, d) => a + d.after, 0) }
  })
  const tbl = (head, numFrom, body) => (
    <div className="table-scroll"><table><thead><tr>{head.map((h, i) => <th key={i} className={i >= numFrom ? 'num' : ''}>{h}</th>)}</tr></thead>
      <tbody>{body}</tbody></table></div>)
  const sum = (k) => list.reduce((a, v) => a + (v[k] || 0), 0)
  const sumX = (k) => rowsX.reduce((a, r) => a + r[k], 0)
  return (
    <Card title={title}
      subtitle={`مانده بدهی و بدهکاران از بخش مالی؛ «${upLabel}» و «${afterLabel}» = مانده به تفکیک ماه فاکتورها (پرداخت‌ها اول قدیمی‌ترین بدهی را تسویه می‌کنند)؛ توزیع‌نشده = فاکتورهای بدون حواله خروج (تب «توزیع بار»)؛ بدهی نهایی = مانده بدهی − توزیع‌نشده. روی هر ویزیتور کلیک کنید.`}>
      <div className="table-scroll"><table>
        <thead><tr><th>ویزیتور</th><th className="num">مانده {upLabel} ({U})</th><th className="num">مانده {afterLabel} ({U})</th>
          <th className="num">مانده بدهی کل ({U})</th><th className="num">توزیع‌نشده ({U})</th><th className="num">بدهی نهایی ({U})</th>
          <th className="num">چک برگشتی ({U})</th><th className="num">مشتری بدهکار</th><th className="num">فاکتور توزیع‌نشده</th></tr></thead>
        <tbody>{rowsX.flatMap(({ v, debtors, up, after }) => {
          const x = v.fin
          const isOpen = open.has(v.id)
          const und = x.undistributed || []
          const chq = x.returned_cheques || []
          const head = (
            <tr key={v.id} className="clickable" onClick={() => toggle(v.id)}>
              <td>{isOpen ? '▾' : '◂'} {v.name}</td><td className="num">{m(up)}</td><td className="num">{m(after)}</td>
              <td className="num">{m(v.debt)}</td><td className="num">{m(v.undist)}</td>
              <td className="num"><b>{m(v.debt_final)}</b></td><td className="num">{m(v.returned)}</td>
              <td className="num">{fmtInt(x.debtor_customer_count)}</td><td className="num">{fmtInt(x.undistributed_count)}</td>
            </tr>)
          if (!isOpen) return [head]
          return [head, (
            <tr key={`${v.id}-d`}><td colSpan={9}>
              <p><b>مشتریان بدهکار</b> ({fmtInt(debtors.length)})</p>
              {debtors.length ? tbl(['کد مشتری', 'نام مشتری', 'قدیمی‌ترین بدهی', 'جدیدترین بدهی', 'سن بدهی (روز)',
                `${upLabel} (${U})`, `${afterLabel} (${U})`, `مانده کل (${U})`], 5, [
                ...debtors.map((d, i) => (
                  <tr key={i}><td>{faDigits(d.customer_code)}</td><td>{d.customer_name}</td>
                    <td title="تاریخ قدیمی‌ترین فاکتور (یا سررسید چک برگشتی) که هنوز در مانده این مشتری است">{d.oldest_date_jalali ? faDigits(d.oldest_date_jalali) : '—'}</td>
                    <td>{d.latest_date_jalali ? faDigits(d.latest_date_jalali) : '—'}</td>
                    <td className={isNum(d.age_days) && d.age_days > 90 ? 'neg' : ''}>{isNum(d.age_days) ? fmtInt(d.age_days) : '—'}</td>
                    <td className="num">{d.up ? m(d.up) : '—'}</td><td className="num">{d.after ? m(d.after) : '—'}</td>
                    <td className="num">{m(d.amount_rial)}</td></tr>)),
                <tr key="t" className="total-row"><td colSpan={5}>جمع {fmtInt(debtors.length)} مشتری</td>
                  <td className="num">{m(up)}</td><td className="num">{m(after)}</td><td className="num">{m(up + after)}</td></tr>])
                : <p className="muted">بدهکاری ندارد.</p>}
              <p><b>فاکتورهای توزیع‌نشده</b> ({fmtInt(und.length)})</p>
              {und.length ? tbl(['شماره فاکتور', 'تاریخ', 'مشتری', `مبلغ (${U})`], 3, und.map((d, i) => (
                <tr key={i}><td>{faDigits(d.number)}</td><td>{faDigits(d.date_jalali)}</td><td>{d.customer_name} ({faDigits(d.customer_code)})</td><td className="num">{m(d.amount_rial)}</td></tr>)))
                : <p className="muted">فاکتور توزیع‌نشده ندارد.</p>}
              <p><b>چک‌های برگشتی</b> ({fmtInt(chq.length)})</p>
              {chq.length ? tbl(['سریال', 'سررسید', 'مشتری', 'وضعیت', `مبلغ (${U})`], 4, chq.map((d, i) => (
                <tr key={i}><td>{faDigits(d.serial)}</td><td>{faDigits(d.due_date_jalali)}</td><td>{d.customer_name} ({faDigits(d.customer_code)})</td><td>{d.status}</td><td className="num">{m(d.amount_rial)}</td></tr>)))
                : <p className="muted">چک برگشتی ندارد.</p>}
            </td></tr>)]
        })}</tbody>
        <tfoot><tr className="total-row"><td>جمع</td>
          <td className="num">{m(sumX('up'))}</td><td className="num">{m(sumX('after'))}</td>
          <td className="num">{m(sum('debt'))}</td><td className="num">{m(sum('undist'))}</td><td className="num"><b>{m(sum('debt_final'))}</b></td>
          <td className="num">{m(sum('returned'))}</td>
          <td className="num">{fmtInt(list.reduce((a, v) => a + (v.fin.debtor_customer_count || 0), 0))}</td>
          <td className="num">{fmtInt(list.reduce((a, v) => a + (v.fin.undistributed_count || 0), 0))}</td></tr></tfoot>
      </table></div>
    </Card>
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
  if (v.type === 'channel') return (
    <div><p><b>{v.name}</b> — فروشنده {v.type_label} (شعبه {v.branch} کارآمد؛ خودکار، بیرون از فهرست ویزیتورها).</p>
      <ul className="small">
        <li>فروش ناخالص {monthName(data.month)}: {money(v.gross, unit)}؛ فروش خالص {money(v.net, unit)} (فروش {money(v.sales_net, unit)} منهای برگشتی {money(v.returns_net, unit)})؛ فروش خالص + درصد نقدی {money(v.net_cash, unit)}.</li>
        {v.mgmt_n > 0 && <li>{fa(v.mgmt_n)} فاکتور با تخفیف مدیریتی: ناخالص {money(v.mgmt_inv_gross, unit)}، تخفیف مدیریتی {money(v.mgmt_disc, unit)} (نرخ {fmtPct(v.mgmt_rate, 2)}).</li>}
        <li><b>هنوز دستورالعمل پورسانت ندارد</b>؛ پورسانت محاسبه نمی‌شود.</li>
      </ul>
    </div>)
  const head = <p><b>{v.name}</b> — {v.type_label}، {v.branch}. محاسبه طبق {r.title}.</p>
  const cashBase = r.comm_base === 'net_cash'
  const B = cashBase ? 'فروش خالص + درصد نقدی' : 'فروش خالص'  // نام مبنای پورسانت این ماه
  const netLine = (
    <li>فروش خالص {monthName(data.month)}: {money(v.net, unit)} (فروش {money(v.sales_net, unit)} منهای برگشتی {money(v.returns_net, unit)}{isNum(v.ret_sale) && <>: برگشت از فروش {money(v.ret_sale, unit)} و برگشت از توزیع {money(v.ret_dist, unit)}</>}). فروش خالص یعنی بعد از کسر برگشتی و همه تخفیف‌ها، بدون ارزش افزوده.
      {cashBase && <> تخفیف نقدی به آن برمی‌گردد: <b>فروش خالص + درصد نقدی = {money(v.net_cash, unit)}</b> ← مبنای پورسانت این ماه.</>}
    </li>)
  // «فاکتور ویژه»: عمده و/یا با تخفیف مدیریتی (طبق قاعده همان ماه) که نرخ ثابت پایه می‌گیرد، نه نرخ سطح
  const spRate = v.type === 'commission' ? r.commission.wholesale_rate : r.employed.wholesale_rate
  const kinds = [(r.special || []).includes('wholesale') && 'عمده باشد (مبلغ ناخالص فاکتور بیش از ۷۰۰ میلیون تومان)',
    (r.special || []).includes('mgmt') && 'تخفیف مدیریتی داشته باشد'].filter(Boolean).join(' یا ')
  const rateText = v.type === 'commission' ? `نرخ سطح (${fmtPct(v.rate, 2)})` : `نرخ نهایی (${fmtPct(v.rate, 2)})`
  const sMin = r.special_min || {}
  const wsShare = isNum(v.gross) && v.gross > 0 ? v.wholesale_gross / v.gross : null
  const mgShare = isNum(v.gross) && v.gross > 0 ? v.mgmt_disc / v.gross : null
  const hasWs = (r.special || []).includes('wholesale'), hasMg = (r.special || []).includes('mgmt')
  const wsLine = v.wholesale_n > 0 && (
    <li>{fa(v.wholesale_n)} فاکتور عمده (مبلغ ناخالص بالای ۷۰۰ میلیون تومان) داشته: {money(v.wholesale_gross, unit)} ناخالص، یعنی درصد عمده‌فروشی <b>{fmtPct(wsShare, 1)}</b> فروش ناخالص.
      {hasWs && isNum(sMin.wholesale) && (v.special_ws_on
        ? <> چون از {fmtPct(sMin.wholesale, 0)} کمتر نیست، این فاکتورها جدا با نرخ پایه حساب می‌شوند.</>
        : <> چون کمتر از {fmtPct(sMin.wholesale, 0)} است، <b>این فاکتورها جدا حساب نمی‌شوند</b> و با نرخ عادی می‌آیند.</>)}
      {v.wholesale_brands?.length > 0 && (
        <div className="table-scroll"><table>
          <thead><tr><th>برند</th><th className="num">مبلغ ناخالص</th><th className="num">فروش خالص</th>{cashBase && <th className="num">خالص + نقدی</th>}<th className="num">سهم از عمده</th></tr></thead>
          <tbody>{v.wholesale_brands.map((b) => (
            <tr key={b.brand}><td>{b.brand}</td><td className="num">{money(b.gross, unit)}</td><td className="num">{money(b.net, unit)}</td>
              {cashBase && <td className="num">{money(b.net_cash, unit)}</td>}<td className="num">{fmtPct(v.wholesale_gross > 0 ? b.gross / v.wholesale_gross : null, 1)}</td></tr>))}
          </tbody>
        </table></div>)}
    </li>)
  const mgLine = v.mgmt_n > 0 && (
    <li>{fa(v.mgmt_n)} فاکتور با تخفیف مدیریتی داشته: مبلغ ناخالص {money(v.mgmt_inv_gross, unit)}، خالص + نقدی {money(v.mgmt_inv_net_cash, unit)}،
      {' '}تخفیف مدیریتی {money(v.mgmt_disc, unit)} یعنی نرخ {fmtPct(v.mgmt_rate, 2)} روی همان فاکتورها؛ درصد فروش مدیریتی (تخفیف مدیریتی ÷ فروش ناخالص) <b>{fmtPct(mgShare, 2)}</b>.
      {hasMg && isNum(sMin.mgmt) && (v.special_mg_on
        ? <> چون بیشتر از {fmtPct(sMin.mgmt, 0)} است، این فاکتورها جدا با نرخ پایه حساب می‌شوند.</>
        : <> چون {fmtPct(sMin.mgmt, 0)} یا کمتر است، <b>این فاکتورها جدا حساب نمی‌شوند</b> و با نرخ عادی می‌آیند.</>)}
    </li>)
  const specialRule = isNum(spRate) && (
    <li><b>قاعده فاکتورهای ویژه این ماه:</b> هر فاکتوری که {kinds}، پورسانتش با نرخ پایه <b>{fmtPct(spRate, 0)}</b> حساب می‌شود، نه {rateText}.
      {' '}بقیه فروش با {rateText} حساب می‌شود.
      {(isNum(sMin.wholesale) || isNum(sMin.mgmt)) && <>{' '}شرط: فاکتورهای عمده فقط وقتی جدا حساب می‌شوند که درصد عمده‌فروشی فرد دست‌کم {fmtPct(sMin.wholesale, 0)} باشد
        {hasMg && <> و فاکتورهای با تخفیف مدیریتی فقط وقتی که درصد فروش مدیریتی بیش از {fmtPct(sMin.mgmt, 0)} باشد</>}؛ وگرنه همان فاکتورها با نرخ عادی می‌آیند.</>}
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
  const rows = rosterOf(data).filter((v) => (type === 'all' || v.type === type)
    && (!q || `${v.name} ${v.branch} ${v.code} ${v.supervisor}`.includes(q.trim())))
  const dirty = Object.keys(draft).length
  const save = async () => {
    try { onSaved(await sendJson('/api/commission', 'PUT', { month: data.month, targets: draft })); setDraft({}) } catch (e) { setErr(e.message) }
  }
  const template = () => {
    const headers = [{ label: 'شناسه', kind: 'text' }, { label: 'شعبه', kind: 'text' }, { label: 'سرپرست', kind: 'text' }, { label: 'کد', kind: 'text' },
      { label: 'نام', kind: 'text' }, { label: 'نوع', kind: 'text' }, { label: 'تارگت ریالی (ریال)', kind: 'money' },
      ...groups.map((g) => ({ label: `${g} (تعداد)`, kind: 'int' }))]
    const body = rosterOf(data).map((v) => {
      const t = val(v.id)
      return [v.id, v.branch, v.supervisor, v.code, v.name, v.type_label, t.rial ? Math.round(t.rial) : '', ...groups.map((g) => t.groups?.[g] || '')]
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
  const list = draft ?? rosterOf(data).map(({ id, branch, supervisor, code, name, phone, phone_from, karamad_name, type, note }) => ({ id, branch, supervisor, code, name, phone, phone_from, karamad_name, type, note }))
  const byId = Object.fromEntries(rosterOf(data).map((v) => [v.id, v]))
  const setType = (id, type) => setDraft(list.map((v) => (v.id === id ? { ...v, type } : v)))
  const save = async () => {
    try { onSaved(await sendJson('/api/commission', 'PUT', { month: data.month, visitors: list })) } catch (e) { setErr(e.message) }
  }
  const upload = async (f) => { try { onSaved(await uploadXlsx(data.month, 'roster', f)) } catch (e) { setErr(e.message) } }
  const enrich = async () => { try { onSaved(await fetchJson(`/api/commission/enrich?month=${encodeURIComponent(data.month)}`, { method: 'POST' })) } catch (e) { setErr(e.message) } }
  const missing = rosterOf(data).filter((v) => !v.seller_key)
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
        { value: 'achievement', label: 'تحقق تارگت' }, { value: 'sheet', label: 'پورسانت' }, { value: 'summary', label: 'گزارش کلی' },
        { value: 'setup', label: 'تارگت و فهرست' }, { value: 'rules', label: 'دستورالعمل' }]} />}
        title={{ achievement: `عملکرد و تحقق تارگت ${monthName(data.month)}`, sheet: `پورسانت ${monthName(data.month)}`, summary: `گزارش کلی پورسانت ${monthName(data.month)}`,
          setup: setup === 'targets' ? `تارگت ${monthName(data.month)}` : 'فهرست ویزیتورها و نوع همکاری', rules: 'قواعد محاسبه' }[view]}
        subtitle={data.updated_at ? `آخرین ذخیره: ${faDigits(data.updated_at)}` : 'برای این ماه هنوز چیزی ذخیره نشده است.'}>
        {view === 'achievement' && <Achievement data={data} unit={unit} onSaved={onSaved} setErr={setErr} />}
        {view === 'sheet' && <Sheet data={data} />}
        {view === 'summary' && <Summary data={data} />}
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
