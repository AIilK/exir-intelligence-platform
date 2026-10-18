import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '@sales/lib.jsx'
import { useJson, faDigits, n0, pct, signedPct, growth, isNum, moneyText, dayOfYear } from '../data.js'
import { hybridRows, hybridTotals, yearCompare } from '../model.js'
import { useSalesSet, NETWORK_URL } from '../hooks.js'
import { PageHead, Card, Pending, Kpi, Bar, Money } from '../ui.jsx'
import HybridTable, { hybridPath } from '../HybridTable.jsx'
import { YearChart } from '../fileTabs.jsx'
import AgentCards from '../AgentCards.jsx'

export default function HybridList() {
  const S = useSalesSet()
  const { P, Y } = S
  const { vat } = useApp()
  const network = useJson(NETWORK_URL)
  const monthly = useJson(`/api/monthly?vat=${vat ? 1 : 0}`)
  const [q, setQ] = useState('')
  const rows = useMemo(() => (network.data && S.cur.data
    ? hybridRows({ network: network.data, salesCur: S.cur.data, salesPrev: S.prev.data, ytd: S.ytd.data, ytdPrev: S.ytdPrev.data, fullPrev: S.fullPrev.data, today: P?.today })
    : null), [network.data, S.cur.data, S.prev.data, S.ytd.data, S.ytdPrev.data, S.fullPrev.data, P?.today])
  const shown = rows?.filter((r) => !q.trim() || `${r.name} ${r.people.join(' ')}`.includes(q.trim()))
  const tot = rows ? hybridTotals(rows) : null

  const ytd = S.ytd.data?.kpis?.net
  const ytdPrev = S.ytdPrev.data?.kpis?.net
  const full = S.fullPrev.data?.kpis?.net
  const cur = S.cur.data?.kpis
  const prev = S.prev.data?.kpis?.net
  const yearSalesFin = network.data?.summary?.current_year_sales_rial
  const dso = tot && yearSalesFin > 0 && P ? tot.debt / (yearSalesFin / dayOfYear(P.today)) : null
  const yg = growth(ytd, ytdPrev)
  const mg = growth(cur?.net, prev)
  const months = Y ? yearCompare(monthly.data?.months, Y.year) : []
  const topSales = rows ? [...rows].filter((r) => r.ytdNet > 0).sort((a, b) => b.ytdNet - a.ytdNet).slice(0, 6) : []
  const topDebt = rows ? [...rows].filter((r) => r.debt > 0).sort((a, b) => b.debt - a.debt).slice(0, 6) : []
  const yl = Y ? faDigits(Y.year) : ''
  const pyl = Y ? faDigits(Y.prevYear) : ''

  return (
    <div className="u-page">
      <PageHead crumb="پرونده‌ها / هیبریدها" title="هیبریدها"
        desc="شاخص‌های مدیریتی همه هیبریدها؛ روی هر کارت یا هیبرید بزنید تا جزئیاتش باز شود." />

      <section className="u-kpis" aria-label="شاخص‌های کلی هیبریدها">
        <Kpi label={`فروش خالص ${yl} تا امروز`} domain="فروش" rial={ytd} to="/sales"
          delta={isNum(yg) ? `${signedPct(yg)} نسبت به همین بازه ${pyl}` : null} deltaTone={yg >= 0 ? 'good' : 'bad'}
          note={isNum(ytdPrev) ? `همین بازه ${pyl}: ${moneyText(ytdPrev)}` : 'در حال دریافت…'} />
        <Kpi label={`فروش خالص کل ${pyl}`} domain="فروش" rial={full} to="/sales"
          note={isNum(full) ? `میانگین ماهانه: ${moneyText(full / 12)}` : 'در حال دریافت…'} />
        <Kpi label={`فروش ${P?.curLabel || 'این ماه'} تا امروز`} domain="فروش" rial={cur?.net} to="/hybrid"
          delta={isNum(mg) ? `${signedPct(mg)} نسبت به همین بازه ${P?.prevLabel}` : null} deltaTone={mg >= 0 ? 'good' : 'bad'}
          note={isNum(cur?.forecast) ? `پیش‌بینی پایان ماه: ${moneyText(cur.forecast)}` : ''} />
        <Kpi label="مطالبات باز هیبریدها" domain="مالی" rial={tot?.debt}
          delta={isNum(dso) ? `دوره وصول: ${n0(dso)} روز` : null} deltaTone={dso > 75 ? 'warn' : 'flat'}
          note={tot ? `${n0(tot.debtors)} مشتری بدهکار` : 'در حال دریافت…'} />
        <Kpi label="چک باز در دست" domain="مالی" rial={tot?.openCheques} to="/finance/receivedCheques"
          note={tot ? `${n0(tot.openChequeCount)} فقره چک مشتریان هیبریدها` : 'در حال دریافت…'} />
        <Kpi label="وضعیت هیبریدها" value={tot ? `${n0(tot.count)} هیبرید` : '—'}
          delta={tot ? `${n0(tot.levels.critical)} بحرانی · ${n0(tot.levels.warn)} نیازمند توجه · ${n0(tot.levels.ok)} سالم` : null}
          deltaTone={tot?.levels.critical ? 'bad' : 'flat'} note="بر اساس دوره وصول و افت فروش نسبت به کل شرکت" />
      </section>

      <AgentCards agents={[{ key: 'sales_finance_bridge' }]} />

      <div className="u-grid-main">
        <YearChart state={monthly} months={months} Y={Y} title="فروش ماهانه هیبریدها" action={<Link to="/sales">داشبورد فروش ←</Link>} />
        <div className="u-stack">
          <Card title={`بیشترین فروش ${yl}`} sub="تا امروز">
            <TopList rows={topSales} field="ytdNet" tone="sales" tab="sales" total={rows?.reduce((s, r) => s + (r.ytdNet > 0 ? r.ytdNet : 0), 0)} />
          </Card>
          <Card title="بیشترین مطالبات باز" sub="مانده دفتر کل مشتریان">
            <TopList rows={topDebt} field="debt" tone="warn" tab="debt" total={tot?.debt} />
          </Card>
        </div>
      </div>

      <Card title={`همه هیبریدها (${n0(shown?.length ?? 0)})`}
        sub={P ? `روی عنوان هر ستون بزنید تا مرتب شود · مبالغ به میلیون تومان · دوره وصول بالای ۷۵ روز «توجه» و بالای ۱۲۰ روز «بحرانی»` : ''}
        action={<label className="u-search"><span>جستجو</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام هیبرید یا هیبرید من…" /></label>}>
        {!shown ? <Pending state={network.error ? network : S.cur} label="هیبریدها" height={300} /> : <HybridTable rows={shown} prevLabel={P?.prevLabel} year={Y?.year} />}
      </Card>
    </div>
  )
}

function TopList({ rows, field, tone, tab, total }) {
  if (!rows.length) return <Pending state={{}} label="فهرست" height={80} />
  const max = rows[0][field] || 1
  return (
    <div className="u-list">
      {rows.map((r) => (
        <Link key={r.key} to={hybridPath(r.name, tab)} className="u-list-row" title="سهم از کل">
          <span>{r.name}</span><Bar value={r[field]} max={max} tone={tone} /><Money rial={r[field]} /><small>{total > 0 ? `${pct((r[field] / total) * 100)} از کل` : ''}</small>
        </Link>
      ))}
    </div>
  )
}
