import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import FinanceDashboard from '@finance/dashboard-client.tsx'

// Views of the finance command center (dashboard-client.tsx `View` type).
const VIEWS = new Set([
  'management', 'customers', 'cheques', 'receivedCheques', 'issuedCheques', 'cashflow', 'liquidity',
  'inventoryPricing', 'purchaseDocs', 'payables',
  'cashBank', 'companyPayments', 'b2bRemittances', 'monthlyExcel', 'collections', 'distribution',
  'representatives', 'simulator', 'alerts', 'history', 'performance', 'settings', 'agents',
])

// customer-facing finance pages → the combined files that put the same customers next to their sales
const CUSTOMER_VIEWS = new Set(['customers', 'receivedCheques', 'collections', 'b2bRemittances', 'representatives', 'distribution'])

/** The original finance dashboard, unchanged, with its own sidebar hidden and its page picked by the URL. */
export default function FinanceView() {
  const { view } = useParams()
  const nav = useNavigate()
  if (!VIEWS.has(view)) return <Navigate to="/finance/management" replace />
  return (
    <>
      {CUSTOMER_VIEWS.has(view) && (
        <div className="u-crosslink u-crosslink-top">
          <div>
            <b>طرف فروش همین مشتریان</b>
            <small>پرونده‌های یکپارچه: فروش هر نماینده راهکاران یا هیبرید کارآمد کنار مطالبات و چک‌هایش</small>
          </div>
          <div className="u-row-gap">
            <Link className="u-btn" to="/files/rahkaran">نمایندگان راهکاران ←</Link>
            <Link className="u-btn ghost" to="/files/hybrids">هیبریدها ←</Link>
          </div>
        </div>
      )}
      {/* data-view lets unified.css hide what moved to the manager page (agent reports on «management») */}
      <div className="fin-scope fin-embedded" data-view={view}>
        <FinanceDashboard view={view} onViewChange={(v) => nav(`/finance/${v}`)} />
      </div>
    </>
  )
}
