// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (cashflow).
import { useCallback, useEffect, useState } from "react";
import { Heading, label } from "./agents";
import { CashChart, CashFlowCompositionChart, CashTable } from "./customer-profile";
import { FutureCashflowExecutive } from "./management";
import { fa, money, policy, request } from "./shared";
import type { AgentResult, CashDay } from "./types";

export function Cashflow({ cash, agent, openAgent }: { cash?: any; agent?: AgentResult; openAgent: (key: string) => void }) {
  const [forecastDays, setForecastDays] = useState(30);
  const [selectedCash, setSelectedCash] = useState<any>(cash);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const loadForecast = useCallback(async (days: number) => {
    setLoading(true);
    setError("");
    try {
      setSelectedCash(await request(`/cashflow/unified?forecast_days=${days}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "دریافت Cash Flow ناموفق بود");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { loadForecast(forecastDays); }, [forecastDays, loadForecast]);
  const activeCash = selectedCash || cash || {};
  const days: CashDay[] = activeCash.timeline || [];
  const summary = activeCash.summary || {};
  const opening = activeCash.opening_balance || {};
  const historical = activeCash.historical_context || {};
  const policy = activeCash.cashflow_policy || {};
  const expensePlan = activeCash.historical_expense_plan || {};
  const management = activeCash.management_summary || {};
  const historicalPeriods = historical?.periods || [];
  const historicalChange = historical?.current_vs_previous || {};
  return (
    <>
      <section className="cash-bank-toolbar fd-panel">
        <div>
          <b>بازهٔ پیش‌بینی از امروز تا آینده</b>
          {[[7, "هفتگی"], [30, "ماهانه"], [90, "۳ ماه"], [180, "۶ ماه"]].map(([value, label]) => (
            <button key={value} className={forecastDays === value ? "active" : ""} onClick={() => setForecastDays(Number(value))}>
              {label}
            </button>
          ))}
        </div>
        <small>{loading ? "در حال محاسبه از SQL…" : `${fa(activeCash.forecast_days || forecastDays)} روز از امروز`}</small>
      </section>
      {error && <div className="fd-errors">{error}</div>}
      <FutureCashflowExecutive cash={activeCash} openAgent={openAgent} />
      <article className={`fd-panel management-cashflow-summary management-status-${management.status || "healthy"}`}>
        <Heading h="خلاصهٔ مدیریتی نقدینگی" p="تصمیم‌یار بازهٔ انتخابی؛ فقط اقلامی که اکنون قابل اتکا یا قطعی هستند." />
        <div className="management-decision-hero">
          <div>
            <span className="management-status-badge">{management.status === "critical" ? "کسری پیش‌بینی‌شده" : management.status === "attention" ? "نیازمند توجه" : "پوشش مناسب"}</span>
            <h3>{management.headline || "در حال آماده‌سازی خلاصه مدیریتی"}</h3>
            <p>{management.first_shortage_date_jalali ? `اولین روز کسری: ${management.first_shortage_date_jalali}` : "در این بازه، برای پرداخت‌های قطعی کسری پیش‌بینی نشده است."}</p>
          </div>
          <div className="management-coverage">
            <small>پوشش پرداخت‌های قطعی</small>
            <strong>{management.coverage_percent == null ? "—" : `${fa(management.coverage_percent)}٪`}</strong>
            <span>{management.coverage_percent != null && management.coverage_percent >= 100 ? "منابع قابل استفاده، پرداخت‌های قطعی را پوشش می‌دهد" : "برای پوشش کامل پرداخت‌های قطعی، اقدام لازم است"}</span>
          </div>
        </div>
        <div className="management-key-points">
          {(management.key_points || []).map((row: any) => <article key={row.label} className={`tone-${row.tone || "neutral"}`}>
            <small>{row.label}</small>
            <b>{row.amount_rial == null ? "نامشخص" : `${money(row.amount_rial)} تومان`}</b>
          </article>)}
        </div>
        <div className="management-explainer">
          <span>مبنای نتیجه</span>
          <b>{management.decision_basis || "موجودی ابتدای بازه + وصول قابل برنامه‌ریزی − پرداخت‌های قطعی"}</b>
          <small>نرخ بازگشت محافظه‌کارانه: {fa(management.return_rate_percent || 25)}٪ · تنخواه، انتقال داخلی و سایر هزینه‌های تاریخی در این نتیجه نیستند.</small>
        </div>
        <section className="management-actions">
          <header><b>سه اقدام اولویت‌دار</b><small>اقدام‌های جزئی‌تر در Agent نقدینگی پایین صفحه باقی می‌مانند.</small></header>
          <div>
            {(management.recommendations || []).slice(0, 3).map((action: any, index: number) => <article key={index}>
              <span>{fa(index + 1)}</span>
              <div><b>{action.action}</b><p>{action.why}</p><small>{action.owner} · {action.deadline}</small></div>
            </article>)}
          </div>
        </section>
      </article>
      <article className="fd-panel">
        <Heading
          h="Cash Flow واحد"
          p="Excel/صورت‌حساب فقط موجودی شروع است؛ آینده از SQL فقط‌خواندنی می‌آید و هر قلم یک‌بار حساب می‌شود."
        />
        <div className="cash-reliance-numbers">
          <span><small>چک پرداختی</small><b>{money(summary.issued_cheques_rial || 0)} تومان</b></span>
          <i>←</i>
          <span><small>حقوق در بازه</small><b>{money(summary.salary_reserve_rial || 0)} تومان</b></span>
          <i>←</i>
          <span><small>وصول تعدیل‌شدهٔ چک</small><b>{money(summary.reliable_received_cheques_rial || 0)} تومان</b></span>
        </div>
        <p>
          حقوق با نرخ ثابت {money(policy.salary_monthly_rial || 0)} تومان در ماه ذخیره می‌شود. سایر هزینه‌های تاریخی فعلاً فقط در بخش کنترل نمایش دارند و در مانده یا توصیه‌های نقدینگی وارد نشده‌اند.
        </p>
        <small>
          منبع موجودی: {opening.snapshot_filename || "فایل Excel ثبت نشده"} · SQL Server: فقط خواندنی · تنخواه، انتقال داخلی و چک‌های پرداخت‌شدهٔ سهامداران وارد Cash Flow نیستند.
        </small>
      </article>
      <article className="fd-panel">
        <Heading
          h="سایر هزینه‌ها؛ مبنای محاسبه و دسته‌بندی"
          p="این عدد دیگر مجموع خام پرداخت‌های گذشته نیست؛ هر دسته جداگانه نمایش داده می‌شود تا بتوان مبنای پیش‌بینی را کنترل کرد."
        />
        <div className="cash-reliance-numbers">
          <span><small>برآورد تاریخی این بازه (خارج از Cash Flow)</small><b>{money(expensePlan.forecast_operating_expense_rial || 0)} تومان</b></span>
          <i>←</i>
          <span><small>پرداخت‌های حذف‌شده از مبنا</small><b>{money(expensePlan.excluded_non_operating?.historical_amount_rial || 0)} تومان</b></span>
          <i>←</i>
          <span><small>دورهٔ مبنا</small><b>{fa(expensePlan.history_days || 365)} روز</b></span>
        </div>
        {(expensePlan.categories || []).length ? (
          <div className="excel-table">
            <table>
              <thead><tr><th>دسته</th><th>پرداخت تاریخچه</th><th>تعداد</th><th>برآورد روزانه</th><th>برآورد این بازه</th><th>وضعیت</th></tr></thead>
              <tbody>{expensePlan.categories.map((row: any) => (
                <tr key={row.code}>
                  <td><b>{row.title}</b></td>
                  <td>{money(row.historical_amount_rial || 0)} تومان</td>
                  <td>{fa(row.payment_count || 0)}</td>
                  <td>{money(row.average_daily_rial || 0)} تومان</td>
                  <td>{money(row.forecast_amount_rial || 0)} تومان</td>
                  <td>{!row.included_in_forecast ? "فقط پس از ثبت موعد واقعی" : "خارج از Cash Flow تا تأیید"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : <div className="fd-empty">ریز طبقه‌بندی هزینه پس از خواندن تاریخچهٔ پرداخت‌ها نمایش داده می‌شود.</div>}
        <p>{expensePlan.rule || "تنخواه، انتقال، سهامدار و پرداخت‌های غیرعملیاتی از Cash Flow خارج هستند."}</p>
      </article>
      <article className="fd-panel">
        <Heading
          h="رفتار Cash Flow در ماه‌های گذشته"
          p="Snapshotهای واقعی Excel برای تفسیر فشار ماه جاری و تصمیم محافظه‌کارانه استفاده می‌شوند."
        />
        {historicalPeriods.length ? (
          <>
            <div className="cash-reliance-numbers">
              <span><small>ماه‌های قابل مقایسه</small><b>{fa(historical.period_count || 0)} ماه</b></span>
              <i>←</i>
              <span><small>تغییر فشار نسبت به ماه قبل</small><b>{fa(historicalChange.pressure_change_percent_point || 0)}٪</b></span>
              <i>←</i>
              <span><small>تغییر موجودی</small><b>{money(Math.abs(historicalChange.liquidity_change_rial || 0))} تومان</b></span>
            </div>
            <div className="excel-table">
              <table>
                <thead><tr><th>ماه</th><th>گزارش</th><th>موجودی آخرین روز</th><th>فشار وزنی</th><th>اوج فشار</th><th>روز کسری</th><th>روند</th></tr></thead>
                <tbody>{historicalPeriods.map((row: any) => (
                  <tr key={`${row.jalali_year}-${row.jalali_month}`}>
                    <td><b>{row.period_label}</b></td><td>{fa(row.snapshot_count)}</td>
                    <td>{money(row.latest_liquidity_rial || 0)}</td><td>{fa(row.weighted_average_pressure_percent || 0)}٪</td>
                    <td>{fa(row.peak_pressure_percent || 0)}٪</td><td>{fa(row.shortfall_days || 0)}</td><td>{row.trend || "—"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p>{historical?.forecast_use?.rule}</p>
          </>
        ) : <div className="fd-empty">برای مقایسه، حداقل دو ماه فایل Cash Flow روزانه را ثبت کن.</div>}
      </article>
      <article className="fd-panel reliance-cashflow">
        <Heading
          h={`چرا ${fa(policy.portfolio_reliability_percent || 75)}٪ از مبلغ چک‌ها وارد Cash Flow شد؟`}
          p="سیاست محافظه‌کارانهٔ نقدینگی، بازگشت ۲۰ تا ۳۰٪ چک‌ها را در نظر می‌گیرد؛ سناریوی پایه با ۲۵٪ برگشت محاسبه شده است. هیچ چک سررسیدداری صرفاً به‌خاطر امتیاز فردی حذف نمی‌شود."
        />
        <div className="cash-reliance-numbers">
          <span>
            <small>مبلغ اسمی چک‌های بازه</small>
            <b>{money(summary.nominal_received_cheques_rial || 0)} تومان</b>
          </span>
          <i>←</i>
          <span><small>ذخیرهٔ ریسک وصول</small><b>{money(summary.risk_reduction_rial || 0)} تومان</b></span>
          <i>←</i>
          <span><small>ورودی قابل برنامه‌ریزی</small><b>{money(summary.reliable_received_cheques_rial || 0)} تومان</b></span>
        </div>
        <p>منبع نرخ: {policy.portfolio_reliability_source || "سیاست محافظه‌کارانهٔ نقدینگی"} · نرخ برگشت پایه: {fa(policy.portfolio_return_rate_percent || 25)}٪ · سناریوها: {fa(policy.portfolio_return_rate_range_percent?.[0] || 20)}٪ تا {fa(policy.portfolio_return_rate_range_percent?.[1] || 30)}٪.</p>
      </article>
      <article className="fd-panel">
        <Heading
          h="خط زمان نهایی نقدینگی"
          p="موجودی شروع + همهٔ چک‌های دریافتی × نرخ وصول واقعی − چک‌های پرداختی − ذخیره حقوق − سایر هزینه‌های برآوردی"
        />
        <CashChart days={days} />
        <CashFlowCompositionChart summary={summary} />
        <CashTable days={days} />
      </article>
    </>
  );
}
// Collection alerts: every received cheque that needs follow-up, with customer, number and amount.
// Same open portfolio as «چک و سررسید» (V117 holding filter), so totals match that tab.
