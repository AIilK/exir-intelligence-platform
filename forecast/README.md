# Demand forecast and production plan (پیش‌بینی فروش و برنامه‌ی تولید)

Monthly sales forecast per product code for the three sales channels, and the factory production need.
Everything reads the databases **read-only**; data pulls and outputs stay on the local machine and are not committed
(see `forecast/.gitignore`).

## Sales definition (matches the company's own figures)
- **Hybrid**: net branch sales in KDB / Karamad (`vwFactorFBLinesFull`, sales minus returns).
- **B2B / Export**: Rahkaran factory invoices to non-branch customers (all statuses), minus returns with status 11;
  gifts («اهدایی») and raw-material buyers («مواد») excluded; export = export customer list + country names.
- Factory invoices to own branches are not added (already inside Hybrid).
- Months of the internet outage and broken months (e.g. 1404/10–1405/01) are excluded from training.

## Connections (`backend/.env`)
`KARAMAD_SQLSERVER_*` for KDB, `RAHKARAN_SQLSERVER_*` for Rahkaran (or `RK_SERVER/RK_DB/RK_USER/RK_PWD`
environment variables), `OPENAI_API_KEY` / `OPENAI_MODEL` for the LLM forecaster.

## Run order
| Step | Script | What it does |
|---|---|---|
| 1 | `pull_data.py` | sales, goods, branch stock (KDB); production receipts, factory stock, open orders (Rahkaran) |
| 2 | `pull_extra.py` | stock ledger, discounts, Rahkaran invoices (and returns, see `channels.py`) |
| 3 | `forecast_lab.py` | Hybrid experiments: each change tested alone, chosen on early months, confirmed on later months |
| 4 | `forecast_lab2.py` | per channel (Hybrid / B2B / Export), tolerance error, inflation inputs, final forecasts |
| 5 | `llm_forecaster.py` → `llm_eval.py` | LLM forecaster via API and its comparison on the same rows |
| 6 | `final_plan2.py` | production plan per channel (forecast, open orders, safety stock, stock, need) |
| 7 | `complete_output.py`, `history_forecasts.py` | one row per product; past forecasts vs actual |
| – | `promo_lab.py` | test of promotion inputs (offer / festival / management discounts) |
| – | `compare_company.py` | comparison with the company's spreadsheet formula |
| – | `build_forecast_v2.py`, `build_forecast_v3.py`, `compare_runs.py`, `final_plan.py` | earlier baseline / improved runs |

## Models
Weighted average of the last 3 months (WMA), exponential smoothing (SES), same month last year (SN), Croston-SBA,
TSB, ADIDA, brand-level split, LightGBM (ML), scikit-learn neural network (DL), median / mean / weighted ensembles,
and an LLM forecaster. The model is chosen per ABC class and channel on 3-month totals; choosing a model per product
was tested and was less accurate on new months.

## Main results (backtest 1403/07–1405/06, error on 3-month totals)
| Channel | Error |
|---|---|
| Hybrid | ~43% |
| B2B | ~74% |
| Export | ~105% |

Against the company spreadsheet formula on the same 3,172 products: 54.5% (ours) vs 65.6% (spreadsheet).
Promotion and inflation inputs did not improve the later months; the LLM helped only for export.

Requirements: `pandas`, `numpy`, `pyodbc`, `jdatetime`, `lightgbm`, `scikit-learn`, `openpyxl`.
