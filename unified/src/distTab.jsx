// Load distribution (توزیع بار) of one hybrid, from the finance dashboard's Karamad distribution reports:
// this month's sales → distributed → collected, delivery lead time, invoices still without an exit slip.
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { sendChatLink } from '@finance/chatbot/chat-link.ts'
import { useJson, n0, pct, isNum, faDigits, moneyText, monthName } from './data.js'
import { normName } from './model.js'
import { Card, Pending, Bar, Money, Mt } from './ui.jsx'
import { VisitorName } from './fileTabs.jsx'

const STALE_DAYS = 14
const sumOf = (xs, k) => xs.reduce((s, x) => s + (Number(x[k]) || 0), 0)
const ymOf = (P) => (P?.month ? { year: Number(P.month.slice(0, 4)), month: Number(P.month.slice(5, 7)) } : null)

/** Distribution data of one hybrid (matched by name, like the rest of the hybrid file). */
export function useHybridDistribution(name, P) {
  const ym = ymOf(P)
  const monthly = useJson(ym ? `/api/v1/finance/distribution/monthly?year=${ym.year}&month=${ym.month}` : null)
  const overview = useJson('/api/v1/finance/distribution')
  return useMemo(() => {
    const key = normName(name)
    const mine = (x) => normName(x.branch_name) === key
    const m = monthly.data
    const o = overview.data
    const undistributed = (o?.undistributed || []).filter(mine).sort((a, b) => (b.days_waiting || 0) - (a.days_waiting || 0))
    const finName = (m?.branches || []).find(mine)?.branch_name || (o?.lead_time || []).find(mine)?.branch_name || undistributed[0]?.branch_name
    return {
      ym, monthly, overview, finName,
      month: (m?.branches || []).find(mine) || null,
      customers: (m?.customers || []).filter(mine),
      lead: (o?.lead_time || []).find(mine) || null,
      distributors: (o?.distributors || []).filter(mine),
      undistributed,
      stale: undistributed.filter((x) => (x.days_waiting || 0) > STALE_DAYS),
    }
  }, [name, monthly, overview, ym?.year, ym?.month]) // eslint-disable-line react-hooks/exhaustive-deps
}

/** Opens the finance «توزیع بار» page already filtered to this hybrid and month. */
export function useOpenDistribution(d) {
  const nav = useNavigate()
  return () => {
    sendChatLink({ view: 'distribution', search: d.finName || '', year: d.ym?.year, month: d.ym?.month })
    nav('/finance/distribution')
  }
}

const leadTone = (days) => (days > 7 ? 't-bad' : days > 3 ? 't-warn' : 't-good')

/** Overview-tab card: this month's distribution and collection in a glance. */
export function DistributionGlance({ d, go }) {
  const b = d.month
  const ready = d.monthly.data && d.overview.data
  const distPct = b?.sales_rial > 0 ? (b.distributed_rial / b.sales_rial) * 100 : null
  const collPct = b?.distributed_rial > 0 ? (b.collected_rial / b.distributed_rial) * 100 : null
  return (
    <Card title={`توزیع بار ${d.ym ? monthName(`${d.ym.year}/${String(d.ym.month).padStart(2, '0')}`) : 'این ماه'}`} sub="از داشبورد مالی (کارآمد): فاکتور ← حواله خروج ← وصول"
      action={go && <button className="u-link-btn" onClick={() => go('distribution')}>جزئیات توزیع ←</button>}>
      {!ready ? <Pending state={d.monthly.error ? d.monthly : d.overview} label="توزیع بار" height={160} />
        : !b && !d.undistributed.length ? <Pending state={{ error: 'این هیبرید در گزارش توزیع بار نیست' }} label="توزیع بار" height={160} /> : (
        <div className="u-facts">
          {b ? <>
            <div><small>فروش ماه</small><Money rial={b.sales_rial} /><span>{isNum(distPct) ? `${pct(distPct)} توزیع شده` : '—'}</span></div>
            <div><small>توزیع‌نشده این ماه (برگشتی‌ها کم شده)</small><Money rial={b.undistributed_rial} className={b.undistributed_rial > 0 ? 't-warn' : ''} /><span>{n0(b.undistributed_count)} فاکتور بدون حواله خروج · با برگشتی: {moneyText(b.undistributed_gross_rial)} ({n0(b.undistributed_gross_count)} فاکتور)</span></div>
            <div><small>وصول از توزیع‌شده</small><Money rial={b.collected_rial} /><span>{isNum(collPct) ? `${pct(collPct)} توزیع‌شده وصول شده` : '—'}</span></div>
            <div><small>مانده وصول‌نشده</small><Money rial={b.remaining_rial} /><span>از فاکتورهای توزیع‌شده ماه</span></div>
          </> : <div><small>این ماه</small><span className="u-money"><b>—</b></span><span>در گزارش توزیع و وصول این ماه فروشی برای این هیبرید ثبت نشده است</span></div>}
          <div><small>میانگین فاصله فاکتور تا خروج</small>
            <span className={`u-money ${d.lead ? leadTone(d.lead.average_days) : ''}`}><b>{d.lead ? n0(d.lead.average_days) : '—'}</b><small>روز</small></span>
            <span>{d.lead ? `${pct(d.lead.within_1_day_percent)} همان روز · ${n0(d.lead.over_7_days)} فاکتور بیش از ۷ روز` : 'امسال'}</span></div>
          <div><small>کل توزیع‌نشده امسال</small><Money rial={sumOf(d.undistributed, 'amount_rial')} className={d.stale.length ? 't-bad' : ''} />
            <span>{n0(d.undistributed.length)} فاکتور · {n0(d.stale.length)} بیش از {n0(STALE_DAYS)} روز</span></div>
        </div>
      )}
    </Card>
  )
}

/** «توزیع بار» tab of the hybrid file. */
export function DistributionTab({ d, ids }) {
  const open = useOpenDistribution(d)
  const ready = d.monthly.data && d.overview.data
  const aging = [
    { label: 'تا ۳ روز (عادی)', tone: 'fin', items: d.undistributed.filter((x) => x.days_waiting <= 3) },
    { label: `۴ تا ${n0(STALE_DAYS)} روز`, tone: 'warn', items: d.undistributed.filter((x) => x.days_waiting > 3 && x.days_waiting <= STALE_DAYS) },
    { label: `بیش از ${n0(STALE_DAYS)} روز (مشکوک)`, tone: 'danger', items: d.stale },
  ]
  const maxAging = Math.max(1, ...aging.map((a) => sumOf(a.items, 'amount_rial')))
  const custs = [...d.customers].filter((c) => c.remaining_rial > 0).sort((a, b) => b.remaining_rial - a.remaining_rial)
  return (
    <div className="u-stack">
      <div className="u-crosslink">
        <div>
          <b>توزیع بار همین هیبرید در داشبورد مالی</b>
          <small>گزارش ماهانه توزیع و وصول، توزیع‌نشده به تفکیک ویزیتور، زمان‌بندی فاکتور تا خروج و خروجی Excel</small>
        </div>
        <button className="u-btn primary" onClick={open} disabled={!ready}>صفحه کامل توزیع بار ←</button>
      </div>

      <DistributionGlance d={d} />

      {ready && <>
        <div className="u-grid2">
          <Card title="سن فاکتورهای توزیع‌نشده" sub={`فاکتورهای فروش ${faDigits(d.overview.data.fiscal_year_label || '')} بدون حواله خروج · بر اساس روزهای انتظار`}>
            <div className="u-list">
              {aging.map((a) => (
                <div key={a.label} className="u-list-row">
                  <span>{a.label}</span><Bar value={sumOf(a.items, 'amount_rial')} max={maxAging} tone={a.tone} />
                  <Money rial={sumOf(a.items, 'amount_rial')} /><small>{n0(a.items.length)} فاکتور</small>
                </div>
              ))}
            </div>
          </Card>
          <Card title="موزعان" sub="خروج‌های امسال این هیبرید">
            {!d.distributors.length ? <div className="u-pending">موزعی برای این هیبرید ثبت نشده است.</div> : (
              <div className="u-table-wrap">
                <table className="u-table">
                  <thead><tr><th>موزع</th><th>خروج</th><th>فاکتور</th><th>مبلغ<small>میلیون تومان</small></th><th>میانگین تا خروج</th><th>آخرین خروج</th></tr></thead>
                  <tbody>
                    {d.distributors.map((x) => (
                      <tr key={x.deliver_name}>
                        <td>{x.deliver_name}</td><td>{n0(x.exit_count)}</td><td>{n0(x.invoice_count)}</td><td><b><Mt rial={x.amount_rial} /></b></td>
                        <td className={leadTone(x.average_lead_days)}>{n0(x.average_lead_days)} روز</td><td className="t-muted">{faDigits(x.last_exit_date_jalali || '—')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <Card title={`فاکتورهای توزیع‌نشده (${n0(d.undistributed.length)})`} sub={`قدیمی‌ترین اول · جمع ${moneyText(sumOf(d.undistributed, 'amount_rial'))} · بیش از ${n0(STALE_DAYS)} روز قرمز`}>
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr><th>شماره</th><th>تاریخ فاکتور</th><th>انتظار</th><th>مشتری</th><th>ویزیتور</th><th>مبلغ<small>میلیون تومان</small></th></tr></thead>
              <tbody>
                {d.undistributed.slice(0, 200).map((x) => (
                  <tr key={x.invoice_id}>
                    <td>{faDigits(x.number)}</td><td className="t-muted">{faDigits(x.date_jalali)}</td>
                    <td className={x.days_waiting > STALE_DAYS ? 't-bad' : x.days_waiting > 3 ? 't-warn' : 't-muted'}>{n0(x.days_waiting)} روز</td>
                    <td>{x.customer_name || '—'}<small className="u-sub">کد {faDigits(x.customer_code || '—')}</small></td>
                    <td><VisitorName name={x.visitor_name} ids={ids} /></td>
                    <td><b><Mt rial={x.amount_rial} /></b></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.undistributed.length > 200 && <small className="u-note">۲۰۰ فاکتور قدیمی‌تر نمایش داده شد؛ بقیه در صفحه کامل توزیع بار.</small>}
            {!d.undistributed.length && <div className="u-pending">فاکتور توزیع‌نشده‌ای ندارد.</div>}
          </div>
        </Card>

        <Card title={`مشتریان با مانده وصول‌نشده ${d.ym ? monthName(`${d.ym.year}/${String(d.ym.month).padStart(2, '0')}`) : ''}`} sub="فاکتورهای توزیع‌شده این ماه که هنوز وصول نشده‌اند">
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr><th>مشتری</th><th>توزیع‌شده<small>میلیون تومان</small></th><th>وصول‌شده<small>میلیون تومان</small></th><th>مانده<small>میلیون تومان</small></th></tr></thead>
              <tbody>
                {custs.slice(0, 100).map((c) => (
                  <tr key={`${c.dl_ref}-${c.customer_code}`}>
                    <td>{c.customer_name}<small className="u-sub">کد {faDigits(c.customer_code || '—')}</small></td>
                    <td><Mt rial={c.distributed_rial} /></td><td className="t-muted"><Mt rial={c.collected_rial} /></td>
                    <td className="t-warn"><b><Mt rial={c.remaining_rial} /></b></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!custs.length && <div className="u-pending">مانده وصول‌نشده‌ای از توزیع این ماه ندارد.</div>}
          </div>
        </Card>
      </>}
    </div>
  )
}
