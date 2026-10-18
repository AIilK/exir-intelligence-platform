import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useApp, detailPath } from '@sales/lib.jsx'
import { useJson, qs, n0, growth, isNum, dayOfYear, faDigits, moneyText, yearPeriods, monthName } from '../data.js'
import { normName, branchCheques, yearCompare } from '../model.js'
import { NETWORK_URL } from '../hooks.js'
import { Card, Pending, Kpi } from '../ui.jsx'
import { YearChart, ChequeHealth, DebtSummary, ChequesTab, DebtTab, InvoicesTab, cleanName } from '../fileTabs.jsx'
import { hybridPath } from '../HybridTable.jsx'

const TABS = [
  { id: 'overview', label: 'نمای کلی', tone: 'text' },
  { id: 'cheques', label: 'چک‌ها', tone: 'fin' },
  { id: 'debt', label: 'مطالبات و بدهکاران', tone: 'fin' },
  { id: 'invoices', label: 'فاکتورهای اخیر و وصول', tone: 'fin' },
]

/**
 * The sales dashboard knows a visitor as «branch code-visitor code» and finance by its Karamad id,
 * so the two are matched by name inside the same branch.
 */
function useSalesSeller(meta, branchName, visitorName) {
  return useMemo(() => {
    if (!meta || !branchName || !visitorName) return null
    const b = normName(branchName)
    const v = normName(visitorName)
    return (meta.options?.seller || []).find((o) => normName(o.group) === b && normName(String(o.label).replace(/\s*\([^)]*\)\s*$/, '')) === v) || null
  }, [meta, branchName, visitorName])
}

export default function VisitorFile() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.id === sp.get('tab')) ? sp.get('tab') : 'overview'
  const bucket = sp.get('bucket') || 'all'
  const go = (t, b) => setSp(b ? { tab: t, bucket: b } : { tab: t }, { replace: true })

  const { meta, vat } = useApp()
  const Y = yearPeriods(meta)
  const v = vat ? 1 : 0
  const file = useJson(`${NETWORK_URL}/visitors/${id}`)
  const f = file.data
  const seller = useSalesSeller(meta, f?.branch_name, f?.visitor_name)
  const detail = useJson(seller ? `/api/detail/seller?${qs({ key: seller.value, vat: v })}` : null)
  const monthly = useJson(seller ? `/api/monthly?${qs({ seller: seller.value, vat: v })}` : null)
  const months = useMemo(() => (Y ? yearCompare(monthly.data?.months, Y.year) : []), [monthly.data, Y?.year])
  const ch = useMemo(() => branchCheques(f), [f])
  const ss = f?.sales_stats
  const debt = f?.debt
  const doy = meta?.file?.today ? dayOfYear(meta.file.today) : null
  const dso = isNum(debt?.open_account_receivable_rial) && ss?.current_year_sales_rial > 0 && doy
    ? debt.open_account_receivable_rial / (ss.current_year_sales_rial / doy) : null
  const yg = ss?.previous_year_sales_rial > 0 ? growth(ss.current_year_sales_rial, ss.previous_year_sales_rial) : null
  const overdue = ch.buckets.find((b) => b.key === 'overdue')
  const returned = ch.buckets.find((b) => b.key === 'returned')
  const k = detail.data?.kpis
  const name = f ? cleanName(f.visitor_name) : '…'
  const cy = faDigits(f?.current_year_label || '')
  const py = faDigits(f?.previous_year_label || '')
  const phone = f?.visitor_name?.includes('/') ? f.visitor_name.split('/').pop().trim() : ''

  if (file.data?.status === 'not_found' || file.error) {
    return <div className="u-page"><Card><Pending state={{ error: file.error || 'این ویزیتور پیدا نشد' }} label="پرونده ویزیتور" /></Card></div>
  }

  return (
    <div className="u-page">
      <nav className="u-breadcrumb" aria-label="مسیر">
        <Link to="/">نمای مدیر</Link><span>›</span><Link to="/files/hybrids">هیبریدها</Link><span>›</span>
        {f?.branch_name ? <Link to={hybridPath(f.branch_name.trim(), 'visitors')}>{f.branch_name.trim()}</Link> : <span>…</span>}
        <span>›</span><b>{name}</b>
      </nav>

      <section className="u-card u-identity">
        <div className="u-identity-top">
          <div className="u-identity-name">
            <i aria-hidden>♙</i>
            <div>
              <div className="u-row-gap">
                <h1>{name}</h1>
                {f && <span className={`u-pill ${f.active ? 'good' : 'muted'}`}>{f.active ? 'ویزیتور فعال' : 'غیرفعال'}</span>}
              </div>
              <small>{f
                ? `هیبرید: ${f.branch_name?.trim() || '—'} · سرپرست: ${f.supervisor || '—'}${seller ? ` · کد فروشنده: ${faDigits(String(seller.value).split('-').pop())}` : ''}${phone ? ` · ${faDigits(phone)}` : ''}`
                : 'در حال دریافت پرونده از داشبورد مالی…'}</small>
            </div>
          </div>
          <div className="u-row-gap">
            {f?.branch_name && <Link className="u-btn" to={hybridPath(f.branch_name.trim())}>پرونده هیبرید</Link>}
            {seller && <Link className="u-btn" to={detailPath('seller', seller.value)}>جزئیات فروش در داشبورد فروش</Link>}
          </div>
        </div>
        <div className="u-kpis u-kpis-file">
          <Kpi label={`فروش ${cy}`} tone="sales" rial={ss?.current_year_sales_rial} onClick={() => go('overview')}
            delta={isNum(yg) ? `فروش کل ${py}: ${moneyText(ss.previous_year_sales_rial)}` : null} deltaTone="flat"
            note={ss ? `${n0(ss.current_year_invoice_count)} فاکتور · از دفاتر کارآمد` : ''} />
          <Kpi label={`فروش ${meta?.file?.month ? monthName(meta.file.month) : 'این ماه'} تا امروز`} tone="sales" rial={k?.net} to={seller ? detailPath('seller', seller.value) : undefined}
            note={k ? `${n0(k.customers)} مشتری · ${n0(k.invoices)} فاکتور` : seller ? 'در حال دریافت…' : 'در داشبورد فروش پیدا نشد'} />
          <Kpi label="مطالبات مشتریانش" tone="fin" rial={debt?.open_account_receivable_rial} onClick={() => go('debt')}
            delta={isNum(dso) ? `معادل ${n0(dso)} روز فروش` : null} deltaTone={dso > 120 ? 'bad' : dso > 75 ? 'warn' : 'flat'}
            note={debt ? `${n0(debt.debtor_customer_count)} مشتری بدهکار از ${n0(debt.customer_count)}` : ''} />
          <Kpi label="چک باز در دست" tone="fin" rial={ch.summary.open?.amount_rial} onClick={() => go('cheques', 'all')}
            note={f ? `${n0(ch.summary.open?.count)} فقره · ${n0(ch.summary.high?.count)} با احتمال برگشت بالا` : ''} />
          <Kpi label="چک سررسید گذشته" tone="fin" rial={overdue?.amount} valueTone={overdue?.amount > 0 ? 'bad' : ''} onClick={() => go('cheques', 'overdue')}
            note={f ? `${n0(overdue?.count)} فقره وصول‌نشده` : ''} />
          <Kpi label="چک برگشتی" tone="fin" rial={returned?.amount} valueTone={returned?.amount > 0 ? 'bad' : ''} onClick={() => go('cheques', 'returned')}
            note={f ? `${n0(returned?.count)} فقره تسویه‌نشده` : ''} />
        </div>
      </section>

      <div className="u-tabs" role="tablist" aria-label="بخش‌های پرونده ویزیتور">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''} onClick={() => go(t.id)}>
            <i className={`u-dot ${t.tone}`} />{t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="u-stack">
          <div className="u-grid-main">
            <YearChart state={seller ? monthly : { error: f ? 'این ویزیتور در داشبورد فروش پیدا نشد' : null }} months={months} Y={Y} title="فروش ماهانه این ویزیتور"
              action={seller && <Link to={detailPath('seller', seller.value)}>جزئیات فروش ←</Link>} />
            <DebtSummary file={file} dso={dso} go={go} />
          </div>
          <div className="u-grid2">
            <ChequeHealth file={file} ch={ch} go={go} title="چک‌های دریافتی از مشتریان این ویزیتور" />
            <InvoicesTab file={file} showVisitor={false} />
          </div>
          {ss && (
            <Card title="سابقه فروش (دفاتر کارآمد)" sub="خالص = قابل پرداخت منهای برگشتی">
              <div className="u-facts">
                <div><small>فروش {cy}</small><span className="u-money"><b>{moneyText(ss.current_year_sales_rial)}</b></span><span>{n0(ss.current_year_invoice_count)} فاکتور</span></div>
                <div><small>فروش {py}</small><span className="u-money"><b>{moneyText(ss.previous_year_sales_rial)}</b></span><span>{n0(ss.previous_year_invoice_count)} فاکتور</span></div>
                <div><small>کل فروش تا امروز</small><span className="u-money"><b>{moneyText(ss.sales_amount_rial)}</b></span><span>{n0(ss.invoice_count)} فاکتور</span></div>
                <div><small>اولین / آخرین فاکتور</small><span className="u-money"><b>{faDigits(ss.last_invoice_date_jalali || '—')}</b></span><span>از {faDigits(ss.first_invoice_date_jalali || '—')}</span></div>
              </div>
            </Card>
          )}
        </div>
      )}
      {tab === 'cheques' && <ChequesTab file={file} ch={ch} bucket={bucket} go={go} scopeLabel="مشتریان این ویزیتور" showVisitor={false} />}
      {tab === 'debt' && <DebtTab file={file} detailUrl={`${NETWORK_URL}/visitors/${id}/debt-detail`} dso={dso} showVisitors={false} />}
      {tab === 'invoices' && <InvoicesTab file={file} showVisitor={false} />}
    </div>
  )
}
