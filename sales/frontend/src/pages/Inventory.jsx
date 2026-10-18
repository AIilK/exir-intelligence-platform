import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApp, useFetch, sendJson, fetchJson, fmtInt, fmtMoney, fmtPct, fmtNum1, faDigits, isNum, UNITS } from '../lib.jsx'
import { Card, Loading, ErrorBox, Tabs, Kpi, DataTable } from '../components/ui.jsx'
import { Chart, HBar, baseOption, useTheme } from '../components/Chart.jsx'
import { brandColor } from '../brands.js'
import { Spark } from '../components/TreeTable.jsx'
import { PageHead } from '../components/Layout.jsx'
import { Alerts } from './Plan.jsx'

const TABS = [
  { value: 'branches', label: 'نمای کلی شعب' },
  { value: 'summary', label: 'خلاصه مدیریتی' },
  { value: 'order', label: 'پیشنهاد سفارش و هشدارها' },
  { value: 'all', label: 'همه کالاها' },
  { value: 'supplier', label: 'تأمین‌کنندگان' },
  { value: 'idle', label: 'راکد و مازاد' },
  { value: 'settings', label: 'تنظیمات و روش' },
]
// تب‌های سطح شرکت (همه شعب)؛ بقیه تب‌ها برای شعبه انتخاب‌شده‌اند
const GLOBAL_TABS = new Set(['branches'])
const BRANCH_KEY = 'sd.invBranch'
const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const monthName = (m) => (m ? `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}` : '—')
const dayName = (d) => (d ? `${faDigits(Number(d.slice(8, 10)))} ${MONTHS[Number(d.slice(5, 7)) - 1]}` : '—')
// رنگ وضعیت: قرمز و نارنجی نیاز به اقدام؛ بقیه خنثی
const ST_CLASS = { red: 'st-red', orange: 'st-yellow', ok: 'st-green', excess: 'st-none', dead: 'st-none', c: 'st-none', nodata: 'st-none' }


function StatusPill({ s, labels }) {
  return <span className={`pill ${ST_CLASS[s] || 'st-none'}`}>{labels[s] || s}</span>
}

export default function Inventory() {
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.value === sp.get('tab')) ? sp.get('tab') : 'summary'
  const [branch, setBranchState] = useState(() => {
    try { return sp.get('branch') || localStorage.getItem(BRANCH_KEY) || '' } catch { return sp.get('branch') || '' }
  })
  const q = branch ? `?branch=${encodeURIComponent(branch)}` : ''
  const { data, error, setData } = useFetch(GLOBAL_TABS.has(tab) && !branch ? null : `/api/inventory${q}`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  // فیلتر وضعیت جدول سفارش و نوع فهرست راکد/مازاد؛ کارت‌ها با کلیک آن‌ها را تنظیم می‌کنند
  const [status, setStatus] = useState('need')
  const [idle, setIdle] = useState('dead')
  const setBranch = (b) => {
    setBranchState(b)
    try { localStorage.setItem(BRANCH_KEY, b) } catch { /* ignore */ }
  }
  const go = (t, extra) => {
    if (t === 'order') setStatus(extra)
    if (t === 'idle') setIdle(extra)
    setSp({ tab: t })
  }
  const openBranch = (b) => { setBranch(b); setStatus('need'); setSp({ tab: 'order' }) }
  const refresh = async () => {
    setBusy(true); setErr(null)
    try { setData(await fetchJson(`/api/inventory${q ? `${q}&` : '?'}refresh=true`)) } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const global = GLOBAL_TABS.has(tab)
  return (
    <>
      <PageHead title="موجودی و سفارش"
        desc={global ? 'همه شعب هیبرید: وضعیت انبار و سفارش‌ها. موجودی از کارآمد فقط خوانده می‌شود.'
          : data ? `${data.branch} — هشدار کمبود، پیشنهاد سفارش (حداکثر دو سفارش در ماه) و کالاهای راکد. موجودی از کارآمد فقط خوانده می‌شود.`
            : 'هشدار کمبود، پیشنهاد سفارش و کالاهای راکد'}>
        <Tabs tabs={TABS} value={tab} onChange={(v) => setSp({ tab: v })} />
      </PageHead>
      {tab === 'branches' && <BranchesTab onOpen={openBranch} current={data?.branch} />}
      {!global && (
        <>
          {(error || err) && <ErrorBox error={error || err} />}
          {data && (
            <div className="plan-bar">
              <label className="inline-field">
                <span>شعبه</span>
                <select value={data.branch} onChange={(e) => setBranch(e.target.value)}>
                  {data.branches.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </label>
              {data.inactive && <span className="pill st-red">شعبه غیرفعال</span>}
              {data.data_issue && <span className="pill st-yellow">داده خرید ناقص</span>}
              {data.break_month && <span className="pill st-yellow">پایه از {faDigits(data.break_month)} (تغییر ساختاری فروش)</span>}
            </div>
          )}
          {!data ? (!error && <Loading />) : (
            <>
              <OrderBar data={data} onRefresh={refresh} busy={busy} />
              {tab === 'summary' && <SummaryTab data={data} go={go} />}
              {tab === 'order' && <OrderTab data={data} status={status} setStatus={setStatus} />}
              {tab === 'all' && <AllTab data={data} />}
              {tab === 'supplier' && <SupplierTab data={data} />}
              {tab === 'idle' && <IdleTab data={data} kind={idle} setKind={setIdle} />}
              {tab === 'settings' && <SettingsTab data={data} setData={setData} />}
            </>
          )}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------- نمای کلی شعب
function BranchesTab({ onOpen, current }) {
  const { unit } = useApp()
  const { data, error } = useFetch('/api/inventory/overview')
  if (error) return <ErrorBox error={error} />
  if (!data) return <div className="state">در حال محاسبه برای همه شعب… (بار اول ممکن است تا یک دقیقه طول بکشد)</div>
  const rows = data.branches.filter((r) => !r.error)
  const act = rows.filter((r) => !r.inactive)
  const sum = (k, rs = act) => rs.reduce((a, r) => a + (r[k] || 0), 0)
  const late = act.filter((r) => r.days_to_deadline === 0).length
  const errs = data.branches.filter((r) => r.error)
  return (
    <>
      <div className="kpis">
        <Kpi label="شعب فعال" value={act.length} type="int" sub={`از ${fmtInt(rows.length)} شعبه هیبرید · ${fmtInt(rows.length - act.length)} غیرفعال`} />
        <Kpi label="مهلت سفارش: همین امروز" value={late} type="int" sub="شعبه‌ای که حداقل یک کالای A یا B آن تا رسیدن بار تمام می‌شود" />
        <Kpi label="کالاهای فوری (همه شعب)" value={sum('red')} type="int" sub={`${fmtInt(sum('red_a'))} تا پرفروش (A)`} />
        <Kpi label="سفارش بعدی (همه شعب)" value={sum('order_value')} sub={`${fmtInt(sum('order_lines'))} قلم · ${fmtInt(sum('order_units'))} عدد`} />
        <Kpi label="ارزش کل موجودی" value={sum('stock_value', rows)} sub={`${fmtInt(sum('stock_units', rows))} عدد به قیمت خرید`} />
        <Kpi label="راکد + مازاد" value={sum('dead_value', rows) + sum('excess_value', rows)}
          sub={`${fmtPct((sum('dead_value', rows) + sum('excess_value', rows)) / Math.max(sum('stock_value', rows), 1), 0)} ارزش موجودی؛ پول خوابیده`} />
      </div>
      <div className="alerts">
        {errs.length > 0 && <div className="alert warn"><span className="alert-icon">!</span>
          <span>شعب بدون سابقه کافی (کمتر از دو ماه عادی): {errs.map((r) => r.branch).join('، ')}</span></div>}
        {rows.filter((r) => r.data_issue).map((r) => (
          <div key={r.branch} className="alert danger"><span className="alert-icon">!</span><span>{r.branch}: {faDigits(r.data_issue)}</span></div>
        ))}
      </div>
      <div className="grid g2">
        <Card title="ترکیب ارزش موجودی هر شعبه" subtitle="سالم، مازاد (بیش از ۶ ماه پوشش) و راکد (بدون فروش ۹۰ روز)؛ به قیمت خرید" className="span2">
          <Chart height={Math.max(260, rows.length * 26)} option={(t) => {
            const rs = [...rows].sort((a, b) => a.stock_value - b.stock_value)
            const ok = (r) => Math.max(r.stock_value - r.dead_value - r.excess_value, 0)
            return {
              grid: { left: 130, right: 30, top: 30, bottom: 30 },
              tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${fmtMoney(v, unit)}` },
              legend: { top: 0, textStyle: { color: t.text } },
              xAxis: { type: 'value', axisLabel: { color: t.text, formatter: (v) => fmtMoney(v, unit) }, splitLine: { lineStyle: { color: t.grid } } },
              yAxis: { type: 'category', data: rs.map((r) => r.branch), axisLabel: { color: t.text } },
              series: [
                { name: 'سالم', type: 'bar', stack: 's', data: rs.map(ok), itemStyle: { color: t.series[2] } },
                { name: 'مازاد', type: 'bar', stack: 's', data: rs.map((r) => r.excess_value), itemStyle: { color: t.series[3] } },
                { name: 'راکد', type: 'bar', stack: 's', data: rs.map((r) => r.dead_value), itemStyle: { color: t.series[7] } },
              ],
            }
          }} onClick={(p) => p?.name && onOpen(p.name)} />
        </Card>
        <Card title="وضعیت هر شعبه" className="span2"
          subtitle={`امروز ${faDigits(data.today)} · موجودی خوانده‌شده ${faDigits(data.fetched.slice(11))} · برای دیدن پیشنهاد سفارش هر شعبه روی ردیف کلیک کنید`}>
          <DataTable rows={data.branches.map((r) => ({ ...r, key: r.branch }))} unit={unit} pageSize={25} dense search={false}
            exportName="inventory-branches" defaultSort={{ key: 'red_a', dir: 'desc' }} onRowClick={(r) => onOpen(r.branch)}
            columns={[
              { key: 'branch', label: 'شعبه', csv: (r) => r.branch, render: (r) => <>{r.branch}{r.branch === current && <span className="tag">انتخاب‌شده</span>}</> },
              { key: 'inactive', label: 'وضعیت', csv: (r) => (r.error ? 'سابقه ناکافی' : r.inactive ? 'غیرفعال' : r.data_issue ? 'داده خرید ناقص' : 'فعال'), render: (r) => r.error ? <span className="pill st-none" title={r.error}>سابقه ناکافی</span>
                : r.inactive ? <span className="pill st-red">غیرفعال</span>
                  : r.data_issue ? <span className="pill st-yellow" title={r.data_issue}>داده خرید ناقص</span>
                    : <span className="pill st-green">فعال</span> },
              { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
              { key: 'deadline', label: 'مهلت سفارش بعدی', type: 'date' },
              { key: 'red_a', label: 'فوری A', type: 'int' },
              { key: 'red', label: 'فوری کل', type: 'int' },
              { key: 'orange', label: 'در سفارش بعدی', type: 'int' },
              { key: 'order_lines', label: 'اقلام سفارش', type: 'int' },
              { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
              { key: 'cover_a', label: 'پوشش کالاهای A (ماه)', type: 'num1', hint: 'موجودی کالاهای A ÷ فروش پیش‌بینی‌شده این ماهشان' },
              { key: 'stock_value', label: 'ارزش موجودی', type: 'money' },
              { key: 'dead_value', label: 'راکد', type: 'money' },
              { key: 'excess_value', label: 'مازاد', type: 'money' },
              { key: 'open_req', label: 'درخواست باز', type: 'int' },
              { key: 'break_month', label: 'تغییر ساختاری', type: 'date', hint: 'اگر فروش شعبه نصف یا دو برابر شده، پایه از این ماه حساب می‌شود' },
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
const ST_SHORT = { red: 'فوری', orange: 'سفارش بعدی', ok: 'کافی', excess: 'مازاد', dead: 'راکد', c: 'نامنظم / بدون سابقه', nodata: 'نامنظم / بدون سابقه' }
const ST_ORDER = ['red', 'orange', 'ok', 'excess', 'dead', 'c']
const stOf = (r) => (r.status === 'nodata' ? 'c' : r.status)
const stColor = (s, t) => ({ red: t.series[7], orange: t.series[3], ok: t.series[2], excess: t.series[0],
  dead: t.dark ? '#8a8984' : '#8f8e88', c: t.dark ? '#4a4a46' : '#dddcd6' })[s === 'nodata' ? 'c' : s]
const NO_BRAND = 'بدون برند'
const brandOf = (r) => r.brand || NO_BRAND

/** جمع val بر اساس کلید؛ خروجی مرتب نزولی [{label, v}] */
function groupSum(rows, keyOf, val) {
  const m = new Map()
  rows.forEach((r) => { const k = keyOf(r) || '—'; m.set(k, (m.get(k) || 0) + (val(r) || 0)) })
  return [...m].map(([label, v]) => ({ key: label, label, v })).filter((x) => x.v > 0).sort((a, b) => b.v - a.v)
}

function SummaryTab({ data, go }) {
  const need = useMemo(() => data.rows.filter((r) => r.status === 'red' || r.status === 'orange'), [data])
  return (
    <>
      <div className="grid g2">
        <StockTreemap data={data} />
        <StockHealth data={data} go={go} />
      </div>
      <OrderSummary rows={need} title="سفارش بعدی" link={() => go('order', 'need')}
        empty="فعلاً کالایی برای سفارش نیست." />
    </>
  )
}

/** موجودی شعبه: برند ← گروه کالا ← کالا؛ اندازه = ارزش یا تعداد، رنگ = برند یا وضعیت */
function StockTreemap({ data }) {
  const { unit } = useApp()
  const [metric, setMetric] = useState('value')
  const [color, setColor] = useState('brand')
  const theme = useTheme()
  const rows = useMemo(() => data.rows.filter((r) => r.stock > 0), [data])
  const val = (r) => (metric === 'value' ? r.value || 0 : r.stock)
  const fmtV = (v) => (metric === 'value' ? `${fmtMoney(v, unit)} ${UNITS[unit].label}` : `${fmtInt(v)} عدد`)
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
    <Card title="موجودی انبار: برند ← گروه کالا ← کالا" className="span2"
      subtitle={`${fmtInt(rows.length)} کالای موجود · جمع ${fmtV(total)} · اندازه هر خانه = ${metric === 'value' ? 'ارزش به قیمت خرید' : 'تعداد'}؛ روی هر گروه کلیک کنید تا کالاهای آن باز شود (برگشت از نوار پایین)`}
      actions={<>
        <Tabs value={metric} onChange={setMetric} tabs={[{ value: 'value', label: 'ارزش' }, { value: 'units', label: 'تعداد' }]} />
        <Tabs value={color} onChange={setColor} tabs={[{ value: 'brand', label: 'رنگ برند' }, { value: 'status', label: 'رنگ وضعیت' }]} />
      </>}>
      {color === 'status' && (
        <div className="legend-row">
          {ST_ORDER.map((s) => (
            <span key={s}><i className="legend-dot" style={{ background: stColor(s, theme) }} />{ST_SHORT[s]}</span>
          ))}
        </div>
      )}
      <Chart height={520} option={(t) => ({
        tooltip: { ...baseOption(t).tooltip, formatter: (p) => {
          const r = p.data?.row
          const path = p.treePathInfo.slice(1).map((x) => x.name).join(' / ')
          const share = total ? ` (${fmtPct(p.value / total, 1)} کل)` : ''
          if (!r) return `${path}<br/><b>${fmtV(p.value)}</b>${share}`
          return `${path}<br/>موجودی: <b>${fmtInt(r.stock)}</b> عدد${r.unity > 1 ? ` (${fmtNum1(r.stock / r.unity)} کارتن)` : ''}`
            + `<br/>ارزش: <b>${fmtMoney(r.value || 0, unit)}</b> ${UNITS[unit].label}${share}`
            + `<br/>وضعیت: ${ST_SHORT[r.status] || r.status} · گروه ${r.abc}`
            + (isNum(r.cover_days) ? `<br/>روز باقی‌مانده: ${fmtInt(r.cover_days)}` : '')
            + (r.order > 0 ? `<br/>سفارش پیشنهادی: <b>${fmtInt(r.order)}</b> عدد` : '')
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
  )
}

/** سلامت موجودی هر برند: ارزش موجودی به تفکیک وضعیت */
function StockHealth({ data, go }) {
  const { unit } = useApp()
  const rows = data.rows.filter((r) => r.stock > 0)
  const brands = groupSum(rows, brandOf, (r) => r.value).reverse()
  const sts = ST_ORDER.filter((s) => rows.some((r) => stOf(r) === s))
  const cell = (b, s) => rows.reduce((a, r) => a + (brandOf(r) === b && stOf(r) === s ? r.value || 0 : 0), 0)
  const tot = rows.reduce((a, r) => a + (r.value || 0), 0)
  const by = Object.fromEntries(sts.map((s) => [s, rows.reduce((a, r) => a + (stOf(r) === s ? r.value || 0 : 0), 0)]))
  const idle = (by.dead || 0) + (by.excess || 0)
  return (
    <Card title="سلامت موجودی هر برند" className="span2"
      subtitle={<>ارزش موجودی به قیمت خرید، به تفکیک وضعیت کالا · {fmtPct(idle / Math.max(tot, 1), 0)} موجودی ({fmtMoney(idle, unit)} {UNITS[unit].label}) راکد یا مازاد است · روی میله کلیک کنید تا فهرست باز شود</>}>
      <Chart height={Math.max(240, brands.length * 30 + 60)}
        onClick={(p) => {
          const s = sts[p.seriesIndex]
          if (s === 'red' || s === 'orange') go('order', s)
          else if (s === 'dead' || s === 'excess') go('idle', s)
        }}
        option={(t) => ({
          grid: { left: 12, right: 12, top: 32, bottom: 8, containLabel: true },
          legend: { top: 0, right: 0, textStyle: { color: t.text } },
          tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
            formatter: (ps) => {
              const sum = ps.reduce((a, p) => a + (p.value || 0), 0)
              return `${ps[0].name} — ${fmtMoney(sum, unit)} ${UNITS[unit].label}<br/>` + ps.filter((p) => p.value > 0)
                .map((p) => `${p.marker} ${p.seriesName}: <b>${fmtMoney(p.value, unit)}</b> (${fmtPct(p.value / sum, 0)})`).join('<br/>')
            } },
          xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => fmtMoney(v, unit) }, splitLine: { lineStyle: { color: t.grid } } },
          yAxis: { type: 'category', position: 'right', data: brands.map((b) => b.label), axisLabel: { color: t.text },
            axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
          series: sts.map((s) => ({
            name: ST_SHORT[s], type: 'bar', stack: 'v', barMaxWidth: 18, cursor: 'pointer',
            itemStyle: { color: stColor(s, t), borderColor: t.surface, borderWidth: 1 },
            data: brands.map((b) => cell(b.label, s)),
          })),
        })} />
    </Card>
  )
}

/** نمای کلی سفارش: سهم برند، فوریت، تأمین‌کننده و گروه کالا (فقط کالاهای دارای مقدار سفارش) */
function OrderSummary({ rows: all, title, empty, link }) {
  const { unit } = useApp()
  const [metric, setMetric] = useState('value')
  const rows = useMemo(() => all.filter((r) => r.order > 0), [all])
  // انتخاب با کلیک روی نمودار: {kind, label, status?} ← فهرست کالاهای همان بخش زیر نمودارها
  const [pick, setPick] = useState(null)
  const pickRef = useRef(null)
  const open = (kind, label, status) => label && setPick({ kind, label, status })
  useEffect(() => { pick && pickRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [pick])
  if (!rows.length) return <div className="alert"><span>{empty}</span></div>
  const val = (r) => (metric === 'value' ? r.order_value || 0 : metric === 'cartons' ? (r.unity > 0 ? r.order / r.unity : 0) : r.order)
  const vt = metric === 'value' ? 'money' : 'int'
  const fmtV = (v) => (metric === 'value' ? `${fmtMoney(v, unit)} ${UNITS[unit].label}` : metric === 'cartons' ? `${fmtNum1(v)} کارتن` : `${fmtInt(v)} عدد`)
  const total = rows.reduce((a, r) => a + val(r), 0)
  const brands = groupSum(rows, brandOf, val)
  const sups = groupSum(rows, (r) => r.supplier, val)
  const cats = groupSum(rows, (r) => r.category, val)
  const red = rows.filter((r) => r.status === 'red')
  const redV = red.reduce((a, r) => a + val(r), 0)
  const aV = rows.filter((r) => r.abc === 'A').reduce((a, r) => a + val(r), 0)
  const top = brands[0]
  const top3 = brands.slice(0, 3).reduce((a, b) => a + b.v, 0)
  const short = (n) => n.slice(0, 12).map((x) => ({ ...x, v: metric === 'cartons' ? Math.round(x.v * 10) / 10 : x.v }))
  return (
    <>
      <div className="inv-summary-head">
        <h3>{title}</h3>
        <span className="muted">
          {fmtInt(rows.length)} قلم · {fmtInt(rows.reduce((a, r) => a + r.order, 0))} عدد · {fmtMoney(rows.reduce((a, r) => a + (r.order_value || 0), 0), unit)} {UNITS[unit].label}
          {' — '}<b>{top.label}</b> {fmtPct(top.v / total, 0)} سفارش؛ سه برند اول {fmtPct(top3 / total, 0)}
          {' · '}فوری {fmtPct(redV / total, 0)} · کالاهای A {fmtPct(aV / total, 0)}
        </span>
        <div className="spacer" />
        {link && <button className="btn ghost" onClick={link}>فهرست کامل ◀</button>}
        <span className="muted small">روی هر برند، تأمین‌کننده یا گروه کلیک کنید تا کالاهایش باز شود</span>
        <Tabs value={metric} onChange={setMetric}
          tabs={[{ value: 'value', label: 'ارزش' }, { value: 'units', label: 'تعداد' }, { value: 'cartons', label: 'کارتن' }]} />
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
        <Card title="فوریت سفارش هر برند" subtitle="فوری: حتی با سفارش امروز تا رسیدن بار کم می‌آید · سفارش بعدی: برای دوام تا سفارش بعد">
          <Chart height={Math.max(240, brands.length * 30 + 60)}
            onClick={(p) => open('brand', p.name, ['red', 'orange'][p.seriesIndex])} option={(t) => {
            const bs = [...brands].reverse()
            const part = (b, s) => rows.reduce((a, r) => a + (brandOf(r) === b && r.status === s ? val(r) : 0), 0)
            return {
              grid: { left: 12, right: 12, top: 32, bottom: 8, containLabel: true },
              legend: { top: 0, right: 0, textStyle: { color: t.text } },
              tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
                formatter: (ps) => `${ps[0].name}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtV(p.value)}</b>`).join('<br/>') + CLICK },
              xAxis: { type: 'value', inverse: true, axisLabel: { color: t.text, formatter: (v) => (vt === 'money' ? fmtMoney(v, unit) : fmtInt(v)) }, splitLine: { lineStyle: { color: t.grid } } },
              yAxis: { type: 'category', position: 'right', data: bs.map((b) => b.label), axisLabel: { color: t.text },
                axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
              series: ['red', 'orange'].map((s) => ({
                name: ST_SHORT[s], type: 'bar', stack: 'o', barMaxWidth: 18, cursor: 'pointer',
                itemStyle: { color: stColor(s, t), borderColor: t.surface, borderWidth: 1 },
                data: bs.map((b) => part(b.label, s)),
              })),
            }
          }} />
        </Card>
        <Card title="سفارش به تفکیک تأمین‌کننده" subtitle={sups.length > 12 ? `۱۲ تأمین‌کننده اول از ${fmtInt(sups.length)}` : `${fmtInt(sups.length)} تأمین‌کننده`}>
          <HBar rows={short(sups)} value="v" valueType={vt} unit={unit} colorIndex={0} onClick={(r) => open('supplier', r.label)} />
        </Card>
        <Card title="سفارش به تفکیک گروه کالا" subtitle={cats.length > 12 ? `۱۲ گروه اول از ${fmtInt(cats.length)}` : `${fmtInt(cats.length)} گروه`}>
          <HBar rows={short(cats)} value="v" valueType={vt} unit={unit} colorIndex={6} onClick={(r) => open('category', r.label)} />
        </Card>
        {pick && <div ref={pickRef} className="span2">
          <OrderItems rows={rows} pick={pick} val={val} vt={vt} fmtV={fmtV} onClose={() => setPick(null)} />
        </div>}
      </div>
    </>
  )
}

const CLICK = '<br/><span style="opacity:.7">برای دیدن کالاها کلیک کنید</span>'
const PICK_KEY = { brand: brandOf, supplier: (r) => r.supplier, category: (r) => r.category }
const PICK_NAME = { brand: 'برند', supplier: 'تأمین‌کننده', category: 'گروه کالا' }

/** ریز کالاهای سفارش یک برند / تأمین‌کننده / گروه (و در صورت انتخاب، یک وضعیت) */
function OrderItems({ rows: all, pick, val, vt, fmtV, onClose }) {
  const { unit } = useApp()
  const theme = useTheme()
  const rows = all.filter((r) => (PICK_KEY[pick.kind](r) || '—') === pick.label && (!pick.status || r.status === pick.status))
    .map((r) => ({ ...r, key: r.code, label: r.product, v: val(r) })).sort((a, b) => b.v - a.v)
  const total = rows.reduce((a, r) => a + r.v, 0)
  const nRed = rows.filter((r) => r.status === 'red').length
  const MAX = 40
  return (
    <Card title={`کالاهای سفارش — ${PICK_NAME[pick.kind]}: ${pick.label}${pick.status ? ` (${ST_SHORT[pick.status]})` : ''}`}
      subtitle={`${fmtInt(rows.length)} قلم · جمع ${fmtV(total)} · ${fmtInt(nRed)} قلم فوری${rows.length > MAX ? ` · نمودار ${fmtInt(MAX)} قلم اول؛ همه در جدول زیر` : ''}`}
      actions={<button className="btn ghost" onClick={onClose}>بستن</button>}>
      {!rows.length ? <div className="state">کالایی نیست.</div> : (
        <>
          <div className="legend-row">
            {['red', 'orange'].map((s) => <span key={s}><i className="legend-dot" style={{ background: stColor(s, theme) }} />{ST_SHORT[s]}</span>)}
          </div>
          <HBar rows={rows.slice(0, MAX)} value="v" valueType={vt} unit={unit} labelWidth={260} colorOf={(r, t) => stColor(r.status, t)} />
          <DataTable rows={rows} unit={unit} pageSize={15} dense search={false} exportName={`order-${pick.kind}`}
            defaultSort={{ key: 'v', dir: 'desc' }}
            columns={[
              { key: 'status', label: 'وضعیت', csv: (r) => ST_SHORT[r.status], render: (r) => <span className={`pill ${ST_CLASS[r.status]}`}>{ST_SHORT[r.status]}</span> },
              { key: 'product', label: 'کالا' },
              ...(pick.kind !== 'brand' ? [{ key: 'brand', label: 'برند' }] : []),
              ...(pick.kind !== 'category' ? [{ key: 'category', label: 'گروه کالا' }] : []),
              ...(pick.kind !== 'supplier' ? [{ key: 'supplier', label: 'تأمین‌کننده' }] : []),
              { key: 'abc', label: 'ABC' },
              { key: 'stock', label: 'موجودی', type: 'int' },
              { key: 'cover_days', label: 'روز باقی‌مانده', type: 'int' },
              { key: 'order', label: 'سفارش (عدد)', type: 'int' },
              { key: 'cartons', label: 'کارتن', type: 'num1' },
              { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
            ]} />
        </>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------- پیشنهاد سفارش
function OrderTab({ data, status, setStatus }) {
  const { unit } = useApp()
  const [supplier, setSupplier] = useState('')
  const [category, setCategory] = useState('')
  const [sel, setSel] = useState(null)
  const labels = data.status_label
  const suppliers = useMemo(() => [...new Set(data.rows.map((r) => r.supplier))].sort(), [data])
  const categories = useMemo(() => [...new Set(data.rows.map((r) => r.category))].sort(), [data])
  const rows = useMemo(() => data.rows.filter((r) =>
    (status === 'need' ? (r.status === 'red' || r.status === 'orange') : status === 'all' ? true : r.status === status)
    && (!supplier || r.supplier === supplier) && (!category || r.category === category)), [data, status, supplier, category])
  const totals = useMemo(() => rows.reduce((a, r) => ({ units: a.units + (r.order || 0), value: a.value + (r.order_value || 0) }), { units: 0, value: 0 }), [rows])
  const counts = useMemo(() => data.rows.reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {}), [data])
  const chips = [['need', 'نیاز به سفارش', (counts.red || 0) + (counts.orange || 0)], ['red', labels.red, counts.red],
    ['orange', labels.orange, counts.orange], ['ok', labels.ok, counts.ok], ['c', labels.c, counts.c], ['all', 'همه', data.rows.length]]
  return (
    <>
      <Alerts items={data.warnings} />
      <div className="plan-bar">
        <div className="seg" role="group" aria-label="وضعیت">
          {chips.map(([v, l, n]) => (
            <button key={v} className={status === v ? 'active' : ''} onClick={() => setStatus(v)}>{l} <span className="tag">{fmtInt(n || 0)}</span></button>
          ))}
        </div>
        <label className="inline-field">
          <span>تأمین‌کننده</span>
          <select value={supplier} onChange={(e) => setSupplier(e.target.value)}>
            <option value="">همه</option>
            {suppliers.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="inline-field">
          <span>گروه کالا</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">همه</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <div className="spacer" />
        <span className="muted">جمع سفارش این فهرست: <strong>{fmtInt(totals.units)}</strong> عدد · {fmtMoney(totals.value, unit)}</span>
      </div>
      <OrderSummary rows={rows} title="خلاصه همین فهرست"
        empty="در این فهرست کالایی برای سفارش نیست؛ نمودارهای سفارش فقط برای کالاهای دارای مقدار سفارش رسم می‌شوند." />
      <div className="grid g2">
        <Card title="فهرست کالاها" className="span2"
          subtitle="مرتب بر اساس روزهای باقی‌مانده موجودی؛ برای دیدن دلیل و تاریخچه هر کالا روی ردیف کلیک کنید.">
          <DataTable rows={rows} unit={unit} pageSize={20} dense exportName={`order-${data.today.replace(/\//g, '-')}`}
            defaultSort={{ key: 'cover_days', dir: 'asc' }} onRowClick={setSel}
            columns={[
              { key: 'status', label: 'وضعیت', csv: (r) => labels[r.status] || r.status, render: (r) => <StatusPill s={r.status} labels={labels} /> },
              { key: 'product', label: 'کالا' },
              { key: 'category', label: 'گروه کالا' },
              { key: 'supplier', label: 'تأمین‌کننده' },
              { key: 'abc', label: 'ABC', hint: 'A: کالاهای ۸۰٪ اول فروش تعدادی؛ B: ۱۵٪ بعدی؛ C: ۵٪ آخر (نامنظم)' },
              { key: 'min', label: 'کمترین ماه', type: 'int', hint: 'کمترین فروش خالص ماهانه (عدد) در ماه‌های پایه' },
              { key: 'mean', label: 'میانگین ماهانه', type: 'int', hint: 'میانگین فروش خالص ماهانه (عدد) در ماه‌های پایه' },
              { key: 'max', label: 'بیشترین ماه', type: 'int', hint: 'بیشترین فروش خالص ماهانه (عدد) در ماه‌های پایه' },
              { key: 'stock', label: 'موجودی', type: 'int' },
              { key: 'open_req', label: 'درخواست باز', type: 'int' },
              { key: 'req_short', label: 'کسری درخواست', type: 'int', hint: 'درخواست باز مشتری بیشتر از موجودی؛ این مقدار هم در سفارش آمده است' },
              { key: 'cover_days', label: 'روز باقی‌مانده', type: 'int', hint: 'موجودی قابل فروش ÷ فروش روزانه (با ضریب فصل)' },
              { key: 'order_by', label: 'مهلت سفارش', type: 'date', hint: `تاریخ اتمام منهای ${data.orders.lead} روز زمان رسیدن بار` },
              { key: 'need', label: 'لازم تا رسیدن بار', type: 'int', hint: `تقاضای پیش‌بینی‌شده از امروز تا ${data.orders.arr0} (اگر امروز سفارش داده شود)` },
              { key: 'target', label: 'سطح هدف', type: 'int', hint: `تقاضا تا ${data.orders.arr1} + safety` },
              { key: 'safety_pct', label: 'safety', type: 'pct' },
              { key: 'order', label: 'سفارش (عدد)', type: 'int' },
              { key: 'cartons', label: 'کارتن', type: 'num1' },
              { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
              { key: 'hist', label: 'روند ۱۲ ماه', csv: false, render: (r) => <Spark values={data.hist[r.code] || []} /> },
            ]} />
        </Card>
        {sel && <ItemDetail data={data} row={sel} onClose={() => setSel(null)} />}
      </div>
    </>
  )
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
      <div className="inv-why"><StatusPill s={row.status} labels={data.status_label} /> {faDigits(row.why)}</div>
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

// ---------------------------------------------------------------- همه کالاها
function AllTab({ data }) {
  const { unit } = useApp()
  const labels = data.status_label
  return (
    <Card title="شاخص‌های ماهانه همه کالاها" subtitle={`ماه‌های پایه: ${faDigits(data.base_months.join('، '))} · اعداد تعدادی و خالص (فروش منهای برگشتی)`}>
      <DataTable rows={data.rows} unit={unit} pageSize={25} dense exportName="inventory-items" defaultSort={{ key: 'base', dir: 'desc' }}
        columns={[
          { key: 'product', label: 'کالا' },
          { key: 'category', label: 'گروه کالا' },
          { key: 'supplier', label: 'تأمین‌کننده' },
          { key: 'abc', label: 'ABC', hint: 'A: کالاهای ۸۰٪ اول فروش تعدادی؛ B: ۱۵٪ بعدی؛ C: ۵٪ آخر (نامنظم)' },
          { key: 'status', label: 'وضعیت', csv: (r) => labels[r.status] || r.status, render: (r) => <StatusPill s={r.status} labels={labels} /> },
          { key: 'min', label: 'کمترین ماه', type: 'int' },
          { key: 'mean', label: 'میانگین', type: 'int' },
          { key: 'median', label: 'میانه', type: 'int' },
          { key: 'max', label: 'بیشترین ماه', type: 'int' },
          { key: 'months_sold', label: 'ماه با فروش', type: 'int' },
          { key: 'cv', label: 'نوسان', type: 'num1' },
          { key: 'trend', label: 'روند ۳ ماه', type: 'pct' },
          { key: 'ly_cur', label: 'همین ماه پارسال', type: 'int' },
          { key: 'ly_next', label: 'ماه بعد پارسال', type: 'int' },
          { key: 'ret_rate', label: 'برگشتی', type: 'pct' },
          { key: 'n_cust', label: 'مشتری', type: 'int' },
          { key: 'top_share', label: 'سهم بزرگ‌ترین مشتری', type: 'pct' },
          { key: 'stock', label: 'موجودی', type: 'int' },
          { key: 'cover_months', label: 'پوشش (ماه)', type: 'num1' },
          { key: 'value', label: 'ارزش موجودی', type: 'money' },
        ]} />
    </Card>
  )
}

// ---------------------------------------------------------------- تأمین‌کنندگان
function SupplierTab({ data }) {
  const { unit } = useApp()
  return (
    <Card title="خلاصه تأمین‌کنندگان" subtitle="نسبت خرید به فروش ۹۰ روز اخیر نزدیک ۱ یعنی خرید متناسب با فروش؛ بالاتر یعنی انباشت موجودی.">
      <DataTable rows={data.suppliers} unit={unit} pageSize={20} dense exportName="inventory-suppliers" defaultSort={{ key: 'value', dir: 'desc' }}
        columns={[
          { key: 'supplier', label: 'تأمین‌کننده' },
          { key: 'skus', label: 'تعداد کالا', type: 'int' },
          { key: 'stock', label: 'موجودی', type: 'int' },
          { key: 'value', label: 'ارزش موجودی', type: 'money' },
          { key: 'monthly', label: 'فروش ماهانه (با فصل)', type: 'int' },
          { key: 'cover_months', label: 'پوشش (ماه)', type: 'num1' },
          { key: 'red', label: 'قرمز', type: 'int' },
          { key: 'orange', label: 'نارنجی', type: 'int' },
          { key: 'order', label: 'سفارش پیشنهادی', type: 'int' },
          { key: 'order_value', label: 'ارزش سفارش', type: 'money' },
          { key: 'bought_90', label: 'خرید ۹۰ روز', type: 'int' },
          { key: 'sold_90', label: 'فروش خالص ۹۰ روز', type: 'int' },
          { key: 'buy_sell', label: 'خرید ÷ فروش', type: 'num1', render: (r) => <span className={r.buy_sell > 1.5 ? 'neg-text' : ''}>{fmtNum1(r.buy_sell)}</span> },
        ]} />
    </Card>
  )
}

// ---------------------------------------------------------------- راکد و مازاد
function IdleTab({ data, kind, setKind }) {
  const { unit } = useApp()
  const rows = useMemo(() => data.rows.filter((r) => r.status === kind), [data, kind])
  const s = data.settings
  return (
    <Card title="کالاهای راکد و مازاد"
      subtitle={kind === 'dead' ? `موجودی دارند ولی بیش از ${fmtInt(s.dead_days)} روز فروش نداشته‌اند` : `پوشش بیش از ${fmtInt(s.excess_months)} ماه فروش`}
      actions={<Tabs tabs={[{ value: 'dead', label: `راکد (${fmtInt(data.kpis.dead_skus)})` }, { value: 'excess', label: `مازاد (${fmtInt(data.kpis.excess_skus)})` }]} value={kind} onChange={setKind} />}>
      <DataTable rows={rows} unit={unit} pageSize={20} dense exportName={`inventory-${kind}`} defaultSort={{ key: 'value', dir: 'desc' }}
        columns={[
          { key: 'product', label: 'کالا' },
          { key: 'category', label: 'گروه کالا' },
          { key: 'supplier', label: 'تأمین‌کننده' },
          { key: 'stock', label: 'موجودی', type: 'int' },
          { key: 'value', label: 'ارزش', type: 'money' },
          { key: 'mean', label: 'فروش ماهانه', type: 'int' },
          { key: 'cover_months', label: 'پوشش (ماه)', type: 'num1' },
          { key: 'last_sale', label: 'آخرین فروش', type: 'date' },
          { key: 'idle_days', label: 'روز بدون فروش', type: 'int' },
          { key: 'bought_90', label: 'خرید ۹۰ روز', type: 'int' },
        ]} />
    </Card>
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
    })
  }, [s])
  if (!f) return null
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const save = async () => {
    setMsg(null)
    try {
      setData(await sendJson('/api/inventory/settings', 'PUT', {
        branch: data.branch, lead_days: Number(f.lead_days), orders_per_month: Number(f.orders_per_month),
        break_detect: f.break_detect, inactive_days: Number(f.inactive_days),
        min_order_cartons: Number(f.min_order_cartons), min_gap_pct: Number(f.min_gap_pct) / 100,
        a_safety: f.a_safety, z_a: Number(f.z_a), b_pct: Number(f.b_pct) / 100,
        breadth: [Number(f.br0) / 100, Number(f.br1) / 100, Number(f.br2) / 100],
        base_months: Number(f.base_months), dead_days: Number(f.dead_days), excess_months: Number(f.excess_months),
        min_months_sold: Number(f.min_months_sold), ly_weight: Number(f.ly_weight) / 100,
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
          <li><strong>مقدار سفارش:</strong> سطح هدف منهای موجودی قابل فروش، به‌اضافه کسری درخواست‌های باز مشتری (اگر درخواست از موجودی بیشتر باشد)؛ از نیم کارتن به بالا گرد به کارتن کامل، کمتر از آن به عدد.</li>
        </ol>
        <p className="muted small">آزمون روی همه شعب هیبرید (اردیبهشت تا شهریور ۱۴۰۵، هر بار فقط با داده قبل از همان تاریخ): از هر ۱۰ کمبود واقعی کالاهای A حدود ۸ تا از قبل هشدار گرفتند و با سفارش پیشنهادی، تأمین فروش از ۸۴٪ به ۹۲٪ رسید؛ حجم سفارش تقریباً به اندازه نیاز بود.</p>
      </Card>
    </div>
  )
}
