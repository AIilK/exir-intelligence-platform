import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useApp, useFetch, sendJson, fmtInt, fmtMoney, fmtPct, fmtNum1, fmtCompact, faDigits, isNum, detailPath, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, Tabs, Kpi, DataTable, Empty } from '../components/ui.jsx'
import { Chart, baseOption } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'

const SEP = '\x1f'
const TABS = [
  { value: 'set', label: 'تعیین تارگت' },
  { value: 'track', label: 'پایش ماه جاری' },
  { value: 'compare', label: 'مقایسه سالانه' },
  { value: 'eval', label: 'ارزیابی و تنظیمات' },
]
const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const monthName = (m) => (m ? `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}` : '—')
const STATUS = { green: 'روی مسیر', yellow: 'عقب، قابل جبران', red: 'نیاز به اقدام' }
const growthOf = (a, b) => (isNum(a) && isNum(b) && b > 0 ? a / b - 1 : null)

export default function Plan() {
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.value === sp.get('tab')) ? sp.get('tab') : 'set'
  const ov = useFetch('/api/plan/overview')
  return (
    <>
      <PageHead title="برنامه‌ریزی و تارگت"
        desc="تارگت ماهانه شعبه × گروه کالا (تعدادی و ریالی)، پایش تحقق و مقایسه با سال قبل. تارگت‌ها فقط در خود داشبورد ذخیره می‌شوند.">
        <Tabs tabs={TABS} value={tab} onChange={(v) => setSp({ tab: v })} />
      </PageHead>
      {ov.error && <ErrorBox error={ov.error} />}
      {!ov.data ? (!ov.error && <Loading />) : (
        <>
          {tab === 'set' && <SetTargets ov={ov.data} />}
          {tab === 'track' && <Track ov={ov.data} />}
          {tab === 'compare' && <Compare ov={ov.data} />}
          {tab === 'eval' && <Evaluate ov={ov.data} setOv={ov.setData} />}
        </>
      )}
    </>
  )
}

export function Alerts({ items }) {
  if (!items?.length) return null
  const one = (w, i) => (
    <div key={i} className={`alert ${w.level}`}>
      <span className="alert-icon" aria-hidden>{w.level === 'info' ? 'i' : '!'}</span>
      <span>{faDigits(w.text)}</span>
    </div>
  )
  // هشدارها همیشه دیده شوند؛ نکته‌های توضیحی جمع‌شده
  const main = [...items.filter((w) => w.level === 'danger'), ...items.filter((w) => w.level === 'warn')]
  const info = items.filter((w) => w.level === 'info')
  return (
    <div className="alerts">
      {main.map(one)}
      {info.length > 0 && (
        <details className="alert-more">
          <summary>{fmtInt(info.length)} نکته درباره نحوه محاسبه</summary>
          <div className="alerts">{info.map(one)}</div>
        </details>
      )}
    </div>
  )
}

// علامت +/− با Intl تا در متن راست‌به‌چپ سر جایش بماند
const signed = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0, signDisplay: 'exceptZero' })
const fmtSigned = (v) => (isNum(v) ? `${signed.format(v * 100)}٪` : '—')
const pctChip = (g) => (isNum(g) ? <span className={g < 0 ? 'neg-text' : 'pos-text'}>{fmtSigned(g)}</span> : '—')

// ---------------------------------------------------------------- ۱. تعیین تارگت
function SetTargets({ ov }) {
  const { unit } = useApp()
  const [month, setMonth] = useState(() => ov.months.find((m) => !m.locked)?.month || ov.current)
  const { data, error, setData } = useFetch(`/api/plan/target?month=${encodeURIComponent(month)}`)
  const [branch, setBranch] = useState(null)
  const [err, setErr] = useState(null)
  const [growth, setGrowth] = useState('')
  const [wd, setWd] = useState('')
  useEffect(() => {
    if (!data) return
    setGrowth(String(Math.round((data.plan.growth || 0) * 1000) / 10))
    setWd(data.plan.wd ? String(data.plan.wd) : '')
  }, [data])

  const save = async (body) => {
    setErr(null)
    try { setData(await sendJson('/api/plan/target', 'PUT', { month, ...body })) } catch (e) { setErr(e.message) }
  }
  if (error) return <ErrorBox error={error} />
  if (!data) return <Loading />
  const locked = !!data.plan.locked
  const t = data.total || {}
  return (
    <>
      <div className="plan-bar">
        <div className="seg" role="group" aria-label="ماه">
          {ov.months.map((m) => (
            <button key={m.month} className={m.month === month ? 'active' : ''} onClick={() => { setMonth(m.month); setBranch(null) }}>
              {monthName(m.month)}
              {m.current && <span className="tag">جاری</span>}
              {m.locked ? <span className="tag lock">قفل</span> : m.saved ? <span className="tag">ذخیره</span> : null}
            </button>
          ))}
        </div>
        <label className="inline-field">
          <span>رشد نسبت به پیشنهاد (٪)</span>
          <input className="input num-in" type="number" step="1" value={growth} disabled={locked}
            onChange={(e) => setGrowth(e.target.value)}
            onBlur={() => Number(growth) / 100 !== (data.plan.growth || 0) && save({ growth: Number(growth || 0) / 100 })}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
        </label>
        <label className="inline-field">
          <span>روز کاری ماه</span>
          <input className="input num-in" type="number" min="1" max="31" placeholder={fmtInt(data.wd_calendar)} value={wd}
            disabled={locked} onChange={(e) => setWd(e.target.value)}
            onBlur={() => (wd ? Number(wd) !== data.plan.wd && save({ wd: Number(wd) }) : data.plan.wd && save({ clear_wd: true }))}
            onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
        </label>
        <div className="spacer" />
        {!locked && data.n_overrides > 0 && (
          <button className="btn ghost" onClick={() => window.confirm('همه اصلاحات دستی این ماه حذف شوند؟') && save({ action: 'reset' })}>
            حذف اصلاحات دستی ({fmtInt(data.n_overrides)})
          </button>
        )}
        {locked
          ? <button className="btn ghost" onClick={() => save({ action: 'unlock' })}>باز کردن قفل</button>
          : <button className="btn" onClick={() => window.confirm(`تارگت ${monthName(month)} با قیمت‌های امروز قفل شود؟ بعد از قفل، اعداد با تغییر داده یا قیمت عوض نمی‌شوند.`) && save({ action: 'lock' })}>
            نهایی و قفل کردن</button>}
      </div>
      {err && <ErrorBox error={err} />}
      {locked && <div className="state ok small">تارگت {monthName(month)} در {faDigits(data.plan.locked_at)} قفل شده است. اعداد و قیمت‌ها ثابت‌اند؛ برای تغییر، قفل را باز کنید.</div>}
      <div className="kpis">
        <Kpi label="تارگت ریالی (خالص)" value={t.target_net} hint="تارگت تعدادی × قیمت خالص فعلی هر واحد (پس از تخفیف، بدون ارزش افزوده) — مبنای مقایسه با فروش خالص داشبورد" />
        <Kpi label="تارگت ریالی (ناخالص)" value={t.target_gross} hint="تارگت تعدادی × قیمت فروش (قبل از تخفیف)" />
        <Kpi label={`فروش خالص ${monthName(data.last_month)}`} value={t.last_net} sub={<>تارگت نسبت به آن: {pctChip(growthOf(t.target_net, t.last_net))}</>} />
        <Kpi label={`فروش خالص ${monthName(data.ly_month)}`} value={t.ly_net} sub={<>تارگت نسبت به آن: {pctChip(growthOf(t.target_net, t.ly_net))}</>}
          hint="همین ماه در سال قبل؛ بسیاری از شعب آن زمان تازه باز شده یا هنوز نبودند" />
        <Kpi label="روز کاری" value={data.wd} type="int" sub={data.plan.wd ? `اصلاح‌شده (تقویم: ${fmtInt(data.wd_calendar)})` : 'از تقویم کارآمد'} />
      </div>
      <Alerts items={data.warnings} />
      <div className="grid g2">
        <Card title="خلاصه گروه‌های کالا" subtitle="جمع همه شعب؛ تعدادی و ریالی خالص" className="span2">
          <DataTable rows={data.categories} unit={unit} pageSize={12} dense exportName={`target-categories-${month.replace('/', '-')}`}
            defaultSort={{ key: 'target_net', dir: 'desc' }}
            columns={[
              { key: 'category', label: 'گروه کالا', render: (r) => <>{r.category}{r.main && <span className="tag">اصلی</span>}</> },
              { key: 'suggest', label: 'پیشنهاد سیستم', type: 'int' },
              { key: 'final', label: 'تارگت نهایی', type: 'int' },
              { key: 'last', label: `فروش ${monthName(data.last_month)}`, type: 'int' },
              { key: 'ly', label: `فروش ${monthName(data.ly_month)}`, type: 'int' },
              { key: 'chg', label: 'تارگت / ماه قبل', type: 'pct', csv: (r) => { const g = growthOf(r.final, r.last); return isNum(g) ? Math.round(g * 1000) / 10 : '' }, render: (r) => pctChip(growthOf(r.final, r.last)) },
              { key: 'target_net', label: 'تارگت ریالی خالص', type: 'money' },
            ]} />
        </Card>
        <Card title="ماتریس تارگت تعدادی شعبه × گروه کالا" className="span2"
          subtitle="برای دیدن جزئیات و اصلاح دستی، روی یک شعبه کلیک کنید. خانه‌های آبی دستی اصلاح شده‌اند؛ علامت ! یعنی فاصله زیاد با ماه قبل.">
          <TargetMatrix data={data} unit={unit} selected={branch} onSelect={setBranch} />
        </Card>
        {branch && (
          <Card title={`تارگت ${branch} — همه گروه‌های کالا`} className="span2"
            subtitle={`ماه‌های پایه: ${faDigits((data.base_months[branch] || []).join('، ')) || '—'} · پیشنهاد = فروش روزانه پایه × ضریب فصل × روز کاری`}
            actions={<button className="btn ghost" onClick={() => setBranch(null)}>بستن</button>}>
            <BranchEditor data={data} branch={branch} unit={unit} locked={locked}
              onSave={(key, v) => save({ overrides: { [key]: v } })} />
          </Card>
        )}
      </div>
    </>
  )
}

function TargetMatrix({ data, unit, selected, onSelect }) {
  const { rows, main } = useMemo(() => {
    const by = {}
    for (const c of data.cells) {
      const r = (by[c.branch] ||= { branch: c.branch, other: 0, total: 0, cells: {} })
      r.total += c.target_net || 0
      if (c.main) r.cells[c.category] = c
      else r.other += c.target_net || 0
    }
    return { rows: Object.values(by).sort((a, b) => b.total - a.total), main: data.main }
  }, [data])
  return (
    <div className="table-scroll">
      <table className="matrix">
        <thead>
          <tr>
            <th>شعبه</th>
            {main.map((c) => <th key={c} className="num">{c}</th>)}
            <th className="num">سایر گروه‌ها <span className="th-unit">({UNITS[unit].label})</span></th>
            <th className="num">جمع ریالی <span className="th-unit">({UNITS[unit].label})</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.branch} className={`clickable ${selected === r.branch ? 'active-row' : ''}`} onClick={() => onSelect(r.branch)}>
              <td>{r.branch}</td>
              {main.map((c) => {
                const x = r.cells[c]
                return (
                  <td key={c} className={`num ${x?.override ? 'ov' : ''}`}
                    title={x ? `پیشنهاد: ${fmtInt(x.suggest)} · ماه قبل: ${fmtInt(x.last)} · سال قبل: ${fmtInt(x.ly)}` : undefined}>
                    {x ? fmtInt(x.final) : '—'}{x?.jump && <span className="jump" aria-label="فاصله زیاد با ماه قبل">!</span>}
                  </td>
                )
              })}
              <td className="num">{fmtMoney(r.other, unit)}</td>
              <td className="num strong">{fmtMoney(r.total, unit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BranchEditor({ data, branch, unit, locked, onSave }) {
  const rows = useMemo(() => data.cells.filter((c) => c.branch === branch)
    .sort((a, b) => (b.main - a.main) || (b.target_net - a.target_net)), [data, branch])
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>گروه کالا</th>
            <th className="num">فروش {monthName(data.last_month)}</th>
            <th className="num">فروش {monthName(data.ly_month)}</th>
            <th className="num" title="فروش هر روز کاری در ماه‌های پایه، پس از حذف اثر فصل">فروش روزانه پایه</th>
            <th className="num" title="ضریب فصلی ماه هدف (تعدیل‌شده)">ضریب فصل</th>
            <th className="num">پیشنهاد سیستم</th>
            <th className="num">تارگت نهایی</th>
            <th className="num" title="قیمت خالص فعلی هر واحد">قیمت خالص <span className="th-unit">(تومان)</span></th>
            <th className="num">تارگت ریالی <span className="th-unit">({UNITS[unit].label})</span></th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => <EditRow key={r.key} r={r} wd={data.wd} unit={unit} locked={locked} onSave={onSave} />)}
        </tbody>
      </table>
    </div>
  )
}

function EditRow({ r, wd, unit, locked, onSave }) {
  const [v, setV] = useState(String(r.final ?? ''))
  useEffect(() => { setV(String(r.final ?? '')) }, [r.final])
  const commit = () => {
    const n = Number(v)
    if (v === '' || !Number.isFinite(n) || n < 0) { setV(String(r.final)); return }
    if (n !== r.final) onSave(r.key, Math.round(n))
  }
  return (
    <tr className={r.main ? '' : 'minor'}>
      <td>{r.category}{r.main && <span className="tag">اصلی</span>}{r.jump && <span className="jump" title="بیش از ۲٫۵ برابر یا کمتر از ۴۰٪ فروش ماه قبل">!</span>}</td>
      <td className="num">{fmtInt(r.last)}</td>
      <td className="num">{fmtInt(r.ly)}</td>
      <td className="num">{fmtNum1(r.base)}</td>
      <td className="num">{isNum(r.idx) ? fmtNum1(r.idx * 100) + '٪' : '—'}</td>
      <td className="num" title={`${fmtNum1(r.base)} × ${fmtInt(wd)} روز × ${fmtNum1((r.idx || 1) * 100)}٪`}>{fmtInt(r.suggest)}</td>
      <td className="num">
        <input className={`input cell-in ${r.override ? 'ov' : ''}`} type="number" min="0" value={v} disabled={locked}
          aria-label={`تارگت ${r.category}`}
          onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} />
      </td>
      <td className="num">{isNum(r.price_net) ? fmtInt(r.price_net / 10) : '—'}</td>
      <td className="num">{fmtMoney(r.target_net, unit)}</td>
      <td>{r.override && !locked && <button className="link" onClick={() => onSave(r.key, null)} title="برگشت به پیشنهاد سیستم">برگشت</button>}</td>
    </tr>
  )
}

// ---------------------------------------------------------------- ۲. پایش ماه جاری
function Track({ ov }) {
  const { unit } = useApp()
  const nav = useNavigate()
  const { data, error } = useFetch('/api/plan/track')
  const [mode, setMode] = useState('qty')
  if (error) return <ErrorBox error={error} />
  if (!data) return <Loading />
  if (!data.cells.length) return <><Alerts items={data.warnings} /><Empty text="تارگتی برای ماه جاری وجود ندارد." /></>
  const t = data.total
  const st = (s) => (s ? `st-${s}` : '')
  return (
    <>
      <div className="kpis">
        <Kpi label={`تارگت ریالی ${monthName(ov.current)}`} value={t.target_net} sub={data.plan.locked ? 'قفل‌شده' : 'پیش‌نویس (قفل نشده)'} />
        <Kpi label="فروش خالص تا امروز" value={t.actual_net} sub={`${fmtInt(data.elapsed)} از ${fmtInt(data.wd_total)} روز کاری`} />
        <div className={`kpi ${st(t.status)}`} title="فروش تا پایان دیروز ÷ (تارگت × سهم معمول فروش تا این نقطه از ماه)">
          <div className="kpi-label">تحقق تا امروز</div>
          <div className="kpi-value">{fmtPct(t.ach_net, 0)}</div>
          <div className="kpi-sub">{STATUS[t.status] || '—'} · انتظار تا امروز: {fmtPct(data.expected_share, 0)} تارگت</div>
        </div>
        <Kpi label="پیش‌بینی پایان ماه" value={t.forecast_net} sub={<>نسبت به تارگت: {fmtPct(t.ratio, 0)}</>}
          hint="فروش تا دیروز ÷ سهم معمول فروش تا این نقطه (الگوی ماه‌های سالم قبل)" />
        <Kpi label="نیاز روزانه از امروز" value={t.need_daily_net}
          sub={<>میانگین روزانه فعلی: {fmtCompact(t.cur_daily_net).value} {fmtCompact(t.cur_daily_net).unit}</>}
          hint="(تارگت − فروش تا دیروز) ÷ روزهای کاری باقی‌مانده" />
      </div>
      <Alerts items={data.warnings} />
      <div className="grid g2">
        <Card title="ماتریس تحقق شعبه × گروه کالا" className="span2"
          subtitle={`درصد تحقق نسبت به انتظار تا امروز. سبز ≥ ${fmtPct(data.thresholds.green, 0)} پیش‌بینی/تارگت، زرد ≥ ${fmtPct(data.thresholds.yellow, 0)}، قرمز کمتر. روی خانه کلیک کنید تا جزئیات باز شود.`}
          actions={<Tabs value={mode} onChange={setMode} tabs={[{ value: 'qty', label: 'تعدادی' }, { value: 'net', label: 'ریالی' }]} />}>
          <TrackMatrix data={data} mode={mode} onCell={(b, c) => nav(c ? detailPath('category', c, [['branch', b]]) : detailPath('branch', b))} />
          <div className="legend-row">
            {['green', 'yellow', 'red'].map((s) => <span key={s} className={`legend st-${s}`}>{STATUS[s]}</span>)}
          </div>
        </Card>
        <Card title="شعب" subtitle="ریالی خالص" className="span2">
          <DataTable rows={data.branches.map((r) => ({ ...r, key: r.branch, label: r.branch }))} unit={unit} pageSize={25} dense
            exportName="track-branches" onRowClick={(r) => nav(detailPath('branch', r.branch))}
            columns={trackCols('شعبه')} />
        </Card>
        <Card title="گروه‌های کالا" subtitle="جمع همه شعب" className="span2">
          <DataTable rows={data.categories.map((r) => ({ ...r, key: r.category, label: r.category }))} unit={unit} pageSize={15} dense
            exportName="track-categories" onRowClick={(r) => nav(detailPath('category', r.category))}
            columns={[
              { key: 'label', label: 'گروه کالا' },
              { key: 'final', label: 'تارگت تعدادی', type: 'int' },
              { key: 'actual', label: 'فروش تعدادی', type: 'int' },
              { key: 'ach', label: 'تحقق تعدادی', type: 'pct', render: (r) => <StatusPct v={r.ach} s={r.status} /> },
              ...trackCols().slice(1),
            ]} />
        </Card>
      </div>
    </>
  )
}

const StatusPct = ({ v, s }) => <span className={`pill st-${s || 'none'}`}>{fmtPct(v, 0)}</span>

const trackCols = (label = 'نام') => [
  { key: 'label', label },
  { key: 'target_net', label: 'تارگت ریالی', type: 'money' },
  { key: 'actual_net', label: 'فروش تا امروز', type: 'money' },
  { key: 'ach_net', label: 'تحقق', type: 'pct', render: (r) => <StatusPct v={r.ach_net} s={r.status} /> },
  { key: 'forecast_net', label: 'پیش‌بینی پایان ماه', type: 'money' },
  { key: 'need_daily_net', label: 'نیاز روزانه', type: 'money', hint: '(تارگت − فروش تا دیروز) ÷ روزهای کاری باقی‌مانده' },
  { key: 'cur_daily_net', label: 'میانگین روزانه فعلی', type: 'money' },
]

function TrackMatrix({ data, mode, onCell }) {
  const rows = useMemo(() => {
    const by = Object.fromEntries(data.branches.map((b) => [b.branch, { ...b, cells: {} }]))
    for (const c of data.cells) if (c.main && by[c.branch]) by[c.branch].cells[c.category] = c
    return data.branches.map((b) => by[b.branch])
  }, [data])
  return (
    <div className="table-scroll">
      <table className="matrix">
        <thead>
          <tr>
            <th>شعبه</th>
            {data.main.map((c) => <th key={c} className="num">{c}</th>)}
            <th className="num">کل شعبه (ریالی)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.branch}>
              <td className="clickable-cell" onClick={() => onCell(r.branch)}>{r.branch}</td>
              {data.main.map((c) => {
                const x = r.cells[c]
                const v = x && (mode === 'qty' ? x.ach : x.ach_net)
                const has = x && x.final > 0
                return (
                  <td key={c} className={`num heat ${has ? `st-${x.status || 'none'}` : ''}`} onClick={() => onCell(r.branch, c)}
                    title={x ? `تارگت ${fmtInt(x.final)} · فروش ${fmtInt(x.actual)} · پیش‌بینی ${fmtInt(x.forecast)}` : undefined}>
                    {has ? fmtPct(v, 0) : '—'}
                  </td>
                )
              })}
              <td className={`num heat strong st-${r.status || 'none'}`} onClick={() => onCell(r.branch)}>{fmtPct(r.ach_net, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------- ۳. مقایسه سالانه
function Compare({ ov }) {
  const { unit } = useApp()
  const [cat, setCat] = useState('')
  const [br, setBr] = useState('')
  const [metric, setMetric] = useState('qty')
  const [lfl, setLfl] = useState(false)
  const q = new URLSearchParams({ metric, lfl: lfl ? '1' : '0' })
  if (cat) q.set('category', cat)
  if (br) q.set('branch', br)
  const { data, error } = useFetch(`/api/plan/compare?${q}`)
  const money = metric !== 'qty'
  const f = (v) => (money ? fmtMoney(v, unit) : fmtInt(v))
  const cats = [...ov.main, ...ov.categories.filter((c) => !ov.main.includes(c))]
  return (
    <>
      <div className="plan-bar">
        <label className="inline-field"><span>گروه کالا</span>
          <select value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">همه گروه‌ها</option>
            {cats.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="inline-field"><span>شعبه</span>
          <select value={br} onChange={(e) => setBr(e.target.value)}>
            <option value="">همه شعب</option>
            {ov.branches.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
        <Tabs value={metric} onChange={setMetric}
          tabs={[{ value: 'qty', label: 'تعدادی' }, { value: 'net', label: 'ریالی خالص' }, { value: 'gross', label: 'ریالی ناخالص' }]} />
        <label className="check" title="در هر ماه فقط شعبه‌هایی که در همان ماه هر دو سال فروش داشته‌اند؛ رشد ناشی از باز شدن شعبه جدید حذف می‌شود">
          <input type="checkbox" checked={lfl} onChange={(e) => setLfl(e.target.checked)} /> فقط شعب مشترک دو سال
        </label>
      </div>
      {error && <ErrorBox error={error} />}
      {!data ? !error && <Loading /> : (
        <>
          <div className="kpis">
            <Kpi label={`تجمعی ${faDigits(data.year)} (تا ${monthName(data.ytd_month ? `${data.year}/${data.ytd_month}` : null)})`}
              value={data.ytd_cur} type={money ? 'money' : 'int'} />
            <Kpi label={`تجمعی ${faDigits(data.prev)} (همان بازه)`} value={data.ytd_prev} type={money ? 'money' : 'int'} />
            <div className="kpi">
              <div className="kpi-label">رشد تجمعی</div>
              <div className="kpi-value">{pctChip(data.ytd_growth)}</div>
              <div className="kpi-sub">{lfl ? 'فقط شعب مشترک' : 'همه شعب (شامل شعب تازه)'}</div>
            </div>
          </div>
          <div className="grid g2">
            <Card title={`فروش ماهانه ${faDigits(data.prev)} و ${faDigits(data.year)}${money ? ` (${UNITS[unit].label})` : ''}`} className="span2"
              subtitle="ستون‌های خاکستری سال قبل، آبی امسال؛ خط‌چین نارنجی تارگت. ماه‌های غیرعادی (جنگ، قطعی اینترنت، فروردین) سایه خورده‌اند؛ ماه جاری هنوز کامل نشده.">
              <CompareChart data={data} f={f} />
            </Card>
            <Card title="فروش تجمعی از ابتدای سال" className="span2">
              <CumChart data={data} f={f} />
            </Card>
            <Card title="جدول ماهانه" className="span2">
              <div className="table-scroll">
                <table>
                  <thead><tr><th>ماه</th><th className="num">{faDigits(data.prev)}</th><th className="num">{faDigits(data.year)}</th>
                    <th className="num">رشد</th><th className="num">تارگت</th><th className="num">تحقق</th><th>توضیح</th></tr></thead>
                  <tbody>
                    {data.rows.map((r) => (
                      <tr key={r.mm} className={r.abn_cur || r.abn_prev ? 'abn-row' : ''}>
                        <td>{MONTHS[Number(r.mm) - 1]}</td>
                        <td className="num">{f(r.prev)}</td>
                        <td className="num">{f(r.cur)}</td>
                        <td className="num">{r.partial ? '—' : pctChip(growthOf(r.cur, r.prev))}</td>
                        <td className="num">{f(r.target)}</td>
                        <td className="num">{isNum(r.target) && isNum(r.cur) && !r.partial ? fmtPct(r.cur / r.target, 0) : '—'}</td>
                        <td className="muted small">{[r.partial && 'ماه جاری (ناقص)', r.abn_prev && `${faDigits(data.prev)} غیرعادی`, r.abn_cur && `${faDigits(data.year)} غیرعادی`].filter(Boolean).join('، ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </>
  )
}

// سایه ماه‌های غیرعادی: میله پس‌زمینه تمام‌عرض روی محور دسته‌ای دوم و پنهان
// (markArea روی محور دسته‌ای معکوس یک خانه جابه‌جا رسم می‌شود)
function abnShade(rows, labels, values, t) {
  const nums = values.filter(isNum)
  const hi = Math.max(0, ...nums) * 1.05
  const lo = Math.min(0, ...nums) * 1.05
  const color = t.dark ? 'rgba(201,133,0,.16)' : 'rgba(237,161,0,.14)'
  const flag = rows.map((r) => r.abn_cur || r.abn_prev)
  return {
    axis: { type: 'category', data: labels, inverse: true, show: false },
    series: [
      { name: 'abn-hi', type: 'bar', xAxisIndex: 1, silent: true, barWidth: '100%', z: 0, itemStyle: { color }, tooltip: { show: false },
        data: flag.map((f) => (f ? hi : null)) },
      { name: 'abn-lo', type: 'bar', xAxisIndex: 1, silent: true, barWidth: '100%', barGap: '-100%', z: 0, itemStyle: { color }, tooltip: { show: false },
        data: flag.map((f) => (f && lo < 0 ? lo : null)) },
    ],
  }
}
const realSeries = (ps) => ps.filter((p) => !String(p.seriesName).startsWith('abn-'))

function CompareChart({ data, f }) {
  const labels = data.rows.map((r) => MONTHS[Number(r.mm) - 1] + (r.partial ? ' *' : ''))
  const vals = data.rows.flatMap((r) => [r.prev, r.cur, r.target])
  return (
    <Chart height={340} option={(t) => {
      const sh = abnShade(data.rows, labels, vals, t)
      const names = [`فروش ${faDigits(data.prev)}`, `فروش ${faDigits(data.year)}`, 'تارگت']
      return {
      grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: t.text }, itemGap: 16, data: names },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (ps) => `${labels[ps[0].dataIndex]}<br/>` + realSeries(ps).map((p) => `${p.marker} ${p.seriesName}: <b>${f(p.value)}</b>`).join('<br/>') },
      xAxis: [{ type: 'category', data: labels, inverse: true, axisLabel: { color: t.text, interval: 0 },
        axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } }, sh.axis],
      yAxis: { type: 'value', position: 'right', axisLabel: { color: t.text, formatter: (v) => f(v) }, splitLine: { lineStyle: { color: t.grid } } },
      series: [
        ...sh.series,
        { name: names[0], type: 'bar', data: data.rows.map((r) => r.prev), barMaxWidth: 18, z: 2,
          itemStyle: { color: t.dark ? '#6b6a64' : '#b4b2a9', borderRadius: [4, 4, 0, 0] } },
        { name: names[1], type: 'bar', data: data.rows.map((r) => r.cur), barMaxWidth: 18, z: 2,
          itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] } },
        { name: names[2], type: 'line', data: data.rows.map((r) => r.target), connectNulls: false, symbolSize: 8, z: 3,
          lineStyle: { type: 'dashed', width: 2, color: t.series[1] }, itemStyle: { color: t.series[1], borderColor: t.surface, borderWidth: 2 } },
      ],
      }
    }} />
  )
}

function CumChart({ data, f }) {
  const cum = (key) => { let s = 0; return data.rows.map((r) => (r[key] == null ? null : (s += r[key]))) }
  const prev = cum('prev'), cur = cum('cur')
  return (
    <Chart height={240} option={(t) => {
      const sh = abnShade(data.rows, MONTHS, [...prev, ...cur], t)
      const names = [`تجمعی ${faDigits(data.prev)}`, `تجمعی ${faDigits(data.year)}`]
      return {
      grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: t.text }, data: names },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps) => `${MONTHS[ps[0].dataIndex]}<br/>` + realSeries(ps).map((p) => `${p.marker} ${p.seriesName}: <b>${f(p.value)}</b>`).join('<br/>') },
      xAxis: [{ type: 'category', data: MONTHS, inverse: true, axisLabel: { color: t.text, interval: 0 }, axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } }, sh.axis],
      yAxis: { type: 'value', position: 'right', axisLabel: { color: t.text, formatter: (v) => f(v) }, splitLine: { lineStyle: { color: t.grid } } },
      series: [
        ...sh.series,
        { name: names[0], type: 'line', data: prev, symbolSize: 6, z: 3,
          lineStyle: { width: 2, type: 'dashed', color: t.dark ? '#8f8e86' : '#888780' }, itemStyle: { color: t.dark ? '#8f8e86' : '#888780' } },
        { name: names[1], type: 'line', data: cur, symbolSize: 8, z: 3,
          lineStyle: { width: 2, color: t.series[0] }, itemStyle: { color: t.series[0], borderColor: t.surface, borderWidth: 2 } },
      ],
      }
    }} />
  )
}

// ---------------------------------------------------------------- ۴. ارزیابی و تنظیمات
const METHOD = { model: 'روش داشبورد (پایه + فصل)', no_season: 'همان روش بدون فصل', naive: 'ساده: تکرار ماه قبل' }

function Evaluate({ ov, setOv }) {
  const { data, error } = useFetch('/api/plan/eval')
  const { reload } = useApp()
  const se = ov.season
  return (
    <div className="grid g2">
      <Card title="دقت روش پیشنهاد (بک‌تست)" className="span2"
        subtitle="برای هر ماه سالم گذشته، پیشنهاد فقط با داده قبل از آن ماه ساخته و با فروش واقعی مقایسه شده است (خطا به ریال خالص). عدد کمتر = بهتر.">
        {error && <ErrorBox error={error} />}
        {!data ? !error && <Loading /> : (
          <>
            <div className="table-scroll">
              <table>
                <thead><tr><th>روش</th><th className="num" title="Σ|پیشنهاد − واقعی| ÷ Σ واقعی در سطح شعبه × گروه">خطای شعبه × گروه</th>
                  <th className="num">خطای سطح شعبه</th><th className="num">خطای کل شرکت</th><th className="num" title="مثبت = بیش‌برآورد">سوگیری</th></tr></thead>
                <tbody>
                  {['model', 'no_season', 'naive'].map((m) => {
                    const s = data.backtest.summary.find((x) => x.method === m)
                    return s && (
                      <tr key={m} className={m === 'model' ? 'active-row' : ''}>
                        <td>{METHOD[m]}</td><td className="num">{fmtPct(s.cell, 0)}</td><td className="num">{fmtPct(s.branch, 0)}</td>
                        <td className="num">{fmtPct(s.total, 0)}</td><td className="num">{fmtSigned(s.bias)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className="table-scroll" style={{ marginTop: 12 }}>
              <table className="dense">
                <thead><tr><th>ماه</th><th className="num">پیشنهاد (ریالی)</th><th className="num">واقعی (ریالی)</th>
                  <th className="num">خطای کل</th><th className="num">خطای شعبه</th></tr></thead>
                <tbody>
                  {data.backtest.rows.filter((r) => r.method === 'model').map((r) => (
                    <tr key={r.month}><td>{monthName(r.month)}</td><td className="num">{fmtMoney(r.suggest_net, 'billion')}</td>
                      <td className="num">{fmtMoney(r.actual_net, 'billion')}</td><td className="num">{fmtSigned(r.total)}</td>
                      <td className="num">{fmtPct(r.branch, 0)}</td></tr>
                  ))}
                </tbody>
              </table>
              <div className="muted small">مبالغ به میلیارد تومان. فروش ماهانه این کانال نوسان زیادی دارد (مثلاً جهش شهریور یا افت بعد از جنگ)؛ برای همین تارگت پیشنهادی نقطه شروع است و اصلاح دستی و ضریب رشد لازم است.</div>
            </div>
          </>
        )}
      </Card>
      <Card title="ضریب‌های فصلی" subtitle={se.available
        ? `از ${faDigits(se.years)} سال تاریخچه قدیمی هیبرید (${faDigits(se.first)} تا ${faDigits(se.last)})؛ میله کم‌رنگ ضریب خام، پررنگ ضریب اعمال‌شده (تعدیل به سمت ۱)`
        : 'تاریخچه قدیمی هنوز از دیتابیس خوانده نشده یا داده کافی ندارد.'}>
        {se.available && <SeasonChart se={se} />}
      </Card>
      <Card title="الگوی فروش در طول ماه"
        subtitle={data?.curve?.linear ? 'الگو در دسترس نیست؛ انتظار خطی استفاده می‌شود.' : `میانه ${faDigits(data?.curve?.months ?? '')} ماه سالم: سهم فروش ماه تا هر نقطه، در برابر خط مستقیم`}>
        {data && <CurveChart c={data.curve} />}
      </Card>
      {data?.history?.length > 0 && (
        <Card title="تاریخچه تحقق تارگت" className="span2">
          <DataTable rows={data.history.map((r, i) => ({ ...r, key: i, label: monthName(r.month) }))} pageSize={20} dense unit="billion"
            columns={[{ key: 'label', label: 'ماه' }, { key: 'branch', label: 'شعبه' }, { key: 'target_net', label: 'تارگت', type: 'money' },
              { key: 'actual_net', label: 'فروش', type: 'money' }, { key: 'ach', label: 'تحقق', type: 'pct' }]} />
        </Card>
      )}
      <Card title="تنظیمات" className="span2">
        <SettingsForm ov={ov} onSaved={(o) => { setOv(o); reload() }} />
      </Card>
    </div>
  )
}

function SeasonChart({ se }) {
  const mms = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, '0'))
  return (
    <Chart height={260} option={(t) => ({
      grid: { left: 12, right: 12, top: 12, bottom: 8, containLabel: true },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps) => `${MONTHS[ps[0].dataIndex]}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtPct(p.value, 0)}</b>`).join('<br/>') },
      xAxis: { type: 'category', data: MONTHS, inverse: true, axisLabel: { color: t.text, interval: 0, rotate: 40 }, axisTick: { show: false } },
      yAxis: { type: 'value', position: 'right', axisLabel: { color: t.text, formatter: (v) => fmtPct(v, 0) }, splitLine: { lineStyle: { color: t.grid } } },
      series: [
        { name: 'ضریب خام', type: 'bar', data: mms.map((m) => se.total[m] ?? null), barMaxWidth: 14, itemStyle: { color: t.dark ? '#33507a' : '#b5d4f4', borderRadius: [3, 3, 0, 0] },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: t.axis, type: 'dashed' }, label: { show: false }, data: [{ yAxis: 1 }] } },
        { name: 'اعمال‌شده', type: 'bar', data: mms.map((m) => se.applied[m]), barMaxWidth: 14, itemStyle: { color: t.series[0], borderRadius: [3, 3, 0, 0] } },
      ],
    })} />
  )
}

function CurveChart({ c }) {
  return (
    <Chart height={260} option={(t) => ({
      grid: { left: 12, right: 12, top: 12, bottom: 24, containLabel: true },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis', formatter: (ps) => `${fmtPct(ps[0].value[0], 0)} روزهای کاری<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtPct(p.value[1], 0)}</b>`).join('<br/>') },
      xAxis: { type: 'value', min: 0, max: 1, inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtPct(v, 0) }, splitLine: { show: false },
        name: 'سهم روزهای کاری سپری‌شده', nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: t.text } },
      yAxis: { type: 'value', min: 0, max: 1, position: 'right', axisLabel: { color: t.text, formatter: (v) => fmtPct(v, 0) }, splitLine: { lineStyle: { color: t.grid } } },
      series: [
        { name: 'الگوی واقعی', type: 'line', showSymbol: false, data: c.grid.map((g, i) => [g, c.curve[i]]), lineStyle: { width: 2, color: t.series[0] }, areaStyle: { color: t.series[0], opacity: 0.08 } },
        { name: 'خطی', type: 'line', showSymbol: false, data: [[0, 0], [1, 1]], lineStyle: { width: 1, type: 'dashed', color: t.axis } },
      ],
    })} />
  )
}

function SettingsForm({ ov, onSaved }) {
  const s = ov.settings
  const [f, setF] = useState(() => ({
    abnormal: s.abnormal_months.join('، '), farvardin: !!s.farvardin_abnormal, base: s.base_months, season: !!s.season,
    shrink: Math.round(s.season_shrink * 100), green: Math.round(s.green * 100), yellow: Math.round(s.yellow * 100),
    alert: Math.round(s.price_alert * 1000) / 10,
  }))
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async () => {
    setErr(null); setMsg(null)
    const months = f.abnormal.replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).split(/[,،\s]+/).filter(Boolean)
    const bad = months.filter((m) => !/^\d{4}[/-]\d{2}$/.test(m))
    if (bad.length) { setErr(`ماه نامعتبر: ${bad.join('، ')} — قالب درست: 1404/10`); return }
    try {
      onSaved(await sendJson('/api/plan/settings', 'PUT', {
        abnormal_months: months, farvardin_abnormal: f.farvardin, base_months: Number(f.base), season: f.season,
        season_shrink: Number(f.shrink) / 100, green: Number(f.green) / 100, yellow: Number(f.yellow) / 100, price_alert: Number(f.alert) / 100,
      }))
      setMsg('تنظیمات ذخیره شد.')
    } catch (e) { setErr(e.message) }
  }
  return (
    <>
      <div className="settings-grid">
        <label className="field wide"><span>ماه‌های غیرعادی (در محاسبات استفاده نمی‌شوند)</span>
          <input className="input ltr" value={f.abnormal} onChange={set('abnormal')} placeholder="1404/10، 1404/11" /></label>
        <label className="check"><input type="checkbox" checked={f.farvardin} onChange={set('farvardin')} /> همه فروردین‌ها غیرعادی‌اند (نوروز)</label>
        <label className="field"><span>تعداد ماه‌های پایه</span>
          <input className="input" type="number" min="1" max="6" value={f.base} onChange={set('base')} /></label>
        <label className="check"><input type="checkbox" checked={f.season} onChange={set('season')} /> اعمال ضریب فصلی</label>
        <label className="field"><span>شدت ضریب فصلی (٪)</span>
          <input className="input" type="number" min="0" max="100" value={f.shrink} disabled={!f.season} onChange={set('shrink')} /></label>
        <label className="field"><span>آستانه سبز: پیش‌بینی ÷ تارگت (٪)</span>
          <input className="input" type="number" min="0" max="200" value={f.green} onChange={set('green')} /></label>
        <label className="field"><span>آستانه زرد (٪)</span>
          <input className="input" type="number" min="0" max="200" value={f.yellow} onChange={set('yellow')} /></label>
        <label className="field"><span>هشدار تغییر قیمت بیش از (٪)</span>
          <input className="input" type="number" min="0" step="0.5" value={f.alert} onChange={set('alert')} /></label>
      </div>
      <div className="muted small">
        پیش‌فرض‌ها: ماه‌های غیرعادی {faDigits(ov.defaults.abnormal_months.join('، '))}، {faDigits(ov.defaults.base_months)} ماه پایه، شدت فصل {faDigits(Math.round(ov.defaults.season_shrink * 100))}٪ (بهترین نتیجه در بک‌تست).
        تاریخچه قدیمی و تقویم هفته‌ای یک بار از دیتابیس خوانده می‌شوند{ov.inputs_fetched ? ` (آخرین بار ${faDigits(ov.inputs_fetched)})` : ''}.
      </div>
      {err && <div className="state error small">{err}</div>}
      {msg && <div className="state ok small">{msg}</div>}
      <button className="btn" onClick={save}>ذخیره تنظیمات</button>
    </>
  )
}
