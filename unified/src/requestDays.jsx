// «نیازمند توجه» در خلاصه مدیریتی فروش: ویزیتورهای فهرست پورسانت که در کمتر از ۸۰٪ روز کاری سپری‌شده
// ماه جاری (تا دیروز) درخواست ثبت کرده‌اند (بک‌اند: /api/request-days در داشبورد فروش).
import { useMemo, useState } from 'react'
import { buildXlsx } from '@sales/xlsx.js'
import { useJson, n0, faDigits } from './data.js'
import { Th, sorter } from './fileTabs.jsx'

const pctTxt = (v) => `${n0(Math.round((v || 0) * 100))}٪`

function exportXlsx(rows, d) {
  const heads = [
    ['ویزیتور', 'text'], ['کد فروشنده', 'text'], ['شعبه', 'text'], ['سرپرست', 'text'],
    ['روز دارای درخواست', 'int'], ['روز کاری سپری‌شده', 'int'], ['سهم از روز کاری', 'pct'],
    ['کسری تا حد نصاب (روز)', 'int'], ['وضعیت', 'text'],
  ]
  const data = rows.map((r) => [r.name, r.code || '', r.branch, r.supervisor || '', r.days, d.elapsed, r.share ?? 0, r.short,
    r.missing ? 'در داده پیدا نشد' : r.share >= 0.5 ? 'نیازمند توجه' : 'بحرانی'])
  const blob = buildXlsx(heads.map(([label, kind]) => ({ label, kind })), data, 'ویزیتورهای کم‌درخواست', { filterRows: data.length, freezeCol: 1 })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `request-days-${String(d.month || '').replace('/', '-')}.xlsx`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export default function RequestDaysAttention() {
  const { data } = useJson('/api/request-days')
  const [sort, setSort] = useState({ key: 'days', dir: 1 })
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const need = data ? Math.ceil(data.need - 1e-9) : 0
  const low = useMemo(() => (data?.visitors || []).filter((v) => v.low).map((v) => ({
    ...v, key: v.id, short: Math.max(0, need - v.days), missing: !v.seller_key,
  })), [data, need])
  if (!data?.elapsed || !low.length) return null
  const shown = low.filter((r) => !q.trim() || `${r.name} ${r.code} ${r.branch} ${r.supervisor}`.includes(q.trim()))
    .sort((a, b) => sorter(sort)(a, b) || a.branch.localeCompare(b.branch, 'fa') || a.name.localeCompare(b.name, 'fa'))
  const zero = low.filter((r) => r.days === 0).length
  const sp = { sort, setSort }
  return (
    <article className="xo-block u-attn" id="xs-attention">
      <div className="xo-block-title">
        <h3>نیازمند توجه</h3>
        <small>{n0(low.length)} ویزیتور کم‌درخواست در ماه جاری</small>
      </div>
      <div className="u-attn-head">
        <p>{`کمتر از ${pctTxt(data.min_share)} روز کاری درخواست ثبت کرده‌اند: دست‌کم ${n0(need)} روز از ${n0(data.elapsed)} روز کاری سپری‌شده تا دیروز (روز دارای درخواست در جمعه هم حساب می‌شود)${zero ? ` · ${n0(zero)} نفر بدون هیچ درخواستی` : ''}`}</p>
        <div className="u-row-gap">
          {open && <label className="u-search"><span>جستجو</span><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="نام، کد، شعبه یا سرپرست…" /></label>}
          <button className="u-btn ghost" onClick={() => setOpen(!open)}>{open ? 'بستن فهرست' : 'نمایش فهرست'}</button>
          <button className="u-btn" onClick={() => exportXlsx(shown, data)}>خروجی اکسل</button>
        </div>
      </div>
        {open && (
          <div className="u-table-wrap">
            <table className="u-table">
              <thead><tr>
                <Th k="name" {...sp}>ویزیتور</Th>
                <Th k="branch" {...sp}>شعبه</Th>
                <Th k="supervisor" {...sp}>سرپرست</Th>
                <Th k="days" {...sp}>روز دارای درخواست</Th>
                <Th k="short" {...sp}>کسری تا حد نصاب</Th>
                <Th k="share" {...sp}>سهم از روز کاری</Th>
              </tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.key}>
                    <td><b>{r.name}</b>{r.code ? <small className="u-sub">کد {faDigits(r.code)}</small> : null}
                      {r.missing && <small className="u-sub t-warn">در داده پیدا نشد</small>}</td>
                    <td className="t-muted">{r.branch}</td>
                    <td className="t-muted">{r.supervisor || '—'}</td>
                    <td>{n0(r.days)} از {n0(data.elapsed)}</td>
                    <td className={r.short > 0 ? 't-bad' : 't-muted'}>{n0(r.short)} روز</td>
                    <td><span className={`u-pill ${r.share >= 0.5 ? 'warn' : 'bad'}`}>{pctTxt(r.share)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </article>
  )
}
