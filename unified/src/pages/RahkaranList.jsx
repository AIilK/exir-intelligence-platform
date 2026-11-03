import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { n0, pct, signedPct, growth, isNum, moneyText, faDigits, mt } from '../data.js'
import { LEVEL } from '../model.js'
import { PageHead, Card, Pending, Kpi, Mt } from '../ui.jsx'
import { Th, sorter } from '../fileTabs.jsx'
import { useRahkaranReps, rahkaranPath, RISK_FA, riskCls } from '../rahkaran.js'

const sum = (rows, k) => rows.reduce((s, r) => s + (isNum(r[k]) && r[k] > 0 ? r[k] : 0), 0)

/** Rahkaran B2B reps (پرونده‌ها / نمایندگان راهکاران): sales from the sales dashboard, receivables and cheques from finance. */
export default function RahkaranList() {
  const { sales, fin, rows, today } = useRahkaranReps()
  const [q, setQ] = useState('')
  const [brand, setBrand] = useState('')
  const [sort, setSort] = useState({ key: 'net', dir: -1 })
  const brands = useMemo(() => [...new Set((rows || []).map((r) => r.brand).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fa')), [rows])
  const scoped = rows?.filter((r) => !brand || r.brand === brand)
  const shown = scoped?.filter((r) => !q.trim() || `${r.name} ${r.code} ${r.city} ${r.province}`.includes(q.trim())).sort(sorter(sort))

  const yl = today ? faDigits(today.slice(0, 4)) : 'امسال'
  const pyl = today ? faDigits(Number(today.slice(0, 4)) - 1) : 'پارسال'
  const net = scoped ? sum(scoped, 'net') : null
  const lyNet = scoped ? sum(scoped, 'lyNet') : null
  const g = growth(net, lyNet)
  const active = scoped?.filter((r) => r.net > 0).length
  const debt = scoped ? sum(scoped, 'debt') : null
  const levels = scoped ? { critical: 0, warn: 0, ok: 0, ...Object.fromEntries(['critical', 'warn', 'ok'].map((l) => [l, scoped.filter((r) => r.level === l).length])) } : null
  const finReady = !!fin.data
  const sp = { sort, setSort }

  return (
    <div className="u-page">
      <PageHead crumb="پرونده‌ها / نمایندگان راهکاران" title="نمایندگان راهکاران (B2B)"
        desc="هر نماینده با فروشش در داشبورد فروش و مطالبات و چک‌هایش در داشبورد مالی، کنار هم؛ روی نام هر نماینده بزنید تا پرونده‌اش باز شود.">
        <label className="u-search"><span>برند</span>
          <select value={brand} onChange={(e) => setBrand(e.target.value)}>
            <option value="">همه برندها</option>
            {brands.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </label>
      </PageHead>

      <section className="u-kpis" aria-label="شاخص‌های کلی نمایندگان">
        <Kpi label={`فروش خالص ${yl} تا امروز`} domain="فروش" rial={net} to="/rahkaran"
          delta={isNum(g) ? `${signedPct(g)} نسبت به همین بازه ${pyl}` : null} deltaTone={g >= 0 ? 'good' : 'bad'}
          note={isNum(lyNet) ? `همین بازه ${pyl}: ${moneyText(lyNet)}` : 'در حال دریافت…'} />
        <Kpi label={`جمع کل ${yl} (خالص + تخفیف نقدی)`} domain="فروش" rial={scoped ? sum(scoped, 'netCash') : undefined} to="/rahkaran"
          note={scoped ? `تخفیف نقدی: ${moneyText(sum(scoped, 'cash'))}` : 'در حال دریافت…'} />
        <Kpi label="نمایندگان فعال" domain="فروش" value={scoped ? `${n0(active)} از ${n0(scoped.length)}` : '—'} to="/rahkaran"
          note={`خرید از ابتدای ${yl}`} />
        <Kpi label="مطالبات باز نمایندگان" domain="مالی" rial={finReady ? debt : undefined} value={finReady ? undefined : '…'} to="/finance/customers"
          note={finReady ? `${n0(scoped?.filter((r) => r.debt > 0).length)} نماینده بدهکار` : 'در حال دریافت از داشبورد مالی…'} />
        <Kpi label="چک باز در دست" domain="مالی" rial={finReady && scoped ? sum(scoped, 'openCheques') : undefined} value={finReady ? undefined : '…'} to="/finance/receivedCheques" />
        <Kpi label="چک سررسید گذشته" domain="مالی" rial={finReady && scoped ? sum(scoped, 'overdue') : undefined} value={finReady ? undefined : '…'}
          valueTone="bad" note={finReady ? `${n0(scoped?.filter((r) => r.overdue > 0).length)} نماینده` : ''} />
        <Kpi label="وضعیت نمایندگان" value={levels && finReady ? `${n0(levels.critical)} بحرانی` : '—'}
          delta={levels && finReady ? `${n0(levels.warn)} نیازمند توجه · ${n0(levels.ok)} سالم` : null} deltaTone={levels?.critical ? 'bad' : 'flat'}
          note="بحرانی: چک برگشتی تسویه‌نشده، دوره وصول بالای ۱۲۰ روز یا بدهی بدون خرید امسال · توجه: چک سررسید گذشته یا بالای ۷۵ روز" />
      </section>

      <Card title={`همه نمایندگان (${n0(shown?.length ?? 0)})`}
        sub="روی عنوان هر ستون بزنید تا مرتب شود · مبالغ به میلیون تومان · فروش از داشبورد فروش (راهکاران)، مطالبات و چک از داشبورد مالی"
        action={<label className="u-search"><span>جستجو</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام، کد، شهر یا استان…" /></label>}>
        {!shown ? <Pending state={sales} label="نمایندگان" height={300} /> : (
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr>
                <Th k="name" {...sp}>نماینده</Th>
                <Th k="brand" {...sp}>برند</Th>
                <Th k="province" {...sp}>استان</Th>
                <Th k="net" {...sp} unit="میلیون تومان">فروش {yl}</Th>
                <Th k="lastDate" {...sp}>آخرین خرید</Th>
                <Th k="debt" {...sp} unit="میلیون تومان">مطالبات</Th>
                <Th k="dso" {...sp}>دوره وصول</Th>
                <Th k="openCheques" {...sp} unit="میلیون تومان">چک باز</Th>
                <Th k="overdue" {...sp} unit="میلیون تومان">سررسید گذشته</Th>
                <Th k="returned" {...sp} unit="میلیون تومان">برگشتی باز</Th>
                <Th k="risk" {...sp}>ریسک</Th>
                <Th k="level" {...sp}>وضعیت</Th>
              </tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.code}>
                    <td><Link className="u-row-link" to={rahkaranPath(r.code)}>{r.short || r.name} <span>←</span></Link><small className="u-sub">کد {faDigits(r.code)} · {r.city || '—'}</small></td>
                    <td className="t-muted">{r.brand || '—'}</td>
                    <td className="t-muted">{r.province || '—'}</td>
                    <td><b><Mt rial={r.net} /></b></td>
                    <td className="t-muted">{faDigits(r.lastDate || '—')}</td>
                    {!r.hasFin ? <td colSpan={7} className="t-muted">{finReady ? 'در داشبورد مالی پیدا نشد' : 'در حال دریافت…'}</td> : <>
                      <td className={r.debt > 0 ? '' : 't-muted'}><Mt rial={r.debt} /></td>
                      <td className={r.dso > 120 || r.staleDebt ? 't-bad' : r.dso > 75 ? 't-warn' : 't-muted'}>{isNum(r.dso) ? `${n0(r.dso)} روز` : r.staleDebt ? 'بدون خرید امسال' : '—'}</td>
                      <td><Mt rial={r.openCheques} />{isNum(r.coverage) && r.openCheques > 0 && <small className="u-sub">پوشش {pct(r.coverage)}</small>}</td>
                      <td className={r.overdue > 0 ? 't-bad' : 't-muted'}><Mt rial={r.overdue} /></td>
                      <td className={r.returned > 0 ? 't-bad' : 't-muted'}><Mt rial={r.returned} /></td>
                      <td><span className={`u-pill ${riskCls(r.risk)}`}>{RISK_FA[r.risk] || '—'}</span></td>
                      <td><span className={`u-pill ${LEVEL[r.level].cls}`}>{LEVEL[r.level].label}</span></td>
                    </>}
                  </tr>
                ))}
              </tbody>
            </table>
            {fin.error && <small className="u-note">داشبورد مالی در دسترس نیست: {fin.error}</small>}
          </div>
        )}
      </Card>
    </div>
  )
}
