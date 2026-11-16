import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp, useRkFetch, faDigits, useSaved } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Kpi } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { CustomerDetail } from './Rahkaran.jsx'

// پیشنهاد ثبت سفارش هر فرد-برند B2B از روی ریتم خرید خودش (backend/b2b_reorder.py)
const STYLE = {
  due: 'st-red', overdue: 'st-red', soon: 'st-yellow', pending: 'st-blue', covered: 'st-green', lost: 'st-none', none: 'st-none',
}
const HINT = {
  due: 'از چرخه معمولش گذشته (۰٫۸ تا ۲ برابر چرخه) — الان وقت تماس و ثبت سفارش است',
  overdue: 'بیش از ۲ برابر چرخه درخواست نداده — احتمال ریزش؛ پیگیری علت',
  soon: '۰٫۵ تا ۰٫۸ چرخه گذشته — به‌زودی وقت سفارش است',
  pending: 'درخواستی دارد که بارش هنوز کامل نرسیده (کامل فاکتور نشده)',
  covered: 'کمتر از نصف چرخه گذشته — فعلاً جنس دارد',
  lost: 'بیش از یک سال بی‌سفارش',
  none: 'هیچ سفارشی از ۱۴۰۰/۱۰ ندارد',
}
const q = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v)).toString()

function Pill({ r }) {
  return <span className={`pill ${STYLE[r.status]}`} title={HINT[r.status]}>{r.status_fa}</span>
}

function HowItWorks() {
  const [open, setOpen] = useState(false)
  return (
    <Card title="این پیشنهاد چطور حساب می‌شود؟" actions={<button className="btn ghost" onClick={() => setOpen(!open)}>{open ? 'بستن' : 'نمایش'}</button>}>
      {open && (
        <div className="reorder-how">
          <ol>
            <li><b>هر درخواست یک سفارش است:</b> هر درخواست فروش راهکاران از ۱۴۰۰/۱۰ (درخواست‌های هم‌روز یکی). فاکتورهای هر درخواست از خود راهکاران پیدا می‌شوند (درخواست ← پیش‌فاکتور ← سفارش ← تحویل انبار ← فاکتور).</li>
            <li><b>چرخه سفارش:</b> میانه فاصله بین درخواست‌های پشت‌سرهم، در ۸ فاصله آخر همان فرد-برند. مثلاً «معمولاً هر ۵۰ روز یک بار سفارش می‌دهد». فروردین در هیچ سالی سفارش ندارد، پس روزهایش شمرده نمی‌شود.</li>
            <li><b>چند روز گذشته:</b> از آخرین درخواست تا امروز.</li>
            <li><b>سفارش در جریان:</b> درخواستی که بارش هنوز کامل نرسیده؛ تا رسیدن بار وضعیت «سفارش در جریان» است و هشدار نمی‌گیرد. بار کامل یعنی ۹۰٪ تعداد درخواست فاکتور شده، یا بخشی فاکتور شده و ۴۵ روز فاکتور تازه نیامده. درخواستی که ۶۰ روز هیچ فاکتوری نگرفته کنار می‌رود.</li>
            <li><b>نسبت = روزهای گذشته ÷ چرخه</b>
              <ul>
                <li>کمتر از ۰٫۵ ← <span className="pill st-green">پوشش دارد</span></li>
                <li>۰٫۵ تا ۰٫۸ ← <span className="pill st-yellow">نزدیک سفارش</span></li>
                <li>۰٫۸ تا ۲ ← <span className="pill st-red">نیاز به سفارش</span></li>
                <li>بیشتر از ۲ ← <span className="pill st-red">معوق</span> (احتمال ریزش، پیگیری علت)</li>
                <li>بیش از یک سال بی‌سفارش ← <span className="pill st-none">ریزش‌کرده</span></li>
              </ul>
            </li>
            <li><b>کم‌داده:</b> کسی که کمتر از ۴ سفارش دارد، چرخه میانه هم‌برندهایش را می‌گیرد (ستون «کم‌داده»).</li>
          </ol>
          <p className="muted">
            این قاعده روی ۲۳ ماه گذشته آزموده شد (۱۴۰۳/۰۹ تا ۱۴۰۵/۰۷): از نماینده‌هایی که «نیاز به سفارش» یا «نزدیک سفارش» بودند حدود ۳۱٪
            ظرف یک ماه درخواست تازه دادند. این رقم برای «پوشش دارد» ۲۳٪ و برای «معوق» ۱۶٪ بود. یعنی سفارش نماینده‌ها نامنظم است و این فهرست
            اولویت تماس را نشان می‌دهد، نه قطعیت را.
          </p>
        </div>
      )}
    </Card>
  )
}

export default function Reorder() {
  const { unit } = useApp()
  const nav = useNavigate()
  const [brand, setBrand] = useSaved('brand', '')
  const [province, setProvince] = useSaved('province', '')
  const [status, setStatus] = useSaved('status', '')
  const [sel, setSel] = useState(null)
  const ref = useRef(null)
  const { data, loading, error } = useRkFetch(`/api/rk_sales/reorder?${q({ brand, province })}`)
  useEffect(() => { if (sel) ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [sel])

  const rows = useMemo(() => (data?.rows || [])
    .filter((r) => !status || r.status === status)
    .map((r) => ({ ...r, key: r.code })), [data, status])

  const columns = useMemo(() => [
    { key: 'short', label: 'نماینده', sticky: true },
    { key: 'brand', label: 'برند' },
    { key: 'province', label: 'استان' },
    { key: 'status_fa', label: 'وضعیت', render: (r) => <Pill r={r} /> },
    { key: 'last_order', label: 'آخرین درخواست', type: 'date' },
    { key: 'last_arrival', label: 'رسیدن آخرین بار', type: 'date', hint: 'تاریخ فاکتوری که آخرین درخواست انجام‌شده با آن کامل شد' },
    { key: 'last_invoice', label: 'آخرین فاکتور', type: 'date', hint: 'تاریخ آخرین فاکتور فروش این کد' },
    { key: 'open_reqs', label: 'درخواست در جریان', type: 'int', hint: 'درخواست‌هایی که بارشان هنوز کامل نرسیده' },
    { key: 'open_left', label: 'تعداد در راه', type: 'int', hint: 'تعداد فاکتورنشده درخواست‌های در جریان' },
    { key: 'elapsed', label: 'روز گذشته', type: 'int', hint: 'روز از آخرین درخواست (بدون فروردین)' },
    { key: 'cycle', label: 'چرخه (روز)', type: 'int', hint: 'معمولاً هر چند روز یک بار درخواست می‌دهد (میانه ۸ فاصله آخر)' },
    { key: 'ratio', label: 'نسبت', type: 'num1', hint: 'روز گذشته ÷ چرخه' },
    { key: 'next_order', label: 'موعد سفارش', type: 'date', hint: 'آخرین درخواست + چرخه' },
    { key: 'sales_12m', label: 'فروش خالص ۱۲ ماه', type: 'money' },
    { key: 'orders', label: 'تعداد سفارش', type: 'int' },
    { key: 'few', label: 'کم‌داده', render: (r) => (r.few ? 'بله' : ''), hint: 'کمتر از ۴ درخواست؛ چرخه از هم‌برندها' },
    { key: 'code', label: 'کد مشتری', exportOnly: true },
  ], [])

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  return (
    <>
      <PageHead title="پیشنهاد ثبت سفارش B2B"
        desc={`هر فرد-برند با ریتم سفارش خودش مقایسه می‌شود · داده از ${faDigits(data.since)} تا ${faDigits(data.today)}`}>
        <div className="plan-bar">
          <label><span className="ms-label">برند</span>{' '}
            <select value={brand} onChange={(e) => setBrand(e.target.value)}>
              <option value="">همه</option>{data.brands.map((b) => <option key={b}>{b}</option>)}
            </select>
          </label>
          <label><span className="ms-label">استان</span>{' '}
            <select value={province} onChange={(e) => setProvince(e.target.value)}>
              <option value="">همه</option>{data.provinces.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <span className={`rk-live ${data.live ? 'on' : ''}`} title={`خوانده‌شده: ${data.fetched}`}>
            {data.live ? 'لایو' : `بروزرسانی ${faDigits((data.fetched || '').slice(11, 16))}`}
          </span>
        </div>
      </PageHead>

      <div className="kpis">
        {data.counts.filter((c) => c.n || c.status !== 'none').map((c) => (
          <Kpi key={c.status} type="int" label={c.label} value={c.n} hint={HINT[c.status]}
            active={status === c.status} onClick={() => setStatus(status === c.status ? '' : c.status)}
            more={status === c.status ? 'نمایش همه ▲' : 'فقط همین‌ها ▼'} />
        ))}
      </div>

      <HowItWorks />

      <Card title={status ? `نماینده‌ها: ${data.counts.find((c) => c.status === status)?.label}` : 'همه نماینده‌ها'}
        subtitle="به ترتیب اولویت: نیاز به سفارش، معوق، نزدیک… · روی هر ردیف بزنید تا پرونده‌اش باز شود">
        <DataTable rows={rows} columns={columns} unit={unit} pageSize={25} exportName="پیشنهاد-سفارش-B2B"
          onRowClick={(r) => setSel(sel === r.code ? null : r.code)} expandedKey={sel} />
      </Card>

      {sel && (
        <div ref={ref} className="rk-anchor">
          <CustomerDetail key={sel} code={sel} period="YTD" onClose={() => setSel(null)}
            onProvince={(p) => nav(`/rahkaran?province=${encodeURIComponent(p)}`)} />
        </div>
      )}
    </>
  )
}
