import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, faDigits } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Empty } from '../components/ui.jsx'
import { CompareBars, Heatmap, SEQ, SEQ_ORANGE } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'
import { BrandShare } from './Reports.jsx'
import { achPill } from './Commission.jsx'
import { MONTH_NAMES } from '../jalali.js'

const monthName = (m) => (m ? `${MONTH_NAMES[+m.slice(5, 7) - 1]} ${faDigits(m.slice(0, 4))}` : '')

export default function Hybrid() {
  const { data, loading, error } = useApi('/api/hybrid')
  const { unit, vat } = useApp()
  const nav = useNavigate()
  const [level, setLevel] = useState('branch')
  const [heatSrc, setHeatSrc] = useState('sales')
  const [heatBy, setHeatBy] = useState('net')      // نقشه حرارتی: مبلغ یا تعداد
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const branches = data.branches
  const rows = level === 'branch' ? branches : data.supervisors
  const achHint = `تحقق تارگت شعبه ${monthName(data.ach_month)}، مثل صفحه «تحقق و پورسانت»: ریال ناخالص فاکتور ماه ÷ تارگت شعبه (فایل ناخالص) تا روز کاری؛ فیلترها جز ماه اثر ندارند`
  const columns = [
    C.label(level === 'branch' ? 'شعبه' : 'سرپرست'),
    // در حالت شعبه ستون سرپرست نمی‌آید: بعضی شعب چند سرپرست دارند
    ...(level === 'branch' ? [C.target_rial, { ...C.ach, hint: achHint, render: achPill('ach') }] : [C.text('branch', 'شعبه')]),
    C.net, C.share, C.daily_avg, C.req_net,
    C.disc_rate, C.mgmt_disc_rate, C.return_rate, C.invoices, C.customers, C.avg_invoice, C.qty,
  ]
  const qtyHeat = heatBy === 'qty'
  return (
    <>
      <PageHead title="عملکرد هیبرید" desc="مقایسه شعب هیبرید: فروش، درخواست، تحقق تارگت و کیفیت فروش" />
      <div className="grid g2">
        <Card title="فروش خالص در برابر درخواست، به تفکیک شعبه" className="span2"
          subtitle="هر دو بر حسب فروش خالص (پس از تخفیف، بدون ارزش افزوده)؛ برای جزئیات روی شعبه کلیک کنید">
          <CompareBars rows={branches} unit={unit} onClick={(r) => nav(detailPath('branch', r.key))}
            series={[{ key: 'net', name: 'فروش خالص (فاکتور)', color: 0 }, { key: 'req_net', name: 'درخواست (سفارش)', color: 1 }]} />
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
