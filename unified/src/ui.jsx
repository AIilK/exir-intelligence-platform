import { Link } from 'react-router-dom'
import { money } from './data.js'

export function PageHead({ crumb, title, desc, children }) {
  return (
    <header className="u-head">
      <div>
        {crumb && <small className="u-crumb">{crumb}</small>}
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
      </div>
      {children && <div className="u-head-tools">{children}</div>}
    </header>
  )
}

export const Chip = ({ domain }) => (
  <span className={`u-chip ${domain === 'فروش' ? 'sales' : 'fin'}`}>{domain}</span>
)

export function Card({ title, sub, action, className = '', children }) {
  return (
    <section className={`u-card ${className}`}>
      {(title || action) && (
        <div className="u-card-head">
          <div>{title && <h2>{title}</h2>}{sub && <small>{sub}</small>}</div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

/** Loading / error placeholder for one data source, so one slow backend never blanks the page. */
export function Pending({ state, label, height = 120 }) {
  if (state?.error) return <div className="u-pending err" style={{ minHeight: height }}>دریافت {label} ناموفق بود: {state.error}</div>
  return <div className="u-pending" style={{ minHeight: height }}>در حال دریافت {label}…</div>
}

export function Bar({ value, max, tone = 'fin' }) {
  const w = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return <span className="u-bar"><i className={tone} style={{ width: `${w}%` }} /></span>
}

export function MaybeLink({ to, className, children }) {
  return to ? <Link to={to} className={className}>{children}</Link> : <div className={className}>{children}</div>
}

/** Amount with its unit, e.g. «۳۱٫۴ میلیارد تومان» (value bold, unit small). */
export function Money({ rial, className = '' }) {
  const m = money(rial)
  return <span className={`u-money ${className}`}><b>{m.v}</b>{m.u && <small>{m.u}</small>}</span>
}

/**
 * Management KPI card: label, amount (with unit) or plain value, a comparison line and a note.
 * With `to` (route) or `onClick` it opens the matching detail.
 */
export function Kpi({ label, rial, value, unit, delta, deltaTone, note, tone, valueTone, to, onClick, domain }) {
  const body = (
    <>
      <span className="u-kpi-top"><span>{label}</span>{domain ? <Chip domain={domain} /> : tone && <i className={`u-dot ${tone}`} />}</span>
      {rial !== undefined
        ? <Money rial={rial} className={valueTone ? `t-${valueTone}` : ''} />
        : <span className={`u-money ${valueTone ? `t-${valueTone}` : ''}`}><b>{value ?? '—'}</b>{unit && <small>{unit}</small>}</span>}
      {delta && <span className={`u-kpi-delta t-${deltaTone || 'flat'}`}>{delta}</span>}
      {note && <small className="u-kpi-sub">{note}</small>}
      {(to || onClick) && <em className="u-kpi-go">جزئیات ←</em>}
    </>
  )
  if (to) return <Link to={to} className="u-kpi linkable">{body}</Link>
  if (onClick) return <button type="button" onClick={onClick} className="u-kpi linkable">{body}</button>
  return <div className="u-kpi">{body}</div>
}

/** Paired vertical bars (e.g. sales vs collection), values in any unit; fmt formats the labels.
 *  dense: many groups (e.g. 12 months) → thinner bars, values only on hover. */
export function PairBars({ items, aKey, bKey, aTone, bTone, fmt, height = 160, labelKey = 'label', subKey, dense, aName, bName }) {
  const max = Math.max(1, ...items.flatMap((x) => [Math.abs(x[aKey] || 0), Math.abs(x[bKey] || 0)]))
  return (
    <div className={`u-pairs ${dense ? 'dense' : ''}`}>
      <div className="u-pairs-plot" style={{ height }}>
        {items.map((x) => (
          <div key={x[labelKey]} className="u-pair">
            {[[aKey, aTone, aName], [bKey, bTone, bName]].map(([k, tone, nm]) => (
              <div key={k} className="u-pair-col" title={`${x[labelKey]}${nm ? ` · ${nm}` : ''}: ${fmt(x[k])}`}>
                {!dense && <small className={`t-${tone}`}>{fmt(x[k])}</small>}
                <i className={tone} style={{ height: `${x[k] == null ? 0 : Math.max(2, (Math.abs(x[k] || 0) / max) * (height - (dense ? 8 : 28)))}px` }} />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="u-pairs-axis">
        {items.map((x) => (
          <div key={x[labelKey]}>
            <small>{x[labelKey]}</small>
            {subKey && x[subKey] != null && <b className={x.subTone || ''}>{x[subKey]}</b>}
          </div>
        ))}
      </div>
    </div>
  )
}
