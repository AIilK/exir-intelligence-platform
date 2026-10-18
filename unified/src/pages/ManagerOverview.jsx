import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '@sales/lib.jsx'
import { useJson, mt, bt, n0, pct, signedPct, growth, isNum, monthName, faDigits, moneyText } from '../data.js'
import { useSalesSet } from '../hooks.js'
import { receivedOverview, issuedOverview, weeklyFlow, hybridRows } from '../model.js'
import { PageHead, Card, Chip, Pending, Bar, MaybeLink, PairBars, Money } from '../ui.jsx'
import HybridTable, { hybridPath } from '../HybridTable.jsx'
import FinanceAgents from '../FinanceAgents.jsx'

const FIN = '/api/v1'

export default function ManagerOverview() {
  const { meta } = useApp()
  const S = useSalesSet()
  const { P, Y, vat: v } = S
  const salesCur = S.cur
  const salesPrev = S.prev
  const monthly = useJson(`/api/monthly?vat=${v}`)
  const network = useJson(`${FIN}/finance/sales-network`)
  const recvR = useJson(`${FIN}/liquidity/received-cheques?horizon_days=365`)
  const issR = useJson(`${FIN}/liquidity/issued-cheques?horizon_days=365`)
  const flowR = useJson(`${FIN}/liquidity/summary?horizon_days=35`)
  const inflR = useJson(`${FIN}/liquidity/inflows?base_days=180&channel=hybrid`)

  const recv = useMemo(() => receivedOverview(recvR.data), [recvR.data])
  const iss = useMemo(() => issuedOverview(issR.data), [issR.data])
  const flow = useMemo(() => weeklyFlow(flowR.data), [flowR.data])
  const hybrids = useMemo(() => (network.data && salesCur.data
    ? hybridRows({ network: network.data, salesCur: salesCur.data, salesPrev: salesPrev.data, ytd: S.ytd.data, ytdPrev: S.ytdPrev.data, fullPrev: S.fullPrev.data, today: P?.today })
    : null), [network.data, salesCur.data, salesPrev.data, S.ytd.data, S.ytdPrev.data, S.fullPrev.data, P?.today])

  // sales vs hybrid collection, per month
  const collByMonth = new Map((inflR.data?.data?.monthly_trend || []).map((m) => [m.month, m.values?.hybrid ?? m.total_rial]))
  const salesNet = salesCur.data?.kpis?.net
  const prevNet = salesPrev.data?.kpis?.net
  const salesGrowth = growth(salesNet, prevNet)
  const collCur = P ? collByMonth.get(P.month) : null
  const collPrevFull = P ? collByMonth.get(meta?.file?.months?.[1]?.month) : null
  const collRatio = isNum(collCur) && salesNet > 0 ? (collCur / salesNet) * 100 : null
  const debtTotal = network.data?.summary?.open_account_receivable_rial
  const trend = (monthly.data?.months || []).slice(-6).map((m) => {
    const c = collByMonth.get(m.month)
    const r = isNum(c) && m.net > 0 ? (c / m.net) * 100 : null
    return {
      label: monthName(m.month), sales: m.net, coll: c ?? null,
      ratio: isNum(r) ? pct(r) : '—', subTone: 't-muted',
    }
  })

  const heaviest = flow?.weeks?.reduce((a, w) => (!a || w.net < a.net ? w : a), null)
  const worstHybrid = hybrids?.find((h) => h.level === 'critical') || hybrids?.find((h) => h.level === 'warn')
  const biggestDrop = hybrids?.filter((h) => isNum(h.growth) && h.prevNet > 1e10).sort((a, b) => a.growth - b.growth)[0]

  const decisions = []
  if (recv && recv.buckets[0].amount > 0) decisions.push({
    level: 'critical', domain: 'مالی', to: '/finance/receivedCheques', cta: 'چک‌های دریافتی',
    text: `${moneyText(recv.buckets[0].amount)} چک دریافتی (${n0(recv.buckets[0].count)} فقره) از سررسید گذشته و وصول نشده؛ ${moneyText(recv.returned.amount)} هم چک برگشتی تسویه‌نشده داریم.`,
  })
  if (heaviest && heaviest.net < 0) decisions.push({
    level: 'warn', domain: 'مالی', to: '/finance/liquidity', cta: 'نقدینگی',
    text: `${heaviest.label} (${faDigits(heaviest.from.slice(5))} تا ${faDigits(heaviest.to.slice(5))}) سنگین‌ترین هفته است: خروجی ${moneyText(heaviest.outflow)} و ورودی ${moneyText(heaviest.inflow)}${heaviest.payroll > 0 ? '، شامل حقوق' : ''}.`,
  })
  if (iss && iss.buckets[0].amount > 0) decisions.push({
    level: 'warn', domain: 'مالی', to: '/finance/issuedCheques', cta: 'چک‌های پرداختی',
    text: `${moneyText(iss.buckets[0].amount)} چک پرداختی (${n0(iss.buckets[0].count)} فقره) از سررسید گذشته و هنوز پاس‌شده ثبت نشده است.`,
  })
  if (worstHybrid) decisions.push({
    level: worstHybrid.level, domain: 'مالی', to: hybridPath(worstHybrid.name), cta: `پرونده ${worstHybrid.name}`,
    text: `${worstHybrid.name}: ${moneyText(worstHybrid.debt)} مطالبات باز${isNum(worstHybrid.dso) ? `، معادل ${n0(worstHybrid.dso)} روز فروش` : ''}${isNum(worstHybrid.growth) ? `؛ فروش ${signedPct(worstHybrid.growth)} نسبت به ${P?.prevLabel}` : ''}.`,
  })
  if (biggestDrop && biggestDrop.growth - (salesGrowth ?? 0) < -15 && biggestDrop !== worstHybrid) decisions.push({
    level: 'warn', domain: 'فروش', to: hybridPath(biggestDrop.name), cta: `پرونده ${biggestDrop.name}`,
    text: `فروش ${biggestDrop.name} ${pct(Math.abs(biggestDrop.growth))} کمتر از همین بازه ${P?.prevLabel} است؛ افت کل شرکت ${pct(Math.abs(salesGrowth ?? 0))} بوده.`,
  })
  const counts = { critical: decisions.filter((d) => d.level === 'critical').length, warn: decisions.filter((d) => d.level === 'warn').length }

  const kpis = [
    {
      label: 'فروش خالص ماه', domain: 'فروش', to: '/sales', rial: salesNet, state: salesCur,
      delta: isNum(salesGrowth) ? `${signedPct(salesGrowth)} نسبت به همین بازه ${P?.prevLabel}` : null, tone: salesGrowth >= 0 ? 'good' : 'bad',
      sub: `پیش‌بینی پایان ماه: ${moneyText(salesCur.data?.kpis?.forecast)}`,
    },
    {
      label: 'وصول حواله و نقد هیبریدها', domain: 'مالی', to: '/finance/cashBank', rial: collCur, state: inflR,
      delta: isNum(collRatio) ? `معادل ${pct(collRatio)} فروش همین ماه` : null, tone: 'flat',
      sub: `بدون وصول چک · تا دیروز · ${monthName(meta?.file?.months?.[1]?.month || '')} کامل: ${moneyText(collPrevFull)}`,
    },
    {
      label: 'مطالبات باز هیبریدها', domain: 'مالی', to: '/files/hybrids', rial: debtTotal, state: network,
      delta: `${n0(network.data?.summary?.debtor_customer_count ?? hybrids?.reduce((s, h) => s + (h.debtors || 0), 0))} مشتری بدهکار`, tone: 'warn',
      sub: 'مانده دفتر کل مشتریان شعب (کارآمد)',
    },
    {
      label: 'چک دریافتی سررسید گذشته', domain: 'مالی', to: '/finance/receivedCheques', rial: recv?.buckets[0].amount, state: recvR,
      delta: recv ? `${n0(recv.buckets[0].count)} فقره` : null, tone: 'bad', valueTone: 'bad',
      sub: recv ? `برگشتی باز: ${moneyText(recv.returned.amount)} (${n0(recv.returned.count)} فقره)` : '',
    },
    {
      label: 'خالص جریان نقد ۳۰ روز', domain: 'مالی', to: '/finance/liquidity', rial: flow?.net30, state: flowR,
      delta: flow ? `سناریوی ${flow.scenario}` : null, tone: flow?.net30 >= 0 ? 'good' : 'warn', valueTone: flow?.net30 < 0 ? 'warn' : '',
      sub: 'ورودی منهای خروجی؛ بدون موجودی اول دوره',
    },
  ]

  return (
    <div className="u-page">
      <PageHead crumb="مرکز فرماندهی / نمای مدیر" title="نمای مدیر"
        desc={P ? `${P.curLabel} ${faDigits(P.cur.date_from.slice(0, 4))} تا ${faDigits(P.today)} — مقایسه با همین بازه ${P.prevLabel}` : 'در حال دریافت…'} />

      <section className="u-summary" aria-label="جمع‌بندی امروز">
        <i aria-hidden>✦</i>
        <div>
          <b>جمع‌بندی امروز</b>
          <p>
            {isNum(salesGrowth) ? <>فروش {P.curLabel} تا امروز <strong className={salesGrowth >= 0 ? 't-good' : 't-bad'}>{signedPct(salesGrowth)}</strong> نسبت به همین بازه {P.prevLabel} است</> : 'در حال جمع‌آوری فروش'}
            {isNum(collRatio) && <>؛ وصول حواله و نقد هیبریدها (بدون چک) معادل <strong>{pct(collRatio)}</strong> فروش این ماه بوده</>}.
            {recv && <> چک دریافتی سررسید گذشته: <strong className="t-bad">{moneyText(recv.buckets[0].amount)}</strong>.</>}
            {heaviest && heaviest.net < 0 && <> سنگین‌ترین هفتهٔ پیش رو: <strong className="t-warn">{heaviest.label}</strong> با خالص {moneyText(heaviest.net)}.</>}
          </p>
        </div>
        <div className="u-summary-counts">
          <a href="#decisions" className="bad"><b>{n0(counts.critical)}</b><small>بحرانی</small></a>
          <a href="#decisions" className="warn"><b>{n0(counts.warn)}</b><small>نیازمند توجه</small></a>
        </div>
      </section>

      <section className="u-kpis" aria-label="شاخص‌های کلیدی">
        {kpis.map((k) => (
          <MaybeLink key={k.label} to={k.to} className="u-kpi">
            <div className="u-kpi-top"><span>{k.label}</span><Chip domain={k.domain} /></div>
            {k.state?.data || isNum(k.rial)
              ? <>
                  <Money rial={k.rial} className={k.valueTone ? `t-${k.valueTone}` : ''} />
                  {k.delta && <span className={`u-kpi-delta t-${k.tone}`}>{k.delta}</span>}
                  <small className="u-kpi-sub">{k.sub}</small>
                </>
              : <small className="u-kpi-sub">{k.state?.error ? `خطا: ${k.state.error}` : 'در حال دریافت…'}</small>}
          </MaybeLink>
        ))}
      </section>

      <FinanceAgents />

      <div className="u-section-head">
        <div><h2>چک‌ها در یک نگاه</h2><small>کل شرکت: هیبریدها از کارآمد و B2B از راهکاران. روی هر ردیف بزنید تا لیست کامل همان چک‌ها باز شود.</small></div>
        <Link to="/finance/cheques">صفحهٔ کامل چک و سررسید ←</Link>
      </div>
      <div className="u-grid2">
        <Card className="u-cheques" title={<><span className="u-dot fin" />چک‌های دریافتی در جریان</>}
          action={recv && <ChannelSplit parts={recv.byChannel} />}>
          {!recv ? <Pending state={recvR} label="چک‌های دریافتی" height={260} /> : <>
            <div className="u-big"><Money rial={recv.total} /><small>· {n0(recv.count)} فقره تا یک سال آینده · اتکا {pct(recv.reliancePct)}</small></div>
            <BucketRows buckets={recv.buckets} to="/finance/receivedCheques" />
            <div className="u-foot3">
              <Link to="/finance/receivedCheques"><small className="t-bad">برگشتی تسویه‌نشده</small><b>{moneyText(recv.returned.amount)}</b><small>{n0(recv.returned.count)} فقره</small></Link>
              <Link to="/finance/liquidity"><small>سهم ۱۰ مشتری بزرگ</small><b>{pct(recv.top10Share)}</b><small>از {n0(recv.customerCount)} مشتری</small></Link>
              <Link to="/finance/liquidity"><small>اتکای سبد</small><b>{pct(recv.reliancePct)}</b><small>بر اساس سابقه وصول</small></Link>
            </div>
          </>}
        </Card>
        <Card className="u-cheques" title={<><span className="u-dot out" />چک‌های پرداختی باز</>}
          action={iss && <ChannelSplit tone="out" parts={[
            ...iss.banks.slice(0, 2).map((b) => ({ key: b.label, label: b.label.replace(/^بانک\s*/, ''), amount: b.amount })),
            { key: 'other', label: 'سایر', amount: iss.banks.slice(2).reduce((s, b) => s + b.amount, 0) },
          ]} />}>
          {!iss ? <Pending state={issR} label="چک‌های پرداختی" height={260} /> : <>
            <div className="u-big"><Money rial={iss.total} /><small>· {n0(iss.count)} فقره تا یک سال آینده</small></div>
            <BucketRows buckets={iss.buckets} to="/finance/issuedCheques" />
            <div className="u-foot3">
              <Link to="/finance/issuedCheques"><small className="t-warn">پیک روزانه</small><b>{moneyText(iss.peakDay?.amount_rial)}</b><small>{faDigits(iss.peakDay?.date_jalali || '')}</small></Link>
              <Link to="/finance/issuedCheques"><small>بزرگ‌ترین ذی‌نفع</small><b>{moneyText(iss.topPayee?.amount_rial)}</b><small className="u-ellipsis">{iss.topPayee?.payee_name || '—'}</small></Link>
              <Link to="/finance/issuedCheques"><small>نیازمند بررسی وضعیت</small><b>{moneyText(iss.needsReview.amount)}</b><small>{n0(iss.needsReview.count)} فقره، بیش از ۲۰ روز معوق</small></Link>
            </div>
          </>}
        </Card>
      </div>

      <div className="u-grid-main">
        <Card title="جریان نقد ۵ هفتهٔ آینده" sub="میلیون تومان · ورودی = چک دریافتی (اتکا) + میانگین حواله و نقد؛ خروجی = چک پرداختی + حقوق + میانگین هزینه‌ها"
          action={<Link to="/finance/liquidity">جزئیات نقدینگی ←</Link>}>
          {!flow ? <Pending state={flowR} label="پیش‌بینی نقدینگی" height={260} /> : <>
            <PairBars items={flow.weeks} aKey="inflow" bKey="outflow" aTone="fin" bTone="out" fmt={mt} height={180} />
            <div className="u-flow-rows">
              <span>خالص هفته<small className="u-sub">میلیون تومان</small></span>
              {flow.weeks.map((w) => <b key={w.label} className={w.net >= 0 ? 't-good' : 't-bad'}>{mt(w.net)}</b>)}
              <span>خالص تجمعی</span>
              {flow.weeks.map((w) => <span key={w.label} className={w.closing >= 0 ? '' : 't-warn'}>{mt(w.closing)}</span>)}
              <span>از آن چک پرداختی</span>
              {flow.weeks.map((w) => <span key={w.label} className="t-muted">{mt(w.issued)}</span>)}
            </div>
            <small className="u-note">موجودی بانک‌ها طبق تصمیم مدیریت (۱۴۰۵/۰۷/۱۳) تا آمدن صورت‌حساب بانکی در داشبورد نمی‌آید؛ اعداد تجمعی از صفر شروع می‌شوند.</small>
          </>}
        </Card>
        <Card title="نیازمند تصمیم امروز" sub="از داده‌های همین صفحه" className="u-decisions">
          <div id="decisions" />
          {decisions.length === 0 && <Pending state={{}} label="هشدارها" height={160} />}
          {decisions.map((d, i) => (
            <Link key={i} to={d.to} className="u-decision">
              <span><em className={`u-pill ${d.level === 'critical' ? 'bad' : 'warn'}`}>{d.level === 'critical' ? 'بحرانی' : 'توجه'}</em><Chip domain={d.domain} /></span>
              <p>{d.text}</p>
              <small>{d.cta} ←</small>
            </Link>
          ))}
        </Card>
      </div>

      <Card title="هیبریدها در یک نگاه" sub={`فروش از داشبورد فروش (${P ? `${faDigits(P.cur.date_from.slice(5))} تا ${faDigits(P.today.slice(5))}` : ''})، مطالبات و چک از داشبورد مالی. مرتب‌شده از پرریسک به سالم.`}
        action={<Link to="/files/hybrids">همه هیبریدها ←</Link>}>
        {!hybrids ? <Pending state={network.error ? network : salesCur} label="هیبریدها" height={240} />
          : <HybridTable rows={hybrids} prevLabel={P?.prevLabel} year={Y?.year} limit={12} />}
      </Card>

      <Card title="فروش در برابر وصول حواله و نقد هیبریدها — ۶ ماه اخیر" sub="میلیارد تومان · وصول چک جدا در «چک‌ها» آمده و اینجا نیست · عدد پایین هر ماه = نسبت وصول حواله و نقد به فروش خالص · ماه جاری تا امروز">
        {!trend.length ? <Pending state={monthly} label="روند ماهانه" height={220} />
          : <>
            <div className="u-legend"><span><i className="sales" />فروش خالص</span><span><i className="fin" />وصول حواله و نقد</span></div>
            <PairBars items={trend} aKey="sales" bKey="coll" aTone="sales" bTone="fin" fmt={bt} height={190} subKey="ratio" />
          </>}
      </Card>
    </div>
  )
}

function BucketRows({ buckets, to }) {
  const max = Math.max(...buckets.map((b) => b.amount || 0), 1)
  return (
    <div className="u-buckets">
      {buckets.map((b) => (
        <Link key={b.key} to={to} className="u-bucket">
          <span className={b.tone === 'danger' ? 't-bad' : ''}>{b.label}</span>
          <Bar value={b.amount} max={max} tone={b.tone} />
          <Money rial={b.amount} />
          <small>{n0(b.count)} فقره</small>
        </Link>
      ))}
    </div>
  )
}

function ChannelSplit({ parts, tone = 'fin' }) {
  const total = parts.reduce((s, p) => s + p.amount, 0)
  if (!total) return null
  return (
    <div className="u-split">
      <div className="u-split-bar">{parts.map((p, i) => <i key={p.key} className={`${tone}${i ? ` s${i}` : ''}`} style={{ width: `${(p.amount / total) * 100}%` }} />)}</div>
      <div className="u-split-labels">{parts.map((p) => <small key={p.key}>{p.label} {pct((p.amount / total) * 100)}</small>)}</div>
    </div>
  )
}
