import { Link, useLocation, useMatch } from 'react-router-dom'
import SalesLayout from '@sales/components/Layout.jsx'
import AgentCards from './AgentCards.jsx'

const fileTab = (name, tab, bucket) => `/files/hybrids/${encodeURIComponent(name)}?tab=${tab}${bucket ? `&bucket=${bucket}` : ''}`

// sales agents shown on top of their sales page (finance-framework cards, outside the sales styles)
const PAGE_AGENTS = {
  '/hybrid': [{ key: 'sales_pace' }, { key: 'sales_requests', collapsed: true }],
  '/team': [{ key: 'sales_requests' }],
}

/** The original sales dashboard layout (filter bar, error handling, <Outlet/>), with its own sidebar hidden. */
export default function SalesFrame() {
  // A hybrid opened from the sales pages gets a direct way into its finance side.
  const m = useMatch('/detail/branch/:key')
  const name = m ? decodeURIComponent(m.params.key) : null
  const agents = PAGE_AGENTS[useLocation().pathname]
  return (
    <>
      {agents && <div className="u-page-agents"><AgentCards agents={agents} /></div>}
      <div className="sales-scope sales-embedded" data-theme="dark">
        {name && (
          <div className="u-crosslink u-crosslink-top">
            <div>
              <b>طرف مالی {name}</b>
              <small>چک‌های دریافتی، مطالبات، ویزیتورها و وصول فاکتورهای همین هیبرید از داشبورد مالی</small>
            </div>
            <div className="u-row-gap">
              <Link className="u-btn primary" to={fileTab(name, 'cheques', 'all')}>چک‌ها ←</Link>
              <Link className="u-btn ghost" to={fileTab(name, 'cheques', 'overdue')}>چک‌های سررسید گذشته</Link>
              <Link className="u-btn ghost" to={fileTab(name, 'debt')}>مطالبات</Link>
              <Link className="u-btn ghost" to={fileTab(name, 'invoices')}>فاکتورها و وصول</Link>
              <Link className="u-btn" to={`/files/hybrids/${encodeURIComponent(name)}`}>پرونده کامل</Link>
            </div>
          </div>
        )}
        <SalesLayout />
      </div>
    </>
  )
}
