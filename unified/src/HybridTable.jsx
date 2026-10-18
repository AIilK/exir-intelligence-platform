import { useState } from 'react'
import { Link } from 'react-router-dom'
import { mt, n0, signedPct, isNum, faDigits } from './data.js'
import { LEVEL } from './model.js'
import { Bar } from './ui.jsx'

export const hybridPath = (name, tab) => `/files/hybrids/${encodeURIComponent(name)}${tab ? `?tab=${tab}` : ''}`

const growthCls = (g) => (isNum(g) ? (g >= 0 ? 't-good' : 't-bad') : 't-muted')

/**
 * One row per hybrid: sales (sales dashboard) next to receivables and cheques (finance).
 * Click a header to sort; amounts in million toman (stated in the headers).
 */
export default function HybridTable({ rows, prevLabel, year, limit }) {
  const [sort, setSort] = useState({ key: 'rank', dir: 1 })
  const hasYtd = rows.some((r) => isNum(r.ytdNet))
  const maxDso = Math.max(150, ...rows.map((r) => r.dso || 0))
  const cols = [
    { key: 'name', label: 'هیبرید' },
    ...(hasYtd ? [
      { key: 'ytdNet', label: `فروش ${year ? faDigits(year) : 'امسال'} تا امروز`, unit: 'میلیون تومان', tone: 't-sales' },
      { key: 'ytdGrowth', label: `نسبت به همین بازه ${year ? faDigits(year - 1) : 'پارسال'}`, tone: 't-sales' },
      { key: 'fullPrevNet', label: `فروش کل ${year ? faDigits(year - 1) : 'پارسال'}`, unit: 'میلیون تومان', tone: 't-sales' },
    ] : []),
    { key: 'salesNet', label: 'فروش این ماه', unit: 'میلیون تومان', tone: 't-sales' },
    { key: 'growth', label: `نسبت به همین بازه ${prevLabel || 'ماه قبل'}`, tone: 't-sales' },
    { key: 'debt', label: 'مطالبات باز', unit: 'میلیون تومان', tone: 't-fin' },
    { key: 'openCheques', label: 'چک باز در دست', unit: 'میلیون تومان', tone: 't-fin' },
    { key: 'dso', label: 'دوره وصول', unit: 'روز', tone: 't-fin', title: 'مطالبات باز ÷ میانگین فروش روزانه امسال' },
    { key: 'rank', label: 'وضعیت' },
  ]
  const sorted = [...rows].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key]
    if (typeof x === 'string' || typeof y === 'string') return sort.dir * String(x ?? '').localeCompare(String(y ?? ''), 'fa')
    if (!isNum(x) && !isNum(y)) return 0
    if (!isNum(x)) return 1
    if (!isNum(y)) return -1
    return sort.dir * (x - y) || (b.debt || 0) - (a.debt || 0)
  })
  const shown = limit ? sorted.slice(0, limit) : sorted
  const click = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === 'rank' || key === 'name' ? 1 : -1 }))
  return (
    <div className="u-table-wrap">
      <table className="u-table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} className={c.tone} title={c.title}>
                <button type="button" className="u-sort" onClick={() => click(c.key)} aria-sort={sort.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                  <span>{c.label}{c.unit && <small>{c.unit}</small>}</span>
                  <i aria-hidden>{sort.key === c.key ? (sort.dir > 0 ? '▴' : '▾') : '↕'}</i>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key}>
              <td>
                <Link className="u-row-link" to={hybridPath(r.name)}>{r.name} <span>←</span></Link>
                {r.people.length > 0 && <small className="u-sub">{r.people.slice(0, 2).join('، ')}{r.people.length > 2 ? ` و ${n0(r.people.length - 2)} نفر دیگر` : ''}</small>}
              </td>
              {hasYtd && <>
                <td><b>{mt(r.ytdNet)}</b></td>
                <td className={growthCls(r.ytdGrowth)}>{signedPct(r.ytdGrowth)}</td>
                <td className="t-muted">{mt(r.fullPrevNet)}</td>
              </>}
              <td>{mt(r.salesNet)}</td>
              <td className={growthCls(r.growth)}>{signedPct(r.growth)}</td>
              <td><Link className="u-cell-link" to={hybridPath(r.name, 'debt')}>{mt(r.debt)}</Link>{isNum(r.debtors) && <small className="u-sub">{n0(r.debtors)} مشتری بدهکار</small>}</td>
              <td><Link className="u-cell-link" to={hybridPath(r.name, 'cheques')}>{mt(r.openCheques)}</Link>{isNum(r.openChequeCount) && <small className="u-sub">{n0(r.openChequeCount)} فقره</small>}</td>
              <td>
                <span className="u-inline-bar">
                  <Bar value={r.dso || 0} max={maxDso} tone={r.dso > 120 ? 'danger' : r.dso > 75 ? 'warn' : 'fin'} />
                  <b>{isNum(r.dso) ? n0(r.dso) : '—'}</b>
                </span>
              </td>
              <td><span className={`u-pill ${LEVEL[r.level].cls}`}>{LEVEL[r.level].label}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
