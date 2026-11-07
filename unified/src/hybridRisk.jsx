// گزارش هفتگی ریسک هیبریدها (بک‌اند: /api/v1/finance/sales-network/risk، backend/app/services/hybrid_risk_service.py).
// امتیاز ۰ تا ۱۰۰ با قواعد ثابت؛ هر شنبه صبح خودکار ساخته می‌شود و با دکمه «به‌روزرسانی» هم دستی.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchJson } from '@sales/lib.jsx'
import { n0 } from './data.js'
import { Card, Pending, Bar } from './ui.jsx'
import { hybridPath } from './HybridTable.jsx'

export const RISK_URL = '/api/v1/finance/sales-network/risk'
const PILL = { low: 'good', medium: 'warn', high: 'bad', critical: 'bad' }
const TONE = { low: 'sales', medium: 'warn', high: 'danger', critical: 'danger' }

/** آخرین گزارش + refresh() که ساخت دوباره را شروع می‌کند و تا آماده شدن نسخه تازه هر ۱۵ ثانیه می‌پرسد. */
export function useHybridRisk() {
  const [state, setState] = useState({ data: null, error: null, building: false })
  const timer = useRef(0)
  const load = useCallback(() => fetchJson(RISK_URL)
    .then((data) => { setState((s) => ({ ...s, data, error: null })); return data })
    .catch((e) => { setState((s) => ({ ...s, error: e.message })); return null }), [])
  useEffect(() => { load(); return () => window.clearTimeout(timer.current) }, [load])
  const refresh = useCallback(async () => {
    const before = state.data?.generated_at
    setState((s) => ({ ...s, building: true }))
    try {
      await fetchJson(`${RISK_URL}/refresh`, { method: 'POST' })
    } catch (e) {
      setState((s) => ({ ...s, building: false, error: e.message }))
      return
    }
    let tries = 0
    const poll = async () => {
      const data = await load()
      tries += 1
      if ((data?.generated_at && data.generated_at !== before && !data.refreshing) || tries > 40) {
        setState((s) => ({ ...s, building: false }))
      } else {
        timer.current = window.setTimeout(poll, 15000)
      }
    }
    timer.current = window.setTimeout(poll, 15000)
  }, [load, state.data?.generated_at])
  return { ...state, refresh }
}

const fa = (v) => String(v).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])
const deltaText = (d) => (d === null || d === undefined ? null : d === 0 ? 'بدون تغییر' : `${d > 0 ? '+' : '−'}${fa(Math.abs(d))}`)
const deltaCls = (d) => (d > 0 ? 'bad' : d < 0 ? 'good' : 'muted')

export function RiskPill({ b, prefix = 'ریسک' }) {
  if (!b) return null
  return <span className={`u-pill ${PILL[b.level] || 'muted'}`} title={b.reasons?.[0]}>{prefix} {b.level_label} · {fa(b.score)}</span>
}

function Delta({ value, label }) {
  const t = deltaText(value)
  if (!t) return null
  return <span className={`u-pill ${deltaCls(value)}`} title={`تغییر امتیاز نسبت به ${label}`}>{label}: {t}</span>
}

function Stamp({ r, building, refresh }) {
  return (
    <div className="u-row-gap">
      <small className="u-sub">
        {r?.generated_at_jalali ? `گزارش ${fa(r.generated_at_jalali)}${r.trigger === 'scheduled' ? ' (هفتگی خودکار)' : ''}` : ''}
        {r?.week_compared_to ? ` · مقایسه با ${fa(r.week_compared_to)}` : ''}
      </small>
      {refresh && <button className="u-btn ghost" onClick={refresh} disabled={building || r?.refreshing}>
        {building || r?.refreshing ? 'در حال ساخت گزارش… (چند دقیقه)' : 'به‌روزرسانی'}
      </button>}
    </div>
  )
}

/** فهرست همه هیبریدها به ترتیب امتیاز ریسک (صفحه «هیبریدها»). */
export function HybridRiskCard({ risk }) {
  const r = risk.data
  const ready = r?.status === 'ready'
  return (
    <Card title="ریسک هیبریدها — گزارش هفتگی"
      sub="امتیاز ۰ تا ۱۰۰ از چک باز پرخطر، چک برگشتی، دوره وصول و دوره چک در دست؛ عدد بیشتر یعنی ریسک بیشتر"
      action={<Stamp r={r} building={risk.building} refresh={risk.refresh} />}>
      {!ready ? <Pending state={risk.error ? risk : { error: r?.status === 'empty' ? r.message : null }} label="گزارش ریسک" height={120} /> : (
        <>
          <div className="u-row-gap" style={{ marginBottom: 10 }}>
            {[['critical', 'بحرانی'], ['high', 'زیاد'], ['medium', 'متوسط'], ['low', 'کم']].map(([k, l]) => (
              <span key={k} className={`u-pill ${PILL[k]}`}>{l}: {n0(r.levels?.[k] || 0)}</span>
            ))}
          </div>
          <div className="u-list">
            {r.branches.map((b) => (
              <Link key={b.branch_id} to={hybridPath(b.branch_name, 'risk')} className="u-list-row u-risk-row" title={b.reasons?.join('\n')}>
                <span>{b.branch_name}</span>
                <Bar value={b.score} max={100} tone={TONE[b.level]} />
                <span className="u-row-gap"><RiskPill b={b} prefix="" /><Delta value={b.week_delta} label="هفته" /></span>
                <small>{b.reasons?.[0]}</small>
              </Link>
            ))}
          </div>
        </>
      )}
    </Card>
  )
}

/** تب «ریسک» پرونده یک هیبرید. */
export function RiskTab({ risk, branchId }) {
  const r = risk.data
  const b = r?.branches?.find((x) => x.branch_id === branchId)
  if (r?.status !== 'ready') return <Card><Pending state={risk.error ? risk : { error: r?.message }} label="گزارش ریسک" height={160} /></Card>
  if (!b) return <Card><Pending state={{ error: 'این هیبرید در آخرین گزارش ریسک نیست' }} label="گزارش ریسک" /></Card>
  const m = b.metrics || {}
  return (
    <div className="u-stack">
      <Card title={`امتیاز ریسک: ${fa(b.score)} از ۱۰۰`} sub="با قواعد ثابت و بدون هوش مصنوعی؛ هر شنبه صبح دوباره حساب می‌شود"
        action={<Stamp r={r} building={risk.building} refresh={risk.refresh} />}>
        <div className="u-row-gap" style={{ marginBottom: 12 }}>
          <RiskPill b={b} />
          <Delta value={b.week_delta} label="هفته قبل" />
          <Delta value={b.month_delta} label="ماه قبل" />
          {b.week_delta === null && <span className="u-pill muted">مقایسه با هفته قبل بعد از گزارش دوم</span>}
        </div>
        <ul className="u-reasons">
          {b.reasons.map((x) => <li key={x}>{x}</li>)}
        </ul>
      </Card>
      <Card title="اجزای امتیاز" sub="هر جزء ۰ تا وزنش امتیاز می‌گیرد؛ جمع اجزا = امتیاز ریسک">
        <div className="u-list">
          {b.components.map((c) => (
            <div key={c.key} className="u-list-row">
              <span>{c.title}</span>
              <Bar value={c.points} max={c.weight} tone={c.points / c.weight > 0.66 ? 'danger' : c.points / c.weight > 0.33 ? 'warn' : 'sales'} />
              <span>{fa(c.points.toFixed(1))} از {fa(c.weight)}</span>
              <small>{fa(Math.round(c.ratio * 100))}٪ از حداکثر</small>
            </div>
          ))}
        </div>
      </Card>
      <Card title="اعداد پایه" sub="همان اعداد پرونده هیبرید در زمان ساخت گزارش">
        <div className="u-list">
          <div className="u-list-row"><span>چک باز</span><span /><span>{n0(m.open_cheque_count)} فقره</span><small>{n0(m.high_risk_cheque_count)} فقره با احتمال برگشت بالا</small></div>
          <div className="u-list-row"><span>چک برگشتی تسویه‌نشده</span><span /><span>{n0(m.returned_cheque_count)} فقره</span><small /></div>
          <div className="u-list-row"><span>دوره وصول</span><span /><span>{m.collection_period_days === null ? '—' : `${n0(m.collection_period_days)} روز`}</span><small>{n0(m.debtor_customer_count)} مشتری بدهکار از {n0(m.customer_count)}</small></div>
          <div className="u-list-row"><span>دوره چک در دست</span><span /><span>{m.cheque_holding_days === null ? '—' : `${n0(m.cheque_holding_days)} روز`}</span><small>چند روز فروش در چک وصول‌نشده است</small></div>
        </div>
      </Card>
    </div>
  )
}
