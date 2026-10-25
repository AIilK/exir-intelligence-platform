import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtPct, fmtInt, fmtCompact, faDigits, tierTabs, TIER_HINT } from '../lib.jsx'
import { Kpi, Card, Loading, ErrorBox, Empty, Tabs } from '../components/ui.jsx'
import { HBar, TrendChart } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { DiscountBars } from './Analysis.jsx'
import { ChainSelloutBlock, isChainOnly, isOnlineOnly } from './ChainSellout.jsx'

const DISC_TABS = [{ value: 'branch', label: 'شعبه' }, { value: 'category', label: 'گروه کالا' }, { value: 'group', label: 'زیرگروه' }]

/** نرخ تخفیف (حجمی + نقدی) به تفکیک شعبه / گروه / زیرگروه، از بیشترین نرخ به کمترین */
function DiscountCard({ discounts }) {
  const nav = useNavigate()
  const [by, setBy] = useState('branch')
  const rows = [...(discounts?.[by] || [])].filter((r) => r.gross > 0).sort((a, b) => (b.rate ?? 0) - (a.rate ?? 0))
  if (!rows.length) return null
  return (
    <Card title="نرخ تخفیف" className="span2"
      subtitle={`سهم تخفیف حجمی و نقدی از جمع قبل از تخفیف — فقط فاکتورهای فروش، بدون فاکتورهای «نمونه کالا»؛ مرتب از بیشترین نرخ${rows.length > 15 ? '، ۱۵ مورد اول' : ''}`}
      actions={<Tabs value={by} onChange={setBy} tabs={DISC_TABS} />}>
      <DiscountBars rows={rows} large onClick={(r) => r && nav(detailPath(by, r.key))} />
    </Card>
  )
}

export function KpiRow({ k }) {
  const compact = (v) => (v == null ? '—' : `${fmtCompact(v).value} ${fmtCompact(v).unit}`)
  const { vat } = useApp()
  return (
    <div className="kpis">
      <Kpi label={vat ? 'فروش خالص (با ارزش افزوده)' : 'فروش خالص'} value={k.net}
        hint={vat
          ? 'قابل پرداخت فاکتورها (جمع قبل از تخفیف − تخفیفات + ارزش افزوده)، پس از کسر برگشتی — برابر «مبلغ کل خالص» گزارش‌های کارآمد. برای عدد بدون ارزش افزوده، «بدون ارزش افزوده» را در نوار بالا انتخاب کنید.'
          : 'جمع قبل از تخفیف − تخفیفات (بدون ارزش افزوده)، پس از کسر برگشتی'}
        sub={`ناخالص (قبل از تخفیف، بدون ارزش افزوده): ${compact(k.gross)}`} />
      <Kpi label="پیش‌بینی پایان ماه" value={k.forecast}
        hint="فروش خالص روزهای کامل‌شده (تا دیروز) ÷ روز کاری سپری‌شده × کل روز کاری ماه. فروش امروز از فردا در پیش‌بینی می‌آید. فقط برای ماه جاری و بدون فیلتر تاریخ."
        sub={k.full_month ? `${fmtInt(k.days)} از ${fmtInt(k.wd_total)} روز کاری (تا دیروز)` : 'فقط برای ماه جاری محاسبه می‌شود'} />
      <Kpi label="میانگین فروش روزانه" value={k.daily_avg}
        hint={k.full_month ? 'فروش خالص تا دیروز ÷ روز کاری سپری‌شده'
          : 'فروش خالص بازه ÷ روزهای کاری تقویم در بازه (همه روزها به‌جز جمعه؛ اگر بازه تا امروز است، تا دیروز). برای همه شعب و فیلترها یکسان است تا میانگین‌ها قابل مقایسه باشند.'}
        sub={`بر مبنای ${fmtInt(k.days)} روز کاری${k.full_month ? ' (تا دیروز)' : ''}`} />
      <Kpi label="نرخ تخفیف" value={k.disc_rate} type="pct"
        sub={`حجمی ${fmtPct(k.vol_disc_rate)} · نقدی ${fmtPct(k.cash_disc_rate)}${k.mgmt_disc_rate ? ` · مدیریتی ${fmtPct(k.mgmt_disc_rate)}` : ''}`} hint="فقط فاکتورهای فروش" />
      <Kpi label="برگشت از فروش" value={k.returns_net} sub={`نرخ برگشت ${fmtPct(k.return_rate)}`} />
      <Kpi label="فاکتور مؤثر" value={k.invoices} type="int" hint="ترکیب (فروشنده، مشتری، روز) با جمع تعداد مثبت؛ چند فاکتور یک فروشنده برای یک مشتری در یک روز، یکی حساب می‌شود"
        sub={`میانگین فاکتور ${compact(k.avg_invoice)}`} />
      <Kpi label="مشتری فعال" value={k.customers} type="int" sub={`${fmtInt(k.sku)} کالای فروش‌رفته`} />
      <Kpi label="تعداد فروش (عدد)" value={k.qty} type="int" sub={`${fmtInt(k.lines)} سطر فاکتور`} />
      {k.req_net != null && (
        <Kpi label="درخواست (سفارش)" value={k.req_net}
          hint={`درخواست‌های (سفارش‌های) ثبت‌شده در کارآمد به‌جز باطل‌شده‌ها، جدا از فاکتورهای فروش؛ ${vat
            ? 'مبلغ = قابل پرداخت با ارزش افزوده، برابر ستون «مبلغ» گزارش تاریخچه تبدیل درخواست کارآمد'
            : 'خالص = جمع قبل تخفیف − تخفیف حجمی، بدون ارزش افزوده'}`}
          sub={`پیش‌بینی ماه: ${compact(k.req_forecast)}`} />
      )}
      {k.req_net != null && (
        <Kpi label="نرخ تبدیل درخواست" value={k.req_conv} type="pct"
          hint="سهم مبلغی درخواست‌های با «وضعیت درخواست = ۱» (تبدیل‌شده به فاکتور)"
          sub={`${fmtInt(k.req_docs_done)} از ${fmtInt(k.req_docs)} درخواست`} />
      )}
    </div>
  )
}

function MonthlyCard() {
  const { data } = useApi('/api/monthly')
  const { unit } = useApp()
  if (!data?.months?.length) return null
  const trend = data.months.map((m) => ({ ...m, date: m.month }))
  return (
    <Card title="روند ماهانه" className="span2"
      subtitle={`فروش خالص، برگشتی و درخواست هر ماه با همه فیلترها به‌جز تاریخ؛ ماه ${faDigits(data.current)} هنوز کامل نشده است`}>
      <TrendChart trend={trend} unit={unit} fullLabel />
    </Card>
  )
}

export default function Overview() {
  const { data, loading, error } = useApi('/api/overview')
  const { unit, filters } = useApp()
  const nav = useNavigate()
  const chainOnly = isChainOnly(filters.branch)
  const onlineOnly = isOnlineOnly(filters.branch)
  const [catBy, setCatBy] = useState('qty')   // ۱۲ گروه کالای برتر: پیش‌فرض بر اساس تعداد
  const [sellerTier, setSellerTier] = useState('all')
  const [custTier, setCustTier] = useState('all')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const k = data.kpis
  if (!data.trend.length) return <Empty />
  return (
    <>
      <PageHead title="نمای کلی" desc="شاخص‌های اصلی فروش در محدوده فیلترهای انتخاب‌شده" />
      <KpiRow k={k} />
      {chainOnly && <ChainSelloutBlock />}
      {onlineOnly && <ChainSelloutBlock kind="online" />}
      <div className="grid g2">
        <Card title="روند روزانه فروش" subtitle="فروش خالص، برگشتی و درخواست‌های ثبت‌شده در هر روز" className="span2">
          <TrendChart trend={data.trend} unit={unit} />
        </Card>
        <MonthlyCard />
        <Card title="فروش خالص به تفکیک شعبه" subtitle="برای جزئیات روی هر شعبه کلیک کنید">
          <HBar rows={data.branches} unit={unit} onClick={(r) => nav(detailPath('branch', r.key))} />
        </Card>
        <Card title="فروش خالص به تفکیک برند">
          <HBar rows={data.brands} unit={unit} onClick={(r) => nav(detailPath('brand', r.key))} />
        </Card>
        <DiscountCard discounts={data.discounts} />
        <Card title="۱۲ گروه کالای برتر"
          subtitle={catBy === 'qty' ? 'بر اساس تعداد فروش خالص (عدد، پس از کسر برگشتی)' : 'بر اساس فروش خالص ریالی'}
          actions={<Tabs value={catBy} onChange={setCatBy} tabs={[{ value: 'qty', label: 'تعداد' }, { value: 'net', label: 'مبلغ' }]} />}>
          <HBar rows={[...data.categories].sort((a, b) => (b[catBy] ?? 0) - (a[catBy] ?? 0)).slice(0, 12)}
            value={catBy} valueType={catBy === 'qty' ? 'int' : 'money'} unit={unit}
            onClick={(r) => nav(detailPath('category', r.key))} />
        </Card>
        <Card title="۱۰ فروشنده برتر" subtitle={TIER_HINT}
          actions={<Tabs value={sellerTier} onChange={setSellerTier} tabs={tierTabs(Object.keys(data.sellers))} />}>
          <HBar rows={(data.sellers[sellerTier] || []).map((s) => ({ ...s, label: `${s.label} — ${s.branch}` }))} unit={unit}
            onClick={(r) => nav(detailPath('seller', r.key))} />
        </Card>
        <Card title="۱۰ مشتری برتر" className="span2" subtitle={TIER_HINT}
          actions={<Tabs value={custTier} onChange={setCustTier} tabs={tierTabs(Object.keys(data.customers))} />}>
          <HBar rows={(data.customers[custTier] || []).map((s) => ({ ...s, label: `${s.label} — ${s.branch}` }))} unit={unit}
            onClick={(r) => nav(detailPath('customer', r.key))} />
        </Card>
      </div>
    </>
  )
}
