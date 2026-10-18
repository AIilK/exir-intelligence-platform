import { useEffect, useRef, useState } from 'react'
import { fetchJson, useApp, fmtInt, faDigits } from '../lib.jsx'
import { Card, Loading, ErrorBox, Kpi } from '../components/ui.jsx'
import { PageHead } from '../components/Layout.jsx'

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export default function DataSource() {
  const { reload } = useApp()
  const [src, setSrc] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const [wd, setWd] = useState({ e: '', t: '' })
  const [sq, setSq] = useState({ branch_like: '', refresh_minutes: '', history_months: '', history_from: '' })

  const apply = (s) => {
    setSrc(s)
    setWd({ e: s.wd_elapsed ?? '', t: s.wd_total ?? '' })
    setSq({ branch_like: s.sql.branch_like ?? '', refresh_minutes: s.sql.refresh_minutes ?? '', history_months: s.sql.history_months ?? '', history_from: s.sql.history_from ?? '' })
  }
  const refresh = () => fetchJson('/api/sources').then(setSrc).catch((e) => setErr(e.message))
  useEffect(() => {
    fetchJson('/api/sources').then(apply).catch((e) => setErr(e.message))
  }, [])
  // وضعیت دریافت ماه‌ها؛ وقتی ماهی در صف است هر ۳ ثانیه، وگرنه هر ۱۰ ثانیه
  const working = !!(src?.sql?.fetching || src?.sql?.queued?.length)
  useEffect(() => {
    const id = setInterval(refresh, working ? 3000 : 10000)
    return () => clearInterval(id)
  }, [working])
  // با تمام شدن صف، بقیه صفحه‌ها هم داده تازه را بگیرند
  const wasWorking = useRef(false)
  useEffect(() => {
    if (wasWorking.current && !working) reload(false)
    wasWorking.current = working
  }, [working, reload])

  const refreshMonths = async (months, ok) => {
    setErr(null); setMsg(null)
    try {
      setSrc(await fetchJson('/api/sources/refresh_months', json('POST', { months })))
      setMsg(ok)
    } catch (e) { setErr(e.message) }
  }

  const run = async (fn, ok, resetFilters = false) => {
    setBusy(true); setErr(null); setMsg(null)
    try {
      apply(await fn()); setMsg(ok); reload(resetFilters)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const num = (v) => (v === '' ? null : Number(v))
  const saveSql = () => run(() => fetchJson('/api/sources/sql', json('POST', {
    branch_like: sq.branch_like, refresh_minutes: num(sq.refresh_minutes), history_months: num(sq.history_months),
    history_from: sq.history_from,
  })), 'تنظیمات ذخیره شد؛ داده در پس‌زمینه دوباره خوانده می‌شود.', true)
  const refreshNow = () => run(() => fetchJson('/api/sources/refresh', { method: 'POST' }),
    'بروزرسانی ماه جاری در پس‌زمینه شروع شد؛ چند ثانیه بعد داشبورد خودکار تازه می‌شود.')
  const saveWd = () => run(() => fetchJson('/api/settings', json('PUT', {
    wd_elapsed: num(wd.e), wd_total: num(wd.t),
  })), 'روز کاری ذخیره شد.')

  if (!src && !err) return <Loading />
  const m = src?.meta
  const sql = src?.sql
  const pending = (m?.months || []).filter((x) => !x.loaded).length
  const queued = new Set(sql?.queued || [])
  const waiting = queued.size + (sql?.fetching && !queued.has(sql.fetching) ? 1 : 0)
  const prev = (m?.months || [])[1]
  const status = (x) => {
    if (sql?.fetching === x.month) return <span className="chip on">در حال دریافت…</span>
    if (queued.has(x.month)) return <span className="chip">در صف</span>
    return null
  }
  const monthsSub = waiting
    ? `${fmtInt(waiting)} ماه در صف بروزرسانی — هر ماه ۱ تا ۵ دقیقه (در ساعت کاری کندتر). در این مدت داشبورد با داده قبلی کار می‌کند.`
    : pending ? `${fmtInt(pending)} ماه در صف دریافت از SQL${sql?.busy ? ' — در حال دریافت…' : ''}`
      : 'لایو: هر چند ثانیه روزهایی که در کارآمد تغییر کرده‌اند (فاکتور، برگشتی یا درخواست تازه، ویرایش یا حذف) پیدا و فقط همان روزها دوباره خوانده می‌شوند. ماه جاری هر چند دقیقه و ماه‌های قبل روزی یک بار هم کامل خوانده می‌شوند.'
  return (
    <>
      <PageHead title="منبع داده" desc="اتصال لایو به دیتابیس نرم‌افزار پخش کارآمد (KDB)" />
      {err && <ErrorBox error={err} />}
      {msg && <div className="state ok">{msg}</div>}
      {src?.error && !m && <div className="state">{src.error}</div>}
      {sql?.error && <div className="state error">آخرین تلاش برای خواندن از SQL ناموفق بود (داده قبلی نمایش داده می‌شود): {sql.error}</div>}
      {sql?.live_error && !sql?.error && <div className="state error">بررسی لایو ناموفق بود (داده قبلی نمایش داده می‌شود): {sql.live_error}</div>}
      {m && (
        <div className="kpis">
          <Kpi label="سطرهای فاکتور فروش" value={m.rows_sales} type="int" sub={`ویو «${m.sales_sheet}» — همه ماه‌ها`} />
          <Kpi label="سطرهای درخواست" value={m.rows_requests} type="int" sub={`ویو «${m.requests_sheet}»`} />
          <Kpi label="مشتریان فعال" value={m.rows_customers} type="int" sub="جدول tblCustomer" />
          <Kpi label="روز کاری ماه جاری" value={m.wd_elapsed_file} type="int" sub={`از ${fmtInt(m.wd_total_file)} روز (تقویم کارآمد)`} />
        </div>
      )}
      <div className="grid g2">
        <Card title="اتصال SQL"
          subtitle={sql?.server ? `${sql.server} / ${sql.database} — کاربر ${sql.username}` : sql?.conn_error}
          actions={m && <>
            {sql?.live_checked && <span className="chip on">لایو · بررسی {faDigits(sql.live_checked.slice(11, 19))}</span>}
            <span className="chip">آخرین تغییر: {faDigits(m.loaded_at?.slice(11, 19))}</span>
          </>}>
          <div className="field-row">
            <label className="field">
              <span>شعبه‌هایی که نامشان شامل این است (چند عبارت را با | جدا کنید)</span>
              <input className="input" placeholder="مثلاً هیبرید|زنجیره|اینترنت — خالی = همه شعب" value={sq.branch_like}
                onChange={(e) => setSq({ ...sq, branch_like: e.target.value })} />
            </label>
            <label className="field">
              <span>بروزرسانی ماه جاری (دقیقه)</span>
              <input className="input" type="number" min="0" placeholder="0 = خاموش" value={sq.refresh_minutes}
                onChange={(e) => setSq({ ...sq, refresh_minutes: e.target.value })} />
            </label>
            <label className="field">
              <span>تعداد ماه تاریخچه</span>
              <input className="input" type="number" min="1" max="60" value={sq.history_months}
                disabled={!!sq.history_from.trim()}
                onChange={(e) => setSq({ ...sq, history_months: e.target.value })} />
            </label>
            <label className="field">
              <span>تاریخچه از ماه</span>
              <input className="input" placeholder="مثلاً 1404/01 — خالی = تعداد ماه" value={sq.history_from}
                onChange={(e) => setSq({ ...sq, history_from: e.target.value })} />
            </label>
          </div>
          <div className="muted small">
            ماه جاری هر چند دقیقه و ماه‌های قبل روزی یک بار از دیتابیس خوانده می‌شوند و روی دیسک (data/cache/sql) می‌مانند.
            خواندن هر ماه کامل حدود ۳۵ ثانیه طول می‌کشد. با تغییر فیلتر شعبه، همه ماه‌ها دوباره خوانده می‌شوند.
            مشخصات اتصال در فایل .env کنار config.json است.
          </div>
          <div className="field-row">
            <button className="btn" disabled={busy} onClick={saveSql}>ذخیره</button>
            <button className="btn ghost" disabled={busy} onClick={refreshNow}>بروزرسانی الان</button>
          </div>
        </Card>
        <Card title="روز کاری ماه جاری">
          <div className="field-row">
            <label className="field">
              <span>روز کاری سپری‌شده</span>
              <input className="input" type="number" min="1" placeholder={m?.wd_elapsed_file ?? ''} value={wd.e}
                onChange={(e) => setWd({ ...wd, e: e.target.value })} />
            </label>
            <label className="field">
              <span>کل روز کاری ماه</span>
              <input className="input" type="number" min="1" placeholder={m?.wd_total_file ?? '26'} value={wd.t}
                onChange={(e) => setWd({ ...wd, t: e.target.value })} />
            </label>
          </div>
          <div className="muted small">
            خالی = محاسبه از تقویم کارآمد (همه روزها به‌جز جمعه). تعطیلات رسمی در تقویم کارآمد ثبت نشده؛
            برای ماهی که تعطیلی دارد عدد را اینجا وارد کنید. مبنای میانگین روزانه و پیش‌بینی ماه است.
          </div>
          <button className="btn" disabled={busy} onClick={saveWd}>ذخیره</button>
        </Card>
        <Card title="ماه‌های بارگذاری‌شده" className="span2" subtitle={monthsSub}
          actions={m && (
            <div className="head-actions">
              {prev && (
                <button className="btn sm" disabled={queued.has(prev.month) || sql?.fetching === prev.month}
                  onClick={() => refreshMonths([prev.month], `ماه ${faDigits(prev.month)} به صف بروزرسانی اضافه شد؛ ۱ تا ۵ دقیقه طول می‌کشد.`)}>
                  بروزرسانی ماه قبل
                </button>
              )}
              <button className="btn ghost sm" onClick={() => {
                const n = m.months.length
                if (window.confirm(`همه ${n} ماه دوباره از کارآمد خوانده شوند؟ حدود ${n * 2} دقیقه طول می‌کشد (در ساعت کاری بیشتر) و در این مدت داشبورد با داده قبلی کار می‌کند.`)) {
                  refreshMonths(null, 'همه ماه‌ها به صف بروزرسانی اضافه شدند؛ از جدید به قدیم خوانده می‌شوند.')
                }
              }}>بروزرسانی همه ماه‌ها</button>
            </div>
          )}>
          <div className="table-scroll">
            <table>
              <thead><tr><th>ماه</th><th>سطر فاکتور</th><th>سطر درخواست</th><th>آخرین دریافت</th><th>بروزرسانی</th></tr></thead>
              <tbody>
                {(m?.months || []).map((x) => (
                  <tr key={x.month} className={x.month === m.month ? 'active-row' : ''}>
                    <td>{faDigits(x.month)}{x.month === m.month && <span className="chip">جاری</span>}</td>
                    <td>{x.loaded ? fmtInt(x.rows_sales) : '—'}</td>
                    <td>{x.loaded ? fmtInt(x.rows_requests) : '—'}</td>
                    <td>{x.loaded ? faDigits(x.fetched) : <span className="muted">در صف</span>}</td>
                    <td>
                      {status(x) || (
                        <button className="btn ghost sm"
                          onClick={() => refreshMonths([x.month], `ماه ${faDigits(x.month)} به صف بروزرسانی اضافه شد.`)}>
                          بروزرسانی
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  )
}
