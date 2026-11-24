import { useEffect, useMemo, useState } from 'react'
import { useApp, fmtInt, fmtMoney, fmtPct, UNITS } from '../lib.jsx'
import { Card, DataTable, Empty, Kpi, Tabs } from './ui.jsx'
import { Chart, baseOption } from './Chart.jsx'
import { brandColor } from '../brands.js'

const MAIN_CATS = ['رنگ مو', 'اکسیدان', 'پودر دکلره', 'اسپری مو', 'چسب مو']
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

/** همان داده فیلترشده جدول کالاها؛ مبلغ B2B ریال و مبلغ صادرات دلار است. */
export default function ProductMix({ nodes, total, currency = 'rial' }) {
  const { unit } = useApp()
  const [metric, setMetric] = useState('net')
  const [selected, setSelected] = useState(null)
  useEffect(() => { setSelected(null) }, [nodes])
  const { brands, categories, products, byId } = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const groups = nodes.filter((n) => n.level === 1)
    const categories = new Map()
    for (const n of groups) categories.set(n.label, (categories.get(n.label) || 0) + (n.qty || 0))
    return { brands: nodes.filter((n) => n.level === 0), categories,
      products: nodes.filter((n) => n.level === 2), byId }
  }, [nodes])
  const qty = total.qty || 0
  const value = (n) => Math.max(n[metric] || 0, 0)
  const chartData = brands.map((b) => ({
    id: b.id, name: b.label,
    children: nodes.filter((n) => n.parent === b.id && n.level === 1 && value(n) > 0)
      .map((n) => ({ id: n.id, name: n.label, value: value(n) })),
  })).filter((b) => b.children.length)
  const format = (v) => metric === 'qty' ? `${fmtInt(v)} عدد`
    : currency === 'usd' ? `${fmtInt(v)} دلار` : `${fmtMoney(v, unit)} ${UNITS[unit].label}`
  const selectedProducts = selected ? products.filter((p) => {
    const group = byId.get(p.parent)
    return selected.category ? group?.label === selected.category : p.parent === selected.id || group?.parent === selected.id
  }).map((p) => ({ ...p, brand: byId.get(byId.get(p.parent)?.parent)?.label, category: byId.get(p.parent)?.label })) : []
  const moneyCol = { key: 'net', label: currency === 'usd' ? 'فروش خالص (دلار)' : 'فروش خالص', type: currency === 'usd' ? 'int' : 'money' }
  return <>
    <div className="kpis">
      <Kpi label="فروش کل تعدادی" value={qty} type="int" hint="تعداد اقلام فاکتور فروش دوره، مطابق جدول کالاهای همین صفحه"
        sub={`${fmtInt(new Set(products.filter((p) => p.qty > 0).map((p) => p.code)).size)} کالای فروش‌رفته`} />
      {MAIN_CATS.map((name) => <Kpi key={name} label={`${name} (تعداد)`} value={categories.get(name) || 0} type="int"
        sub={`سهم از کل ${fmtPct(qty > 0 ? (categories.get(name) || 0) / qty : null)}`}
        hint="تعداد فروش گروه در بازه و فیلترهای انتخاب‌شده؛ برای جزئیات کلیک کنید"
        active={selected?.category === name} onClick={() => setSelected(selected?.category === name ? null : { category: name, label: name })} />)}
    </div>
    <Card title="ترکیب فروش: برند ← گروه کالا"
      subtitle={`اندازه هر خانه = ${metric === 'qty' ? 'تعداد فروش مثبت' : currency === 'usd' ? 'فروش خالص دلاری مثبت' : 'فروش خالص ریالی مثبت'}؛ برای مشاهده کالاها روی برند یا گروه کلیک کنید`}
      actions={<Tabs value={metric} onChange={setMetric} tabs={[{ value: 'qty', label: 'تعداد' }, { value: 'net', label: currency === 'usd' ? 'مبلغ (دلار)' : 'مبلغ' }]} />}>
      {!chartData.length ? <Empty /> : <Chart height={420} onClick={(p) => {
        if (p.data?.id) setSelected({ id: p.data.id, label: p.name })
      }} option={(t) => ({
        tooltip: { ...baseOption(t).tooltip, formatter: (p) => `${p.treePathInfo.slice(1).map((x) => escape(x.name)).join(' / ')}<br/><b>${escape(format(p.value))}</b>` },
        series: [{ type: 'treemap', roam: false, nodeClick: false, breadcrumb: { show: false },
          left: 0, right: 0, top: 0, bottom: 0,
          label: { show: true, formatter: '{b}', color: '#fff', fontFamily: 'Vazirmatn' },
          upperLabel: { show: true, height: 22, color: '#fff', fontFamily: 'Vazirmatn' },
          itemStyle: { borderColor: t.surface, borderWidth: 2, gapWidth: 2 },
          levels: [{ itemStyle: { borderWidth: 0, gapWidth: 3 } }, { itemStyle: { gapWidth: 2, borderColorSaturation: 0.6 } }],
          data: chartData.map((b) => ({ ...b, itemStyle: { color: brandColor(b.name, t) } })),
        }],
      })} />}
    </Card>
    {selected && <Card title={`کالاهای ${selected.label}`} actions={<button className="btn ghost sm" onClick={() => setSelected(null)}>بستن ✕</button>}>
      <DataTable rows={selectedProducts} columns={[{ key: 'code', label: 'کد کالا' }, { key: 'label', label: 'کالا' },
        { key: 'brand', label: 'برند' }, { key: 'category', label: 'گروه کالا' }, { key: 'qty', label: 'تعداد', type: 'int' }, moneyCol]}
        unit={unit} pageSize={12} exportName={`product-mix-${currency}`} />
    </Card>}
  </>
}
