"use client";
// «نقدینگی (جدید)»: every number comes from /api/v1/liquidity (database only, no Excel).
// Amounts arrive in rial; `toman` is the single conversion point on this page.
import { useEffect, useMemo, useState } from "react";
import "./liquidity.css";

type Channel = "all" | "b2b" | "hybrid";
type Section = "forecast" | "received" | "issued" | "flows" | "payroll";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const LIQUIDITY_API = () => `http://${apiHost()}:8000/api/v1/liquidity`;

const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number = 0) => nf.format(v || 0);
/** rial → «۱۲٫۳ میلیارد» toman */
const toman = (rial: number | null | undefined = 0) => {
  const t = Number(rial || 0) / 10, abs = Math.abs(t);
  if (abs >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (abs >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
/** rial → the exact toman amount with thousands separators («۳٬۱۴۴٬۸۶۹٬۲۵۳») */
const fullToman = (rial: number | null | undefined = 0) => nf.format(Math.round(Number(rial || 0) / 10));
const PAYROLL_COLORS: Record<string, string> = {
  exir: "#38bdf8", kadus: "#34d399", faraz: "#a78bfa", uninsured: "#94a3b8", zarin: "#f59e0b",
};
const pct = (v: number | null | undefined) => (v == null ? "—" : `${nf1.format(v)}٪`);

const CHANNELS: [Channel, string][] = [["all", "کل گروه"], ["b2b", "B2B (راهکاران)"], ["hybrid", "هیبرید (کارآمد)"]];
const SECTIONS: [Section, string][] = [
  ["forecast", "پیش‌بینی"],
  ["received", "چک دریافتی"],
  ["issued", "چک پرداختی"],
  ["flows", "ورودی و خروجی"],
  ["payroll", "حقوق"],
];
// One period filter: «N روز آینده» on forward-looking tabs, «N روز گذشته» on history tabs.
const PERIODS = [7, 14, 30, 60, 90, 180];
const FORWARD_SECTIONS: Section[] = ["forecast", "received", "issued"];
const HISTORY_SECTIONS: Section[] = ["flows"];
// The forecast's daily inflow/outflow estimate always averages the last 90 days, so the
// forecast does not jump with the period filter.
const FORECAST_BASE_DAYS = 90;

function useLiquidity(path: string | null, reloadKey: number) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) return;
    let active = true;
    setLoading(true);
    setError("");
    const refresh = reloadKey > 0 ? `${path.includes("?") ? "&" : "?"}refresh=true` : "";
    fetch(`${LIQUIDITY_API()}${path}${refresh}`)
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw Error(typeof j.detail === "string" ? j.detail : `خطای ${r.status}`);
        return j;
      })
      .then((j) => { if (active) setData(j); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت داده ناموفق بود"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, reloadKey]);
  return { data, error, loading };
}

function Warnings({ items }: { items?: { code: string; message: string }[] }) {
  if (!items?.length) return null;
  return <div className="fd-errors lq-warnings">{items.map((w) => <span key={w.code}>⚠ {w.message}</span>)}</div>;
}

function State({ loading, error, children }: { loading: boolean; error: string; children: any }) {
  if (error) return <div className="profile-warning">{error}</div>;
  if (loading) return <div className="lq-loading">در حال محاسبه از دیتابیس… (بار اول تا ۲۰ ثانیه)</div>;
  return children;
}

function Kpi({ label, value, note, tone = "teal" }: { label: string; value: string; note?: string; tone?: string }) {
  return <div className={`fd-kpi ${tone}`}><small>{label}</small><b>{value}</b>{note && <em>{note}</em>}</div>;
}

function Rule({ text }: { text?: string }) {
  return text ? <p className="lq-rule">ⓘ {text}</p> : null;
}

// ------------------------------------------------------------------ chart

const SCENARIO_COLORS: Record<string, string> = { definite: "#34d399", reliance: "#38bdf8", pessimistic: "#f59e0b" };

function BalanceChart({ scenarios, active }: { scenarios: any[]; active: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 900, H = 260, P = { l: 70, r: 12, t: 14, b: 28 };
  const days = scenarios[0]?.days || [];
  const all = scenarios.flatMap((s) => s.days.map((d: any) => d.closing_rial)).concat(scenarios.map((s) => s.opening_rial), [0]);
  const max = Math.max(...all), min = Math.min(...all);
  const span = max - min || 1;
  const x = (i: number) => P.l + (i / Math.max(1, days.length - 1)) * (W - P.l - P.r);
  const y = (v: number) => P.t + ((max - v) / span) * (H - P.t - P.b);
  const ticks = [max, (max + min) / 2, min];
  const activeScenario = scenarios.find((s) => s.key === active) || scenarios[0];
  const hovered = hover == null ? null : activeScenario.days[hover];
  return (
    <div className="lq-chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * W;
          const i = Math.round(((px - P.l) / (W - P.l - P.r)) * (days.length - 1));
          setHover(Math.max(0, Math.min(days.length - 1, i)));
        }}>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} className="lq-grid" />
            <text x={P.l - 8} y={y(t) + 4} className="lq-axis" textAnchor="end">{toman(t)}</text>
          </g>
        ))}
        {min < 0 && <line x1={P.l} x2={W - P.r} y1={y(0)} y2={y(0)} className="lq-zero" />}
        {scenarios.map((s) => (
          <polyline key={s.key} fill="none" stroke={SCENARIO_COLORS[s.key]}
            strokeWidth={s.key === active ? 3 : 1.5} opacity={s.key === active ? 1 : 0.45}
            points={s.days.map((d: any, i: number) => `${x(i)},${y(d.closing_rial)}`).join(" ")} />
        ))}
        {days.map((d: any, i: number) => (i % Math.ceil(days.length / 8) === 0 ? (
          <text key={d.date} x={x(i)} y={H - 8} className="lq-axis" textAnchor="middle">{d.date_jalali.slice(5)}</text>
        ) : null))}
        {hovered && <line x1={x(hover!)} x2={x(hover!)} y1={P.t} y2={H - P.b} className="lq-cursor" />}
      </svg>
      <div className="lq-legend">
        {scenarios.map((s) => <span key={s.key}><i style={{ background: SCENARIO_COLORS[s.key] }} />{s.label}</span>)}
        {hovered && (
          <b>{hovered.date_jalali}: مانده {toman(hovered.closing_rial)} · ورودی {toman(hovered.inflow_rial)} · خروجی {toman(hovered.outflow_rial)}</b>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ forecast

const COMPONENTS: [string, string, 1 | -1][] = [
  ["received_cheques_rial", "چک دریافتی", 1],
  ["estimated_inflow_rial", "ورودی برآوردی (میانگین روز کاری)", 1],
  ["issued_cheques_rial", "چک پرداختی", -1],
  ["payroll_rial", "حقوق", -1],
  ["estimated_outflow_rial", "خروجی برآوردی (میانگین روز کاری)", -1],
];

function ForecastSection({ channel, horizon, baseDays, reloadKey }: { channel: Channel; horizon: number; baseDays: number; reloadKey: number }) {
  const [scenarioKey, setScenarioKey] = useState("reliance");
  const [manualInput, setManualInput] = useState("");
  const [manual, setManual] = useState<number | null>(null);
  const [showAllDays, setShowAllDays] = useState(false);
  const path = `/summary?channel=${channel}&horizon_days=${horizon}&base_days=${baseDays}` +
    (manual != null ? `&opening_balance=${manual}` : "");
  const { data, error, loading } = useLiquidity(path, reloadKey);
  const d = data?.data;
  const scenario = d?.scenarios?.find((s: any) => s.key === scenarioKey);
  const applyManual = () => {
    const value = Number(manualInput.replace(/[^\d.-]/g, ""));
    setManual(manualInput.trim() && Number.isFinite(value) ? value * 1e9 * 10 : null);
  };
  const days = scenario?.days || [];
  const listed = showAllDays ? days : days.filter((x: any) => x.issued_cheques_rial || x.payroll_rial || x.received_cheques_rial || x.closing_rial < 0);
  const withOpening = d?.opening.source === "manual";

  return (
    <State loading={loading && !d} error={error}>
      {d && scenario && <>
        <Warnings items={data.warnings} />
        <div className="lq-scenarios">
          {d.scenarios.map((s: any) => (
            <button key={s.key} className={s.key === scenarioKey ? "active" : ""} onClick={() => setScenarioKey(s.key)}>
              <i style={{ background: SCENARIO_COLORS[s.key] }} />
              <b>{s.label}{s.key === d.base_scenario && " (مبنا)"}</b>
              <small>{s.description}</small>
            </button>
          ))}
        </div>
        <div className="fd-kpis lq-kpis">
          <Kpi label={`خالص جریان نقد ${fa(horizon)} روز`} value={`${toman(scenario.inflow_rial - scenario.outflow_rial)} تومان`}
            note="ورودی − خروجی" tone={scenario.inflow_rial >= scenario.outflow_rial ? "teal" : "red"} />
          <Kpi label="کل ورودی" value={`${toman(scenario.inflow_rial)} تومان`} note="چک دریافتی + ورودی برآوردی" tone="blue" />
          <Kpi label="کل خروجی" value={`${toman(scenario.outflow_rial)} تومان`} note="چک پرداختی + حقوق + خروجی برآوردی" tone="amber" />
          <Kpi label="اولین روز کسری تجمعی" value={scenario.first_shortage ? scenario.first_shortage.date_jalali : "کسری ندارد"}
            note={scenario.first_shortage ? `${fa(scenario.first_shortage.days_from_today)} روز دیگر` : `در ${fa(horizon)} روز آینده`}
            tone={scenario.first_shortage ? "red" : "teal"} />
          <Kpi label="بیشترین کسری تجمعی" value={scenario.financing_need_rial ? `${toman(scenario.financing_need_rial)} تومان` : "کسری ندارد"}
            note={scenario.financing_need_rial ? `در ${scenario.worst_balance.date_jalali} · باید از موجودی یا تأمین مالی پوشش داده شود` : undefined}
            tone={scenario.financing_need_rial ? "red" : "teal"} />
          <Kpi label="نسبت پوشش" value={pct(scenario.coverage_percent)} note={withOpening ? "(موجودی + ورودی) ÷ خروجی" : "ورودی ÷ خروجی"}
            tone={(scenario.coverage_percent ?? 0) < 100 ? "red" : "teal"} />
        </div>

        <section className="fd-panel">
          <div className="lq-panel-head">
            <div className="fd-heading"><h2>جریان نقد خالص تجمعی</h2><p>{d.rule}</p></div>
            <div className="lq-opening">
              <small>موجودی اول دوره (اختیاری)</small>
              <span>
                <input value={manualInput} onChange={(e) => setManualInput(e.target.value)} placeholder="میلیارد تومان"
                  onKeyDown={(e) => e.key === "Enter" && applyManual()} />
                <button onClick={applyManual}>اعمال</button>
                {manual != null && <button onClick={() => { setManual(null); setManualInput(""); }}>حذف</button>}
              </span>
            </div>
          </div>
          <BalanceChart scenarios={d.scenarios} active={scenarioKey} />
        </section>

        <div className="fd-grid">
          <section className="fd-panel">
            <div className="fd-heading"><h2>اجزای پیش‌بینی ({scenario.label})</h2><p>جمع {fa(horizon)} روز آینده</p></div>
            <table className="lq-table">
              <tbody>
                {withOpening && <tr><td>موجودی اول دوره (دستی)</td><td className="num">{toman(scenario.opening_rial)}</td></tr>}
                {COMPONENTS.map(([key, label, sign]) => (
                  <tr key={key}><td>{sign > 0 ? "+" : "−"} {label}</td>
                    <td className={`num ${sign > 0 ? "pos" : "neg"}`}>{toman(scenario.totals[key])}</td></tr>
                ))}
                <tr className="total"><td>{withOpening ? "مانده پایان دوره" : "خالص جریان نقد"}</td><td className="num">{toman(scenario.closing_rial)}</td></tr>
              </tbody>
            </table>
            <p className="lq-rule">میانگین روز کاری: ورودی {toman(d.basis.daily_inflow_rial)} · خروجی {toman(d.basis.daily_outflow_rial)} (مبنای {fa(d.basis.base_days)} روز اخیر). مبالغ به تومان.</p>
          </section>
          <section className="fd-panel">
            <div className="fd-heading"><h2>مقایسه سناریوها</h2><p>{fa(horizon)} روز آینده</p></div>
            <table className="lq-table">
              <thead><tr><th>سناریو</th><th>ورودی</th><th>خروجی</th><th>خالص</th><th>بیشترین کسری</th><th>پوشش</th></tr></thead>
              <tbody>
                {d.scenarios.map((s: any) => (
                  <tr key={s.key} className={s.key === scenarioKey ? "sel" : ""} onClick={() => setScenarioKey(s.key)}>
                    <td><i className="dot" style={{ background: SCENARIO_COLORS[s.key] }} />{s.label}</td>
                    <td className="num">{toman(s.inflow_rial)}</td><td className="num">{toman(s.outflow_rial)}</td>
                    <td className={`num ${s.inflow_rial < s.outflow_rial ? "neg" : "pos"}`}>{toman(s.inflow_rial - s.outflow_rial)}</td>
                    <td className={`num ${s.financing_need_rial ? "neg" : ""}`}>{s.financing_need_rial ? toman(s.financing_need_rial) : "—"}</td>
                    <td className="num">{pct(s.coverage_percent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>

        <section className="fd-panel">
          <div className="lq-panel-head">
            <div className="fd-heading"><h2>جدول روزانه ({scenario.label})</h2><p>{showAllDays ? "همه روزها" : "فقط روزهای دارای چک، حقوق یا کسری تجمعی"}</p></div>
            <button className="lq-link" onClick={() => setShowAllDays(!showAllDays)}>{showAllDays ? "فقط روزهای مهم" : "همه روزها"}</button>
          </div>
          <div className="fd-table">
            <table>
              <thead><tr><th>تاریخ</th><th>چک دریافتی</th><th>ورودی برآوردی</th><th>چک پرداختی</th><th>حقوق</th><th>خروجی برآوردی</th><th>خالص روز</th><th>تجمعی</th></tr></thead>
              <tbody>
                {listed.map((x: any) => (
                  <tr key={x.date} className={x.closing_rial < 0 ? "lq-neg-row" : ""}>
                    <td>{x.date_jalali}{x.weekday === 4 && <small> جمعه</small>}</td>
                    <td className="pos">{x.received_cheques_rial ? toman(x.received_cheques_rial) : "—"}</td>
                    <td>{x.estimated_inflow_rial ? toman(x.estimated_inflow_rial) : "—"}</td>
                    <td className="neg">{x.issued_cheques_rial ? toman(x.issued_cheques_rial) : "—"}</td>
                    <td className="neg">{x.payroll_rial ? toman(x.payroll_rial) : "—"}</td>
                    <td>{x.estimated_outflow_rial ? toman(x.estimated_outflow_rial) : "—"}</td>
                    <td className={x.net_rial < 0 ? "neg" : "pos"}>{toman(x.net_rial)}</td>
                    <td className={x.closing_rial < 0 ? "neg" : ""}><b>{toman(x.closing_rial)}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </>}
    </State>
  );
}

// ------------------------------------------------------------------ received cheques

function ReceivedSection({ channel, horizon, reloadKey }: { channel: Channel; horizon: number; reloadKey: number }) {
  const { data, error, loading } = useLiquidity(`/received-cheques?channel=${channel}&horizon_days=${horizon}`, reloadKey);
  const [customer, setCustomer] = useState<any>(null);
  const d = data?.data;
  return (
    <State loading={loading && !d} error={error}>
      {d && <>
        <Warnings items={data.warnings} />
        <div className="fd-kpis">
          <Kpi label={`قطعی ${fa(horizon)} روز`} value={`${toman(d.kpis.horizon.definite_rial)} تومان`} note={`${fa(d.kpis.horizon.count)} چک`} />
          <Kpi label="اتکا" value={`${toman(d.kpis.horizon.reliance_rial)} تومان`} note={`${pct(d.kpis.horizon.reliance_percent)} از قطعی`} tone="blue" />
          <Kpi label="ریسک وصول" value={`${toman(d.kpis.horizon.collection_risk_rial)} تومان`} tone="amber" />
          <Kpi label="سررسید امروز (قطعی / اتکا)" value={`${toman(d.kpis.today.definite_rial)} / ${toman(d.kpis.today.reliance_rial)}`}
            note={`${fa(d.kpis.today.count)} چک`} />
        </div>
        <div className="fd-grid lq-grid3">
          <section className="fd-panel">
            <div className="fd-heading"><h2>معوق باز</h2><p>{d.overdue.rule}</p></div>
            <p className="lq-big">{toman(d.overdue.definite_rial)} تومان · {fa(d.overdue.count)} چک</p>
            <table className="lq-table"><tbody>
              {d.overdue.age_buckets.map((b: any) => <tr key={b.label}><td>{b.label}</td><td className="num">{toman(b.definite_rial)}</td><td className="num">{fa(b.count)} چک</td></tr>)}
            </tbody></table>
          </section>
          <section className="fd-panel">
            <div className="fd-heading"><h2>برگشتی تسویه‌نشده</h2><p>{d.returned_open.rule} مستقل از افق: همه چک‌های برگشتی که هنوز تسویه نشده‌اند.</p></div>
            <p className="lq-big">{toman(d.returned_open.amount_rial)} تومان · {fa(d.returned_open.count)} چک</p>
            <table className="lq-table"><tbody>
              {d.returned_open.by_system.map((s: any) => <tr key={s.system}><td>{s.label}</td><td className="num">{toman(s.amount_rial)}</td><td className="num">{fa(s.count)} چک</td></tr>)}
              <tr><td>سررسید در ۱۲ ماه اخیر</td><td className="num">{toman(d.returned_open.last_365_days_rial)}</td><td /></tr>
            </tbody></table>
          </section>
          <section className="fd-panel">
            <div className="fd-heading"><h2>محل نگهداری چک‌های بازه</h2><p>همان چک‌های کارت‌های بالا (سررسید از امروز تا پایان افق)، به تفکیک اینکه الان کجا هستند.</p></div>
            <table className="lq-table">
              <thead><tr><th>محل</th><th>قطعی</th><th>اتکا</th><th>تعداد</th></tr></thead>
              <tbody>
                {d.by_holding.map((h: any) => <tr key={h.holding}><td>{h.label}</td><td className="num">{toman(h.definite_rial)}</td><td className="num">{toman(h.reliance_rial)}</td><td className="num">{fa(h.count)}</td></tr>)}
                <tr className="total"><td>جمع (= کارت قطعی و اتکا)</td><td className="num">{toman(d.kpis.horizon.definite_rial)}</td><td className="num">{toman(d.kpis.horizon.reliance_rial)}</td><td className="num">{fa(d.kpis.horizon.count)}</td></tr>
              </tbody>
            </table>
            {d.hybrid_settlement.count > 0 && <p className="lq-rule">جدا از جمع: چک‌های تسویه هیبرید با شرکت {toman(d.hybrid_settlement.definite_rial)} تومان ({fa(d.hybrid_settlement.count)} چک) — {d.hybrid_settlement.eliminated_in_group ? "در جمع گروه حذف شده" : "نمای کانال"}.</p>}
          </section>
        </div>
        <section className="fd-panel">
          <div className="fd-heading"><h2>مشتریان بازه (بیشترین ریسک وصول)</h2><p>{d.rule} برای ریز چک‌ها روی مشتری کلیک کنید.</p></div>
          <div className="fd-table">
            <table>
              <thead><tr><th>مشتری</th><th>کانال</th><th>قطعی</th><th>اتکا</th><th>درصد اتکا</th><th>ریسک وصول</th><th>نزدیک‌ترین سررسید</th><th>سابقه</th></tr></thead>
              <tbody>
                {d.customers.slice(0, 100).map((c: any) => (
                  <tr key={c.customer_key} onClick={() => setCustomer(c)}>
                    <td>{c.customer_name}<small> {c.customer_code}</small></td><td>{c.channel === "b2b" ? "B2B" : "هیبرید"}</td>
                    <td>{toman(c.definite_rial)}</td><td>{toman(c.reliance_rial)}</td><td>{pct(c.reliance_percent)}</td>
                    <td className="neg">{toman(c.collection_risk_rial)}</td><td>{c.nearest_due_date_jalali}</td><td>{fa(c.resolved_history_count)} چک</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {customer && <CustomerModal customer={customer} close={() => setCustomer(null)} />}
      </>}
    </State>
  );
}

function CustomerModal({ customer, close }: { customer: any; close: () => void }) {
  const ref = customer.customer_key.split(":").slice(1).join(":");
  const { data, error, loading } = useLiquidity(`/received-cheques/customers/${customer.system}/${encodeURIComponent(ref)}`, 0);
  const d = data?.data;
  return (
    <div className="fd-backdrop" onClick={close}>
      <article className="lq-modal" onClick={(e) => e.stopPropagation()}>
        <button onClick={close}>×</button>
        <h2>{customer.customer_name}</h2>
        <State loading={loading} error={error}>
          {d && <>
            <p>باز: قطعی {toman(d.open.definite_rial)} · اتکا {toman(d.open.reliance_rial)} · معوق {toman(d.overdue.definite_rial)} تومان</p>
            <div className="fd-table"><table>
              <thead><tr><th>سریال</th><th>سررسید</th><th>مبلغ</th><th>اتکا</th><th>نگهداری</th><th>دلایل کسر اتکا</th></tr></thead>
              <tbody>{d.cheques.map((c: any) => (
                <tr key={c.cheque_id}><td>{c.serial_number}</td><td>{c.due_date_jalali}</td><td>{toman(c.amount_rial)}</td>
                  <td>{pct(c.reliance_percent)}</td><td>{c.holding_label || c.holding}</td>
                  <td className="lq-reasons">{(c.reliance_reasons || c.reasons || []).map((r: any, i: number) => <span key={i}>{typeof r === "string" ? r : r.label || r.reason || JSON.stringify(r)}</span>)}</td></tr>
              ))}</tbody>
            </table></div>
          </>}
        </State>
      </article>
    </div>
  );
}

// ------------------------------------------------------------------ issued cheques

function IssuedSection({ channel, horizon, reloadKey }: { channel: Channel; horizon: number; reloadKey: number }) {
  const { data, error, loading } = useLiquidity(`/issued-cheques?channel=${channel}&horizon_days=${horizon}`, reloadKey);
  const [showReview, setShowReview] = useState(false);
  const d = data?.data;
  return (
    <State loading={loading && !d} error={error}>
      {d && <>
        <Warnings items={data.warnings} />
        <div className="fd-kpis">
          <Kpi label={`تعهد ${fa(horizon)} روز`} value={`${toman(d.kpis.horizon.amount_rial)} تومان`} note={`${fa(d.kpis.horizon.count)} چک`} tone="red" />
          <Kpi label="معوق (تا ۲۰ روز، روی امروز)" value={`${toman(d.kpis.overdue.amount_rial)} تومان`} note={`${fa(d.kpis.overdue.count)} چک`} tone="amber" />
          <Kpi label="۷ روز آینده" value={`${toman(d.kpis.next_7_days.amount_rial)} تومان`} />
          <Kpi label="پیک روزانه" value={d.kpis.peak_day ? `${toman(d.kpis.peak_day.amount_rial)} تومان` : "—"} note={d.kpis.peak_day?.date_jalali} />
        </div>
        <div className="fd-grid">
          <section className="fd-panel lq-review">
            <div className="fd-heading"><h2>نیازمند بررسی وضعیت</h2><p>{d.needs_status_review.rule}</p></div>
            <p className="lq-big">{toman(d.needs_status_review.amount_rial)} تومان · {fa(d.needs_status_review.count)} چک</p>
            <table className="lq-table"><tbody>
              {d.needs_status_review.age_buckets.map((b: any) => <tr key={b.label}><td>{b.label}</td><td className="num">{toman(b.amount_rial)}</td><td className="num">{fa(b.count)} چک</td></tr>)}
            </tbody></table>
            <button className="lq-link" onClick={() => setShowReview(!showReview)}>{showReview ? "بستن فهرست" : "فهرست چک‌ها"}</button>
          </section>
          <section className="fd-panel">
            <div className="fd-heading"><h2>ذی‌نفعان اصلی بازه</h2><p>ده ذی‌نفع بزرگ در معوق و بازه؛ چک‌های سهامداران درون‌شرکتی است و اینجا نیست.</p></div>
            <table className="lq-table"><tbody>
              {d.top_payees.map((p: any) => <tr key={`${p.payee_code}-${p.payee_name}`}><td>{p.payee_name}</td><td className="num">{toman(p.amount_rial)}</td><td className="num">{fa(p.count)} چک</td></tr>)}
            </tbody></table>
          </section>
        </div>
        {showReview && (
          <section className="fd-panel"><div className="fd-table"><table>
            <thead><tr><th>ذی‌نفع</th><th>سریال</th><th>سررسید</th><th>تأخیر</th><th>مبلغ</th><th>بانک</th></tr></thead>
            <tbody>{d.needs_status_review.cheques.slice(0, 300).map((c: any) => (
              <tr key={c.cheque_id}><td>{c.payee_name}</td><td>{c.serial_number}</td><td>{c.due_date_jalali}</td><td>{fa(-c.days_to_due)} روز</td><td>{toman(c.amount_rial)}</td><td>{c.bank_name} {c.account_number}</td></tr>
            ))}</tbody>
          </table></div></section>
        )}
        {d.own_account_transfers?.count > 0 && (
          <section className="fd-panel">
            <div className="fd-heading"><h2>انتقال بین حساب‌های خود شرکت (خروجی نیست)</h2><p>{d.own_account_transfers.rule}</p></div>
            <p className="lq-big">{toman(d.own_account_transfers.amount_rial)} تومان · {fa(d.own_account_transfers.count)} چک باز</p>
            <div className="fd-table"><table>
              <thead><tr><th>سیستم</th><th>از حساب</th><th>در وجه</th><th>سریال</th><th>سررسید</th><th>مبلغ</th></tr></thead>
              <tbody>{d.own_account_transfers.cheques.map((c: any) => (
                <tr key={c.cheque_id}><td>{c.system === "rahkaran" ? "راهکاران" : "کارآمد"}</td><td>{c.bank_name} {c.account_number || ""}</td><td>{c.payee_name}</td>
                  <td>{c.serial_number}</td><td>{c.due_date_jalali}{c.days_to_due < 0 && <small> ({fa(-c.days_to_due)} روز گذشته)</small>}</td><td>{toman(c.amount_rial)}</td></tr>
              ))}</tbody>
            </table></div>
          </section>
        )}
        <section className="fd-panel">
          <div className="fd-heading"><h2>تعهد چک به تفکیک حساب بانکی</h2><p>هر ردیف یک حساب بانکی است: چقدر چک از آن حساب باید پاس شود (معوق، ۷، ۳۰ و ۹۰ روز آینده). حساب‌های شخصی سهامداران با «شخصی» مشخص شده‌اند.</p></div>
          <div className="fd-table"><table>
            <thead><tr><th>بانک / حساب</th><th>معوق</th><th>۷ روز</th><th>۳۰ روز</th><th>۹۰ روز</th></tr></thead>
            <tbody>{d.by_bank_account.map((a: any) => (
              <tr key={a.bank_account_key}>
                <td>{a.bank_name} {a.account_number}<small> {a.system === "rahkaran" ? "راهکاران" : "کارآمد"}</small>{a.personal_account && <span className="fd-badge danger lq-tag">شخصی</span>}</td>
                <td>{toman(a.overdue_rial)}</td><td>{toman(a.next_7_days_rial)}</td><td>{toman(a.next_30_days_rial)}</td><td>{toman(a.next_90_days_rial)}</td>
              </tr>
            ))}</tbody>
          </table></div>
        </section>
      </>}
    </State>
  );
}

// ------------------------------------------------------------------ inflows / outflows

function FlowsSection({ channel, baseDays, reloadKey }: { channel: Channel; baseDays: number; reloadKey: number }) {
  const inflows = useLiquidity(`/inflows?channel=${channel}&base_days=${baseDays}`, reloadKey);
  const outflows = useLiquidity(`/outflows?channel=${channel}&base_days=${baseDays}`, reloadKey);
  const i = inflows.data?.data, o = outflows.data?.data;
  const change = (group: string) => o?.categories.find((c: any) => c.category === group)?.month_comparison.change_percent;
  return (
    <State loading={(inflows.loading || outflows.loading) && !(i && o)} error={inflows.error || outflows.error}>
      {i && o && <>
        <Warnings items={[...(inflows.data.warnings || []), ...(outflows.data.warnings || [])]} />
        <div className="fd-kpis">
          <Kpi label={`ورودی از مشتری (${fa(i.base_period.days)} روز)`} value={`${toman(i.breakdown.total_rial)} تومان`} note={`${i.base_period.from_jalali} تا ${i.base_period.to_jalali}`} />
          <Kpi label={`خروجی (${fa(o.base_period.days)} روز)`} value={`${toman(o.breakdown.total_rial)} تومان`} tone="red" />
          <Kpi label="میانگین ورودی روز کاری" value={`${toman(i.forecast_basis.daily_working_rial)} تومان`} note={`مبنای پیش‌بینی · میانه ${toman(i.forecast_basis.median_daily_rial)}`} tone="blue" />
          <Kpi label="میانگین خروجی روز کاری" value={`${toman(o.forecast_basis.daily_working_rial)} تومان`} note={`مبنای پیش‌بینی · میانه ${toman(o.forecast_basis.median_daily_rial)}`} tone="amber" />
        </div>
        <section className="fd-panel">
          <div className="fd-heading"><h2>ورودی: وصول از مشتری</h2><p>{i.rule}</p></div>
          <FlowTable breakdown={i.breakdown} channel={channel} totalLabel="جمع ورودی" />
          <div className="fd-heading"><h2>الگوی روز هفته (میانگین وصول از مشتری)</h2></div>
          <WeekdayBars items={i.weekday_pattern} />
        </section>
        <section className="fd-panel">
          <div className="fd-heading"><h2>خروجی به تفکیک مقصد</h2><p>{o.rule}</p></div>
          <FlowTable breakdown={o.breakdown} channel={channel} totalLabel="جمع خروجی"
            change={{ title: `${o.month_comparison.month} نسبت به ${o.month_comparison.previous_month}`, of: change }} />
        </section>
      </>}
    </State>
  );
}

const SYSTEM_LABELS: Record<string, string> = { rahkaran: "راهکاران", karamad: "کارآمد" };

/** One row per group (customer collections, imports, suppliers, …); a click opens the accounts behind it. */
function FlowTable({ breakdown, channel, totalLabel, change }: {
  breakdown: any; channel: Channel; totalLabel: string;
  change?: { title: string; of: (group: string) => number | null | undefined };
}) {
  const [open, setOpen] = useState<string | null>(null);
  const both = channel === "all";
  const columns = 5 + (both ? 2 : 0) + (change ? 1 : 0);
  return (
    <div className="lq-scroll"><table className="lq-table lq-flow">
      <thead><tr>
        <th>دسته</th>{both && <><th>راهکاران</th><th>کارآمد</th></>}<th>حواله</th><th>نقد</th><th>جمع</th><th>سهم</th>
        {change && <th>{change.title}</th>}
      </tr></thead>
      <tbody>
        {breakdown.items.map((g: any) => <FlowRows key={g.group} g={g} both={both} columns={columns} change={change}
          open={open === g.group} onToggle={() => setOpen(open === g.group ? null : g.group)} />)}
        <tr className="total">
          <td>{totalLabel}</td>
          {both && <><td className="num">{toman(sum(breakdown.items, "rahkaran_rial"))}</td><td className="num">{toman(sum(breakdown.items, "karamad_rial"))}</td></>}
          <td className="num">{toman(sum(breakdown.items, "bank_rial"))}</td><td className="num">{toman(sum(breakdown.items, "cash_rial"))}</td>
          <td className="num">{toman(breakdown.total_rial)}</td><td />{change && <td />}
        </tr>
      </tbody>
      <caption className="lq-rule">همین ارقام مبنای میانگین روز کاری و پیش‌بینی است. روی هر دسته بزنید تا حساب‌هایش را ببینید.</caption>
    </table></div>
  );
}

function FlowRows({ g, both, columns, change, open, onToggle }: {
  g: any; both: boolean; columns: number; open: boolean; onToggle: () => void;
  change?: { of: (group: string) => number | null | undefined };
}) {
  return <>
    <tr className={`lq-flow-row${open ? " sel" : ""}`} onClick={onToggle}>
      <td className="lq-flow-label">{open ? "▾" : "◂"} {g.label}
        <small>{fa(g.row_count)} ردیف</small></td>
      {both && <><td className="num">{toman(g.rahkaran_rial)}</td><td className="num">{toman(g.karamad_rial)}</td></>}
      <td className="num">{toman(g.bank_rial)}</td><td className="num">{toman(g.cash_rial)}</td>
      <td className="num"><b>{toman(g.total_rial)}</b></td><td className="num">{pct(g.share_percent)}</td>
      {change && <td className="num">{pct(change.of(g.group))}</td>}
    </tr>
    {open && <tr className="lq-flow-sources"><td colSpan={columns}>
      {g.sources.map((s: any, n: number) => (
        <div key={n}>
          <span>{SYSTEM_LABELS[s.system] || s.system} · {s.account_code || "بدون حساب"} {s.account_name || ""}</span>
          <b>{toman(s.amount_rial)}</b>
        </div>
      ))}
      {g.other_sources_rial != null && <div><span>سایر حساب‌ها و طرف‌حساب‌ها</span><b>{toman(g.other_sources_rial)}</b></div>}
    </td></tr>}
  </>;
}

const sum = (items: any[], key: string) => items.reduce((a, x) => a + Number(x[key] || 0), 0);

function WeekdayBars({ items }: { items: any[] }) {
  const max = Math.max(1, ...items.map((x) => x.average_rial));
  return <div className="lq-bars">{items.map((x) => (
    <div key={x.weekday}><i style={{ height: `${(x.average_rial / max) * 100}%` }} title={toman(x.average_rial)} /><small>{x.label}</small></div>
  ))}</div>;
}

// ------------------------------------------------------------------ payroll

function PayrollSection({ reloadKey }: { reloadKey: number }) {
  const { data, error, loading } = useLiquidity(`/payroll`, reloadKey);
  const [selected, setSelected] = useState("zarin");
  const d = data?.data;
  const companies: any[] = d?.companies || [];
  const company = companies.find((c) => c.key === selected) || companies[0];
  // The group total only makes sense for a month every company has finished; companies can
  // be on different months (e.g. Rahkaran recalculating while Karamad is already closed).
  const monthly: any[] = d?.by_company_monthly || [];
  const latestRow = [...monthly].reverse().find((r) => companies.every((c) => r.companies[c.key] != null))
    ?? monthly[monthly.length - 1];
  const behind = companies.filter((c) => c.latest_month && latestRow && c.latest_month.month !== latestRow.month);
  const isZarin = company?.key === "zarin";
  return (
    <State loading={loading && !d} error={error}>
      <Warnings items={data?.warnings} />
      {d && d.kpis && <>
        {latestRow && (
          <section className="fd-panel lq-pay-summary">
            <div className="lq-pay-total">
              <small>جمع حقوق گروه · {latestRow.month}</small>
              <b>{fullToman(latestRow.total_rial)}<span>تومان</span></b>
              <em>{fa(latestRow.headcount)} نفر · خالص + بیمه سهم کارفرما</em>
              {behind.length > 0 && <em className="lq-unverified">آخرین ماه کامل هر شرکت روی کارت خودش است: {behind.map((c) => `${c.label} ${c.latest_month.month}`).join("، ")}</em>}
            </div>
            <div className="lq-pay-share">
              <div className="lq-share-bar">
                {companies.filter((c) => latestRow.companies[c.key]).map((c) => (
                  <i key={c.key} title={c.label} style={{ width: `${(latestRow.companies[c.key] / latestRow.total_rial) * 100}%`, background: PAYROLL_COLORS[c.key] }} />
                ))}
              </div>
              <div className="lq-share-legend">
                {companies.filter((c) => latestRow.companies[c.key]).map((c) => (
                  <span key={c.key}><i style={{ background: PAYROLL_COLORS[c.key] }} />{c.label}
                    <b>{nf.format(Math.round((latestRow.companies[c.key] / latestRow.total_rial) * 100))}٪</b></span>
                ))}
              </div>
            </div>
          </section>
        )}

        <div className="lq-pay-cards">
          {companies.map((c) => {
            const m = c.latest_month;
            if (!m) return null;
            const change = c.total_change_percent;
            const rows: [string, number][] = c.key === "zarin"
              ? [["حقوق پایه", m.base_pay_rial], ["پورسانت", m.commission_rial], ["بیمه سهم کارفرما", m.insurance_rial]]
              : [["خالص", m.net_pay_rial], ["بیمه سهم کارفرما", m.insurance_rial]];
            return (
              <button key={c.key} className={`lq-pay-card ${c.key === company?.key ? "active" : ""}`} onClick={() => setSelected(c.key)}
                style={{ ["--accent" as any]: PAYROLL_COLORS[c.key] }}>
                <header><span>{c.label}</span><small>{c.system === "karamad" ? "کارآمد" : "راهکاران"} · {m.month}</small></header>
                <b>{fullToman(m.total_rial)}<span>تومان</span></b>
                <div className="lq-pay-meta">
                  <span>{fa(m.headcount)} نفر</span>
                  {change != null && <span className={change > 0 ? "up" : change < 0 ? "down" : ""}>{change > 0 ? "▲" : change < 0 ? "▼" : ""} {nf1.format(Math.abs(change))}٪</span>}
                </div>
                <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{fullToman(value)}</dd></div>)}</dl>
              </button>
            );
          })}
        </div>

        <section className="fd-panel">
          <div className="fd-heading"><h2>حقوق ماه‌به‌ماه به تفکیک شرکت</h2><p>جمع کل هر شرکت (خالص + بیمه سهم کارفرما)، فقط ماه‌های کامل. مبالغ به تومان.</p></div>
          <div className="fd-table"><table>
            <thead><tr><th>ماه</th>{companies.map((c) => <th key={c.key}>{c.label}</th>)}<th>جمع گروه</th></tr></thead>
            <tbody>{[...d.by_company_monthly].reverse().map((row: any) => (
              <tr key={row.month}><td>{row.month}</td>
                {companies.map((c) => <td key={c.key} className="num">{row.companies[c.key] == null ? "—" : fullToman(row.companies[c.key])}</td>)}
                <td className="num"><b>{fullToman(row.total_rial)}</b></td></tr>
            ))}</tbody>
          </table></div>
          <Rule text={d.rule} />
        </section>

        {company && (
          <section className="fd-panel">
            <div className="lq-panel-head">
              <div className="fd-heading"><h2>جزئیات ماهانه: {company.label}</h2>
                <p>{isZarin ? "از حقوق کارآمد. پورسانت = «اضافات» فیش حقوق هر ماه (عمدتاً ویزیتورها و سرپرستان فروش)؛ حقوق پایه ثابت است و نوسان از پورسانت می‌آید." : "از راهکاران، به تفکیک کارگاه بیمه هر کارمند در همان ماه."} مبالغ به تومان.</p></div>
              <div className="lq-seg">{companies.map((c) => <button key={c.key} className={c.key === company.key ? "active" : ""} onClick={() => setSelected(c.key)}>{c.label}</button>)}</div>
            </div>
            <div className="fd-table"><table>
              <thead><tr><th>ماه</th><th>نفرات</th>{isZarin && <><th>حقوق پایه</th><th>پورسانت (اضافات)</th></>}<th>خالص پرداختی</th><th>بیمه سهم کارفرما</th><th>جمع کل</th></tr></thead>
              <tbody>{[...company.monthly_trend].reverse().map((m: any) => (
                <tr key={m.month}><td>{m.month}</td><td>{fa(m.headcount)}</td>
                  {isZarin && <><td className="num">{fullToman(m.base_pay_rial)}</td><td className="num pos">{fullToman(m.commission_rial)}</td></>}
                  <td className="num">{fullToman(m.net_pay_rial)}</td><td className="num">{fullToman(m.insurance_rial)}</td><td className="num"><b>{fullToman(m.total_rial)}</b></td></tr>
              ))}</tbody>
            </table></div>
          </section>
        )}
      </>}
    </State>
  );
}

// ------------------------------------------------------------------ page

export default function LiquidityPage() {
  const [channel, setChannel] = useState<Channel>("all");
  const [period, setPeriod] = useState(30);
  const [section, setSection] = useState<Section>("forecast");
  const [reloadKey, setReloadKey] = useState(0);
  const today = useMemo(() => new Intl.DateTimeFormat("fa-IR-u-ca-persian", { dateStyle: "long" }).format(new Date()), []);
  return (
    <div className="lq-page">
      <header className="lq-header">
        <div className="fd-heading">
          <h2>مدیریت نقدینگی</h2>
          <p>{today} · مبالغ به تومان</p>
        </div>
        <div className="lq-toolbar">
          <div className="lq-seg">{CHANNELS.map(([k, label]) => <button key={k} className={channel === k ? "active" : ""} onClick={() => setChannel(k)}>{label}</button>)}</div>
          {(FORWARD_SECTIONS.includes(section) || HISTORY_SECTIONS.includes(section)) && (
            <div className="lq-field">
              <small>بازه: {fa(period)} روز {FORWARD_SECTIONS.includes(section) ? "آینده" : "گذشته"}</small>
              <div className="lq-seg">{PERIODS.map((d) => <button key={d} className={period === d ? "active" : ""} onClick={() => setPeriod(d)}>{fa(d)} روز</button>)}</div>
            </div>
          )}
          <button className="run" onClick={() => setReloadKey((k) => k + 1)}>↻ بروزرسانی</button>
        </div>
      </header>
      <div className="lq-tabs" role="tablist">{SECTIONS.map(([k, label]) => <button key={k} className={section === k ? "active" : ""} onClick={() => setSection(k)}>{label}</button>)}</div>
      {section === "forecast" && <ForecastSection channel={channel} horizon={period} baseDays={FORECAST_BASE_DAYS} reloadKey={reloadKey} />}
      {section === "received" && <ReceivedSection channel={channel} horizon={period} reloadKey={reloadKey} />}
      {section === "issued" && <IssuedSection channel={channel} horizon={period} reloadKey={reloadKey} />}
      {section === "flows" && <FlowsSection channel={channel} baseDays={period} reloadKey={reloadKey} />}
      {section === "payroll" && <PayrollSection reloadKey={reloadKey} />}
    </div>
  );
}
