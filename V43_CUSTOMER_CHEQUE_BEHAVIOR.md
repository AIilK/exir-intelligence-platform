# V43 — Customer Cheque Behavior Architecture

## Data flow

1. `FinancePredictionService._customer_behavior_rows` reads all available aggregate cheque history from SQL Server.
2. `CustomerChequeBehaviorEngine` calculates reliability, historical rates, confidence, reliance and credit policy.
3. `cheque_return_predictions` applies cheque-specific term, amount and overdue adjustments.
4. `ChequeRiskRuleEngine` evaluates and groups every open cheque by customer.
5. `cash_shortage_forecast` uses each cheque's risk-adjusted collectible amount instead of a flat 75% rate.
6. `CustomerChequeBehaviorDecisionAgent` explains behaviour and proposes controlled credit actions.
7. `FinanceManagerDecisionAgent` receives the specialist output with all other finance agents.

## Test endpoints

- `GET /api/v1/finance/customer-cheque-behavior`
- `GET /api/v1/finance/predictions/cheque-return`
- `GET /api/v1/finance/predictions/cash-shortage`
- `POST /api/v1/finance/agents/run-all`
- `GET /api/v1/finance/agents/latest`

## Important rules

- SQL provides facts; it does not contain a reliance percentage.
- The deterministic engine owns calculations.
- The LLM only explains approved numeric output and suggests actions.
- Guarantee cheques are excluded by the existing SQL filters.
- Backend monetary amounts remain rial; the frontend converts them to toman for display.
