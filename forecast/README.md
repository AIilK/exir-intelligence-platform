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


## Production dashboard

The unified app exposes `/forecast/production` behind the `productionForecast` permission.
The published production plan combines Hybrid and domestic B2B demand. Export and open orders
are excluded from this dashboard. Monthly category production consumes inventory once over the
forecast horizon. Quarterly and annual summaries show the published months and report incomplete coverage.

Install the worker dependencies with `python -m pip install -r forecast/requirements.txt`.
Set `FORECAST_PYTHON` to that Python executable when the API uses a separate environment.
Company connection settings are read from `backend/env`, `backend/.env`, and environment variables.
`SQLSERVER_*` is accepted for Rahkaran. Keep credentials and all snapshots local.

The API reads atomic JSON snapshots from `backend/data/production_forecast` or `FORECAST_DATA_DIR`.
To refresh from live, read-only company databases, run

```sh
python forecast/scripts/refresh_production_dashboard.py refresh --data-root backend/data/production_forecast
```

The selected model definitions and backtest artifacts must exist in local `forecast/lab`.
Public-market collection uses the local source and brand catalogs in `forecast/data`.
Use `market` in place of `refresh` to collect public prices and USD observations.
With `FORECAST_REFRESH_ENABLED=true`, inventory refresh runs daily at 06:15 Tehran and retraining
uses the last Persian month closed after day 3. Public-market refresh runs Saturday at 09:15 Tehran.
Last successful data remains available if refresh fails. The page displays observation dates and job status.

## Historical integrity and safety-stock audit

`forecast_lab2.backtest` estimates statistical seasonality separately at each origin.
Learned models use seasonal factors estimated at their training cutoff. Configuration
selection uses early outcomes only; early totals that cross into the late period are
excluded. Automatic low-sales detection in `forecast_lab` uses a trailing baseline.

Run the reproducible audit against an explicit saved snapshot:

```powershell
$env:EXIR_FORECAST_SNAPSHOT = (Resolve-Path forecast/data/confirmation_2026-11-25).Path
$env:EXIR_FORECAST_LAST_CLOSED_MONTH = '1405/08'
.venv-runtime/Scripts/python.exe forecast/scripts/audit_forecast_fixes.py --output forecast/review/causal-safety-latest-2026-11-28
```

Outputs include input hashes, both full-history and causal backtests, early-selected
model definitions, and held-out safety coverage. This reads saved company exports;
it does not query the LAN or publish a production snapshot. Checkpoints require the
same input hashes. Keep these private artifacts in the ignored `forecast/review/`.

The safety candidate pools normalized **joint three-month Hybrid+B2B residuals**
within ABC classes, calibrated on early outcomes for horizons 2, 3, 4. It measures
late-period coverage and buffer size without assuming independent monthly/channel
errors. Sparse SKU history uses its class pool. Overlapping forecast windows and
shared SKU shocks mean these observations are dependent: targets are not guarantees.
The 1-, 6-, and 12-month displayed buffers remain square-root approximations and
have no demonstrated coverage. Legacy plans are explicitly labeled unvalidated;
missing SKU RMSE uses a nonzero historical pool instead of zero.

Use `run_hybrid_b2b_plan.py --lab-dir <audit-output> --output-dir <candidate-output>`
with the same snapshot/month environment to build an isolated candidate. The audit
does not automatically replace operational models or inventory recommendations.
