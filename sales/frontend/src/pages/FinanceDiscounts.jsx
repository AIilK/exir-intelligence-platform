import { useEffect, useMemo, useRef, useState } from 'react'
import { faDigits, fmtPct, useFetch, useRkFetch } from '../lib.jsx'
import { Card, DataTable, ErrorBox, Kpi, Loading, Tabs } from '../components/ui.jsx'
import SalesDateRange from '../components/SalesDateRange.jsx'
import './finance-discounts.css'

const CHANNELS = [{ value: 'b2b', label: 'نمایندگان B2B' }, { value: 'export', label: 'صادرات' }]
const SOURCES = {
  rahkaran: { label: 'راهکاران', description: 'نمایندگان B2B و فروش صادراتی', action: 'مشاهده تخفیف‌های راهکاران' },
  karamad: { label: 'کارآمد', description: 'هیبریدها و شعب فروش', action: 'مشاهده تخفیف‌های کارآمد' },
}
const GROUP_LABEL = { karamad: 'شعبه / هیبرید', b2b: 'استان', export: 'کشور' }
const DISCOUNTS = [
  ['discount', 'کل تخفیف'], ['cash', 'نقدی'], ['mgmt', 'مدیریتی'], ['volume', 'حجمی'], ['other', 'سایر'],
]

function useDiscounts(query) {
  const url = '/api/finance-discounts?' + new URLSearchParams(query)
  const karamad = useFetch(query.source === 'karamad' ? url : null)
  const rahkaran = useRkFetch(query.source === 'karamad' ? null : url)
  return query.source === 'karamad' ? karamad : rahkaran
}

const REGISTERED_COLUMNS = [['mgmt', 'مدیریتی'], ['cash', 'نقدی'], ['volume', 'حجمی']]
  .map(([key, label]) => ({
    key, label,
    csv: (row) => (row[key] || []).map(({ policy, pct }) => `${policy}: ${pct == null ? 'درصد ناموجود' : fmtPct(pct / 100, 2)}`).join('، '),
    render: (row) => row[key]?.length ? <ul className="fd-discount-rates">
      {row[key].map(({ policy, pct }, index) => <li key={index}>
        <strong>{pct == null ? 'درصد ناموجود' : fmtPct(pct / 100, 2)}</strong>
        <small className="fd-discount-subvalue">{policy}</small>
      </li>)}
    </ul> : '—',
  }))

function invoiceRateSummary(row, key) {
  const rates = row.registered_rates?.[key]
  if (!rates?.length) return row[key] ? 'درصد ناموجود' : '—'
  return rates.map(({ pct }) => pct == null ? 'درصد ناموجود' : fmtPct(pct / 100, 2)).join('، ')
}

function InvoiceDialog({ query, group, invoice, onClose, columns }) {
  const dialog = useRef(null)
  useEffect(() => {
    dialog.current.showModal()
  }, [])
  const { data, loading, error } = useDiscounts({
    ...query, group, invoice_id: invoice.invoice_id,
  })
  const karamad = query.source === 'karamad'
  const itemColumns = karamad ? REGISTERED_COLUMNS : query.source === 'export'
    ? [...columns, { key: 'discount_title', label: 'عنوان تخفیف' }]
    : columns
  const rows = karamad && data
    ? (data.registered_discounts?.length ? data.registered_discounts
      : data.rows.map((row) => ({ ...row, mgmt: [], cash: [], volume: [] })))
    : data?.rows
  return <dialog ref={dialog} className="fd-discount-dialog" aria-labelledby="fd-invoice-title" onClose={onClose}>
    <header>
      <div><h3 id="fd-invoice-title">فاکتور {faDigits(invoice.invoice)}</h3>
        <p>{[invoice.customer, faDigits(invoice.date), group].filter(Boolean).join(' · ')}</p>
      </div>
      <form method="dialog"><button className="btn ghost" type="submit" autoFocus>بستن</button></form>
    </header>
    <div className="fd-discount-dialog-body fd-discount-table">
      {error ? <ErrorBox error={error} /> : loading || !data ? <Loading /> : <>
        {data.registered_error && <p role="status" className="muted">{data.registered_error}</p>}
        <DataTable rows={rows} columns={[
          { key: 'product', label: 'کالا', render: (r) => <>{r.product}<small className="fd-discount-subvalue">{faDigits(r.product_code)}</small></> },
          { key: 'product_code', label: 'کد کالا', exportOnly: true },
          { key: 'qty', label: 'تعداد', type: 'int' }, ...itemColumns,
        ]} pageSize={Math.max(1, rows.length)} exportName="discount-invoice-items" />
      </>}
    </div>
  </dialog>
}

function DiscountRows({ query, group, columns }) {
  const [invoice, setInvoice] = useState(null)
  const { data, loading, error } = useDiscounts({ ...query, group })
  const rows = useMemo(() => (data?.rows || []).map((row) => {
    const invoice = { ...row, key: row.invoice_id }
    if (query.source === 'karamad') {
      for (const { key } of REGISTERED_COLUMNS) {
        invoice[key + '_registered'] = invoiceRateSummary(row, key)
      }
    }
    return invoice
  }), [data, query.source])
  if (error) return <ErrorBox error={error} />
  if (loading || !data) return <Loading />
  const invoiceColumns = query.source === 'karamad'
    ? [
      { ...columns.find((column) => column.key === 'discount_rate'), label: 'کل مؤثر' },
      ...REGISTERED_COLUMNS.map(({ key, label }) => ({ key: key + '_registered', label })),
    ]
    : columns
  const fields = [
      { key: 'invoice', label: 'فاکتور', render: (r) => <>
        <button type="button" className="fd-discount-drill" aria-haspopup="dialog" onClick={() => setInvoice(r)}>
          {faDigits(r.invoice)} <span aria-hidden="true">↗</span>
        </button>
        <small className="fd-discount-subvalue">{faDigits(r.date)}</small>
      </> },
      { key: 'date', label: 'تاریخ', type: 'date', exportOnly: true },
      { key: 'customer', label: 'مشتری' },
  ]
  return <div className="fd-discount-detail fd-discount-table fd-discount-invoices">
    <h3>فاکتورهای {group}</h3>
    {data.registered_error && <p role="status" className="muted">{data.registered_error}</p>}
    <DataTable rows={rows} columns={[...fields, ...invoiceColumns]} pageSize={Math.max(1, rows.length)}
      exportName="discount-invoices" />
    {invoice && <InvoiceDialog query={query} group={group} invoice={invoice}
      onClose={() => setInvoice(null)} columns={columns} />}
  </div>
}

function SourceReport({ source, actions }) {
  const [range, setRange] = useState(null)
  const [open, setOpen] = useState(null)
  const query = { source, ...(range ? { date_from: range.from, date_to: range.to } : {}) }
  const { data, loading, error } = useDiscounts(query)
  const defaultPeriod = data?.period?.latest_month ? data.period : null
  const activeRange = range || defaultPeriod
  const detailQuery = activeRange ? { source, date_from: activeRange.from, date_to: activeRange.to } : query
  const exportSale = source === 'export'
  const discounts = DISCOUNTS.filter(([key]) => exportSale ? key === 'discount'
    : source === 'b2b' ? key !== 'volume' : key !== 'other')
  const columns = discounts.map(([key, label]) => {
    const field = key + '_rate'
    return { key: field, label, type: 'pct', pctDigits: 2, render: (r) => <strong>{fmtPct(r[field], 2)}</strong> }
  })
  return <>
    <div className="fd-discount-toolbar">
      {data && <SalesDateRange today={data.today} dates={data.dates} from={activeRange?.from} to={activeRange?.to}
        onChange={(from, to) => { setRange({ from, to }); setOpen(null) }} />}
      {actions}
    </div>
    {error ? <ErrorBox error={error} /> : loading || !data ? <Loading /> : <>
      {defaultPeriod && <p className="muted">در ماه جاری فاکتوری ثبت نشده است. آخرین ماه دارای فاکتور نمایش داده می‌شود.</p>}
      {!data.rows.length && <p className="muted" role="status">در بازهٔ انتخاب‌شده فاکتوری ثبت نشده است.</p>}
      <div className="fd-discount-metrics">{discounts.map(([key, label]) => <Kpi key={key} label={label} type="pct" percentDigits={2}
        value={data.total[key + '_rate']} />)}</div>
      <Card title={'تخفیف به تفکیک ' + GROUP_LABEL[source]} subtitle="برای دیدن فاکتورها ردیف را باز کنید.">
        <div className="fd-discount-table">
        <DataTable rows={data.rows.map((r) => ({ ...r, key: r.group }))} exportName={'discounts-' + source}
          pageSize={Math.max(1, data.rows.length)}
          columns={[{ key: 'group', label: GROUP_LABEL[source], render: (r) => (
            <button type="button" className="fd-discount-drill" aria-expanded={open === r.key} onClick={() => setOpen(open === r.key ? null : r.key)}>
              <span aria-hidden="true">{open === r.key ? '▾' : '◂'}</span> {r.group}
            </button>
          ) }, ...columns]} expandedKey={open}
          renderExpanded={(r) => <DiscountRows key={r.key} query={detailQuery} group={r.group} columns={columns} />} />
        </div>
      </Card>
    </>}
  </>
}

function SourceCard({ system, onSelect }) {
  const info = SOURCES[system]
  const { data, loading, error } = useDiscounts({ source: system === 'rahkaran' ? 'b2b' : system })
  const month = data?.period?.latest_month ? 'آخرین ماه دارای فاکتور' : 'ماه جاری'
  const summary = loading ? 'در حال دریافت خلاصه…' : error ? 'خلاصهٔ ماه در دسترس نیست' :
    'نرخ کل تخفیف ' + month + (system === 'rahkaran' ? ' B2B' : '')
  return <button type="button" className={`fd-discount-source ${system}`} onClick={() => onSelect(system)}>
    <span>{info.description}</span>
    <h2>{info.label}</h2>
    <strong>{fmtPct(data?.total.discount_rate, 2)}</strong>
    <small>{summary}</small>
    <b>{info.action} ←</b>
  </button>
}

export default function FinanceDiscounts() {
  const [system, setSystem] = useState(null)
  const [channel, setChannel] = useState('b2b')
  const source = system === 'karamad' ? system : channel
  return <div className="sales-scope sales-embedded fd-discounts" data-theme="dark" dir="rtl">
    <header className="fd-discount-hero">
      <div>
        <small>مالی و خزانه</small>
        <h1>{system ? 'تخفیف‌های ' + SOURCES[system].label : 'تخفیف‌ها'}</h1>
        <p>{system ? 'درصدهای خلاصه، سهم مبلغ تخفیف از فروش ناخالص همان فاکتورها را نشان می‌دهند.' : 'منبع گزارش را انتخاب کنید تا درصد تخفیف و ریز فاکتورها را ببینید.'}</p>
      </div>
      {system && <button type="button" className="btn ghost" onClick={() => setSystem(null)}>تغییر منبع</button>}
    </header>
    {system ? <SourceReport key={source} source={source}
      actions={system === 'rahkaran' && <Tabs tabs={CHANNELS} value={channel} onChange={setChannel} />} />
      : <section className="fd-discount-sources" aria-label="منابع گزارش تخفیف">
        <SourceCard system="rahkaran" onSelect={setSystem} />
        <SourceCard system="karamad" onSelect={setSystem} />
      </section>}
  </div>
}
