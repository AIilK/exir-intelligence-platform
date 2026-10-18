// Finance-framework agent cards (PageAgentCard) rendered anywhere in the unified dashboard.
// Importing the finance dashboard module also loads the (scoped) styles of these cards.
import '@finance/dashboard-client.tsx'
import { PageAgentCard } from '@finance/page-agents.tsx'

/** agents: [{ key: 'sales_pace', collapsed?: true }, ...] */
export default function AgentCards({ agents, round = 0, children }) {
  return (
    <div className="fin-scope fin-inline">
      <div className="fd enterprise">
        {agents.map((a) => <PageAgentCard key={`${a.key}-${round}`} agentKey={a.key} defaultCollapsed={!!a.collapsed} />)}
        {children}
      </div>
    </div>
  )
}
