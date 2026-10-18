import { useState } from 'react'
import { Link } from 'react-router-dom'
// Importing the finance dashboard module also loads its (scoped) styles for these components.
import { ManagerPanel } from '@finance/dashboard-client.tsx'
import { fetchJson } from '@sales/lib.jsx'
import { useJson } from './data.js'
import AgentCards from './AgentCards.jsx'

/**
 * Management agents on the manager page:
 * - finance: Finance Manager card + its report (moved here from «خلاصه مدیریتی مالی») and bank reconciliation;
 * - sales: Sales Manager (it runs the sales team: pace, request conversion, sales–finance bridge).
 */
export default function FinanceAgents() {
  const [round, setRound] = useState(0)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const pack = useJson(`/api/v1/finance/agents/latest${round ? `?r=${round}` : ''}`)
  const manager = pack.data?.status === 'empty' ? undefined : pack.data?.management_summary?.analysis
  // same action as the finance dashboard's «اجرای همه Agentها» button (finance team, then sales team)
  const runAll = async () => {
    setRunning(true)
    setError('')
    try {
      await fetchJson('/api/v1/finance/agents/run-all', { method: 'POST' })
      setRound((n) => n + 1)
    } catch (e) {
      setError(e.message || 'اجرای Agentها ناموفق بود')
    } finally {
      setRunning(false)
    }
  }
  return (
    <section className="u-agents" aria-label="گزارش Agentها">
      <div className="u-section-head">
        <div>
          <h2>گزارش Agentهای مدیریتی</h2>
          <small>تحلیل خودکار مدیر مالی و مدیر فروش: هشدارها، پیش‌بینی‌ها و اقدام‌های پیشنهادی. هر صبح خودکار اجرا می‌شوند.</small>
        </div>
        <div className="u-row-gap">
          <Link to="/finance/agents">تیم Agentها ←</Link>
          <button type="button" className="u-btn primary" onClick={runAll} disabled={running}>
            ✦ {running ? 'در حال اجرای تیم Agentها… (چند دقیقه)' : 'اجرای همه Agentها'}
          </button>
        </div>
      </div>
      {error && <div className="u-pending err">{error}</div>}
      <div className="u-agents-grid">
        <div className="u-agents-col">
          <h3 className="u-agents-label"><i className="u-dot fin" />مالی</h3>
          <AgentCards agents={[{ key: 'management' }]} round={`${pack.data?.report_id}-${round}`}>
            {pack.data && <ManagerPanel a={manager} />}
          </AgentCards>
        </div>
        <div className="u-agents-col">
          <h3 className="u-agents-label"><i className="u-dot sales" />فروش</h3>
          <AgentCards agents={[{ key: 'sales_manager' }]} round={`${pack.data?.report_id}-${round}`} />
          <small className="u-note">Agentهای تیم فروش در صفحه خودشان: سرعت فروش و تبدیل درخواست در <Link to="/hybrid">عملکرد هیبرید</Link>، پل فروش و مالی در <Link to="/files/hybrids">پرونده هیبریدها</Link>.</small>
        </div>
      </div>
      <AgentCards agents={[{ key: 'reconciliation', collapsed: true }]} round={`${pack.data?.report_id}-${round}`} />
    </section>
  )
}
