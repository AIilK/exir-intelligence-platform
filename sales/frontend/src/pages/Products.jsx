import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtInt, fmtPct } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs } from '../components/ui.jsx'
import { HBar, ParetoChart, Chart, baseOption } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { C } from '../cols.js'
import { DailyReport } from './Reports.jsx'
import { fmtMoney, UNITS } from '../lib.jsx'
import { brandColor } from '../brands.js'

function Treemap({ rows, unit, onClick }) {
  // برند ← گروه کالا؛ هر برند با رنگ سازمانی خودش (brands.js)
  const brands = [...new Set(rows.map((r) => r.brand))]
  const tot = (b) => rows.filter((r) => r.brand === b).reduce((a, r) => a + r.net, 0)
  brands.sort((a, b) => tot(b) - tot(a))
  return (
    <Chart
      height={420}
      onClick={onClick}
      option={(t) => ({
        tooltip: { ...baseOption(t).tooltip, formatter: (p) =>
          `${p.treePathInfo.slice(1).map((x) => x.name).join(' / ')}<br/><b>${fmtMoney(p.value, unit)}</b> ${UNITS[unit].label}` },
        series: [{
          type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false }, left: 0, right: 0, top: 0, bottom: 0,
          label: { show: true, formatter: '{b}', color: '#fff', fontFamily: 'Vazirmatn' },
          upperLabel: { show: true, height: 22, color: '#fff', fontFamily: 'Vazirmatn' },
          itemStyle: { borderColor: t.surface, borderWidth: 2, gapWidth: 2 },
          levels: [{ itemStyle: { borderWidth: 0, gapWidth: 3 } }, { itemStyle: { gapWidth: 2, borderColorSaturation: 0.6 } }],
          data: brands.map((b) => ({
            name: b, itemStyle: { color: brandColor(b, t) },
            children: rows.filter((r) => r.brand === b).map((r) => ({ name: r.category, value: r.net })),
          })),
        }],
      })}
    />
  )
}

export default function Products() {
  const { data, loading, error } = useApi('/api/products')
  const { unit } = useApp()
  const nav = useNavigate()
  const [level, setLevel] = useState('product')
  const [topBy, setTopBy] = useState('qty')   // ۱۵ کالای پرفروش: پیش‌فرض بر اساس تعداد
  const [catBy, setCatBy] = useState('qty')   // ۱۵ گروه کالای برتر: پیش‌فرض بر اساس تعداد
  const [paretoBy, setParetoBy] = useState('sku')   // پارتو: هر کالا یا هر گروه کالا
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const cls = Object.fromEntries((data.pareto.classes || []).map((c) => [c.abc, c]))
  const tables = {
    product: { rows: data.products, cols: [C.text('key', 'کد کالا'), C.label('نام کالا'), C.text('brand', 'برند'), C.text('category', 'گروه'), C.text('product_group', 'زیرگروه'),
      C.net, C.share, C.qty, C.forecast, C.forecast_qty, C.customers, C.invoices, C.disc_rate, C.returns, C.req_net, { key: 'abc', label: 'کلاس ABC' }] },
    group: { rows: data.groups, cols: [C.label('زیرگروه کالا'), C.text('category', 'گروه کالا'), C.text('brand', 'برند'), C.net, C.share, C.forecast, C.qty, C.customers, C.sku, C.disc_rate, C.return_rate, C.req_net] },
    category: { rows: data.categories, cols: [C.label('گروه کالا'), C.net, C.share, C.forecast, C.qty, C.customers, C.sku, C.disc_rate, C.return_rate, C.req_net] },
    brand: { rows: data.brands, cols: [C.label('برند'), C.net, C.share, C.forecast, C.qty, C.customers, C.sku, C.disc_rate, C.return_rate, C.req_net] },
  }
  const t = tables[level]
  return (
    <>
      <PageHead title="محصولات و گروه‌ها" desc="برندها، گروه‌های کالا و کالاها؛ برای جزئیات روی هر مورد کلیک کنید" />
      <div className="grid g2">
        <Card title="ترکیب فروش: برند ← گروه کالا" className="span2" subtitle="اندازه هر خانه = فروش خالص مثبت؛ کلیک روی گروه، جزئیات آن را باز می‌کند">
          <Treemap rows={data.brand_category} unit={unit}
            onClick={(p) => p.treePathInfo?.length === 3
              ? nav(detailPath('category', p.name, [['brand', p.treePathInfo[1].name]]))
              : p.treePathInfo?.length === 2 && nav(detailPath('brand', p.name))} />
        </Card>
        <Card title="فروش خالص برندها">
          <HBar rows={data.brands} unit={unit} onClick={(r) => nav(detailPath('brand', r.key))} />
        </Card>
        <Card title="۱۵ گروه کالای برتر"
          subtitle={catBy === 'qty' ? 'بر اساس تعداد فروش خالص (عدد، پس از کسر برگشتی)' : 'بر اساس فروش خالص ریالی'}
          actions={<Tabs value={catBy} onChange={setCatBy} tabs={[{ value: 'qty', label: 'تعداد' }, { value: 'net', label: 'مبلغ' }]} />}>
          <HBar rows={[...data.categories].sort((a, b) => (b[catBy] ?? 0) - (a[catBy] ?? 0)).slice(0, 15)}
            value={catBy} valueType={catBy === 'qty' ? 'int' : 'money'} unit={unit}
            onClick={(r) => nav(detailPath('category', r.key))} />
        </Card>
        <Card title="۱۵ کالای پرفروش"
          subtitle={topBy === 'qty' ? 'بر اساس تعداد فروش خالص (عدد، پس از کسر برگشتی)' : 'بر اساس فروش خالص ریالی'}
          actions={<Tabs value={topBy} onChange={setTopBy} tabs={[{ value: 'qty', label: 'تعداد' }, { value: 'net', label: 'مبلغ' }]} />}>
          <HBar rows={[...data.products].sort((a, b) => (b[topBy] ?? 0) - (a[topBy] ?? 0)).slice(0, 15)}
            value={topBy} valueType={topBy === 'qty' ? 'int' : 'money'} unit={unit}
            onClick={(r) => nav(detailPath('product', r.key))} />
        </Card>
        <Card title={paretoBy === 'sku' ? 'تحلیل پارتو (ABC) کالاها' : 'تحلیل پارتو (ABC) گروه‌های کالا'}
          subtitle={`${paretoBy === 'sku' ? 'هر کالا (SKU)' : 'هر گروه کالا'} از پرفروش به کم‌فروش؛ منحنی = سهم تجمعی از فروش خالص ریالی. A: مواردی که ۸۰٪ اول فروش را می‌سازند، B: تا ۹۵٪، C: بقیه`}
          actions={<Tabs value={paretoBy} onChange={setParetoBy} tabs={[{ value: 'sku', label: 'کالا (SKU)' }, { value: 'category', label: 'گروه کالا' }]} />}>
          {paretoBy === 'sku'
            ? <ParetoChart curve={data.pareto.curve} classes={data.pareto.classes} what="کالا" />
            : <ParetoChart key="category" curve={data.pareto_cat?.curve || []} classes={data.pareto_cat?.classes || []} what="گروه" />}
        </Card>
        <Card title="گزارش کالا: برند ← گروه ← زیرگروه ← کالا" className="span2"
          subtitle="میانگین روزانه، روز گزارش، از ابتدای ماه و پیش‌بینی ریالی و تعدادی با جمع جزء هر سطح — معادل شیت Goods&Group">
          <DailyReport dims={['brand', 'category', 'group', 'product']} variant="goods" exportName="goods-report" />
        </Card>
        <Card title="جدول جزئیات" className="span2"
          actions={<Tabs value={level} onChange={setLevel} tabs={[{ value: 'product', label: 'کالا' }, { value: 'group', label: 'زیرگروه' }, { value: 'category', label: 'گروه کالا' }, { value: 'brand', label: 'برند' }]} />}>
          <DataTable rows={t.rows} columns={t.cols} unit={unit} pageSize={20} exportName={`products-${level}`}
            onRowClick={(r) => nav(detailPath(level, r.key))} />
        </Card>
      </div>
    </>
  )
}
