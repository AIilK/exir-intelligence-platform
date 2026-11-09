import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtInt, fmtPct, fmtCompact, faDigits, tierOf, tierTabs, TIER_HINT } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Kpi, Tabs } from '../components/ui.jsx'
import { HBar, ParetoChart } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'

export default function Customers() {
  const { data, loading, error } = useApi('/api/customers')
  const { unit, meta } = useApp()
  const nav = useNavigate()
  const [tier, setTier] = useState('all')   // ۱۵ مشتری برتر: کل یا یک دسته شعبه
  const [showReqOnly, setShowReqOnly] = useState(false)   // فهرست «فقط درخواست، بدون فروش»
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const k = data.kpis
  const cust = data.customers
  const cls = Object.fromEntries((data.pareto.classes || []).map((c) => [c.abc, c]))
  const top10 = cust.slice(0, 10).reduce((a, c) => a + Math.max(c.net, 0), 0)
  const posTotal = cust.reduce((a, c) => a + Math.max(c.net, 0), 0)
  const reqOnlyRows = cust.filter((c) => !(c.net > 0) && c.req_net > 0).sort((a, b) => b.req_net - a.req_net)
  const reqOnly = reqOnlyRows.length
  const netNeg = cust.filter((c) => c.net < 0).length
  const freq = data.frequency.map((f) => ({ key: f.k, label: f.k >= 5 ? '۵+ فاکتور' : `${faDigits(f.k)} فاکتور`, count: f.count }))
  const cols = [C.text('key', 'کد'), C.label('مشتری'), C.text('branch', 'شعبه'), C.text('city', 'شهر'), C.text('seller', 'فروشنده اصلی'),
    C.net, C.share, C.invoices, C.avg_invoice, C.qty, C.sku, C.returns, C.req_net, C.req_conv,
    { key: 'first_date', label: 'اولین خرید', type: 'date', hint: 'اولین فاکتور فروش مشتری در کل تاریخچه بارگذاری‌شده' },
    { key: 'last_date', label: 'آخرین خرید', type: 'date' }, { key: 'abc', label: 'ABC' }]
  return (
    <>
      <PageHead title="مشتریان" desc="مشتریان بر اساس فاکتورهای فروش و درخواست‌ها در محدوده فیلتر" />
      <div className="kpis">
        <Kpi label="مشتری فعال" value={k.customers} type="int" hint="جمع خالص تعداد خرید مثبت" />
        <Kpi label="میانگین فروش هر مشتری" value={k.customers ? k.net / k.customers : null}
          hint="فروش خالص کل ÷ مشتری فعال. برگشتی مشتریانی که در این بازه خرید نداشته‌اند از صورت کسر کم شده، پس از میانگین خرید واقعی مشتریان کمتر است."
          sub={k.customers ? `میانگین خرید مشتریان فعال: ${fmtCompact(posTotal / k.customers).value} ${fmtCompact(posTotal / k.customers).unit}` : ''} />
        <Kpi label="میانگین فاکتور مؤثر" value={k.avg_invoice} />
        <Kpi label="سهم ۱۰ مشتری برتر" value={posTotal ? top10 / posTotal : null} type="pct" hint="از جمع فروش خالص مثبت مشتریان" />
        <Kpi label="مشتری جدید" value={data.new_customers} type="int"
          hint={`مشتریانی که اولین خریدشان (در داده بارگذاری‌شده از ${faDigits(data.history_from)}) در همین بازه بوده و خرید خالص مثبت دارند. برای ماه‌های اول تاریخچه بیشتر از واقعیت است.`} />
        <Kpi label="مشتریان کلاس A" value={cls.A?.count} type="int" sub={cls.A ? `${fmtPct(cls.A.share)} فروش` : ''} />
        <Kpi label="فقط درخواست، بدون فروش" value={reqOnly} type="int" hint="مشتریانی که درخواست دارند ولی فروش خالص مثبت ندارند"
          onClick={() => setShowReqOnly((v) => !v)} active={showReqOnly} />
        <Kpi label="فروش خالص منفی" value={netNeg} type="int" hint="برگشتی بیشتر از خرید در این بازه" />
      </div>
      <div className="grid g2">
        {showReqOnly && (
          <Card title={`فقط درخواست، بدون فروش (${fmtInt(reqOnly)} مشتری)`} className="span2"
            subtitle="مشتریانی که در محدوده فیلتر درخواست ثبت کرده‌اند ولی فروش خالص مثبت ندارند؛ به ترتیب مبلغ درخواست">
            <DataTable rows={reqOnlyRows} unit={unit} pageSize={20} exportName="customers-request-only"
              columns={[C.text('key', 'کد'), C.label('مشتری'), C.text('branch', 'شعبه'), C.text('city', 'شهر'), C.text('seller', 'فروشنده اصلی'),
                C.req_net, C.net, { key: 'last_date', label: 'آخرین خرید', type: 'date' }]}
              onRowClick={(r) => nav(detailPath('customer', r.key))} />
          </Card>
        )}
        <Card title="۱۵ مشتری برتر" subtitle={`${TIER_HINT} (دسته = شعبه اصلی مشتری)`}
          actions={<Tabs value={tier} onChange={setTier} tabs={tierTabs([...new Set(cust.map((c) => tierOf(meta, c.branch)))])} />}>
          <HBar rows={cust.filter((c) => tier === 'all' || tierOf(meta, c.branch) === tier).slice(0, 15)
            .map((c) => ({ ...c, label: `${c.label} — ${c.city}` }))} unit={unit}
            onClick={(r) => nav(detailPath('customer', r.key))} />
        </Card>
        <Card title="تمرکز فروش روی مشتریان (پارتو)"
          subtitle="مشتریان از پرخرید به کم‌خرید؛ منحنی = سهم تجمعی از فروش خالص. A: مشتریانی که ۸۰٪ اول فروش را می‌سازند، B: تا ۹۵٪، C: بقیه">
          <ParetoChart curve={data.pareto.curve} classes={data.pareto.classes} what="مشتری" />
        </Card>
        <Card title="توزیع مشتریان بر اساس تعداد فاکتور مؤثر" subtitle="تعداد روزهایی که مشتری خرید خالص مثبت داشته است">
          <HBar rows={[...freq].reverse()} value="count" valueType="int" unit={unit} colorIndex={2} />
        </Card>
        <Card title="فهرست مشتریان" className="span2">
          <DataTable rows={cust} columns={cols} unit={unit} pageSize={20} exportName="customers"
            onRowClick={(r) => nav(detailPath('customer', r.key))} />
        </Card>
      </div>
    </>
  )
}
