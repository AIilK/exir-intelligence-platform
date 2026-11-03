import { useMemo } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { sendChatLink } from '@finance/chatbot/chat-link.ts'
import { useJson, qs, mt, n0, pct, signedPct, isNum, faDigits, moneyText, monthName } from '../data.js'
import { LEVEL } from '../model.js'
import { Card, Pending, Bar, Kpi, Money, PairBars, Mt } from '../ui.jsx'
import { PORTFOLIO_URL, finFacts, repLevel, RISK_FA, riskCls } from '../rahkaran.js'

const TABS = [
  { id: 'overview', label: 'نمای کلی', tone: 'text' },
  { id: 'sales', label: 'فروش', tone: 'sales' },
  { id: 'cheques', label: 'چک‌های باز', tone: 'fin' },
  { id: 'invoices', label: 'فاکتورها و وصول', tone: 'fin' },
]

const daysText = (d) => (!isNum(d) ? '—' : d < 0 ? `${n0(-d)} روز گذشته` : d === 0 ? 'امروز' : `${n0(d)} روز مانده`)

/** One Rahkaran B2B rep: sales (sales dashboard) and receivables / cheques / invoice collection (finance dashboard). */
export default function RahkaranFile() {
  const { code: rawCode } = useParams()
  const code = decodeURIComponent(rawCode)
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.id === sp.get('tab')) ? sp.get('tab') : 'overview'
  const period = sp.get('period') || 'YTD'
  const go = (t) => setSp((p) => { const n = new URLSearchParams(p); n.set('tab', t); return n }, { replace: true })
  const setPeriod = (v) => setSp((p) => { const n = new URLSearchParams(p); n.set('period', v); return n }, { replace: true })

  const sales = useJson(`/api/rk_sales/customer?${qs({ code, period })}`)
  const portfolio = useJson(PORTFOLIO_URL)
  const today = sales.data?.today
  const finRow = portfolio.data?.customers?.find((c) => String(c.counterpart_code) === code)
  const f = useMemo(() => finFacts(finRow, today), [finRow, today])
  const ref = f?.ref
  const file = useJson(ref ? `/api/v1/finance/customer-file/rahkaran/${ref}` : null)
  const cheques = useJson(ref ? `/api/v1/liquidity/received-cheques/customers/rahkaran/${ref}` : null)

  const c = sales.data?.customer
  const k = sales.data?.kpis
  const name = c?.name || f?.name || code
  const yl = today ? faDigits(today.slice(0, 4)) : 'امسال'
  const pyl = today ? faDigits(Number(today.slice(0, 4)) - 1) : 'پارسال'
  const periodLabel = period === 'YTD' ? `${yl} تا امروز` : monthName(period)
  const level = f ? repLevel(f) : null
  const finMissing = portfolio.data && !finRow

  // open the same customer inside the original dashboards
  const openFinance = () => { if (ref) sendChatLink({ view: 'customers', source: 'rahkaran', ref: String(ref), search: f?.name }); nav('/finance/customers') }
  const openSales = `/rahkaran?${qs({ customer: code })}`

  if (sales.error && finMissing) {
    return <div className="u-page"><Card><Pending state={{ error: `نماینده با کد ${code} در هیچ‌کدام از دو سیستم پیدا نشد` }} label="پرونده" /></Card></div>
  }

  return (
    <div className="u-page">
      <nav className="u-breadcrumb" aria-label="مسیر">
        <Link to="/">نمای مدیر</Link><span>›</span><Link to="/files/rahkaran">نمایندگان راهکاران</Link><span>›</span><b>{c?.short || name}</b>
      </nav>

      <section className="u-card u-identity">
        <div className="u-identity-top">
          <div className="u-identity-name">
            <i aria-hidden>◉</i>
            <div>
              <div className="u-row-gap">
                <h1>{name}</h1>
                {f && <span className={`u-pill ${LEVEL[level].cls}`}>{LEVEL[level].label}</span>}
                {f?.risk && <span className={`u-pill ${riskCls(f.risk)}`}>{RISK_FA[f.risk]}</span>}
              </div>
              <small>
                کد {faDigits(code)}{c ? ` · برند ${c.brand || '—'} · ${c.city || '—'}، ${c.province || '—'}` : ''}
                {(file.data?.purchase_stats?.first_invoice_date_jalali || sales.data?.first_date) ? ` · اولین خرید ${faDigits(file.data?.purchase_stats?.first_invoice_date_jalali || sales.data.first_date)}` : ''}
              </small>
            </div>
          </div>
          <div className="u-row-gap">
            <label className="u-search"><span>دوره فروش</span>
              <select value={period} onChange={(e) => setPeriod(e.target.value)}>
                {(sales.data?.periods || [{ value: 'YTD', label: 'از ابتدای سال' }]).map((p) => <option key={p.value} value={p.value}>{faDigits(p.label)}</option>)}
              </select>
            </label>
            <Link className="u-btn" to={openSales}>در داشبورد فروش</Link>
            <button className="u-btn" onClick={openFinance} disabled={!ref}>پرونده مشتری در داشبورد مالی</button>
          </div>
        </div>
        <div className="u-kpis u-kpis-file">
          <Kpi label={`فروش خالص ${periodLabel}`} tone="sales" rial={k?.net} onClick={() => go('sales')}
            delta={isNum(k?.growth) ? `${signedPct(k.growth * 100)} نسبت به همین بازه ${pyl}` : null} deltaTone={k?.growth >= 0 ? 'good' : 'bad'}
            note={isNum(k?.ly_net) ? `همین بازه ${pyl}: ${moneyText(k.ly_net)}` : ''} />
          <Kpi label="فاکتور و آخرین خرید" tone="sales" value={k ? n0(k.invoices) : '—'} unit="فاکتور" onClick={() => go('sales')}
            note={sales.data ? `آخرین خرید: ${faDigits(sales.data.last_date || '—')} · میانگین ${moneyText(k?.avg_invoice)}` : ''} />
          <Kpi label="برگشت از فروش" tone="sales" rial={k?.returns} valueTone={k?.returns > 0 ? 'warn' : ''}
            note={isNum(k?.return_rate) ? `${pct(k.return_rate * 100, 1)} فروش` : ''} />
          <Kpi label="مطالبات باز" tone="fin" rial={f?.debt} onClick={() => go('invoices')}
            delta={isNum(f?.dso) ? `دوره وصول: ${n0(f.dso)} روز` : f?.staleDebt ? 'بدهی بدون خرید امسال' : null} deltaTone={f?.dso > 120 || f?.staleDebt ? 'bad' : f?.dso > 75 ? 'warn' : 'flat'}
            note={finMissing ? 'در داشبورد مالی پیدا نشد' : f ? `کل در معرض وصول: ${moneyText(f.exposure)}` : 'در حال دریافت…'} />
          <Kpi label="چک باز در دست" tone="fin" rial={f?.openCheques} onClick={() => go('cheques')}
            note={f ? `${n0(f.openChequeCount)} فقره · پوشش مطالبات ${pct(f.coverage)}` : ''} />
          <Kpi label="چک سررسید گذشته" tone="fin" rial={f?.overdue} valueTone={f?.overdue > 0 ? 'bad' : ''} onClick={() => go('cheques')}
            note={f ? `${n0(f.overdueCount)} فقره وصول‌نشده` : ''} />
          <Kpi label="چک برگشتی تسویه‌نشده" tone="fin" rial={f?.returned} valueTone={f?.returned > 0 ? 'bad' : ''}
            note={f ? `در کل سابقه: ${n0(f.returnedCount)} فقره (${moneyText(f.returnedHist)})` : ''} />
        </div>
      </section>

      <div className="u-tabs" role="tablist" aria-label="بخش‌های پرونده">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''} onClick={() => go(t.id)}>
            <i className={`u-dot ${t.tone}`} />{t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="u-stack">
          <div className="u-grid-main">
            <MonthlyCard sales={sales} yl={yl} pyl={pyl} />
            <FinanceSummary f={f} portfolio={portfolio} finMissing={finMissing} go={go} openFinance={openFinance} />
          </div>
          <div className="u-grid2">
            <CategoriesCard sales={sales} periodLabel={periodLabel} />
            <InvoicesCard file={file} finMissing={finMissing} portfolio={portfolio} limit={5} action={<button className="u-link-btn" onClick={() => go('invoices')}>همه ←</button>} />
          </div>
        </div>
      )}
      {tab === 'sales' && <SalesTab sales={sales} periodLabel={periodLabel} f={f} go={go} openSales={openSales} />}
      {tab === 'cheques' && <ChequesCard cheques={cheques} ref_={ref} finMissing={finMissing} portfolio={portfolio} nav={nav} />}
      {tab === 'invoices' && <InvoicesCard file={file} finMissing={finMissing} portfolio={portfolio} open />}
    </div>
  )
}

function MonthlyCard({ sales, yl, pyl }) {
  const months = (sales.data?.monthly || []).map((m) => ({ label: monthName(m.month), cur: m.net, prev: m.ly_net }))
  return (
    <Card title={`فروش ماهانه: ${yl} در برابر ${pyl}`} sub="فروش خالص هر ماه از داشبورد فروش (راهکاران) · ماه جاری تا امروز">
      {!sales.data ? <Pending state={sales} label="فروش ماهانه" height={220} /> : <>
        <div className="u-legend"><span><i className="muted" />{pyl}</span><span><i className="sales" />{yl}</span></div>
        <PairBars items={months} aKey="prev" bKey="cur" aTone="muted" bTone="sales" aName={pyl} bName={yl} fmt={moneyText} height={190} dense />
      </>}
    </Card>
  )
}

function FinanceSummary({ f, portfolio, finMissing, go, openFinance }) {
  return (
    <Card title="وضعیت مالی" sub="از داشبورد مالی (راهکاران)" action={<button className="u-link-btn" onClick={openFinance}>پرونده مالی ←</button>}>
      {finMissing ? <Pending state={{ error: 'این نماینده در پرتفوی مطالبات داشبورد مالی نیست' }} label="وضعیت مالی" height={160} />
        : !f ? <Pending state={portfolio} label="وضعیت مالی" height={160} /> : (
        <div className="u-stack">
          <div className="u-facts">
            <div><small>مانده حساب</small><Money rial={f.debt} /><span>{isNum(f.dso) ? `معادل ${n0(f.dso)} روز فروش` : ''}</span></div>
            <div><small>چک باز در دست</small><Money rial={f.openCheques} /><span>پوشش {pct(f.coverage)} مطالبات</span></div>
            <div><small>فروش امسال در دفاتر مالی</small><Money rial={f.yearSalesFin} /><span>آخرین فاکتور: {faDigits(f.lastInvoice || '—')}</span></div>
          </div>
          {f.explanation && <p className="u-note">{String(f.explanation)}</p>}
          {!!f.actions?.length && (
            <div className="u-list">
              {f.actions.slice(0, 3).map((a, i) => <small key={i} className="u-sub">• {typeof a === 'string' ? a : a.title || a.action || JSON.stringify(a)}</small>)}
            </div>
          )}
          <div className="u-row-gap">
            <button className="u-btn ghost" onClick={() => go('cheques')}>چک‌های باز ←</button>
            <button className="u-btn ghost" onClick={() => go('invoices')}>فاکتورها و وصول ←</button>
          </div>
        </div>
      )}
    </Card>
  )
}

function CategoriesCard({ sales, periodLabel }) {
  const cats = (sales.data?.categories || []).filter((x) => x.net > 0)
  const max = Math.max(1, ...cats.map((x) => x.net))
  return (
    <Card title="گروه کالا" sub={`فروش خالص ${periodLabel}`}>
      {!sales.data ? <Pending state={sales} label="گروه‌های کالا" height={160} />
        : !cats.length ? <div className="u-pending">در این دوره خریدی نداشته است.</div> : (
        <div className="u-list">
          {cats.map((x) => (
            <div key={x.key} className="u-list-row"><span>{x.key}</span><Bar value={x.net} max={max} tone="sales" /><Money rial={x.net} /><small>{pct((x.share || 0) * 100)}</small></div>
          ))}
        </div>
      )}
    </Card>
  )
}

function SalesTab({ sales, periodLabel, f, go, openSales }) {
  const prods = sales.data?.products || []
  const inv = sales.data?.invoices || []
  return (
    <div className="u-stack">
      <div className="u-crosslink">
        <div>
          <b>وضعیت مالی همین نماینده</b>
          <small>{f ? `${moneyText(f.debt)} مطالبات باز · ${moneyText(f.openCheques)} چک باز · ${n0(f.overdueCount)} چک سررسید گذشته (${moneyText(f.overdue)})` : 'در حال دریافت از داشبورد مالی…'}</small>
        </div>
        <div className="u-row-gap">
          <button className="u-btn primary" onClick={() => go('cheques')}>چک‌ها ←</button>
          <button className="u-btn ghost" onClick={() => go('invoices')}>فاکتورها و وصول ←</button>
          <Link className="u-btn" to={openSales}>جزئیات در داشبورد فروش</Link>
        </div>
      </div>
      <div className="u-grid2">
        <Card title="کالاها" sub={`فروش خالص ${periodLabel} · میلیون تومان`}>
          {!sales.data ? <Pending state={sales} label="کالاها" height={200} /> : (
            <div className="u-table-wrap">
              <table className="u-table">
                <thead><tr><th>کالا</th><th>گروه</th><th>تعداد</th><th>ناخالص</th><th>خالص</th></tr></thead>
                <tbody>
                  {prods.slice(0, 100).map((p) => (
                    <tr key={p.product_code}><td>{p.product}<small className="u-sub">{faDigits(p.product_code)}</small></td><td className="t-muted">{p.cat2 || '—'}</td>
                      <td>{n0(p.qty)}</td><td className="t-muted"><Mt rial={p.gross} /></td><td><b><Mt rial={p.net} /></b></td></tr>
                  ))}
                </tbody>
              </table>
              {!prods.length && <div className="u-pending">در این دوره خریدی نداشته است.</div>}
            </div>
          )}
        </Card>
        <Card title="فاکتورها، برگشتی‌ها و درخواست‌ها" sub={`${periodLabel} · میلیون تومان`}>
          {!sales.data ? <Pending state={sales} label="فاکتورها" height={200} /> : (
            <div className="u-table-wrap">
              <table className="u-table">
                <thead><tr><th>نوع</th><th>شماره</th><th>تاریخ</th><th>اقلام</th><th>خالص</th><th>تخفیف نقدی</th></tr></thead>
                <tbody>
                  {inv.slice(0, 150).map((x) => (
                    <tr key={`${x.kind}-${x.inv}-${x.date}`}>
                      <td><span className={`u-pill ${x.kind === 'برگشتی' ? 'bad' : x.kind === 'درخواست' ? 'muted' : 'good'}`}>{x.kind}</span></td>
                      <td>{faDigits(x.inv)}</td><td className="t-muted">{faDigits(x.date)}</td><td>{n0(x.lines)}</td>
                      <td><b><Mt rial={x.net} /></b></td><td className="t-muted"><Mt rial={x.cash} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!inv.length && <div className="u-pending">در این دوره فاکتوری ندارد.</div>}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function ChequesCard({ cheques, ref_, finMissing, portfolio, nav }) {
  if (finMissing) return <Card><Pending state={{ error: 'این نماینده در داشبورد مالی نیست' }} label="چک‌ها" /></Card>
  if (!ref_) return <Card><Pending state={portfolio} label="چک‌ها" height={200} /></Card>
  const d = cheques.data?.data
  const rows = [...(d?.cheques || [])].sort((a, b) => String(a.due_date || '').localeCompare(String(b.due_date || '')))
  const openList = () => { sendChatLink({ view: 'receivedCheques', source: 'rahkaran', search: d?.customer_name }); nav('/finance/receivedCheques') }
  return (
    <Card title="چک‌های دریافتی باز" sub="از داشبورد مالی · درصد اتکا = احتمال وصول هر چک از سابقه همین مشتری (نشانگر را روی آن نگه دارید)"
      action={<button className="u-link-btn" onClick={openList}>چک‌های دریافتی راهکاران ←</button>}>
      {!d ? <Pending state={cheques} label="چک‌ها" height={200} /> : <>
        <div className="u-facts">
          <div><small>چک باز (قطعی)</small><Money rial={d.open?.definite_rial} /><span>{n0(d.open?.count)} فقره · اتکا {pct(d.open?.reliance_percent)}</span></div>
          <div><small>قابل اتکا</small><Money rial={d.open?.reliance_rial} /><span>ریسک وصول: {moneyText(d.open?.collection_risk_rial)}</span></div>
          <div><small>سررسید گذشته</small><Money rial={d.overdue?.definite_rial} className={d.overdue?.definite_rial > 0 ? 't-bad' : ''} /><span>{n0(d.overdue?.count)} فقره</span></div>
        </div>
        <div className="u-table-wrap">
          <table className="u-table">
            <thead><tr><th>سررسید</th><th>زمان</th><th>شماره چک</th><th>مبلغ<small>میلیون تومان</small></th><th>اتکا</th><th>محل نگهداری</th><th>ثبت</th></tr></thead>
            <tbody>
              {rows.slice(0, 300).map((x) => (
                <tr key={x.cheque_id}>
                  <td className={x.days_to_due < 0 ? 't-bad' : ''}>{faDigits(x.due_date_jalali || '—')}</td>
                  <td className="t-muted">{daysText(x.days_to_due)}</td>
                  <td className="t-muted">{faDigits(x.serial_number || '—')}</td>
                  <td><b><Mt rial={x.amount_rial} /></b></td>
                  <td title={(x.reliance_reasons || []).join('\n')}><span className={`u-pill ${x.reliance_percent >= 75 ? 'good' : x.reliance_percent >= 50 ? 'warn' : 'bad'}`}>{pct(x.reliance_percent)}</span></td>
                  <td className="t-muted">{x.holding === 'bank' ? 'بانک' : x.holding === 'cashbox' ? 'صندوق' : x.holding || '—'}</td>
                  <td className="t-muted">{faDigits(x.registered_at_jalali?.slice(0, 10) || '—')}{x.registered_by && <small className="u-sub">{x.registered_by}</small>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 300 && <small className="u-note">۳۰۰ ردیف اول نمایش داده شد.</small>}
          {!rows.length && <div className="u-pending">چک باز ندارد.</div>}
        </div>
      </>}
    </Card>
  )
}

function InvoicesCard({ file, finMissing, portfolio, limit, action, open }) {
  if (finMissing) return <Card><Pending state={{ error: 'این نماینده در داشبورد مالی نیست' }} label="فاکتورها" /></Card>
  const d = file.data
  const last = (d?.last_invoices || []).slice(0, limit || undefined)
  return (
    <div className="u-stack">
      <Card title="آخرین فاکتورها و وصول" sub={d?.remaining_note || 'مانده هر فاکتور از مانده حساب مشتری (FIFO)'} action={action}>
        {!d ? <Pending state={file.error ? file : portfolio} label="فاکتورها" height={160} /> : (
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr><th>شماره</th><th>تاریخ</th><th>مبلغ<small>میلیون تومان</small></th><th>وصول‌شده</th><th>مانده<small>میلیون تومان</small></th></tr></thead>
              <tbody>
                {last.map((x) => (
                  <tr key={x.invoice_id}>
                    <td>{faDigits(x.number)}</td><td className="t-muted">{faDigits(x.date_jalali)}</td><td><b><Mt rial={x.amount_rial} /></b></td>
                    <td><span className="u-inline-bar"><Bar value={x.collected_percent || 0} max={100} tone="fin" /><b>{pct(x.collected_percent)}</b></span></td>
                    <td className={x.remaining_rial > 0 ? 't-warn' : ''}><Mt rial={x.remaining_rial} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!last.length && <div className="u-pending">فاکتوری ثبت نشده است.</div>}
          </div>
        )}
      </Card>
      {open && d && (
        <Card title={`فاکتورهای باز (${n0(d.open_invoices?.length)})`} sub="فاکتورهایی که مانده حساب به آن‌ها تخصیص یافته است">
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr><th>شماره</th><th>تاریخ</th><th>سن</th><th>مبلغ<small>میلیون تومان</small></th><th>مانده<small>میلیون تومان</small></th></tr></thead>
              <tbody>
                {(d.open_invoices || []).map((x) => (
                  <tr key={x.invoice_id}>
                    <td>{faDigits(x.number)}</td><td className="t-muted">{faDigits(x.date_jalali)}</td>
                    <td className={x.age_days > 90 ? 't-bad' : x.age_days > 60 ? 't-warn' : 't-muted'}>{n0(x.age_days)} روز</td>
                    <td><Mt rial={x.amount_rial} /></td><td><b><Mt rial={x.remaining_rial} /></b></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!d.open_invoices?.length && <div className="u-pending">فاکتور بازی ندارد.</div>}
          </div>
          {d.purchase_stats && <small className="u-note">
            خرید {faDigits(d.current_year_label)}: {moneyText(d.purchase_stats.current_year_amount_rial)} در {n0(d.purchase_stats.current_year_invoice_count)} فاکتور ·
            {' '}{faDigits(d.previous_year_label)}: {moneyText(d.purchase_stats.previous_year_amount_rial)} · اولین فاکتور {faDigits(d.purchase_stats.first_invoice_date_jalali || '—')}
          </small>}
        </Card>
      )}
    </div>
  )
}
