// تحلیل هوشمند پرونده هیبرید یا نماینده راهکاران از روی تاریخچه‌اش
// (بک‌اند: /api/v1/finance/ai-analysis/{kind}/{key}، backend/app/services/ai_file_analysis_service.py).
// هوش مصنوعی فقط «پروفایل تاریخچه» ساخته‌شده با کد را می‌بیند؛ همان پروفایل زیر تحلیل قابل باز کردن است.
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchJson } from '@sales/lib.jsx'
import { Card, Pending } from './ui.jsx'

const URL = (kind, key) => `/api/v1/finance/ai-analysis/${kind}/${encodeURIComponent(key)}`
const ASSESS = { 'خوب': 'good', 'قابل قبول': 'good', 'نیازمند توجه': 'warn', 'پرخطر': 'bad' }
const TREND = { 'رو به بهبود': 'good', 'ثابت': 'muted', 'رو به افت': 'bad', 'نامشخص': 'muted' }
const fa = (v) => String(v ?? '').replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d])

function jalaliStamp(iso) {
  if (!iso) return ''
  try {
    return new Intl.DateTimeFormat('fa-IR-u-ca-persian', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
  } catch {
    return iso.slice(0, 16)
  }
}

export function useAiAnalysis(kind, key) {
  const [state, setState] = useState({ data: null, error: null, busy: false })
  const timer = useRef(0)
  const load = useCallback(() => (key ? fetchJson(URL(kind, key))
    .then((data) => { setState((s) => ({ ...s, data, error: null })); return data })
    .catch((e) => { setState((s) => ({ ...s, error: e.message })); return null }) : Promise.resolve(null)), [kind, key])
  useEffect(() => { load(); return () => window.clearTimeout(timer.current) }, [load])
  const refresh = useCallback(async () => {
    const before = state.data?.created_at
    setState((s) => ({ ...s, busy: true }))
    try {
      await fetchJson(`${URL(kind, key)}/refresh`, { method: 'POST' })
    } catch (e) {
      setState((s) => ({ ...s, busy: false, error: e.message }))
      return
    }
    let tries = 0
    const poll = async () => {
      const d = await load()
      tries += 1
      if ((d?.created_at && d.created_at !== before && !d.refreshing) || (!d?.refreshing && tries > 3) || tries > 30) setState((s) => ({ ...s, busy: false }))
      else timer.current = window.setTimeout(poll, 10000)
    }
    timer.current = window.setTimeout(poll, 10000)
  }, [kind, key, load, state.data?.created_at])
  return { ...state, refresh }
}

function List({ title, items, tone }) {
  if (!items?.length) return null
  return (
    <div className="u-ai-list">
      <b className={tone}>{title}</b>
      <ul>{items.map((x) => <li key={x}>{x}</li>)}</ul>
    </div>
  )
}

/** داده‌ای که مدل دیده؛ برای وارسی هر جمله. */
function ProfileTable({ profile }) {
  const sales = profile?.monthly_sales || profile?.monthly_sales_vs_last_year || []
  const cheques = profile?.monthly_cheques_received || []
  const byMonth = new Map(cheques.map((c) => [c.month, c]))
  const months = [...new Set([...sales.map((s) => s.month), ...cheques.map((c) => c.month)])].sort().slice(-14)
  const salesBy = new Map(sales.map((s) => [s.month, s]))
  const cell = (v) => (v === null || v === undefined ? '—' : fa(Math.round(v).toLocaleString('en-US')))
  return (
    <div className="u-ai-table-wrap">
      <table className="u-ai-table">
        <thead>
          <tr><th>ماه</th><th>فروش خالص</th>{profile?.monthly_sales_vs_last_year && <th>همان ماه پارسال</th>}
            <th>چک دریافتی</th><th>وصول‌شده</th><th>برگشتی</th><th>هنوز باز</th><th>مدت متوسط</th></tr>
        </thead>
        <tbody>
          {months.map((m) => {
            const s = salesBy.get(m) || {}
            const c = byMonth.get(m) || {}
            return (
              <tr key={m}>
                <td>{fa(m)}</td><td>{cell(s.net_mt)}</td>{profile?.monthly_sales_vs_last_year && <td>{cell(s.last_year_mt)}</td>}
                <td>{cell(c.amount_mt)}</td><td>{cell(c.collected_mt)}</td><td className={c.returned_mt > 0 ? 'bad' : ''}>{cell(c.returned_mt)}</td>
                <td>{cell(c.still_open_mt)}</td><td>{c.avg_term_days ? `${fa(c.avg_term_days)} روز` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <small className="u-sub">مبالغ به میلیون تومان · چک‌ها به ماه دریافت (ثبت) · «هنوز باز» یعنی هنوز سررسید یا تعیین تکلیف نشده</small>
    </div>
  )
}

export function AiAnalysisPanel({ ai, subject }) {
  const r = ai.data
  const [showData, setShowData] = useState(false)
  if (!r && !ai.error) return <Card><Pending state={{}} label="تحلیل هوشمند" height={160} /></Card>
  const button = r?.enabled && (
    <button className="u-btn ghost" onClick={ai.refresh} disabled={ai.busy || r?.refreshing}>
      {ai.busy || r?.refreshing ? 'در حال تحلیل… (حدود یک دقیقه)' : 'تحلیل دوباره'}
    </button>
  )
  if (r?.status !== 'ready') {
    return (
      <Card title="تحلیل هوشمند" action={button}>
        <Pending state={{ error: ai.error || r?.message || 'تحلیلی نیست' }} label="تحلیل هوشمند" height={120} />
        {r?.last_error && <small className="u-sub">آخرین تلاش ناموفق بود: {r.last_error}</small>}
      </Card>
    )
  }
  const a = r.analysis
  return (
    <div className="u-stack">
      <Card title={`تحلیل هوشمند ${subject}`}
        sub={`با هوش مصنوعی از روی تاریخچه فروش، وصول و چک‌ها · ${jalaliStamp(r.created_at)}${r.trigger === 'scheduled' ? ' (هفتگی خودکار)' : ''}`}
        action={button}>
        <div className="u-row-gap" style={{ marginBottom: 10 }}>
          <span className={`u-pill ${ASSESS[a.assessment] || 'muted'}`}>ارزیابی: {a.assessment}</span>
          <span className={`u-pill ${TREND[a.sales_trend] || 'muted'}`}>فروش: {a.sales_trend}</span>
          <span className={`u-pill ${TREND[a.payment_trend] || 'muted'}`}>پرداخت: {a.payment_trend}</span>
        </div>
        <h3 className="u-ai-headline">{a.headline}</h3>
        <p className="u-ai-text">{a.summary}</p>
        <p className="u-ai-text"><b>چرا «{a.assessment}»: </b>{a.assessment_reason}</p>
        {r.last_error && <small className="u-sub">آخرین تحلیل دوباره ناموفق بود؛ این تحلیل قبلی است.</small>}
      </Card>
      <div className="u-grid2">
        <Card title="روند فروش"><p className="u-ai-text">{a.sales_story}</p></Card>
        <Card title="رفتار پرداخت و چک"><p className="u-ai-text">{a.payment_story}</p></Card>
      </div>
      <Card title="تغییرها، نقاط قوت و ریسک‌ها">
        <div className="u-ai-lists">
          <List title="تغییرهای مهم نسبت به گذشته" items={a.changes} tone="" />
          <List title="نقاط قوت" items={a.strengths} tone="good" />
          <List title="ریسک‌ها" items={a.risks} tone="bad" />
        </div>
      </Card>
      <div className="u-grid2">
        <Card title="چشم‌انداز ۱ تا ۳ ماه آینده"><p className="u-ai-text">{a.outlook}</p></Card>
        <Card title="اقدام‌های پیشنهادی"><List title="" items={a.actions} tone="" /></Card>
      </div>
      <Card title="داده‌ای که هوش مصنوعی دیده" sub="همه اعداد با کد از راهکاران و کارآمد ساخته شده‌اند؛ هوش مصنوعی خودش عددی حساب نکرده است"
        action={<button className="u-link-btn" onClick={() => setShowData((v) => !v)}>{showData ? 'بستن' : 'نمایش جدول'}</button>}>
        {showData && <ProfileTable profile={r.profile} />}
      </Card>
    </div>
  )
}
