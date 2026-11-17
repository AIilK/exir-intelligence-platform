import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtPct, fmtMoney, UNITS, fmtInt } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs, Kpi } from '../components/ui.jsx'
import { Chart, baseOption, HBar } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'

/** نرخ تخفیف انباشته (حجمی + نقدی + مدیریتی) با درصد کل کنار هر میله. large: نسخه بزرگ نمای کلی */
export function DiscountBars({ rows, onClick, large = false }) {
  const data = rows.filter((r) => r.gross > 0).slice(0, 15).reverse()
  const rowH = large ? 36 : 28
  const barW = large ? 22 : 16
  // بازه محور تا کمی بیشتر از بزرگ‌ترین نرخ (گرد به ۵٪)، تا میله‌ها عرض نمودار را پر کنند و برچسب جا شود
  const top = Math.max(...data.map((r) => r.rate || 0), 0.05)
  const xMax = Math.min(1, Math.ceil((top * 1.12) / 0.05) * 0.05)
  const parts = [
    { key: 'vol_rate', name: 'تخفیف حجمی', color: 0 },
    { key: 'cash_rate', name: 'تخفیف نقدی', color: 1 },
    { key: 'mgmt_rate', name: 'تخفیف مدیریتی', color: 2 },
  ]
  return (
    <Chart
      height={Math.max(240, data.length * rowH + 70)}
      onClick={onClick && ((p) => onClick(data[p.dataIndex]))}
      option={(t) => ({
        grid: { left: 16, right: 12, top: 34, bottom: 20, containLabel: true },
        legend: { top: 0, right: 0, textStyle: { color: t.text } },
        tooltip: { ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (ps) => `${ps[0].name}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtPct(p.value)}</b>`).join('<br/>') +
            `<br/>جمع: <b>${fmtPct(data[ps[0].dataIndex].rate)}</b>` },
        xAxis: { type: 'value', inverse: true, min: 0, max: xMax, interval: xMax > 0.5 ? 0.1 : 0.05,
          axisLabel: { color: t.text, formatter: (v) => fmtPct(v, 0) }, splitLine: { lineStyle: { color: t.grid } } },
        yAxis: { type: 'category', position: 'right', data: data.map((r) => r.key),
          axisLabel: { color: t.text, width: large ? 230 : 140, overflow: 'truncate', fontSize: large ? 13 : 12 }, axisTick: { show: false } },
        series: parts.map((s, i) => {
          const last = i === parts.length - 1
          return {
            name: s.name, type: 'bar', stack: 'd', data: data.map((r) => r[s.key] || 0), barMaxWidth: barW,
            itemStyle: { color: t.series[s.color], borderColor: t.surface, borderWidth: 1, ...(last ? { borderRadius: [4, 0, 0, 4] } : {}) },
            // درصد کل در انتهای میله (سمت چپ، چون محور برعکس است)
            ...(last ? { label: { show: true, position: 'left', color: t.text, fontWeight: 600,
              formatter: (p) => fmtPct(data[p.dataIndex].rate) } } : {}),
          }
        }),
      })}
    />
  )
}

export default function Analysis() {
  const { data, loading, error } = useApi('/api/analysis')
  const { unit } = useApp()
  const nav = useNavigate()
  const [discBy, setDiscBy] = useState('category')
  const [retBy, setRetBy] = useState('branch')
  const [discTableBy, setDiscTableBy] = useState('branch')
  const [discOpen, setDiscOpen] = useState(null)  // شعبه‌ای که ریز ویزیتورهایش زیر ردیف باز است
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  const k = data.kpis
  // نرخ تخفیف: از بیشترین نرخ به کمترین (مثل نمای کلی)
  const disc = [...({ category: data.disc_category, group: data.disc_group, branch: data.disc_branch }[discBy] || [])]
    .sort((a, b) => (b.rate ?? 0) - (a.rate ?? 0))
  const ret = { branch: data.ret_branch, category: data.ret_category, group: data.ret_group, product: data.ret_product }[retBy]
  const retDim = retBy
  // جدول تخفیفات به تفکیک شعبه یا ویزیتور، با هر سه نوع تخفیف (حجمی، نقدی، مدیریتی)
  const bySeller = discTableBy === 'seller'
  const byRate = (a, b) => (b.rate ?? 0) - (a.rate ?? 0)
  const discRows = [...((bySeller ? data.disc_seller : data.disc_branch) || [])].sort(byRate)
  const discMetricCols = [
    { key: 'gross', label: 'جمع قبل تخفیف', type: 'money' },
    { key: 'vol', label: 'تخفیف حجمی', type: 'money' }, { key: 'cash', label: 'تخفیف نقدی', type: 'money' },
    { key: 'mgmt', label: 'تخفیف مدیریتی', type: 'money' }, { key: 'disc', label: 'جمع تخفیف', type: 'money' },
    { key: 'vol_rate', label: '٪ حجمی', type: 'pct' }, { key: 'cash_rate', label: '٪ نقدی', type: 'pct' },
    { key: 'mgmt_rate', label: '٪ مدیریتی', type: 'pct' }, { key: 'rate', label: '٪ کل', type: 'pct' }]
  const discCols = [
    ...(bySeller
      ? [{ key: 'seller', label: 'ویزیتور' }, { key: 'branch', label: 'شعبه' }, { key: 'supervisor', label: 'سرپرست', exportOnly: true }]
      : [{ key: 'key', label: 'شعبه', csv: (r) => (r.key === '__total' ? 'جمع کل' : r.key),
          render: (r) => (r.key === '__total' ? <b>جمع کل</b> : <span>{discOpen === r.key ? '▾' : '◂'} {r.key}</span>) }]),
    ...discMetricCols]
  // ردیف جمع: درصدها از جمع مبالغ، نه میانگین درصدها
  const discTotalsFor = (labelKey) => (rs) => {
    const t = Object.fromEntries(['gross', 'vol', 'cash', 'mgmt', 'disc'].map((c) => [c, rs.reduce((a, r) => a + (r[c] || 0), 0)]))
    const rate = (c) => (t.gross ? t[c] / t.gross : null)
    return { ...t, key: '__total', [labelKey]: 'جمع کل', vol_rate: rate('vol'), cash_rate: rate('cash'), mgmt_rate: rate('mgmt'), rate: rate('disc') }
  }
  // کلیک روی شعبه: ریز ویزیتورهای همان شعبه زیر ردیفش باز می‌شود؛ کلیک روی ویزیتور پرونده‌اش را باز می‌کند
  const sellerCols = [{ key: 'seller', label: 'ویزیتور' }, { key: 'supervisor', label: 'سرپرست' }, ...discMetricCols]
  const renderBranchSellers = (b) => (
    <div className="disc-table">
      <DataTable rows={(data.disc_seller || []).filter((r) => r.branch === b.key).sort(byRate)} columns={sellerCols} unit={unit}
        pageSize={50} search={false} exportName={`discount-${b.key}`} totals={discTotalsFor('seller')}
        onRowClick={(r) => r.key !== '__total' && nav(detailPath('seller', r.key))} />
    </div>
  )
  const retCols = [{ key: 'label', label: { branch: 'شعبه', category: 'گروه کالا', group: 'زیرگروه کالا', product: 'کالا' }[retBy] },
    { key: 'returns', label: 'برگشتی خالص', type: 'money' }, { key: 'qty', label: 'تعداد برگشتی', type: 'int' },
    { key: 'rate', label: 'نرخ برگشت', type: 'pct', hint: 'برگشتی ÷ فروش خالص همان مورد' }]
  // برگشتی‌ها در کارآمد نحوه پرداخت ندارند و با «نامشخص» منفی می‌آیند؛ درصدها فقط از فروش (مقادیر مثبت)
  const pay = data.payment.map((p) => ({ ...p, key: p.payment,
    label: p.payment === 'نامشخص' && p.net < 0 ? 'برگشتی (بدون نحوه پرداخت)' : p.payment }))
  const payTot = pay.reduce((a, p) => a + Math.max(p.net, 0), 0)
  return (
    <>
      <PageHead title="تحلیل فروش" desc="تخفیفات، برگشت از فروش و نحوه پرداخت" />
      <div className="kpis">
        <Kpi label="جمع قبل از تخفیف (فاکتورهای فروش)" value={k.sales_gross} />
        <Kpi label="نرخ کل تخفیف" value={k.disc_rate} type="pct" sub={`حجمی ${fmtPct(k.vol_disc_rate)} · نقدی ${fmtPct(k.cash_disc_rate)} · مدیریتی ${fmtPct(k.mgmt_disc_rate)}`} />
        <Kpi label="نرخ تخفیف مدیریتی" value={k.mgmt_disc_rate ?? 0} type="pct" hint="تخفیف مدیریتی ÷ جمع قبل از تخفیف فاکتورهای فروش" />
        <Kpi label="برگشت از فروش" value={k.returns_net} sub={`${fmtInt(k.docs_return)} سند برگشتی`} />
        <Kpi label="نرخ برگشت" value={k.return_rate} type="pct" />
        <Kpi label="ارزش افزوده" value={k.vat} />
        <Kpi label="قابل پرداخت (با ارزش افزوده)" value={k.payable} />
      </div>
      <div className="grid g2">
        <Card title="نرخ تخفیف" subtitle="سهم تخفیف حجمی، نقدی و مدیریتی از جمع قبل از تخفیف — فقط فاکتورهای فروش، بدون فاکتورهای «نمونه کالا»؛ مرتب از بیشترین نرخ"
          actions={<Tabs value={discBy} onChange={setDiscBy} tabs={[{ value: 'category', label: 'گروه کالا' }, { value: 'group', label: 'زیرگروه' }, { value: 'branch', label: 'شعبه' }]} />}>
          <DiscountBars rows={disc} onClick={(r) => nav(detailPath(discBy, r.key))} />
        </Card>
        <Card title="برگشت از فروش"
          actions={<Tabs value={retBy} onChange={setRetBy} tabs={[{ value: 'branch', label: 'شعبه' }, { value: 'category', label: 'گروه' }, { value: 'group', label: 'زیرگروه' }, { value: 'product', label: 'کالا' }]} />}>
          <HBar rows={ret.slice(0, 15)} value="returns" unit={unit} colorIndex={7} onClick={(r) => nav(detailPath(retDim, r.key))} />
        </Card>
        <Card title={`جدول تخفیفات به تفکیک ${bySeller ? 'ویزیتور' : 'شعبه'}`} className="span2"
          subtitle={`هر سه نوع تخفیف (حجمی، نقدی، مدیریتی) برای همه ${bySeller ? 'ویزیتورها' : 'شعبه‌ها'} — فقط فاکتورهای فروش، بدون «نمونه کالا»؛ درصد = مبلغ تخفیف ÷ جمع قبل تخفیف؛ مرتب از بیشترین نرخ کل${bySeller ? '' : '؛ برای ریز ویزیتورها روی شعبه کلیک کنید'}.
            تخفیف برگشتی‌ها کم نمی‌شود، چون این جدول تخفیف داده‌شده هنگام فروش را نشان می‌دهد و برگشتی ممکن است مال فاکتور دوره‌های قبل با نرخ تخفیف دیگری باشد (در صفحه «تحقق و پورسانت» برگشتی کم می‌شود).`}
          actions={<Tabs value={discTableBy} onChange={setDiscTableBy} tabs={[{ value: 'branch', label: 'شعبه' }, { value: 'seller', label: 'ویزیتور' }]} />}>
          <div className="disc-table"><DataTable key={discTableBy} rows={discRows} columns={discCols} unit={unit} pageSize={30}
            exportName={bySeller ? 'discount-seller' : 'discount-branch'} totals={discTotalsFor(bySeller ? 'seller' : 'key')}
            {...(bySeller
              ? { onRowClick: (r) => r.key !== '__total' && nav(detailPath('seller', r.key)) }
              : { onRowClick: (r) => r.key !== '__total' && setDiscOpen(discOpen === r.key ? null : r.key),
                  expandedKey: discOpen, renderExpanded: renderBranchSellers })} /></div>
        </Card>
        <Card title="نحوه پرداخت" subtitle="فروش خالص به تفکیک شرایط پرداخت. برگشتی‌ها در کارآمد نحوه پرداخت ندارند و جدا نمایش داده می‌شوند؛ درصدها فقط از فروش است">
          <HBar rows={pay} unit={unit} />
          <div className="chips">{pay.filter((p) => p.net > 0).map((p) => <span key={p.key} className="chip">{p.label}: {fmtPct(payTot ? p.net / payTot : null)}</span>)}</div>
        </Card>
        <Card title="جدول برگشت از فروش" className="span2">
          <DataTable rows={ret} columns={retCols} unit={unit} pageSize={10} exportName={`returns-${retBy}`}
            onRowClick={(r) => nav(detailPath(retDim, r.key))} />
        </Card>
      </div>
    </>
  )
}
