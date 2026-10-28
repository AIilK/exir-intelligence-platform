import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Empty } from '../components/ui.jsx'
import { CompareBars, Heatmap, HBar, SEQ, SEQ_ORANGE } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'
import { BrandShare } from './Reports.jsx'

export default function Hybrid() {
  const { data, loading, error } = useApi('/api/hybrid')
  const { unit, vat } = useApp()
  const nav = useNavigate()
  const [level, setLevel] = useState('branch')
  const [heatSrc, setHeatSrc] = useState('sales')
  const [heatBy, setHeatBy] = useState('net')      // نقشه حرارتی: مبلغ یا تعداد
  const [convDir, setConvDir] = useState('desc')   // نرخ تبدیل: نزولی یا صعودی
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const branches = data.branches
  const rows = level === 'branch' ? branches : data.supervisors
  const columns = [
    C.label(level === 'branch' ? 'شعبه' : 'سرپرست'),
    // در حالت شعبه ستون سرپرست نمی‌آید: بعضی شعب چند سرپرست دارند
    ...(level === 'branch' ? [] : [C.text('branch', 'شعبه')]),
    C.net, C.share, C.forecast, C.daily_avg, C.req_net, C.req_conv, C.req_forecast,
    C.disc_rate, C.return_rate, C.invoices, C.customers, C.avg_invoice, C.qty,
  ]
  const byConv = branches.filter((b) => b.req_net > 0)
    .sort((a, b) => ((b.req_conv ?? 0) - (a.req_conv ?? 0)) * (convDir === 'desc' ? 1 : -1))
  const qtyHeat = heatBy === 'qty'
  return (
    <>
      <PageHead title="عملکرد هیبرید" desc="مقایسه شعب هیبرید: فروش، درخواست، پیش‌بینی ماه و کیفیت فروش" />
      <div className="grid g2">
        <Card title="فروش خالص در برابر درخواست، به تفکیک شعبه" className="span2"
          subtitle="هر دو بر حسب فروش خالص (پس از تخفیف، بدون ارزش افزوده)؛ برای جزئیات روی شعبه کلیک کنید">
          <CompareBars rows={branches} unit={unit} onClick={(r) => nav(detailPath('branch', r.key))}
            series={[{ key: 'net', name: 'فروش خالص (فاکتور)', color: 0 }, { key: 'req_net', name: 'درخواست (سفارش)', color: 1 }]} />
        </Card>
        <Card title="پیش‌بینی فروش پایان ماه به تفکیک شعبه" subtitle="بر مبنای فاکتورهای فروش">
          <HBar rows={[...branches].sort((a, b) => (b.forecast ?? 0) - (a.forecast ?? 0)).map((r) => ({ ...r }))}
            value="forecast" unit={unit} onClick={(r) => nav(detailPath('branch', r.key))} />
        </Card>
        <Card title="نرخ تبدیل درخواست به فاکتور" subtitle="سهم مبلغی درخواست‌های با وضعیت «۱»"
          actions={<Tabs value={convDir} onChange={setConvDir}
            tabs={[{ value: 'desc', label: 'نزولی' }, { value: 'asc', label: 'صعودی' }]} />}>
          <HBar rows={byConv} value="req_conv" valueType="pct" unit={unit} colorIndex={2}
            onClick={(r) => nav(detailPath('branch', r.key))} />
        </Card>
        <Card title={heatSrc === 'sales' ? 'نقشه حرارتی فروش روزانه شعب' : 'نقشه حرارتی درخواست روزانه شعب'} className="span2"
          subtitle={heatSrc === 'sales'
            ? (qtyHeat ? 'تعداد فروش خالص (فروش منهای برگشتی) هر شعبه در هر روز (روزهای با فروش مثبت)'
              : 'فروش خالص هر شعبه در هر روز (روزهای با فروش مثبت)')
            : qtyHeat ? 'تعداد درخواست (سفارش) هر شعبه در هر روز، بدون درخواست‌های باطل‌شده'
            : `درخواست (سفارش) هر شعبه در هر روز، بدون درخواست‌های باطل‌شده؛ ${vat
              ? 'مبلغ با ارزش افزوده، مثل ستون «مبلغ» گزارش تاریخچه تبدیل درخواست کارآمد'
              : 'خالص = جمع قبل تخفیف − تخفیف حجمی، بدون ارزش افزوده'}`}
          actions={<>
            <Tabs value={heatBy} onChange={setHeatBy} tabs={[{ value: 'net', label: 'مبلغ' }, { value: 'qty', label: 'تعداد' }]} />
            <Tabs value={heatSrc} onChange={setHeatSrc}
              tabs={[{ value: 'sales', label: 'فاکتور فروش' }, { value: 'requests', label: 'درخواست' }]} />
          </>}>
          {(heatSrc === 'sales' ? data.heat : data.heat_req || []).length ? (
            <Heatmap rows={heatSrc === 'sales' ? data.heat : data.heat_req} xKey="date" yKey="branch" vKey={heatBy} unit={unit}
              valueType={qtyHeat ? 'int' : 'money'}
              palette={heatSrc === 'sales' ? SEQ : SEQ_ORANGE} onClickY={(b) => nav(detailPath('branch', b))} />
          ) : <Empty />}
        </Card>
        <Card title="فاکتور به مشتری و سهم از فروش، به تفکیک برند" className="span2"
          subtitle="فاکتور به مشتری = فاکتور مؤثر ÷ تعداد جفت‌های (فروشنده، مشتری) با خرید مثبت؛ یعنی هر مشتری به‌طور میانگین چند بار از هر فروشنده خریده. سهم برند = فروش خالص برند در شعبه ÷ فروش خالص کل آن برند — معادل پایین شیت TotalReport">
          <BrandShare />
        </Card>
        <Card title="جدول عملکرد" className="span2"
          actions={<Tabs value={level} onChange={setLevel} tabs={[{ value: 'branch', label: 'شعبه' }, { value: 'supervisor', label: 'سرپرست' }]} />}>
          <DataTable rows={rows} columns={columns} unit={unit} pageSize={25} exportName={`hybrid-${level}`}
            onRowClick={(r) => nav(detailPath(level, r.key))} />
        </Card>
      </div>
    </>
  )
}
