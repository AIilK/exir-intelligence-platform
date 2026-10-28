import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useJson, bt, pct, isNum, monthName, faDigits } from '../data.js'
import { useSalesSet } from '../hooks.js'
import { hybridRows } from '../model.js'
import { Card, Pending, PairBars } from '../ui.jsx'
import HybridTable from '../HybridTable.jsx'
import CommandOverview from '@finance/management/manager-overview.tsx'

const FIN = '/api/v1'

export default function ManagerOverview() {
  const nav = useNavigate()
  const S = useSalesSet()
  const { P, Y, vat: v } = S
  const salesCur = S.cur
  const salesPrev = S.prev
  const monthly = useJson(`/api/monthly?vat=${v}`)
  const network = useJson(`${FIN}/finance/sales-network`)
  const inflR = useJson(`${FIN}/liquidity/inflows?base_days=180&channel=hybrid`)
  const hybrids = useMemo(() => (network.data && salesCur.data
    ? hybridRows({ network: network.data, salesCur: salesCur.data, salesPrev: salesPrev.data, ytd: S.ytd.data, ytdPrev: S.ytdPrev.data, fullPrev: S.fullPrev.data, today: P?.today })
    : null), [network.data, salesCur.data, salesPrev.data, S.ytd.data, S.ytdPrev.data, S.fullPrev.data, P?.today])
  // فروش در برابر وصول حواله و نقد هیبریدها، ماه به ماه
  const collByMonth = new Map((inflR.data?.data?.monthly_trend || []).map((m) => [m.month, m.values?.hybrid ?? m.total_rial]))
  const trend = (monthly.data?.months || []).slice(-6).map((m) => {
    const c = collByMonth.get(m.month)
    const r = isNum(c) && m.net > 0 ? (c / m.net) * 100 : null
    return { label: monthName(m.month), sales: m.net, coll: c ?? null, ratio: isNum(r) ? pct(r) : '—', subTone: 't-muted' }
  })
  return (
    <div className="u-page">
      {/* ترکیب خلاصه مدیریتی مالی و فروش (frontend/app/management/manager-overview.tsx) */}
      <div className="fin-scope fin-inline u-mo">
        <CommandOverview go={(view) => nav(view.startsWith('/') ? view : `/finance/${view}`)} />
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
