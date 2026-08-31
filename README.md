# Exir AI Platform

> Enterprise Agentic AI Platform for automation, analytics, forecasting, and intelligent decision support across business departments.

Exir AI Platform is a modular enterprise AI system designed to connect organizational data, business rules, automation workflows, analytical engines, and specialized AI agents into one intelligent platform.

Finance and Treasury are currently the first implemented domains, while the architecture is designed to expand across Sales, Warehouse, Production, Planning, Marketing, HR, Procurement, Export, Quality Control, and other organizational departments.

---

## Platform Overview

```text
Enterprise Systems
       │
       ▼
SQL Server / ERP / Excel / APIs
       │
       ▼
Services & Business Rules
       │
       ▼
Tools & Prediction Engines
       │
       ▼
Specialized AI Agents
       │
       ▼
Automation & Orchestration
       │
       ▼
Enterprise AI Assistant
       │
       ▼
Dashboard / Alerts / Recommendations
```

The platform is designed to go beyond traditional reporting.

Instead of only answering:

> What happened?

it aims to help managers understand:

> Why did it happen?

> What is changing?

> What may happen next?

> Which issue should be handled first?

> What action should be considered?

---

# Screenshots

## Enterprise Dashboard

![Exir AI Platform Dashboard](docs/images/dashboard-overview.png)

The main dashboard provides management with a consolidated view of KPIs, risks, alerts, forecasts, and AI-generated insights.

---

## Treasury Intelligence

![Treasury Dashboard](docs/images/treasury-dashboard.png)

Treasury intelligence includes account balances, receipts, payments, cheque monitoring, liquidity information, and operational alerts.

---

## Customer Risk Intelligence

![Customer Risk](docs/images/customer-risk.png)

Customer intelligence combines financial exposure, overdue amounts, payment behavior, cheque history, and explainable risk indicators.

---

## Cash Flow Forecast

![Cash Flow Forecast](docs/images/cashflow-forecast.png)

The forecasting engine estimates future cash inflows, outflows, liquidity pressure, and possible shortage scenarios.

---

## AI Agent Analysis

![AI Agent Analysis](docs/images/agent-analysis.png)

AI agents receive structured and validated outputs from backend services and convert them into management-oriented explanations and recommended actions.

---

# Core Capabilities

| Capability                  | Description                                              | Status         |
| --------------------------- | -------------------------------------------------------- | -------------- |
| Enterprise SQL Integration  | Connect organizational databases to the AI platform      | ✅ Implemented  |
| Treasury Intelligence       | Accounts, transactions, receipts, payments and cheques   | ✅ Implemented  |
| Customer Risk Analysis      | Analyze customer financial behavior and exposure         | ✅ Implemented  |
| Cash Flow Forecasting       | Forecast future inflows, outflows and liquidity pressure | ✅ MVP          |
| Collection Prioritization   | Rank customers based on exposure and collection risk     | ✅ Implemented  |
| Financial Anomaly Detection | Identify unusual financial activities for review         | ✅ MVP          |
| AI Financial Analysis       | Generate management-friendly explanations                | ✅ MVP          |
| Automation Engine           | Automatically execute intelligence workflows             | 🟡 In Progress |
| Historical Intelligence     | Compare risk, forecasts and KPIs over time               | 🟡 In Progress |
| Dynamic SQL Assistant       | Answer ad-hoc questions using validated read-only SQL    | 🟡 In Progress |
| Sales Intelligence          | Sales analysis and forecasting                           | 🔵 Planned     |
| Warehouse Intelligence      | Inventory risk and stock optimization                    | 🔵 Planned     |
| Production Intelligence     | Production planning and operational intelligence         | 🔵 Planned     |
| HR Intelligence             | Workforce analytics and HR assistant                     | 🔵 Planned     |
| Marketing Intelligence      | Campaign and marketing performance analysis              | 🔵 Planned     |

---

# Architecture

```text
                         ┌─────────────────────┐
                         │      Frontend       │
                         │ Dashboard / Chat UI │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   FastAPI Backend   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                       ┌─────────────────────────┐
                       │ Enterprise Agent Manager│
                       └────────────┬────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
         Finance Agent        Sales Agent       Operations Agent
                │                   │                   │
                ▼                   ▼                   ▼
         Specialist Agents    Specialist Agents   Specialist Agents
                │
                ▼
              Tools
                │
                ▼
        Business Services
                │
                ▼
        Prediction Engines
                │
                ▼
       Repository / SQL Layer
                │
                ▼
        SQL Server / ERP / APIs
```

---

# Agent Architecture

The platform follows a hierarchical multi-agent architecture.

| Agent                    | Responsibility                             | Current Status           |
| ------------------------ | ------------------------------------------ | ------------------------ |
| Enterprise Manager Agent | Coordinate business-domain agents          | 🔵 Planned               |
| Finance Manager Agent    | Coordinate financial intelligence          | 🟡 Planned / In Design   |
| Treasury Agent           | Access and analyze treasury operations     | ✅ Foundation Implemented |
| Finance Analyst Agent    | Interpret financial KPIs and risks         | ✅ MVP                    |
| Customer Behavior Agent  | Analyze customer financial behavior        | ✅ Implemented            |
| Collection Agent         | Prioritize collection activities           | 🔵 Planned               |
| Cash Flow Agent          | Interpret cash-flow forecasts              | 🔵 Planned               |
| Reconciliation Agent     | Investigate reconciliation exceptions      | 🔵 Planned               |
| Sales Agent              | Analyze sales performance                  | 🔵 Planned               |
| Warehouse Agent          | Analyze inventory and warehouse operations | 🔵 Planned               |
| Production Agent         | Support production planning                | 🔵 Planned               |
| HR Agent                 | Workforce intelligence                     | 🔵 Planned               |
| Marketing Agent          | Marketing intelligence and ROI analysis    | 🔵 Planned               |

---

# Business Logic Design

One of the core design principles of Exir AI Platform is separation between deterministic business logic and AI reasoning.

```text
Business Data
     ↓
Service Layer
     ↓
Rules / Calculations
     ↓
Tool Layer
     ↓
AI Agent
     ↓
Explanation / Recommendation
```

## Service Layer

Services are responsible for:

* SQL queries
* Financial formulas
* Company business rules
* Risk thresholds
* KPI calculations
* Forecast calculations
* Validation

Example:

```python
risk_score = (
    0.45 * late_payment_risk
    + 0.35 * cheque_return_risk
    + 0.20 * overdue_ratio
)
```

These calculations remain deterministic and auditable.

## Tool Layer

Tools expose controlled capabilities to AI agents.

Example:

```python
account_balance_tool()
latest_receipts_tool()
latest_payments_tool()
cheque_due_report_tool()
cash_shortage_prediction_tool()
collection_priority_tool()
```

## Agent Layer

Agents are responsible for:

* Understanding user intent
* Selecting the correct tool
* Combining multiple outputs
* Interpreting results
* Prioritizing issues
* Explaining risks
* Suggesting possible actions

Agents should not invent financial values.

---

# Finance Module

Finance is currently the most developed domain.

## Treasury Capabilities

| Feature                | Description                                |
| ---------------------- | ------------------------------------------ |
| Account Search         | Find treasury accounts by name             |
| Account Balance        | Retrieve current account information       |
| Account Transactions   | Review recent account transactions         |
| Latest Receipts        | Retrieve approved receipt documents        |
| Latest Payments        | Retrieve approved payment documents        |
| Received Cheques       | Monitor customer cheques                   |
| Issued Cheques         | Monitor company-issued cheques             |
| Cheque Due Reports     | Analyze upcoming and overdue cheques       |
| Cheque Status Analysis | Review collected and protested cheques     |
| Customer Settlement    | Analyze cheque-based customer settlement   |
| Payment Planning       | Estimate payment pressure                  |
| Treasury Briefing      | Create daily treasury intelligence summary |

---

# Prediction & Intelligence Engine

The platform currently contains an explainable prediction service.

Current engines include:

| Engine                         | Output                             |
| ------------------------------ | ---------------------------------- |
| Customer Collection Prediction | Expected customer collection       |
| Late Payment Risk              | Estimated risk of payment delay    |
| Cheque Return Prediction       | Explainable cheque-return risk     |
| Cash Shortage Forecast         | Future liquidity-pressure timeline |
| Collection Priority            | Customer collection priority score |

Current financial predictions are transparent empirical and rule-based estimates.

They are not represented as trained machine-learning probabilities unless an actual trained and validated ML model is deployed.

---

# Customer Intelligence

Customer intelligence combines:

* Open financial exposure
* Overdue exposure
* Cheque history
* Returned cheques
* Payment-term deviations
* Expected collection
* Late-payment risk
* Collection priority

Example structured result:

```json
{
  "customer": "Customer A",
  "risk_score": 78,
  "risk_level": "high",
  "open_exposure": 5000000000,
  "overdue_amount": 1800000000,
  "expected_collection": 3200000000
}
```

The AI agent can then explain why this customer needs management attention.

---

# Automation

The platform is being designed to operate proactively.

```text
Scheduler
    ↓
Read Latest Business Data
    ↓
Run Business Rules
    ↓
Run Prediction Engines
    ↓
Detect Important Changes
    ↓
Generate Alerts
    ↓
Run AI Analysis
    ↓
Save Historical Snapshot
    ↓
Update Dashboard
```

Instead of waiting for the manager to ask questions, the system can automatically identify important changes.

Example:

> Three high-risk customers require attention today.

> Cash-flow pressure is expected to increase during the next 14 days.

> Two large issued cheques may create a liquidity gap if expected receivables are delayed.

---

# History & Organizational Intelligence

Historical data is stored as structured business history rather than uncontrolled LLM memory.

Planned datasets include:

| History Type             | Purpose                                   |
| ------------------------ | ----------------------------------------- |
| Daily Business Snapshots | Compare operational KPIs                  |
| Customer Risk History    | Identify worsening or improving customers |
| Forecast History         | Measure forecast performance              |
| Alert History            | Detect recurring problems                 |
| Agent Analysis History   | Audit AI analysis                         |
| Decision History         | Track management actions                  |

This enables insights such as:

> Customer risk has increased for three consecutive weeks.

> Cash-flow pressure is worsening compared with the previous period.

> The same reconciliation issue has appeared multiple times.

---

# Dynamic Enterprise Query

Critical financial reports use controlled SQL and business services.

For ad-hoc management questions, the platform is designed to support controlled dynamic SQL generation.

```text
Manager Question
       ↓
Schema Context Builder
       ↓
SQL Generator
       ↓
SQL Validator
       ↓
Schema Validator
       ↓
Read-Only Query Executor
       ↓
Enterprise Database
```

This allows managers to ask questions in natural language while maintaining database safety.

---

# Planned Enterprise Domains

| Department      | Planned Intelligence                            |
| --------------- | ----------------------------------------------- |
| Finance         | Treasury, risk, forecast, budgeting, FP&A       |
| Sales           | Performance, forecasting, customer intelligence |
| Warehouse       | Inventory health, stock risk, replenishment     |
| Production      | Capacity, scheduling, material planning         |
| Planning        | Demand and supply planning                      |
| Procurement     | Supplier risk and purchase intelligence         |
| Marketing       | Campaign performance and ROI                    |
| HR              | Workforce analytics and planning                |
| Export          | Customer, market and currency intelligence      |
| Quality Control | Quality trends and non-conformance analysis     |
| R&D             | Product and research intelligence               |

---

# Human-in-the-Loop

Exir AI Platform follows a supervised autonomy approach.

AI may:

* Detect
* Analyze
* Forecast
* Prioritize
* Recommend
* Prepare workflows

Humans remain responsible for sensitive decisions.

```text
AI Recommendation
       ↓
Manager Review
       ↓
Approval
       ↓
Business Action
```

Examples of actions requiring approval include:

* Payment execution
* Credit-limit changes
* Customer restrictions
* Supplier blocking
* Financial approvals

---

# Technology Stack

| Layer               | Technology                              |
| ------------------- | --------------------------------------- |
| Backend             | Python / FastAPI                        |
| API Validation      | Pydantic                                |
| ORM / Database      | SQLAlchemy                              |
| Enterprise Database | Microsoft SQL Server                    |
| Local Metadata      | SQLite                                  |
| AI                  | LLM + Tool Calling + Agent Architecture |
| Automation          | Scheduled and event-based workflows     |
| Frontend            | Enterprise Web Dashboard                |
| Data Sources        | ERP, SQL Server, Excel, APIs            |

---

# Current Status

```text
████████████████░░░░░░░░ Enterprise Data Integration
██████████████░░░░░░░░░░ Finance Intelligence
████████████░░░░░░░░░░░░ Agent Architecture
██████████░░░░░░░░░░░░░░ Automation
██████░░░░░░░░░░░░░░░░░░ Multi-Department Expansion
```

Finance and Treasury currently serve as the first real-world implementation and validation environment for the broader platform architecture.

---

# Roadmap

### Phase 1 — Finance Intelligence

* Treasury integration
* Finance prediction
* Customer risk
* Cash-flow intelligence
* Collection intelligence
* Explainable alerts

### Phase 2 — Enterprise Automation

* Automated AI Assistant
* Scheduler
* History engine
* Alert workflows
* Human approval flows

### Phase 3 — Cross-Department Intelligence

* Sales Agent
* Warehouse Agent
* Production Agent
* Planning Agent
* HR Agent
* Marketing Agent

### Phase 4 — Enterprise Manager Agent

* Cross-department reasoning
* Multi-agent orchestration
* Management briefing
* Strategic recommendations
* Organization-wide AI assistant

---

# Project Vision

Exir AI Platform is not intended to become another reporting application.

It is designed to become an intelligent layer above enterprise systems.

```text
DATA
  ↓
CONTEXT
  ↓
ANALYSIS
  ↓
PREDICTION
  ↓
RECOMMENDATION
  ↓
AUTOMATION
  ↓
HUMAN DECISION
```

The long-term goal is to build a modular Enterprise AI Assistant capable of continuously observing organizational data, understanding business context, identifying important changes, predicting future conditions, and helping managers decide what to do next.
