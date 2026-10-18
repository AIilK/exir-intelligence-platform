import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useApi, useApp, detailPath, fmtInt } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Tabs } from '../components/ui.jsx'
import { HBar, TrendChart } from '../components/Chart.jsx'
import { PageHead } from '../components/Layout.jsx'
import { KpiRow } from './Overview.jsx'
import { C } from '../cols.js'
import { ChainSelloutBlock } from './ChainSellout.jsx'

export const DIM_LABELS = {
  branch: 'شعبه', supervisor: 'سرپرست', seller: 'فروشنده', brand: 'برند',
  category: 'گروه کالا', group: 'زیرگروه کالا', product: 'کالا', customer: 'مشتری', city: 'شهر',
}
const INFO_LABELS = { branch: 'شعبه', supervisor: 'سرپرست', seller: 'فروشنده', brand: 'برند', category: 'گروه کالا', group: 'زیرگروه کالا',
  city: 'شهر', route: 'مسیر', payment: 'نحوه پرداخت' }
// واحد شمارش برای «۱۲ شعبه»، «۳۸ فروشنده»، ...
const COUNT_UNITS = { branch: 'شعبه', supervisor: 'سرپرست', seller: 'فروشنده', brand: 'برند', category: 'گروه', group: 'زیرگروه',
  city: 'شهر', route: 'مسیر', payment: 'روش' }
const FILTERABLE = ['branch', 'supervisor', 'seller', 'brand', 'category', 'group', 'city']
const LINKABLE = ['branch', 'supervisor', 'seller', 'brand', 'category', 'group', 'city']

export default function Detail() {
  const { dim, key } = useParams()
  const [search] = useSearchParams()
  const k = decodeURIComponent(key)
  const within = search.getAll('within')
  const extra = within.map((w) => `&within=${encodeURIComponent(w)}`).join('')
  const { data, loading, error } = useApi(`/api/detail/${dim}?key=${encodeURIComponent(k)}`, extra)
  const { unit, filters, setFilters } = useApp()
  const nav = useNavigate()
  const [tab, setTab] = useState(null)
  const bdRef = useRef(null)
  // با رفتن به مورد دیگر، تب تفکیک به حالت پیش‌فرض برمی‌گردد
  useEffect(() => { setTab(null) }, [dim, key, search.toString()])

  if (loading && !data) return <Loading />
  if (error) return (
    <>
      <PageHead title={`${DIM_LABELS[dim] || ''}: ${k}`} />
      <ErrorBox error={error} />
    </>
  )
  const bd = Object.keys(data.breakdowns)
  const cur = tab && bd.includes(tab) ? tab : bd[0]
  const scope = data.within || []
  const title = [data.label, ...scope.map((w) => w.label)].join(' — ')
  const desc = [
    DIM_LABELS[dim] + (scope.length ? ` در ${scope.map((w) => `${DIM_LABELS[w.dim]} ${w.label}`).join(' و ')}` : ''),
    data.code && data.code !== data.label ? `کد ${data.code}` : null,
  ].filter(Boolean).join(' · ')
  const canFilter = FILTERABLE.includes(dim) && scope.every((w) => FILTERABLE.includes(w.dim))
  const applyFilter = () => {
    const next = { ...filters, [dim]: [data.key] }
    for (const w of scope) next[w.dim] = [w.key]
    setFilters(next)
  }
  const openTab = (d) => {
    setTab(d)
    bdRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const lineCols = [{ key: 'date', label: 'تاریخ', type: 'date' }, C.text('inv_type', 'نوع'), C.text('inv_no', 'شماره'),
    C.text('branch', 'شعبه'), C.text('seller', 'فروشنده'), C.text('customer', 'مشتری'), C.text('product', 'کالا'),
    C.text('category', 'گروه'), C.text('product_group', 'زیرگروه'), { key: 'qty', label: 'تعداد', type: 'int' }, { key: 'unit_price', label: 'فی', type: 'money' },
    { key: 'gross', label: 'قبل تخفیف', type: 'money' }, { key: 'disc', label: 'تخفیف', type: 'money' }, C.net]
  const bdCols = [C.label(DIM_LABELS[cur]), C.net, C.share, C.qty, C.invoices, C.customers, C.returns]
  return (
    <>
      <PageHead title={title} desc={desc}>
        <div className="head-actions">
          {canFilter && (
            <button className="btn" onClick={applyFilter}>اعمال به‌عنوان فیلتر سراسری</button>
          )}
          <button className="btn ghost" onClick={() => nav(-1)}>بازگشت</button>
        </div>
      </PageHead>
      <div className="info-row">
        {Object.entries(data.info).map(([k2, v]) => v.count > 0 && (
          <div key={k2} className="info">
            <span className="muted">{INFO_LABELS[k2]}: </span>
            {bd.includes(k2)
              ? <button className="link" onClick={() => openTab(k2)} title="نمایش همه در «تفکیک فروش»">{fmtInt(v.count)} {COUNT_UNITS[k2]}</button>
              : <span>{fmtInt(v.count)} {COUNT_UNITS[k2]}</span>}
            <span className="muted"> — </span>
            {v.top.map((t, i) => (
              <span key={t.key}>
                {LINKABLE.includes(k2) ? <Link to={detailPath(k2, t.key)}>{t.label}</Link> : t.label}
                {i < v.top.length - 1 ? '، ' : ''}
              </span>
            ))}
            {v.count > v.top.length && (
              <>
                {' و '}
                {bd.includes(k2)
                  ? <button className="link" onClick={() => openTab(k2)}>{fmtInt(v.count - v.top.length)} مورد دیگر</button>
                  : <span className="muted">{fmtInt(v.count - v.top.length)} مورد دیگر</span>}
              </>
            )}
          </div>
        ))}
        {data.master && (
          <div className="info"><span className="muted">از لیست مشتریان: </span>
            {[data.master.trade, data.master.city, data.master.grade && `گرید ${data.master.grade}`].filter(Boolean).join(' · ')}
          </div>
        )}
        <div className="info muted small">ترتیب نام‌ها بر اساس فروش خالص است.</div>
      </div>
      <KpiRow k={data.kpis} />
      {dim === 'branch' && String(data.key).includes('زنجیره') && !scope.length && <ChainSelloutBlock />}
      <div className="grid g2">
        <Card title="روند روزانه" className="span2">
          <TrendChart trend={data.trend} unit={unit} height={260} />
        </Card>
        {cur && (
          <div className="span2" ref={bdRef}>
            <Card title="تفکیک فروش"
              subtitle={`${fmtInt(data.breakdowns[cur].length)} ${DIM_LABELS[cur]} — نمودار ۱۲ مورد اول بر اساس فروش خالص را نشان می‌دهد و جدول همه موارد را`}
              actions={<Tabs value={cur} onChange={setTab} tabs={bd.map((b) => ({ value: b, label: DIM_LABELS[b] }))} />}>
              <div className="grid g2 inner">
                <HBar rows={data.breakdowns[cur].filter((r) => r.net > 0).slice(0, 12)} unit={unit}
                  onClick={(r) => nav(detailPath(cur, r.key))} />
                <DataTable rows={data.breakdowns[cur]} columns={bdCols} unit={unit} pageSize={10} dense
                  exportName={`breakdown-${cur}`} onRowClick={(r) => nav(detailPath(cur, r.key))} />
              </div>
            </Card>
          </div>
        )}
        <Card title="سطرهای فاکتور" className="span2"
          subtitle={data.lines.total > data.lines.rows.length ? `${fmtInt(data.lines.rows.length)} سطر آخر از ${fmtInt(data.lines.total)}` : `${fmtInt(data.lines.total)} سطر`}>
          <DataTable rows={data.lines.rows} columns={lineCols} unit={unit} pageSize={15} exportName={`lines-${dim}-${data.key}`} dense />
        </Card>
      </div>
    </>
  )
}
