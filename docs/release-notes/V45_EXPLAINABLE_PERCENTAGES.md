# V45 — Explainable Reliability and Reliance Percentages

## Customer profile

The customer profile now shows:

- reliability score;
- four scoring components with weight, observed rate and contribution;
- expected collection rate;
- history-confidence factor;
- final recommended reliance percentage;
- evidence for the result;
- concrete actions that may improve future scoring.

## Per-cheque output

Every cheque prediction includes:

- `customer_base_reliance_percent`;
- `reliance_breakdown.deductions`;
- `collection_probability_cap_percent`;
- `recommended_reliance_percent`;
- `risk_adjusted_collectible_amount_rial`;
- `reliance_reasons`;
- `improvement_actions`.

## Cash Flow

`cash_shortage_forecast` now returns `reliance_summary` with nominal received
cheques, risk-adjusted amount, portfolio reliance percentage, excluded risk
amount, human explanation and improvement steps.

The LLM does not calculate or change these values. It explains the deterministic
engine output and recommends an operational response.
