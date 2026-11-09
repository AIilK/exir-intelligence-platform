import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp, useRkFetch, faDigits } from '../lib.jsx'
import { Card, Loading, ErrorBox, DataTable, Kpi } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'
import { CustomerDetail } from './Rahkaran.jsx'

// پیشنهاد ثبت سفارش هر فرد-برند B2B از روی ریتم خرید خودش (backend/b2b_reorder.py)
const STYLE = {
  due: 'st-red', overdue: 'st-red', soon: 'st-yellow', pending: 'st-blue', covered: 'st-green', lost: 'st-none', none: 'st-none',
}
const HINT = {
  due: 'از چرخه معمولش گذشته (۰٫۸ تا ۲ برابر چرخه) — الان وقت تماس و ثبت سفارش است',
  overdue: 'بیش از ۲ برابر چرخه سفارش نداده — احتمال ریزش؛ پیگیری علت',
  soon: '۰٫۵ تا ۰٫۸ چرخه گذشته — به‌زودی وقت سفارش است',
  pending: 'در ۲۱ روز اخیر سفارش داده یا درخواست تأییدشده‌اش هنوز فاکتور نشده',
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
            <li><b>سفارش‌ها را پیدا می‌کنیم:</b> هر درخواست فروش راهکاران از ۱۴۰۰/۱۰ یک سفارش است. درخواست‌هایی که کمتر از ۲۱ روز با هم فاصله دارند یک سفارش حساب می‌شوند.</li>
            <li><b>چرخه خرید:</b> میانه فاصله ۸ سفارش آخر همان فرد-برند. مثلاً «معمولاً هر ۵۵ روز یک بار سفارش می‌دهد». فروردین در هیچ سالی سفارش ندارد، پس روزهایش شمرده نمی‌شود.</li>
            <li><b>چند روز گذشته:</b> از آخرین سفارش تا امروز.</li>
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
            <li><b>مبلغ پیشنهادی:</b> میانه مبلغ ۳ سفارش آخر.</li>
          </ol>
          <p className="muted">
            این قاعده روی ۲۷ ماه گذشته آزموده شد (۱۴۰۳/۰۶ تا ۱۴۰۵/۰۷): از نماینده‌هایی که «نیاز به سفارش» بودند حدود ۳۳٪ ظرف یک ماه
            سفارش دادند. این رقم برای «پوشش دارد» ۲۱ تا ۲۷٪ و برای «معوق» ۱۴٪ بود. یعنی سفارش نماینده‌ها نامنظم است و این فهرست
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
  const [brand, setBrand] = useState('')
  const [province, setProvince] = useState('')
  const [status, setStatus] = useState('')
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
    { key: 'last_order', label: 'آخرین سفارش', type: 'date' },
    { key: 'elapsed', label: 'روز گذشته', type: 'int', hint: 'روز از آخرین سفارش (بدون فروردین)' },
    { key: 'cycle', label: 'چرخه (روز)', type: 'int', hint: 'معمولاً هر چند روز یک بار سفارش می‌دهد' },
    { key: 'ratio', label: 'نسبت', type: 'num1', hint: 'روز گذشته ÷ چرخه' },
    { key: 'next_order', label: 'موعد سفارش', type: 'date', hint: 'آخرین سفارش + چرخه' },
    { key: 'typical_amount', label: 'مبلغ پیشنهادی', type: 'money', hint: 'میانه مبلغ ۳ سفارش آخر (ناخالص درخواست)' },
    { key: 'sales_12m', label: 'فروش خالص ۱۲ ماه', type: 'money' },
    { key: 'orders', label: 'تعداد سفارش', type: 'int' },
    { key: 'few', label: 'کم‌داده', render: (r) => (r.few ? 'بله' : ''), hint: 'کمتر از ۴ سفارش؛ چرخه از هم‌برندها' },
    { key: 'code', label: 'کد مشتری', exportOnly: true },
  ], [])

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />

  return (
    <>
      <PageHead title="پیشنهاد ثبت سفارش B2B"
        desc={`هر فرد-برند با ریتم خرید خودش مقایسه می‌شود · داده از ${faDigits(data.since)} تا ${faDigits(data.today)}`}>
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
