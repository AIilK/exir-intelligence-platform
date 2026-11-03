import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { detailPath } from '@sales/lib.jsx'
import { useJson, qs, mt, n0, pct, signedPct, growth, isNum, dayOfYear, faDigits, moneyText } from '../data.js'
import { normName, branchCheques, chequesByVisitor, hybridLevel, yearCompare, LEVEL, MIN_GROWTH_BASE_RIAL } from '../model.js'
import { useSalesSet, NETWORK_URL } from '../hooks.js'
import { PageHead, Card, Pending, Bar, Kpi, Money } from '../ui.jsx'
import { YearChart, ChequeHealth, DebtSummary, ChequesTab, DebtTab, InvoicesTab, VisitorsTable, visitorIds } from '../fileTabs.jsx'
import { useHybridDistribution, DistributionGlance, DistributionTab } from '../distTab.jsx'

const TABS = [
  { id: 'overview', label: 'نمای کلی', tone: 'text' },
  { id: 'sales', label: 'فروش', tone: 'sales' },
  { id: 'cheques', label: 'چک‌ها', tone: 'fin' },
  { id: 'debt', label: 'مطالبات', tone: 'fin' },
  { id: 'visitors', label: 'ویزیتورها', tone: 'text' },
  { id: 'invoices', label: 'فاکتورهای اخیر و وصول', tone: 'fin' },
  { id: 'distribution', label: 'توزیع بار', tone: 'fin' },
]

const short = (xs = []) => (xs.length ? `${xs.slice(0, 3).join('، ')}${xs.length > 3 ? ` و ${n0(xs.length - 3)} نفر دیگر` : ''}` : '—')
const findBranch = (resp, key) => resp?.branches?.find((b) => normName(b.key) === key)

export default function HybridFile() {
  const { name: rawName } = useParams()
  const name = decodeURIComponent(rawName)
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.id === sp.get('tab')) ? sp.get('tab') : 'overview'
  const bucket = sp.get('bucket') || 'all'
  const go = (t, b) => setSp(b ? { tab: t, bucket: b } : { tab: t }, { replace: true })

  const S = useSalesSet()
  const { P, Y, vat } = S
  const network = useJson(NETWORK_URL)
  const key = normName(name)
  const branch = network.data?.branches?.find((b) => normName(b.branch_name) === key)
  const salesKey = findBranch(S.cur.data, key)?.key || findBranch(S.ytd.data, key)?.key
  const file = useJson(branch ? `${NETWORK_URL}/branches/${branch.branch_id}` : null)
  const detail = useJson(P && salesKey ? `/api/detail/branch?${qs({ key: salesKey, vat })}` : null)
  const monthly = useJson(salesKey ? `/api/monthly?${qs({ branch: salesKey, vat })}` : null)

  const curNet = detail.data?.kpis?.net ?? findBranch(S.cur.data, key)?.net
  const prevNet = findBranch(S.prev.data, key)?.net
  const g = prevNet >= MIN_GROWTH_BASE_RIAL ? growth(curNet, prevNet) : null
  const overall = growth(S.cur.data?.kpis?.net, S.prev.data?.kpis?.net)
  const ytd = findBranch(S.ytd.data, key)?.net
  const ytdPrev = findBranch(S.ytdPrev.data, key)?.net
  const fullPrev = findBranch(S.fullPrev.data, key)?.net
  const yg = ytdPrev >= MIN_GROWTH_BASE_RIAL ? growth(ytd, ytdPrev) : null

  const dist = useHybridDistribution(name, P)
  const ch = useMemo(() => branchCheques(file.data), [file.data])
  const chq = useMemo(() => chequesByVisitor(ch.rows), [ch])
  const ids = useMemo(() => visitorIds(file.data?.visitors), [file.data])
  const monthBy = useMemo(() => new Map((detail.data?.breakdowns?.seller || []).map((s) => [normName(s.label), s.net])), [detail.data])
  const months = useMemo(() => (Y ? yearCompare(monthly.data?.months, Y.year) : []), [monthly.data, Y?.year])
  const debt = file.data?.debt
  const doy = P ? dayOfYear(P.today) : null
  const yearSales = file.data?.sales_stats?.current_year_sales_rial
  const dso = isNum(debt?.open_account_receivable_rial) && yearSales > 0 && doy ? debt.open_account_receivable_rial / (yearSales / doy) : null
  const level = hybridLevel({ dso, growth: g, overall })
  const overdue = ch.buckets.find((b) => b.key === 'overdue')
  const returned = ch.buckets.find((b) => b.key === 'returned')
  const yl = Y ? faDigits(Y.year) : 'امسال'
  const pyl = Y ? faDigits(Y.prevYear) : 'پارسال'

  if (network.data && !branch && S.cur.data && !salesKey) {
    return <div className="u-page"><PageHead crumb="پرونده‌ها / هیبریدها" title={name} /><Card><Pending state={{ error: 'این هیبرید در هیچ‌کدام از دو سیستم پیدا نشد' }} label="پرونده" /></Card></div>
  }

  return (
    <div className="u-page">
      <nav className="u-breadcrumb" aria-label="مسیر">
        <Link to="/">نمای مدیر</Link><span>›</span><Link to="/files/hybrids">هیبریدها</Link><span>›</span><b>{name}</b>
      </nav>

      <section className="u-card u-identity">
        <div className="u-identity-top">
          <div className="u-identity-name">
            <i aria-hidden>⬢</i>
            <div>
              <div className="u-row-gap"><h1>{name}</h1>{file.data && <span className={`u-pill ${LEVEL[level].cls}`}>{LEVEL[level].label}</span>}</div>
              <small>
                {file.data
                  ? `هیبرید من: ${short(file.data.hybrids)} · سرپرست: ${short(file.data.supervisors)} · ${n0(file.data.visitors?.length)} ویزیتور · ${n0(debt?.customer_count)} مشتری`
                  : 'در حال دریافت پرونده از داشبورد مالی…'}
              </small>
            </div>
          </div>
          <div className="u-row-gap">
            {salesKey && <Link className="u-btn" to={detailPath('branch', salesKey)}>جزئیات فروش در داشبورد فروش</Link>}
            <Link className="u-btn" to="/finance/collections">مرکز عملیات وصول</Link>
          </div>
        </div>
        <div className="u-kpis u-kpis-file">
          <Kpi label={`فروش ${yl} تا امروز`} tone="sales" rial={ytd} onClick={() => go('overview')}
            delta={isNum(yg) ? `${signedPct(yg)} نسبت به همین بازه ${pyl}` : null} deltaTone={yg >= 0 ? 'good' : 'bad'}
            note={isNum(ytdPrev) ? `همین بازه ${pyl}: ${moneyText(ytdPrev)}` : ''} />
          <Kpi label={`فروش کل ${pyl}`} tone="sales" rial={fullPrev} onClick={() => go('overview')}
            note={isNum(fullPrev) ? `میانگین ماهانه: ${moneyText(fullPrev / 12)}` : ''} />
          <Kpi label={`فروش ${P?.curLabel || 'این ماه'} تا امروز`} tone="sales" rial={curNet} onClick={() => go('sales')}
            delta={isNum(g) ? `${signedPct(g)} نسبت به همین بازه ${P?.prevLabel}` : null} deltaTone={isNum(g) && isNum(overall) && g - overall < -15 ? 'bad' : g >= 0 ? 'good' : 'warn'}
            note={isNum(overall) ? `کل شرکت: ${signedPct(overall)}` : ''} />
          <Kpi label="مطالبات باز" tone="fin" rial={debt?.open_account_receivable_rial} onClick={() => go('debt')}
            delta={isNum(dso) ? `دوره وصول: ${n0(dso)} روز` : null} deltaTone={dso > 120 ? 'bad' : dso > 75 ? 'warn' : 'flat'}
            note={debt ? `${n0(debt.debtor_customer_count)} مشتری بدهکار از ${n0(debt.customer_count)}` : ''} />
          <Kpi label="چک باز در دست" tone="fin" rial={ch.summary.open?.amount_rial} onClick={() => go('cheques', 'all')}
            note={file.data ? `${n0(ch.summary.open?.count)} فقره · ${n0(ch.summary.high?.count)} با احتمال برگشت بالا` : ''} />
          <Kpi label="چک سررسید گذشته" tone="fin" rial={overdue?.amount} valueTone={overdue?.amount > 0 ? 'bad' : ''} onClick={() => go('cheques', 'overdue')}
            note={file.data ? `${n0(overdue?.count)} فقره وصول‌نشده` : ''} />
          <Kpi label="چک برگشتی" tone="fin" rial={returned?.amount} valueTone={returned?.amount > 0 ? 'bad' : ''} onClick={() => go('cheques', 'returned')}
            note={file.data ? `${n0(returned?.count)} فقره تسویه‌نشده` : ''} />
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
            <YearChart state={salesKey ? monthly : { error: 'این هیبرید در داشبورد فروش نیست' }} months={months} Y={Y}
              action={<button className="u-link-btn" onClick={() => go('sales')}>فروش این ماه ←</button>} />
            <DebtSummary file={file} dso={dso} go={go} />
          </div>
          <div className="u-grid2">
            <ChequeHealth file={file} ch={ch} go={go} />
            <MonthGlance detail={detail} salesKey={salesKey} P={P} go={go} />
          </div>
          <DistributionGlance d={dist} go={go} />
          {!file.data ? <Card><Pending state={file} label="ویزیتورها" height={160} /></Card>
            : <VisitorsTable visitors={file.data.visitors} monthBy={monthBy} chq={chq} Y={Y} limit={8}
                title={`ویزیتورها — ۸ نفر با بیشترین فروش ${yl}`}
                action={<button className="u-link-btn" onClick={() => go('visitors')}>همه {n0(file.data.visitors?.length)} ویزیتور ←</button>} />}
        </div>
      )}
      {tab === 'sales' && <SalesTab detail={detail} salesKey={salesKey} file={file} go={go} ch={ch} debt={debt} />}
      {tab === 'cheques' && <ChequesTab file={file} ch={ch} bucket={bucket} go={go} ids={ids} />}
      {tab === 'debt' && <DebtTab file={file} detailUrl={branch ? `${NETWORK_URL}/branches/${branch.branch_id}/debt-detail` : null} dso={dso} ids={ids} />}
      {tab === 'visitors' && (!file.data ? <Card><Pending state={file} label="ویزیتورها" height={220} /></Card>
        : <VisitorsTable visitors={file.data.visitors} monthBy={monthBy} chq={chq} Y={Y} />)}
      {tab === 'invoices' && <InvoicesTab file={file} ids={ids} />}
      {tab === 'distribution' && <DistributionTab d={dist} ids={ids} />}
    </div>
  )
}

/** This month's sales in a glance (overview tab). */
function MonthGlance({ detail, salesKey, P, go }) {
  const k = detail.data?.kpis
  return (
    <Card title={`فروش ${P?.curLabel || 'این ماه'} در یک نگاه`} sub="از داشبورد فروش" action={<button className="u-link-btn" onClick={() => go('sales')}>جزئیات فروش ←</button>}>
      {!salesKey ? <Pending state={{ error: 'این هیبرید در داشبورد فروش این دوره فروشی ندارد' }} label="فروش" height={160} />
        : !k ? <Pending state={detail} label="فروش این ماه" height={160} /> : (
        <div className="u-facts">
          <div><small>فروش خالص</small><Money rial={k.net} /><span>{n0(k.days)} روز کاری · {n0(k.invoices)} فاکتور</span></div>
          <div><small>پیش‌بینی پایان ماه</small><Money rial={k.forecast} /><span>با روند فعلی</span></div>
          <div><small>درخواست (سفارش)</small><Money rial={k.req_net} /><span>نرخ تبدیل به فاکتور: {pct((k.req_conv || 0) * 100)}</span></div>
          <div><small>برگشت از فروش</small><Money rial={k.returns_net} /><span>{pct((k.return_rate || 0) * 100, 1)} فروش</span></div>
          <div><small>مشتری خریدار</small><span className="u-money"><b>{n0(k.customers)}</b><small>مشتری</small></span><span>میانگین فاکتور: {moneyText(k.avg_invoice)}</span></div>
          <div><small>نرخ تخفیف</small><span className="u-money"><b>{pct((k.disc_rate || 0) * 100, 1)}</b></span><span>تخفیف حجمی و نقدی</span></div>
        </div>
      )}
    </Card>
  )
}

// ---------------------------------------------------------------- sales tab
function SalesTab({ detail, salesKey, file, go, ch, debt }) {
  const k = detail.data?.kpis
  const trend = detail.data?.trend || []
  const maxDay = Math.max(1, ...trend.map((d) => d.net || 0))
  const avg = trend.length ? trend.reduce((s, d) => s + (d.net || 0), 0) / trend.length : 0
  const brands = (detail.data?.breakdowns?.brand || []).filter((b) => b.net > 0).slice(0, 8)
  const maxBrand = Math.max(1, ...brands.map((b) => b.net || 0))
  const overdue = ch.buckets.find((b) => b.key === 'overdue')
  return (
    <div className="u-stack">
      <div className="u-crosslink">
        <div>
          <b>وضعیت مالی همین هیبرید</b>
          <small>{file.data
            ? `${moneyText(debt?.open_account_receivable_rial)} مطالبات باز · ${n0(overdue?.count)} چک سررسید گذشته (${moneyText(overdue?.amount)}) · ${n0(ch.summary.high?.count)} چک با احتمال برگشت بالا`
            : 'در حال دریافت از داشبورد مالی…'}</small>
        </div>
        <div className="u-row-gap">
          <button className="u-btn primary" onClick={() => go('cheques', 'all')}>مشاهده چک‌ها ←</button>
          <button className="u-btn ghost" onClick={() => go('invoices')}>فاکتورها و وصول ←</button>
        </div>
      </div>

      {!salesKey ? <Card><Pending state={{ error: detail.error || 'این هیبرید در داشبورد فروش این دوره فروشی ندارد' }} label="فروش" /></Card>
        : !k ? <Card><Pending state={detail} label="فروش این ماه" height={220} /></Card> : <>
        <div className="u-kpis">
          <Kpi label="فروش خالص" rial={k.net} note={`${n0(k.days)} روز کاری · ${n0(k.invoices)} فاکتور`} />
          <Kpi label="درخواست (سفارش)" rial={k.req_net} note={`نرخ تبدیل به فاکتور: ${pct((k.req_conv || 0) * 100)}`} />
          <Kpi label="پیش‌بینی پایان ماه" rial={k.forecast} note="با روند فعلی" />
          <Kpi label="برگشت از فروش" rial={k.returns_net} note={`${pct((k.return_rate || 0) * 100, 1)} فروش`} />
          <Kpi label="مشتری خریدار" value={n0(k.customers)} unit="مشتری" note={`میانگین هر فاکتور: ${moneyText(k.avg_invoice)}`} />
        </div>
        <div className="u-grid-main">
          <Card title="فروش خالص روزانه" sub={`خط‌چین = میانگین روزانه این دوره (${moneyText(avg)}) · نشانگر را روی ستون نگه دارید`}
            action={<Link to={detailPath('branch', salesKey)}>جزئیات کامل ←</Link>}>
            <div className="u-daily" style={{ '--avg': `${(avg / maxDay) * 100}%` }}>
              <i className="u-daily-avg" />
              {trend.map((d) => (
                <span key={d.date} title={`${faDigits(d.date)}: ${moneyText(d.net)}`}
                  className={d.net >= avg ? 'hi' : ''} style={{ height: `${Math.max(1, (Math.max(0, d.net) / maxDay) * 100)}%` }} />
              ))}
            </div>
            <div className="u-daily-axis"><small>{faDigits(trend[0]?.date?.slice(5) || '')}</small><small>{faDigits(trend[trend.length - 1]?.date?.slice(5) || '')}</small></div>
          </Card>
          <Card title="سهم برندها" sub="فروش خالص این ماه · روی برند بزنید">
            <div className="u-list">
              {brands.map((b) => (
                <Link key={b.key} to={detailPath('brand', b.key, [['branch', salesKey]])} className="u-list-row">
                  <span>{b.label}</span><Bar value={b.net} max={maxBrand} tone="sales" /><Money rial={b.net} /><small>{pct((b.share || 0) * 100)}</small>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </>}
    </div>
  )
}
