Exir Finance AI Assistant

Exir Finance AI Assistant is an agentic finance intelligence platform designed to transform traditional financial reporting into an automated decision-support system for finance and treasury managers.

The platform connects to enterprise financial data sources, runs deterministic financial rules and forecasting services, exposes them as tools, and uses specialized AI agents to interpret the results, prioritize risks, and generate manager-friendly recommendations.

The project is currently focused on treasury and finance intelligence, with a broader goal of becoming a modular enterprise AI platform.

Core Idea

Traditional finance systems usually answer questions such as:

What is the current account balance?
What payments were made today?
Which cheques are overdue?
How much was collected this month?

Exir Finance AI Assistant goes one step further.

It aims to answer:

What needs management attention today?
Which customers are becoming risky?
Which receivables should be collected first?
Is there a possible cash shortage in the coming weeks?
Which payments may create liquidity pressure?
What changed compared with previous periods?
What actions should the finance team prioritize?

The platform separates financial calculation from AI interpretation.

SQL Server
    ↓
Finance Services
    ↓
Rules / Forecast / Prediction Engines
    ↓
Agent Tools
    ↓
Finance AI Agents
    ↓
Dashboard / Alerts / Recommendations

Financial values are calculated by deterministic services and SQL queries. AI agents are used for interpretation, prioritization, explanation, and decision support.

Architecture
Frontend Dashboard
        ↓
FastAPI Backend
        ↓
Agent Layer
        ↓
Tools
        ↓
Services
        ↓
Repositories / SQL Queries
        ↓
SQL Server / ERP

The system follows a layered architecture to keep financial calculations auditable and controlled.

Main Components
Treasury Services

Treasury services provide direct access to operational finance data.

Current capabilities include:

Account search
Account balances
Account transactions
Latest receipts
Latest payments
Received cheques
Issued cheques
Cheque due reports
Received cheque status reports
Customer cheque settlement
Receivable reports
Reconciliation reports
Treasury briefing
Payment planning
Treasury Tools

Treasury services are exposed to agents through a controlled tool layer.

Examples:

account_balance_tool()
account_transactions_tool()
latest_receipts_tool()
latest_payments_tool()
latest_received_cheques_tool()
latest_issued_cheques_tool()
cheque_due_report_tool()
customer_cheque_settlement_tool()

This allows an AI agent to request financial information without directly accessing or generating uncontrolled SQL.

Finance Prediction Service

FinancePredictionService is the analytical engine of the platform.

It works directly with company SQL data and produces explainable rule-based and empirical financial predictions.

Current capabilities include:

Customer Collection Prediction

Analyzes customer cheque history and current exposure to estimate:

Expected collection amount
Collection probability
Late payment risk
Cheque return probability
Current overdue exposure
Collection priority
Late Payment Risk

Late-payment risk is calculated using a transparent weighted model based on factors such as:

Overdue cheque ratio
Policy-term violations
Historical cheque return rate

Example concept:

Late Payment Risk =
50% Overdue Exposure
+
25% Policy Deviation
+
25% Historical Return Risk

These values are explainable and auditable.

The current implementation is not presented as a trained machine-learning probability model.

Cheque Return Prediction

The system estimates the risk of future received cheques using:

Customer historical cheque behavior
Cheque amount compared with historical average
Cheque maturity period
Current overdue exposure
Company cheque-term policy

Outputs include:

Estimated return probability
Risk level
Evidence
Calculation method
Cash Shortage Forecast

The cash-flow engine analyzes:

Historical receipts
Historical payments
Upcoming received cheques
Upcoming issued cheques
Optional opening cash balance

It creates a daily timeline containing:

Projected inflow
Projected outflow
Net daily movement
Cumulative movement
Possible shortage date
Number of negative cash-pressure days
Collection Priority

Customers are ranked according to a weighted collection-priority score using factors such as:

Open financial exposure
Overdue ratio
Late-payment risk
Cheque-return risk

This allows the finance team to focus collection efforts where they can have the highest short-term impact.

Customer Intelligence Service

CustomerIntelligenceService sits above the prediction engine.

It converts prediction outputs into a structured customer intelligence dashboard.

Responsibilities include:

Customer risk scoring
Risk-level classification
Customer prioritization
Exposure aggregation
Expected collection aggregation
Risk alerts
Customer-level decision context

Example output:

{
  "counterpart_name": "Customer A",
  "risk_score": 78,
  "risk_level": "high",
  "open_exposure": 5000000000,
  "overdue_open_amount": 1800000000,
  "expected_collection_amount": 3200000000
}
AI Agents
Customer Behavior Agent

The Customer Behavior Agent receives structured outputs from the financial engines and converts them into human-readable managerial analysis.

The agent is instructed not to invent, recalculate, or modify financial values.

Its responsibilities include:

Executive summary
Good signals
Bad signals
Future outlook
Recommended actions
Next best action

Example flow:

SQL Data
   ↓
FinancePredictionService
   ↓
CustomerIntelligenceService
   ↓
Customer Behavior Agent
   ↓
Manager-Friendly Analysis

The agent can use an LLM when configured. If the LLM is unavailable, the system can fall back to rule-based analysis.

Treasury Agent

The Treasury Agent acts as an intelligent assistant for treasury operations.

Instead of directly querying the database, it uses controlled treasury tools.

Example questions:

What is the balance of this treasury account?
Show the latest payments.
Which cheques are due this week?
Which received cheques were protested?
Show the financial profile of this customer.

The agent chooses the appropriate tool and returns a structured response.

Finance Analyst Agent

The Finance Analyst Agent focuses on interpretation rather than raw data retrieval.

Its role is to analyze outputs from:

Treasury services
Customer risk engines
Cash-flow forecasts
Alerts
Collection priorities
Financial prediction services

The goal is to answer:

What do these financial signals mean for management?

Planned Finance Manager Agent

A higher-level Finance Manager Agent is planned as the orchestration layer above specialized finance agents.

Its role will be to:

Understand management questions
Select the appropriate specialist agent
Combine multiple agent outputs
Produce executive-level finance summaries
Prioritize actions across treasury, risk, collection, and forecasting

Planned architecture:

Finance Manager Agent
        ↓
-----------------------------------
|                |                |
Treasury Agent   Finance Analyst  Customer Behavior Agent
|                |                |
Tools            Tools            Tools
-----------------------------------
        ↓
Finance Services
        ↓
SQL Server
Automation

The long-term direction of the project is not only conversational AI.

The platform is designed to support autonomous finance monitoring.

Example daily workflow:

Scheduler
    ↓
Read Latest SQL Data
    ↓
Run Finance Engines
    ↓
Run Risk Checks
    ↓
Run Cashflow Forecast
    ↓
Run Collection Priorities
    ↓
Generate Alerts
    ↓
Run Finance AI Analysis
    ↓
Save History Snapshot
    ↓
Update Dashboard

This allows management to receive financial intelligence without manually asking questions.

History and Trend Analysis

A history layer is being designed to allow agents to understand changes over time.

Planned historical datasets include:

Daily finance snapshots
Customer risk history
Cash-flow forecast history
Alert history
Agent analysis history
Decision history

This will enable the system to produce insights such as:

Customer risk has increased over the last 10 days.
Critical alerts are rising.
Cash-flow pressure is worsening.
Forecast accuracy has improved.
Customer collection behavior has changed.

History is stored as auditable structured data, not as free-form LLM memory.

Explainability and Safety

The project follows several important design principles.

Financial numbers are not generated by the LLM

Financial calculations come from:

SQL
Services
Rule engines
Prediction engines

The AI agent receives structured values and explains them.

Human approval for sensitive actions

The system may recommend actions such as:

Credit review
Collection prioritization
Payment rescheduling
Customer follow-up

However, sensitive financial actions remain subject to human approval.

The goal is decision support, not uncontrolled autonomous finance execution.

Read-only SQL for dynamic queries

For ad-hoc financial questions, the platform can support controlled SQL generation.

The intended pipeline is:

User Question
    ↓
Schema Context
    ↓
SQL Generator
    ↓
SQL Validator
    ↓
Schema Validator
    ↓
Query Executor
    ↓
SQL Server

Only safe read-only queries should be allowed.

Current Technology Stack
Backend
Python
FastAPI
SQLAlchemy
Pydantic
Database
Microsoft SQL Server
SQLite / local storage for platform metadata and history where needed
AI
OpenAI API / LLM integration
Custom agent classes
Tool-based agent architecture
Rule-based fallback analysis
Data Sources

Current financial integrations are designed around enterprise ERP and treasury data stored in SQL Server.

Current Project Status

Implemented or partially implemented:

SQL Server connectivity
Treasury account tools
Receipt and payment tools
Received and issued cheque tools
Cheque due reports
Customer cheque settlement
Reconciliation support
Treasury briefing
Financial anomaly reporting
Payment planning
Customer financial profiles
Cash-flow scenarios
Customer collection prediction
Late-payment risk
Cheque return prediction
Cash-shortage forecasting
Collection prioritization
Customer Intelligence Service
Customer Behavior Agent
Finance Analyst Agent foundation
Finance dashboard foundation
Automation and history architecture
Roadmap

Planned future capabilities include:

Finance Manager Agent
Automated daily finance assistant
Complete historical trend engine
Reconciliation Agent
Invoice OCR and invoice-processing workflow
Budget vs Actual analysis
FP&A Agent
What-if simulation
Supplier risk analysis
Advanced anomaly and fraud detection
Customer credit-limit recommendation
Working-capital optimization
DSO / DPO prediction
Multi-month financial forecasting
Decision tracking and human approval workflows
Vision

The goal of Exir Finance AI Assistant is not to build another reporting dashboard.

The goal is to build an AI-powered financial decision-support system that can continuously observe financial activity, identify risks, forecast future conditions, explain what is happening, and help finance managers decide what to do next.

Data
 ↓
Understanding
 ↓
Prediction
 ↓
Explanation
 ↓
Recommendation
 ↓
Human Decision

The platform is being designed with enterprise reliability, explainability, auditability, and human oversight as core principles.
