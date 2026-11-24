import DateRange from './DateRange.jsx'
import { monthEnd } from '../jalali.js'

export default function SalesDateRange({ today, dates = [], from, to, onChange }) {
  const current = today.slice(0, 7)
  const keys = [...new Set([current, ...dates.map((d) => d.slice(0, 7))])].sort().reverse()
  const months = keys.map((month) => ({ month, loaded: true, from: `${month}/01`, to: monthEnd(+month.slice(0, 4), +month.slice(5, 7)) }))
  const meta = { dates, file: { today, month: current, month_to: months[0].to, months } }
  return <DateRange filters={{ date_from: from, date_to: to }} meta={meta}
    setFilters={(f) => onChange(f.date_from || `${current}/01`, f.date_to || months[0].to)} />
}
