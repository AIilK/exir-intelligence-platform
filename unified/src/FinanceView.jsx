import { Navigate, useNavigate, useParams } from 'react-router-dom'
import FinanceDashboard from '@finance/dashboard-client.tsx'

// Views of the finance command center (dashboard-client.tsx `View` type).
const VIEWS = new Set([
  'management', 'customers', 'cheques', 'receivedCheques', 'issuedCheques', 'cashflow', 'liquidity',
  'cashBank', 'companyPayments', 'b2bRemittances', 'monthlyExcel', 'collections', 'distribution',
  'representatives', 'simulator', 'alerts', 'history', 'performance', 'settings', 'agents',
])

/** The original finance dashboard, unchanged, with its own sidebar hidden and its page picked by the URL. */
export default function FinanceView() {
  const { view } = useParams()
  const nav = useNavigate()
  if (!VIEWS.has(view)) return <Navigate to="/finance/management" replace />
  return (
    // data-view lets unified.css hide what moved to the manager page (agent reports on «management»)
    <div className="fin-scope fin-embedded" data-view={view}>
      <FinanceDashboard view={view} onViewChange={(v) => nav(`/finance/${v}`)} />
    </div>
  )
}
