"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import "./functional.css";
import "./enterprise.css";
import "./operations.css";
import "./cheque-remaining.css";
import "./visual-dashboard.css";
import "./monthly-excel.css";
import "./agent.css";
import "./readability-fix.css";
import "./customer-reliability.css";
import "./font-size-v36.css";
import "./drilldown.css";
import "./folder-automation.css";
import "./reliance-explanation.css";
import "./excel-viewer.css";
import "./command-center-3d.css";
import "./cash-bank-movements.css";

type View =
  | "management"
  | "customers"
  | "cheques"
  | "receivedCheques"
  | "issuedCheques"
  | "cashflow"
  | "cashBank"
  | "monthlyExcel"
  | "collections"
  | "representatives"
  | "simulator"
  | "alerts"
  | "history"
  | "performance"
  | "settings"
  | "agents";
type AgentContent =
  string | number | Record<string, unknown> | null | undefined;
type Analysis = {
  headline?: AgentContent;
  summary?: AgentContent;
  human_summary?: AgentContent;
  management_status?: string;
  good_signals?: AgentContent[];
  risks?: AgentContent[];
  bad_signals?: AgentContent[];
  future_outlook?: AgentContent;
  prediction?: any;
  scenarios?: any;
  recommended_actions?: Action[];
  decisions_today?: AgentContent[];
  seven_day_plan?: AgentContent[];
  next_best_action?: AgentContent;
  executive_kpis?: Array<{
    label: string;
    value?: number | null;
    value_rial?: number | null;
    format: string;
    tone?: string;
    available?: boolean;
  }>;
};
type Action = {
  action?: string;
  why?: string;
  expected_effect?: string;
  owner?: string;
  priority?: string;
  deadline?: string;
};
type CustomerAudit = Customer & {
  counterpart_code?: string;
  source_row_count?: number;
  distinct_cheque_count?: number;
  repeated_source_row_count?: number;
  historical_cheque_count?: number;
  overdue_open_cheque_count?: number;
  other_state_cheque_count?: number;
  other_state_cheque_amount?: number;
};
type AgentResult = {
  metadata?: {
    agent_name?: string;
    mode?: string;
    agent_mode?: string;
    model?: string;
    fallback_used?: boolean;
  };
  analysis?: Analysis;
  rule_output?: any;
};
type Customer = {
  counterpart_ref?: number;
  counterpart_name?: string;
  customer_name?: string;
  risk_score?: number;
  risk_level?: string;
  current_overdue_open_ratio_percent?: number;
  open_exposure?: number;
  overdue_open_amount?: number;
  over_policy_count?: number;
  outside_policy_count?: number;
  historical_total_cheque_amount?: number;
  historical_average_cheque_amount?: number;
  historical_cheque_count?: number;
  collected_cheque_amount?: number;
  collected_cheque_count?: number;
  returned_cheque_amount?: number;
  returned_cheque_count?: number;
  open_cheque_count?: number;
  open_cheques?: Cheque[];
  late_payment_risk?: { value?: number; reasons?: string[] };
  cheque_return_probability?: { value?: number };
  collection_forecast?: { expected_collection_amount?: number };
  customer_behavior?: {
    reliability_score?: number;
    behavior_level?: string;
    historical_collection_rate_percent?: number;
    historical_return_rate_percent?: number;
    resolved_cheque_count?: number;
    open_overdue_ratio_percent?: number;
    history_confidence?: string;
  };
  credit_decision?: {
    policy?: string;
    recommended_reliance_percent?: number;
    recommended_max_new_cheque_amount_rial?: number;
    requires_human_approval?: boolean;
    reasons?: string[];
  };
  evidence?: string[];
};
type Cheque = {
  cheque_id?: number;
  serial_number?: string;
  sayad_number?: string;
  document_number?: number | string;
  counterpart_name?: string;
  amount?: number;
  receipt_date_jalali?: string;
  receipt_date?: string;
  due_date_jalali?: string;
  due_date?: string;
  term_days?: number;
  days_to_due?: number;
  days_overdue?: number;
  due_status?: string;
  state_label?: string;
  estimated_return_probability_percent?: number;
  risk_level?: string;
  reasons?: string[];
};
type CashDay = {
  date?: string;
  date_jalali?: string;
  projected_inflow?: number;
  projected_outflow?: number;
  daily_net_change?: number;
  cumulative_net_change?: number;
  projected_cash?: number | null;
  cash_shortage?: boolean;
};
type Rep = {
  representative_id?: string;
  representative_name?: string;
  customer_count?: number;
  high_risk_customer_count?: number;
  open_exposure?: number;
  overdue_open_amount?: number;
  average_risk_score?: number;
  status?: string;
  human_analysis?: string;
};
type Alert = {
  alert_id: string;
  level?: string;
  title?: string;
  status?: string;
  assignee?: string;
  payload?: {
    description?: string;
    reason?: string;
    recommended_action?: string;
  };
};
type TreasuryCheque = Cheque & {
  document_date?: string;
  bank_name?: string;
  branch_name?: string;
  description?: string;
  counterpart_ref?: number;
  cheque_item_id?: number;
};
type Case = {
  case_id: string;
  counterpart_ref?: number;
  counterpart_name: string;
  status: string;
  priority: string;
  assignee?: string;
  due_at?: string;
  followups?: any[];
  promises?: any[];
};
type Pack = {
  status?: string;
  generated_at?: string;
  agents?: Record<string, AgentResult>;
  management_summary?: AgentResult;
  data?: {
    customer?: { customers?: Customer[] };
    cheques?: { cheques?: Cheque[] };
    cashflow?: {
      timeline?: CashDay[];
      negative_cash_pressure_days?: number;
      first_predicted_shortage_date_jalali?: string;
    };
    collections?: any;
    representatives?: {
      representatives?: Rep[];
      unmapped_customer_count?: number;
    };
  };
  policies?: Record<string, any>;
};
type InsightRecord = {
  name: string;
  number: string;
  amount: string;
  due: string;
  timing: string;
};
type InsightPayload = {
  title: string;
  subtitle?: string;
  stats: { label: string; value: string }[];
  notes?: string[];
  records?: InsightRecord[];
  tone?: string;
};

const openInsight = (payload: InsightPayload) => {
  if (typeof window !== "undefined")
    window.dispatchEvent(new CustomEvent("exir:insight", { detail: payload }));
};

function InsightCenter() {
  const [item, setItem] = useState<InsightPayload | null>(null);
  useEffect(() => {
    const listener = (event: Event) =>
      setItem((event as CustomEvent<InsightPayload>).detail);
    window.addEventListener("exir:insight", listener);
    return () => window.removeEventListener("exir:insight", listener);
  }, []);
  if (!item) return null;
  return (
    <div className="insight-backdrop" onClick={() => setItem(null)}>
      <article
        className={`insight-modal ${item.tone || "blue"}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button aria-label="بستن" onClick={() => setItem(null)}>
          ×
        </button>
        <header>
          <small>جزئیات آماری</small>
          <h2>{item.title}</h2>
          {item.subtitle && <p>{item.subtitle}</p>}
        </header>
        <section>
          {item.stats.map((x, i) => (
            <div key={i}>
              <small>{x.label}</small>
              <b>{x.value}</b>
            </div>
          ))}
        </section>
        {item.records?.length ? (
          <div className="insight-records">
            <h3>ریز موارد این گزارش</h3>
            <div>
              <table>
                <thead>
                  <tr>
                    <th>طرف حساب</th>
                    <th>شماره چک</th>
                    <th>مبلغ</th>
                    <th>سررسید</th>
                    <th>وضعیت زمانی</th>
                  </tr>
                </thead>
                <tbody>
                  {item.records.map((x, i) => (
                    <tr key={i}>
                      <td>
                        <b>{x.name}</b>
                      </td>
                      <td>{x.number}</td>
                      <td>{x.amount}</td>
                      <td>{x.due}</td>
                      <td>{x.timing}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {item.records.length >= 50 && (
              <small>برای خوانایی، ۵۰ مورد اول نمایش داده شده است.</small>
            )}
          </div>
        ) : null}
        {item.notes?.length ? (
          <ul>
            {item.notes.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : null}
        <footer>
          اطلاعات براساس آخرین اجرای اتوماسیون و داده‌های دریافت‌شده از SQL
          Server است.
        </footer>
      </article>
    </div>
  );
}

const apiHost = () =>
  typeof window !== "undefined" ? window.location.hostname : "127.0.0.1";
const API = () => `http://${apiHost()}:8000/api/v1/finance`;
const TREASURY_API = () => `http://${apiHost()}:8000/api/v1/treasury`;
const fa = (v: number = 0) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 }).format(v);
// تمام مبالغ Backend بر حسب ریال هستند. تنها نقطه تبدیل رابط کاربری همین
// تابع است تا هیچ کارت یا نموداری ریال و تومان را با هم مخلوط نکند.
const money = (rial: number = 0) => {
  const toman = Number(rial || 0) / 10,
    abs = Math.abs(toman);
  return abs >= 1e12
    ? `${fa(toman / 1e12)} همت`
    : abs >= 1e9
      ? `${fa(toman / 1e9)} میلیارد`
      : abs >= 1e6
        ? `${fa(toman / 1e6)} میلیون`
        : fa(toman);
};
const fieldFa: Record<string, string> = {
  customers_requiring_review: "مشتریان نیازمند بررسی",
  payment_capacity_percent: "توان پوشش پرداخت",
  latest_obligations_rial: "تعهدات نزدیک",
  estimated_payment_capacity_percent: "توان پوشش پایان ماه",
  actual_payment_rate_to_date_percent: "نرخ پرداخت قطعی تا امروز",
  inflow: "ورودی نقد",
  outflow: "خروجی نقد",
  projected_inflow: "ورودی پیش‌بینی‌شده",
  projected_outflow: "خروجی پیش‌بینی‌شده",
  net_change: "خالص تغییر نقدینگی",
  expected_collection_amount: "وصول مورد انتظار",
  open_exposure: "چک‌های دریافتی باز",
  top_customer_count: "مشتریان اولویت‌دار",
  risk_direction: "جهت ریسک",
  first_shortage: "اولین کسری",
  assumption: "فرض سناریو",
  collection_multiplier: "ضریب وصول",
  due_cheque_count: "تعداد چک سررسیدشونده",
  due_cheque_amount_rial: "مبلغ چک‌های سررسیدشونده",
  high_risk_cheque_count: "چک پرریسک",
  risk_adjusted_collectible_amount_rial: "وصول تعدیل‌شده",
  processed_cheque_count: "چک بررسی‌شده",
  high_risk_count: "چک ریسک بالا",
  over_policy_count: "بیشتر از ۹۰ روز",
  high_risk_open_amount_rial: "مبلغ پرریسک",
  management_action: "اقدام مدیریتی",
};
const textOf = (value: unknown, key = ""): string => {
  if (value == null) return "";
  if (typeof value === "number") {
    if (key.includes("percent") || key.includes("rate")) return `${fa(value)}٪`;
    if (
      key.includes("rial") ||
      key.includes("amount") ||
      [
        "inflow",
        "outflow",
        "projected_inflow",
        "projected_outflow",
        "net_change",
        "open_exposure",
      ].includes(key)
    )
      return `${money(value)} تومان`;
    return fa(value);
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value))
    return value
      .map((x) => textOf(x))
      .filter(Boolean)
      .join("؛ ");
  if (typeof value === "object") {
    const row = value as Record<string, unknown>;
    if (row.summary) {
      const summary = textOf(row.summary),
        assumption = textOf(row.assumption);
      return assumption ? `${summary}؛ فرض: ${assumption}` : summary;
    }
    const action = textOf(row.action ?? row.text ?? row.message),
      why = textOf(row.why ?? row.reason ?? row.explanation);
    if (action && why && action !== why) return `${action} — ${why}`;
    if (action || why || row.value) return action || why || textOf(row.value);
    return Object.entries(row)
      .filter(([k]) => k !== "title")
      .slice(0, 5)
      .map(
        ([k, v]) => `${fieldFa[k] || k.replaceAll("_", " ")}: ${textOf(v, k)}`,
      )
      .join(" • ");
  }
  return String(value);
};
const cname = (c: Customer) =>
  c.counterpart_name || c.customer_name || "مشتری نامشخص";
const policy = (c: Customer) =>
  c.over_policy_count ?? c.outside_policy_count ?? 0;
const risk = (c: Customer) => {
  const score = c.risk_score ?? c.late_payment_risk?.value ?? 0;
  const severeEvidence =
    policy(c) >= 10 || (c.current_overdue_open_ratio_percent || 0) >= 60;
  return score >= 85 && severeEvidence
    ? "critical"
    : score >= 40 || policy(c) >= 3
      ? "danger"
      : "safe";
};
const daysToDue = (c: Cheque) => {
  if (typeof c.days_to_due === "number") return c.days_to_due;
  if (!c.due_date) return undefined;
  const raw = String(c.due_date).slice(0, 10),
    target = new Date(`${raw}T00:00:00`),
    today = new Date();
  today.setHours(0, 0, 0, 0);
  return Number.isNaN(target.getTime())
    ? undefined
    : Math.ceil((target.getTime() - today.getTime()) / 86400000);
};
const remainingLabel = (c: Cheque) => {
  const d = daysToDue(c);
  return d === undefined
    ? "زمان باقی‌مانده نامشخص"
    : d < 0
      ? `${fa(Math.abs(d))} روز از سررسید گذشته`
      : d === 0
        ? "سررسید امروز"
        : `${fa(d)} روز تا سررسید`;
};
const chequeInsightRows = (rows: TreasuryCheque[]): InsightRecord[] =>
  [...rows]
    .sort(
      (a, b) =>
        (daysToDue(a) ?? Number.POSITIVE_INFINITY) -
        (daysToDue(b) ?? Number.POSITIVE_INFINITY),
    )
    .slice(0, 50)
    .map((x) => ({
      name: x.counterpart_name || "طرف حساب نامشخص",
      number: String(
        x.serial_number || x.document_number || x.cheque_id || "—",
      ),
      amount: `${money(x.amount || 0)} تومان`,
      due: x.due_date_jalali || String(x.due_date || "—").slice(0, 10),
      timing: remainingLabel(x),
    }));
function ChequeHub({
  received,
  issued,
  error,
  open,
}: {
  received: TreasuryCheque[];
  issued: TreasuryCheque[];
  error: string;
  open: (v: View) => void;
}) {
  const card = (kind: "received" | "issued", rows: TreasuryCheque[]) => {
    const incoming = kind === "received",
      total = rows.reduce((s, x) => s + (x.amount || 0), 0),
      overdue = rows.filter((x) => (daysToDue(x) ?? 1) < 0),
      month = rows.filter((x) => {
        const d = daysToDue(x);
        return d !== undefined && d >= 0 && d <= 30;
      }),
      over90 = rows.filter((x) => (x.term_days || 0) > 90);
    return (
      <button
        className={`cheque-flow-card ${incoming ? "received" : "issued"}`}
        onClick={() => open(incoming ? "receivedCheques" : "issuedCheques")}
      >
        <header>
          <span className="flow-icon">{incoming ? "↓" : "↑"}</span>
          <div>
            <small>{incoming ? "ورودی خزانه" : "خروجی خزانه"}</small>
            <h2>{incoming ? "چک‌های دریافتی" : "چک‌های پرداختی / صادرشده"}</h2>
            <p>
              {incoming
                ? "مطالبات، وصول، برگشتی و ریسک مشتری"
                : "تعهدات، پرداخت آینده و فشار نقدینگی"}
            </p>
          </div>
          <i>مشاهده جزئیات ←</i>
        </header>
        <strong>
          {money(total)} <small>تومان</small>
        </strong>
        <div className="flow-stats">
          <span>
            <b>{fa(rows.length)}</b>
            <small>کل چک‌ها</small>
          </span>
          <span>
            <b>{fa(month.length)}</b>
            <small>تا ۳۰ روز</small>
          </span>
          <span className={overdue.length ? "danger" : ""}>
            <b>{fa(overdue.length)}</b>
            <small>سررسیدگذشته</small>
          </span>
          <span className={over90.length ? "warn" : ""}>
            <b>{fa(over90.length)}</b>
            <small>بیش از ۹۰ روز</small>
          </span>
        </div>
        <div className="flow-bar">
          <i
            style={{
              width: `${rows.length ? (month.length / rows.length) * 100 : 0}%`,
            }}
          />
          <i
            className="late"
            style={{
              width: `${rows.length ? (overdue.length / rows.length) * 100 : 0}%`,
            }}
          />
        </div>
      </button>
    );
  };
  return (
    <>
      <section className="cheque-hub-intro">
        <div>
          <small>مدیریت چک‌ها از کل به جزء</small>
          <h2>ابتدا نوع جریان چک را انتخاب کنید</h2>
          <p>
            هر بخش خلاصه، سررسیدها، ریز چک‌ها و هشدارهای خودش را نشان می‌دهد.
          </p>
        </div>
        <span>SQL Server • خزانه راهکاران</span>
      </section>
      {error && <div className="profile-warning">{error}</div>}
      <section className="cheque-flow-grid">
        {card("received", received)}
        {card("issued", issued)}
      </section>
      <article className="fd-panel cheque-flow-guide">
        <Heading h="مسیر بررسی" p="از تصویر کلان تا ریز هر چک" />
        <div>
          <span>انتخاب دریافتی یا پرداختی</span>
          <i>←</i>
          <span>خلاصه و نمودار سررسید</span>
          <i>←</i>
          <span>ریز چک و روز باقی‌مانده</span>
          <i>←</i>
          <span>هشدار و اقدام پیشنهادی</span>
        </div>
      </article>
    </>
  );
}
function ChequeDetails({
  kind,
  rows,
  agent,
  back,
}: {
  kind: "received" | "issued";
  rows: TreasuryCheque[];
  agent?: AgentResult;
  back: () => void;
}) {
  const incoming = kind === "received";
  const [period, setPeriod] = useState("all");
  const viewRows = incoming
    ? rows.filter((x) => {
        const days = daysToDue(x);
        if (period === "all") return true;
        if (period === "overdue") return days !== undefined && days < 0;
        const horizon =
          period === "1m"
            ? 30
            : period === "3m"
              ? 90
              : period === "6m"
                ? 180
                : 365;
        return days !== undefined && days >= 0 && days <= horizon;
      })
    : rows;
  const sortedRows = [...viewRows].sort(
      (a, b) =>
        (daysToDue(a) ?? Number.POSITIVE_INFINITY) -
        (daysToDue(b) ?? Number.POSITIVE_INFINITY),
    ),
    total = viewRows.reduce((s, x) => s + (x.amount || 0), 0),
    overdue = viewRows.filter((x) => (daysToDue(x) ?? 1) < 0),
    soon = viewRows.filter((x) => {
      const d = daysToDue(x);
      return d !== undefined && d >= 0 && d <= 7;
    }),
    over90 = viewRows.filter((x) => (x.term_days || 0) > 90),
    due = [
      {
        label: "سررسیدگذشته",
        value: overdue.length,
        tone: "red",
        records: chequeInsightRows(overdue),
      },
      {
        label: "تا ۷ روز",
        value: soon.length,
        tone: "amber",
        records: chequeInsightRows(soon),
      },
      {
        label: "۸ تا ۳۰ روز",
        value: viewRows.filter((x) => {
          const d = daysToDue(x);
          return d !== undefined && d > 7 && d <= 30;
        }).length,
        tone: "teal",
        records: chequeInsightRows(
          viewRows.filter((x) => {
            const d = daysToDue(x);
            return d !== undefined && d > 7 && d <= 30;
          }),
        ),
      },
      {
        label: "بعد از ۳۰ روز",
        value: viewRows.filter((x) => (daysToDue(x) ?? -1) > 30).length,
        tone: "violet",
        records: chequeInsightRows(
          viewRows.filter((x) => (daysToDue(x) ?? -1) > 30),
        ),
      },
    ];
  return (
    <>
      <button className="cheque-back" onClick={back}>
        → بازگشت به انتخاب نوع چک
      </button>
      {incoming && (
        <section className="cheque-period-filter">
          <div>
            <b>بازه سررسید چک‌های باز</b>
            <small>چک‌های تضمینی در تمام گزینه‌ها حذف شده‌اند.</small>
          </div>
          {[
            ["all", "همه چک‌های باز"],
            ["overdue", "سررسیدگذشته"],
            ["1m", "یک ماه آینده"],
            ["3m", "سه ماه آینده"],
            ["6m", "شش ماه آینده"],
            ["12m", "دوازده ماه آینده"],
          ].map(([id, title]) => (
            <button
              key={id}
              className={period === id ? "active" : ""}
              onClick={() => setPeriod(id)}
            >
              {title}
            </button>
          ))}
        </section>
      )}
      {incoming && <AgentPanel agent={agent} />}
      <div className="fd-kpis">
        <K
          t={incoming ? "مبلغ چک‌های دریافتی" : "مبلغ چک‌های صادرشده"}
          v={money(total)}
          n="تومان"
          c={incoming ? "teal" : "blue"}
        />
        <K t="تعداد چک" v={fa(viewRows.length)} n="فقره" c="blue" />
        <K
          t="سررسیدگذشته"
          v={fa(overdue.length)}
          n={money(overdue.reduce((s, x) => s + (x.amount || 0), 0)) + " تومان"}
          c="red"
          detail={{
            title: incoming
              ? "چک‌های دریافتی سررسیدگذشته"
              : "چک‌های پرداختی سررسیدگذشته",
            subtitle: "فهرست مواردی که موعد آن‌ها گذشته است",
            tone: "red",
            stats: [
              { label: "تعداد چک", value: fa(overdue.length) },
              {
                label: "مبلغ کل",
                value: `${money(overdue.reduce((s, x) => s + (x.amount || 0), 0))} تومان`,
              },
            ],
            records: chequeInsightRows(overdue),
          }}
        />
        <K
          t="خارج از سیاست ۹۰ روز"
          v={fa(over90.length)}
          n="نیازمند کنترل"
          c="amber"
        />
      </div>
      <section className="cheque-detail-grid">
        <article className="fd-panel visual-card">
          <Heading
            h="توزیع سررسید"
            p={
              incoming
                ? "زمان‌بندی وصول چک‌های دریافتی"
                : "زمان‌بندی پرداخت چک‌های صادرشده"
            }
          />
          <VerticalBars rows={due} />
        </article>
        <article
          className={`fd-panel cheque-side-note ${incoming ? "received" : "issued"}`}
        >
          <small>{incoming ? "Collection View" : "Payment View"}</small>
          <h3>
            {incoming
              ? "اولویت با وصول چک‌های معوق و نزدیک است."
              : "چک‌های نزدیک به سررسید باید در برنامه نقدینگی پوشش داده شوند."}
          </h3>
          <p>
            {incoming
              ? "چک‌های پرریسک و خارج از سیاست ۹۰ روز قبل از پذیرش اعتبار جدید بررسی شوند."
              : "برای روزهای دارای تمرکز پرداخت، موجودی حساب و ورودی‌های قابل اتکا کنترل شود."}
          </p>
          <div>
            <span>{fa(soon.length)} فقره تا ۷ روز</span>
            <span>{fa(overdue.length)} فقره معوق</span>
          </div>
        </article>
      </section>
      <article className="fd-panel">
        <Heading
          h={incoming ? "ریز چک‌های دریافتی" : "ریز چک‌های پرداختی / صادرشده"}
          p="مرتب‌شده از سررسیدگذشته و نزدیک‌ترین موعد به دورترین موعد"
        />
        <div className="cheque-detail-table">
          <table>
            <thead>
              <tr>
                <th>طرف حساب</th>
                <th>شماره سند</th>
                <th>مبلغ</th>
                <th>تاریخ سررسید</th>
                <th>مدت چک</th>
                <th>زمان باقی‌مانده ↑</th>
                <th>بانک / شعبه</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((x, i) => {
                const d = daysToDue(x),
                  state =
                    d !== undefined && d < 0
                      ? "critical"
                      : d !== undefined && d <= 7
                        ? "danger"
                        : "safe";
                return (
                  <tr
                    key={x.cheque_id || x.cheque_item_id || i}
                    className={state}
                  >
                    <td>
                      <b>{x.counterpart_name || "طرف حساب نامشخص"}</b>
                    </td>
                    <td>{x.document_number || "—"}</td>
                    <td>{money(x.amount || 0)} تومان</td>
                    <td>{x.due_date_jalali || x.due_date || "—"}</td>
                    <td>
                      {x.term_days == null ? "—" : `${fa(x.term_days)} روز`}
                    </td>
                    <td>
                      <span
                        className={`profile-due ${state === "critical" ? "late" : state === "danger" ? "soon" : "normal"}`}
                      >
                        {remainingLabel(x)}
                      </span>
                    </td>
                    <td>
                      {[x.bank_name, x.branch_name]
                        .filter(Boolean)
                        .join(" / ") || "—"}
                    </td>
                    <td>
                      <Risk x={state} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!rows.length && (
            <div className="profile-loading">چکی در این بخش پیدا نشد.</div>
          )}
        </div>
      </article>
    </>
  );
}
function CustomerSqlAudit({ c }: { c: CustomerAudit }) {
  const rows = [
    {
      title: "کل چک‌های دریافتی",
      count: c.historical_cheque_count,
      amount: c.historical_total_cheque_amount,
      tone: "blue",
    },
    {
      title: "وصول‌شده قطعی",
      count: c.collected_cheque_count,
      amount: c.collected_cheque_amount,
      tone: "green",
    },
    {
      title: "چک‌های باز",
      count: c.open_cheque_count,
      amount: c.open_exposure,
      tone: "amber",
    },
    {
      title: "بازِ سررسیدگذشته",
      count: c.overdue_open_cheque_count,
      amount: c.overdue_open_amount,
      tone: "red",
    },
    {
      title: "برگشتی / واخواست‌شده",
      count: c.returned_cheque_count,
      amount: c.returned_cheque_amount,
      tone: "red",
    },
    {
      title: "سایر وضعیت‌ها",
      count: c.other_state_cheque_count,
      amount: c.other_state_cheque_amount,
      tone: "violet",
    },
  ];
  return (
    <section className="sql-audit">
      <div className="profile-section-title">
        <div>
          <h3>تطبیق کامل پرونده با SQL</h3>
          <p>تمام ستون‌های گزارش کنترلی؛ تمام مبالغ نمایشی به تومان</p>
        </div>
        <b>CounterPartRef: {fa(c.counterpart_ref)}</b>
      </div>
      <div className="audit-identity">
        <div>
          <small>کد مشتری</small>
          <b>{c.counterpart_code || "—"}</b>
        </div>
        <div>
          <small>نام مشتری</small>
          <b>{cname(c)}</b>
        </div>
        <div>
          <small>تعداد ردیف منبع</small>
          <b>{fa(c.source_row_count)}</b>
        </div>
        <div>
          <small>تعداد چک یکتا</small>
          <b>{fa(c.distinct_cheque_count)}</b>
        </div>
        <div
          className={(c.repeated_source_row_count || 0) > 0 ? "has-repeat" : ""}
        >
          <small>ردیف تکراری</small>
          <b>{fa(c.repeated_source_row_count)}</b>
        </div>
      </div>
      <div className="audit-status-grid">
        {rows.map((x, i) => (
          <article key={i} className={x.tone}>
            <header>
              <span>{x.title}</span>
              <b>{fa(x.count)} فقره</b>
            </header>
            <strong>{money(x.amount || 0)} تومان</strong>
            <small>بدون احتساب چک‌های تضمینی</small>
          </article>
        ))}
      </div>
      <div
        className={`audit-check ${(c.repeated_source_row_count || 0) === 0 ? "ok" : "warn"}`}
      >
        <i>{(c.repeated_source_row_count || 0) === 0 ? "✓" : "!"}</i>
        <span>
          <b>
            {(c.repeated_source_row_count || 0) === 0
              ? "تطبیق تعداد ردیف و چک یکتا برقرار است"
              : "ردیف تکراری در منبع مشاهده شد"}
          </b>
          <small>
            SourceRowCount: {fa(c.source_row_count)} • DistinctChequeCount:{" "}
            {fa(c.distinct_cheque_count)} • RepeatedSourceRowCount:{" "}
            {fa(c.repeated_source_row_count)}
          </small>
        </span>
      </div>
    </section>
  );
}
async function request(path: string, options?: RequestInit) {
  const r = await fetch(`${API()}${path}`, options);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
async function treasuryRequest(path: string) {
  const r = await fetch(`${TREASURY_API()}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const menu: [View, string, string][] = [
  ["management", "✦", "خلاصه مدیریتی"],
  ["customers", "◎", "پرونده مشتری"],
  ["cheques", "◷", "چک و سررسید"],
  ["cashBank", "⇄", "نقد و حواله"],
  ["cashflow", "⌁", "پیش‌بینی نقدینگی"],
  ["monthlyExcel", "▥", "Cash Flow روزانه"],
  ["collections", "✓", "مرکز عملیات وصول"],
  ["representatives", "♙", "تحلیل نمایندگان"],
  ["simulator", "◫", "سناریوساز نقدینگی"],
  ["alerts", "!", "هشدارها"],
  ["history", "↺", "تاریخچه و مقایسه"],
  ["performance", "◉", "دقت پیش‌بینی"],
  ["settings", "⚙", "قوانین و اتوماسیون"],
  ["agents", "⬡", "تیم Agentها"],
];

export default function Page() {
  const [view, setView] = useState<View>("management"),
    [pack, setPack] = useState<Pack | null>(null),
    [alerts, setAlerts] = useState<Alert[]>([]),
    [cases, setCases] = useState<Case[]>([]),
    [history, setHistory] = useState<any[]>([]),
    [performance, setPerformance] = useState<any>(null),
    [policies, setPolicies] = useState<Record<string, any>>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<Customer | null>(null),
    [scenario, setScenario] = useState<any>(null),
    [received, setReceived] = useState<TreasuryCheque[]>([]),
    [issued, setIssued] = useState<TreasuryCheque[]>([]),
    [treasuryError, setTreasuryError] = useState(""),
    [chequeQuality, setChequeQuality] = useState<any>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      request("/agents/latest"),
      request("/customer-alerts?status=open&limit=100"),
      request("/collection-cases"),
      request("/agent-reports/history?limit=30"),
      request("/prediction-performance"),
      request("/policies"),
    ]);
    if (
      results[0].status === "fulfilled" &&
      results[0].value.status !== "empty"
    )
      setPack(results[0].value);
    else if (results[0].status === "rejected")
      setError(results[0].reason.message);
    if (results[1].status === "fulfilled")
      setAlerts(results[1].value.alerts || []);
    if (results[2].status === "fulfilled")
      setCases(results[2].value.cases || []);
    if (results[3].status === "fulfilled")
      setHistory(results[3].value.reports || []);
    if (results[4].status === "fulfilled") setPerformance(results[4].value);
    if (results[5].status === "fulfilled")
      setPolicies(results[5].value.values || {});
    setLoading(false);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const cards = Array.from(
      document.querySelectorAll<HTMLElement>(
        ".fd-kpi,.fd-panel,.manager-panel,.section-agent,.agent-grid>article,.cheque-flow-card,.audit-status-grid>article",
      ),
    );
    const cleanups = cards.map((card) => {
      const move = (event: PointerEvent) => {
        const rect = card.getBoundingClientRect(),
          x = (event.clientX - rect.left) / rect.width,
          y = (event.clientY - rect.top) / rect.height;
        card.style.setProperty("--mx", `${x * 100}%`);
        card.style.setProperty("--my", `${y * 100}%`);
        card.style.setProperty("--rx", `${(0.5 - y) * 3.5}deg`);
        card.style.setProperty("--ry", `${(x - 0.5) * 4.5}deg`);
      };
      const leave = () => {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      };
      card.addEventListener("pointermove", move);
      card.addEventListener("pointerleave", leave);
      return () => {
        card.removeEventListener("pointermove", move);
        card.removeEventListener("pointerleave", leave);
      };
    });
    return () => cleanups.forEach((fn) => fn());
  }, [view, pack, selected]);
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      treasuryRequest("/cheques/received/open?period=all"),
      treasuryRequest("/cheques/issued/latest?limit=100"),
      treasuryRequest("/cheques/status-quality"),
    ]).then(([r, i, q]) => {
      if (!active) return;
      const errors: string[] = [];
      if (r.status === "fulfilled") setReceived(r.value.cheques || []);
      else errors.push(`چک دریافتی: ${r.reason?.message || "خطای نامشخص"}`);
      if (i.status === "fulfilled") setIssued(i.value.cheques || []);
      else errors.push(`چک پرداختی: ${i.reason?.message || "خطای نامشخص"}`);
      if (q.status === "fulfilled") setChequeQuality(q.value);
      else errors.push(`وضعیت قطعی: ${q.reason?.message || "خطای نامشخص"}`);
      setTreasuryError(errors.join(" | "));
    });
    return () => {
      active = false;
    };
  }, []);
  const runAll = async () => {
    setLoading(true);
    setError("");
    try {
      setPack(await request("/agents/run-all", { method: "POST" }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "اجرای Agentها ناموفق بود");
      setLoading(false);
    }
  };
  const customers = useMemo(
    () =>
      [...(pack?.data?.customer?.customers || [])].sort(
        (a, b) => (b.open_exposure || 0) - (a.open_exposure || 0),
      ),
    [pack],
  );
  const cheques = pack?.data?.cheques?.cheques || [],
    cash = pack?.data?.cashflow,
    reps = pack?.data?.representatives?.representatives || [],
    manager = pack?.management_summary?.analysis;
  return (
    <main className="fd enterprise">
      <aside>
        <div className="fd-brand">
          <i>ا</i>
          <div>
            <b>اکسیر کادوس</b>
            <small>Finance Agent Command Center</small>
          </div>
        </div>
        <nav>
          {menu.map(([id, icon, label]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => setView(id)}
            >
              <i>{icon}</i>
              <span>{label}</span>
              {id === "alerts" && <em>{fa(alerts.length)}</em>}
            </button>
          ))}
        </nav>
        <div className="fd-health">
          <i className={error ? "warn" : ""} />
          <div>
            <b>{error ? "نیازمند بررسی اتصال" : "اتوماسیون آماده است"}</b>
            <small>۷ Agent تخصصی متصل</small>
          </div>
        </div>
      </aside>
      <section className="fd-content">
        <header>
          <div>
            <small>مرکز فرماندهی مالی / {label(view)}</small>
            <h1>{label(view)}</h1>
            <p>{description(view)}</p>
          </div>
          <button className="run" onClick={runAll} disabled={loading}>
            ✦ {loading ? "در حال اجرای تیم Agentها…" : "اجرای همه Agentها"}
          </button>
        </header>
        {error && (
          <div className="fd-errors">
            <span>{error}</span>
            <small>
              FastAPI باید روی پورت ۸۰۰۰ اجرا و SQL Server در دسترس باشد.
            </small>
          </div>
        )}
        {view === "management" && (
          <Management
            manager={manager}
            agents={pack?.agents}
            customers={customers}
            cheques={cheques}
            cash={cash}
            alerts={alerts}
          />
        )}
        {view === "customers" && (
          <Customers
            customers={customers}
            agent={pack?.agents?.customer_behavior}
            open={setSelected}
          />
        )}
        {view === "cheques" && (
          <ChequeHub
            received={received.length ? received : cheques}
            issued={issued}
            error={treasuryError}
            open={setView}
          />
        )}
        {view === "receivedCheques" && (
          <ChequeDetails
            kind="received"
            rows={received.length ? received : cheques}
            agent={pack?.agents?.cheque_risk}
            back={() => setView("cheques")}
          />
        )}
        {view === "issuedCheques" && (
          <>
            <AgentPanel agent={pack?.agents?.cheque_payment} />
            <ChequeDetails
              kind="issued"
              rows={issued}
              back={() => setView("cheques")}
            />
          </>
        )}
        {view === "cashflow" && (
          <Cashflow cash={cash} agent={pack?.agents?.cashflow} />
        )}
        {view === "cashBank" && (
          <CashBankMovements agent={pack?.agents?.cash_bank_movement} />
        )}
        {view === "monthlyExcel" && (
          <MonthlyExcelAutomation chequeQuality={chequeQuality} />
        )}
        {view === "collections" && (
          <Collections
            cases={cases}
            agent={pack?.agents?.collection}
            refresh={load}
          />
        )}
        {view === "representatives" && (
          <Representatives
            reps={reps}
            unmapped={pack?.data?.representatives?.unmapped_customer_count}
            agent={pack?.agents?.representative}
          />
        )}
        {view === "simulator" && (
          <>
            <AgentPanel agent={pack?.agents?.scenario} />
            <Simulator result={scenario} setResult={setScenario} />
          </>
        )}
        {view === "alerts" && <Alerts rows={alerts} refresh={load} />}
        {view === "history" && <History rows={history} />}
        {view === "performance" && <Performance data={performance} />}
        {view === "settings" && (
          <Settings values={policies} setValues={setPolicies} />
        )}
        {view === "agents" && (
          <Agents agents={pack?.agents} manager={pack?.management_summary} />
        )}
      </section>
      {selected && (
        <CustomerProfile
          c={selected}
          close={() => setSelected(null)}
          refresh={load}
        />
      )}
      <InsightCenter />
    </main>
  );
}

function CashBankMovements({ agent }: { agent?: AgentResult }) {
  const [period, setPeriod] = useState("month"),
    [approval, setApproval] = useState("approved"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [offset, setOffset] = useState(0),
    [report, setReport] = useState<any>(null),
    [transfers, setTransfers] = useState<any>(null),
    [tab, setTab] = useState<"movements" | "transfers">("movements"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const limit = 500;
  const loadMovements = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const dates =
        period === "custom" ? `&date_from=${from}&date_to=${to}` : "";
      const [movementResult, transferResult] = await Promise.all([
        treasuryRequest(
          `/cash-bank/movements?period=${period}&approval_status=${approval}&limit=${limit}&offset=${offset}${dates}`,
        ),
        treasuryRequest(
          `/cash-bank/transfers?period=${period}&limit=${limit}&offset=${offset}${dates}`,
        ),
      ]);
      setReport(movementResult);
      setTransfers(transferResult);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "دریافت گردش نقد و حواله ناموفق بود",
      );
    } finally {
      setBusy(false);
    }
  }, [period, approval, from, to, offset]);
  useEffect(() => {
    if (period !== "custom" || (from && to)) loadMovements();
  }, [loadMovements, period, from, to]);
  const summary = report?.summary || {};
  const approvalCaption =
    approval === "approved"
      ? "اسناد قطعی"
      : approval === "pending"
        ? "اسناد غیرقطعی"
        : "همه وضعیت‌ها";
  const pageInfo =
    tab === "movements" ? report?.pagination : transfers?.pagination;
  const movementLabel: Record<string, string> = {
    cash_receipt: "دریافت نقدی",
    bank_receipt: "واریز / حواله ورودی",
    cash_payment: "پرداخت نقدی",
    bank_payment: "برداشت / حواله خروجی",
  };
  return (
    <div className="cash-bank-page">
      <AgentPanel agent={agent} />
      <section className="cash-bank-toolbar fd-panel">
        <div>
          <b>بازه گزارش</b>
          {[
            ["today", "امروز"],
            ["week", "۷ روز"],
            ["month", "۳۰ روز"],
            ["3m", "۳ ماه"],
            ["6m", "۶ ماه"],
            ["12m", "۱۲ ماه"],
            ["custom", "دلخواه"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={period === id ? "active" : ""}
              onClick={() => {
                setPeriod(id);
                setOffset(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div>
          <b>وضعیت سند</b>
          {[
            ["approved", "قطعی"],
            ["pending", "غیرقطعی"],
            ["all", "همه"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={approval === id ? "active" : ""}
              onClick={() => {
                setApproval(id);
                setOffset(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {period === "custom" && (
          <div className="custom-dates">
            <label>
              از
              <input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label>
              تا
              <input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
          </div>
        )}
        <button className="refresh" onClick={loadMovements} disabled={busy}>
          {busy ? "در حال خواندن…" : "به‌روزرسانی"}
        </button>
      </section>
      {error && <div className="fd-errors">{error}</div>}
      <section className="fd-kpis cash-bank-kpis">
        <K
          t="دریافت نقدی"
          v={money(summary.cash_receipt_rial || 0)}
          n={`تومان؛ ${approvalCaption}`}
          c="teal"
        />
        <K
          t="واریز و حواله ورودی"
          v={money(summary.bank_receipt_rial || 0)}
          n={`تومان؛ ${approvalCaption}`}
          c="blue"
        />
        <K
          t="پرداخت نقدی"
          v={money(summary.cash_payment_rial || 0)}
          n={`تومان؛ ${approvalCaption}`}
          c="amber"
        />
        <K
          t="برداشت و حواله خروجی"
          v={money(summary.bank_payment_rial || 0)}
          n={`تومان؛ ${approvalCaption}`}
          c="red"
        />
        <K
          t="خالص واقعی نقد و بانک"
          v={money(Math.abs(summary.net_rial || 0))}
          n={`تومان ${Number(summary.net_rial || 0) >= 0 ? "مثبت" : "منفی"}`}
          c={Number(summary.net_rial || 0) >= 0 ? "teal" : "red"}
        />
        <K
          t="انتقال داخلی"
          v={money(transfers?.summary?.transfer_amount_rial || 0)}
          n="تومان؛ اثر خالص شرکت صفر"
          c="blue"
        />
      </section>
      <section className="cash-bank-tabs">
        <button
          className={tab === "movements" ? "active" : ""}
          onClick={() => setTab("movements")}
        >
          دریافت و پرداخت
        </button>
        <button
          className={tab === "transfers" ? "active" : ""}
          onClick={() => setTab("transfers")}
        >
          انتقال داخلی
        </button>
      </section>
      {tab === "movements" ? (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز دریافت و پرداخت نقدی و بانکی"
            p={`${fa(report?.pagination?.total_count || 0)} ردیف در کل بازه؛ مبالغ نمایشی به تومان`}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>نوع</th>
                  <th>شماره سند</th>
                  <th>طرف حساب</th>
                  <th>مبلغ</th>
                  <th>حساب / صندوق</th>
                  <th>عامل Cash Flow</th>
                  <th>وضعیت</th>
                  <th>شرح</th>
                </tr>
              </thead>
              <tbody>
                {(report?.movements || []).map((x: any) => (
                  <tr key={`${x.movement_type}-${x.movement_id}`}>
                    <td>
                      <b>
                        {x.document_date_jalali ||
                          x.document_date?.slice(0, 10)}
                      </b>
                    </td>
                    <td>
                      <span className={`movement-kind ${x.direction}`}>
                        {movementLabel[x.movement_type] || x.movement_type}
                      </span>
                    </td>
                    <td>{x.document_number}</td>
                    <td>
                      {x.counterpart_name ||
                        x.counterpart_code ||
                        x.counterpart_ref ||
                        "—"}
                    </td>
                    <td className={x.direction}>
                      {money(x.amount_rial)} تومان
                    </td>
                    <td>
                      {x.bank_account_number ||
                        (x.cash_ref ? `صندوق ${x.cash_ref}` : "—")}
                    </td>
                    <td>{x.cash_flow_factor_ref || "—"}</td>
                    <td>
                      <span className={`approve-state s${x.approve_state}`}>
                        {x.approve_state === 3
                          ? "قطعی"
                          : x.approve_state === 4
                            ? "ردشده"
                            : "غیرقطعی"}
                      </span>
                    </td>
                    <td>{x.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز انتقال‌های داخلی"
            p="در سطح کل شرکت اثر صفر؛ برای کنترل جابه‌جایی بین حساب‌ها و صندوق‌ها"
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>شماره</th>
                  <th>نوع</th>
                  <th>مبدأ</th>
                  <th>مقصد</th>
                  <th>مبلغ خروج</th>
                  <th>مبلغ ورود</th>
                  <th>State</th>
                  <th>شرح</th>
                </tr>
              </thead>
              <tbody>
                {(transfers?.transfers || []).map((x: any) => (
                  <tr key={`${x.transfer_type}-${x.transfer_id}`}>
                    <td>
                      <b>{x.date_jalali || x.date?.slice(0, 10)}</b>
                    </td>
                    <td>{x.number}</td>
                    <td>
                      {x.transfer_type === "bank_transfer"
                        ? "انتقال بانکی"
                        : "انتقال صندوق"}
                    </td>
                    <td>
                      {x.source_bank_account_ref
                        ? `حساب ${x.source_bank_account_ref}`
                        : x.source_cash_ref
                          ? `صندوق ${x.source_cash_ref}`
                          : "—"}
                    </td>
                    <td>
                      {x.destination_bank_account_ref
                        ? `حساب ${x.destination_bank_account_ref}`
                        : x.destination_cash_ref
                          ? `صندوق ${x.destination_cash_ref}`
                          : "—"}
                    </td>
                    <td>{money(x.payment_amount_rial)} تومان</td>
                    <td>{money(x.receipt_amount_rial)} تومان</td>
                    <td>{x.state}</td>
                    <td>{x.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
      <footer className="cash-bank-pagination">
        <button
          disabled={offset === 0 || busy}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          صفحه قبل
        </button>
        <span>
          ردیف {fa(pageInfo?.total_count || 0 ? offset + 1 : 0)} تا{" "}
          {fa(Math.min(offset + limit, pageInfo?.total_count || 0))} از{" "}
          {fa(pageInfo?.total_count || 0)}
        </span>
        <button
          disabled={!pageInfo?.has_more || busy}
          onClick={() => setOffset(offset + limit)}
        >
          صفحه بعد
        </button>
      </footer>
    </div>
  );
}

function MonthlyExcelAutomation({ chequeQuality }: { chequeQuality?: any }) {
  const [file, setFile] = useState<File | null>(null),
    [analysis, setAnalysis] = useState<any>(null),
    [months, setMonths] = useState<any[]>([]),
    [folder, setFolder] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [viewer, setViewer] = useState<any>(null),
    [activeSheet, setActiveSheet] = useState(0);
  const loadMonths = useCallback(async () => {
    try {
      const j = await request("/cashflow-excel/months");
      setMonths(j.months || []);
      if (!analysis && j.months?.length) {
        const m = j.months[0];
        setAnalysis(
          await request(
            `/cashflow-excel/analysis?jalali_year=${m.jalali_year}&jalali_month=${m.jalali_month}`,
          ),
        );
      }
    } catch {}
  }, [analysis]);
  const loadFolder = useCallback(async () => {
    try {
      setFolder(await request("/cashflow-excel/folder/status"));
    } catch (e) {
      setFolder({
        status: "error",
        last_error: {
          error: e instanceof Error ? e.message : "وضعیت پوشه دریافت نشد",
        },
      });
    }
  }, []);
  useEffect(() => {
    loadMonths();
    loadFolder();
    const timer = window.setInterval(() => {
      loadFolder();
      loadMonths();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const body = new FormData();
      body.append("file", file);
      const j = await request("/cashflow-excel/upload", {
        method: "POST",
        body,
      });
      setAnalysis(j.month_analysis);
      setMessage(
        `فایل ${file.name} ثبت شد؛ ماه ${j.month_analysis?.period_label || ""} از ابتدا بازمحاسبه شد.`,
      );
      await loadMonths();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "پردازش فایل ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const scanFolder = async () => {
    setBusy(true);
    setMessage("");
    try {
      const j = await request("/cashflow-excel/folder/scan", {
        method: "POST",
      });
      setMessage(
        j.imported_count
          ? `${fa(j.imported_count)} فایل جدید پردازش شد.`
          : "فایل جدیدی برای پردازش پیدا نشد.",
      );
      await loadFolder();
      await loadMonths();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "بررسی پوشه ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const choose = async (value: string) => {
    const [y, m] = value.split("-");
    setBusy(true);
    try {
      setAnalysis(
        await request(
          `/cashflow-excel/analysis?jalali_year=${y}&jalali_month=${m}`,
        ),
      );
    } finally {
      setBusy(false);
    }
  };
  const showWorkbook = async (row: any) => {
    setBusy(true);
    setMessage("");
    try {
      const j = await request(
        `/cashflow-excel/files/${row.jalali_year}/${row.jalali_month}/${encodeURIComponent(row.stored_file)}/preview`,
      );
      setViewer({ ...j, snapshot: row });
      setActiveSheet(0);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "نمایش فایل ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const downloadWorkbook = (row: any) =>
    window.open(
      `${API()}/cashflow-excel/files/${row.jalali_year}/${row.jalali_month}/${encodeURIComponent(row.stored_file)}/download`,
      "_blank",
    );
  const rows = analysis?.snapshots || [],
    summary = analysis?.summary || {},
    forecast = analysis?.forecast || {},
    agent = analysis?.agent_analysis || {},
    max = Math.max(...rows.map((x: any) => x.pressure_percent || 0), 1);
  return (
    <div className="monthly-excel">
      <section
        className={`folder-automation-card ${folder?.status || "loading"}`}
      >
        <div className="folder-state">
          <i>
            {folder?.status === "ready"
              ? "✓"
              : folder?.status === "disabled"
                ? "∥"
                : "!"}
          </i>
          <span>
            <small>ورودی خودکار Cash Flow</small>
            <h2>
              {folder?.status === "ready"
                ? "پوشه Excel فعال است"
                : folder?.status === "disabled"
                  ? "خواندن پوشه غیرفعال است"
                  : "در حال بررسی وضعیت پوشه"}
            </h2>
            <p>فایل‌ها را در این مسیر قرار بده؛ مدیر نیازی به آپلود ندارد.</p>
          </span>
        </div>
        <code>{folder?.inbox || "در حال دریافت مسیر…"}</code>
        <div className="folder-metrics">
          <span>
            <small>فایل در انتظار</small>
            <b>{fa(folder?.waiting_count || 0)}</b>
          </span>
          <span>
            <small>آخرین فایل موفق</small>
            <b>{folder?.last_successful_file?.filename || "هنوز ثبت نشده"}</b>
          </span>
          <span>
            <small>بررسی خودکار</small>
            <b>هر {fa(folder?.scan_minutes || 15)} دقیقه</b>
          </span>
        </div>
        {folder?.last_error && (
          <div className="folder-error">
            خطای آخر: {folder.last_error.error || folder.last_error}
          </div>
        )}
        <button onClick={scanFolder} disabled={busy}>
          {busy ? "در حال بررسی…" : "بررسی همین حالا"}
        </button>
      </section>
      <details className="manual-upload-fallback">
        <summary>بارگذاری دستی فایل؛ فقط برای حالت پشتیبان</summary>
        <section className="excel-upload-card">
          <div>
            <small>روش جایگزین</small>
            <h2>بارگذاری دستی Cash Flow</h2>
            <p>اگر سرویس پوشه در دسترس نبود، فایل را از این قسمت ثبت کنید.</p>
          </div>
          <label>
            <input
              type="file"
              accept=".xlsx"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <span>{file ? file.name : "انتخاب فایل Excel"}</span>
          </label>
          <button onClick={upload} disabled={!file || busy}>
            {busy ? "در حال پردازش…" : "بارگذاری و تحلیل ماه"}
          </button>
        </section>
      </details>
      {message && (
        <div
          className={`excel-message ${message.includes("ثبت شد") ? "ok" : "error"}`}
        >
          {message}
        </div>
      )}
      <div className="excel-period">
        <div>
          <b>ماه مورد بررسی</b>
          <small>هر روز فقط یک Snapshot معتبر نگهداری می‌شود.</small>
        </div>
        <select
          value={
            analysis ? `${analysis.jalali_year}-${analysis.jalali_month}` : ""
          }
          onChange={(e) => choose(e.target.value)}
        >
          {months.map((m) => (
            <option
              key={`${m.jalali_year}-${m.jalali_month}`}
              value={`${m.jalali_year}-${m.jalali_month}`}
            >
              {m.month_name} {fa(m.jalali_year)} — {fa(m.snapshot_count)} فایل
            </option>
          ))}
        </select>
      </div>
      {!!rows.length && (
        <article className="fd-panel excel-files">
          <Heading
            h="فایل‌های Excel معتبر این ماه"
            p="همان فایل‌هایی که مبنای Snapshot و تحلیل Agent قرار گرفته‌اند"
          />
          <div className="excel-file-list">
            {[...rows].reverse().map((row: any) => (
              <div key={row.stored_file}>
                <i>▥</i>
                <span>
                  <b>{row.filename}</b>
                  <small>
                    {row.jalali_date} • ثبت‌شده در{" "}
                    {row.uploaded_at
                      ? new Date(row.uploaded_at).toLocaleString("fa-IR")
                      : "سیستم"}
                  </small>
                </span>
                <em>پردازش موفق</em>
                <button onClick={() => showWorkbook(row)} disabled={busy}>
                  مشاهده محتوا
                </button>
                <button
                  className="secondary"
                  onClick={() => downloadWorkbook(row)}
                >
                  دانلود اصل فایل
                </button>
              </div>
            ))}
          </div>
        </article>
      )}
      {analysis?.status === "success" ? (
        <>
          <article className={`excel-agent ${forecast.status || "attention"}`}>
            <header>
              <i>✦</i>
              <div>
                <small>Monthly Cash Flow Agent</small>
                <h2>{agent.headline}</h2>
              </div>
              <Status x={forecast.status || "attention"} />
            </header>
            <p>{agent.human_summary}</p>
            <div>
              <section>
                <b>نقاط مثبت</b>
                {(agent.good_signals || []).map((x: string, i: number) => (
                  <span key={i}>✓ {x}</span>
                ))}
              </section>
              <section>
                <b>ریسک‌ها و اقدام</b>
                {(agent.risks || []).map((x: string, i: number) => (
                  <span key={i}>! {x}</span>
                ))}
                {(agent.recommended_actions || []).map((x: any, i: number) => (
                  <span key={"a" + i}>→ {textOf(x)}</span>
                ))}
              </section>
            </div>
          </article>
          <div className="fd-kpis">
            <K
              t="میانگین تعهد ماه"
              v={money(summary.average_obligations_rial || 0)}
              n="تومان"
              c="blue"
            />
            <K
              t="فشار وزنی چک‌ها"
              v={`${fa(summary.weighted_average_pressure_percent)}٪`}
              n="تعهد ÷ موجودی"
              c="amber"
            />
            <K
              t="ظرفیت پرداخت پیش‌بینی‌شده"
              v={`${fa(forecast.estimated_payment_capacity_percent)}٪`}
              n={`اطمینان ${forecast.confidence === "medium" ? "متوسط" : "کم"}`}
              c="teal"
            />
            <K
              t={
                chequeQuality?.issued_actual_payment_rate
                  ? "نرخ واقعی پاس‌شدن پرداختی"
                  : "نرخ واقعی وصول دریافتی"
              }
              v={
                chequeQuality?.issued_actual_payment_rate
                  ? `${fa(chequeQuality.issued_actual_payment_rate.amount_rate_percent)}٪`
                  : chequeQuality?.received_verified
                    ? `${fa(chequeQuality.received_verified.amount_rate_percent)}٪`
                    : "در انتظار SQL"
              }
              n={
                chequeQuality?.issued_actual_payment_rate
                  ? `${fa(chequeQuality.issued_actual_payment_rate.paid_count)} چک پرداخت‌شده`
                  : chequeQuality?.received_verified
                    ? `${fa(chequeQuality.received_verified.collected_count)} چک وصول‌شده`
                    : "وضعیت قطعی چک"
              }
              c="teal"
            />
          </div>
          <section className="excel-grid">
            <article className="fd-panel">
              <Heading
                h={`روند فشار چک‌های ${analysis.period_label}`}
                p="درصد تعهدات چکی نسبت به موجودی کل در هر فایل روزانه"
              />
              <div className="excel-bars">
                {rows.map((x: any) => (
                  <div key={x.jalali_date}>
                    <b>{fa(x.pressure_percent)}٪</b>
                    <span>
                      <i
                        className={
                          x.pressure_percent >= 50
                            ? "critical"
                            : x.pressure_percent >= 30
                              ? "warning"
                              : "normal"
                        }
                        style={{
                          height: `${Math.max(5, (x.pressure_percent / max) * 100)}%`,
                        }}
                      />
                    </span>
                    <small>{String(x.jalali_date).slice(8)}</small>
                  </div>
                ))}
              </div>
            </article>
            <article className="fd-panel excel-forecast">
              <Heading h="پیش‌بینی پایان ماه" p={forecast.method || ""} />
              <strong>
                {fa(forecast.estimated_payment_capacity_percent)}٪
              </strong>
              <span>ظرفیت احتمالی پرداخت</span>
              <dl>
                <div>
                  <dt>روند</dt>
                  <dd>{forecast.trend}</dd>
                </div>
                <div>
                  <dt>فشار پایان ماه</dt>
                  <dd>{fa(forecast.projected_end_month_pressure_percent)}٪</dd>
                </div>
                <div>
                  <dt>آخرین فایل</dt>
                  <dd>{analysis.latest_snapshot?.jalali_date}</dd>
                </div>
                <div>
                  <dt>نرخ واقعی پرداخت</dt>
                  <dd>
                    {chequeQuality?.issued_actual_payment_rate
                      ? `${fa(chequeQuality.issued_actual_payment_rate.amount_rate_percent)}٪`
                      : "در انتظار تأیید State"}
                  </dd>
                </div>
              </dl>
              <p>
                {chequeQuality?.issued_actual_payment_rate
                  ? `نرخ واقعی پرداخت از SQL و Stateهای تأییدشده ${chequeQuality.issued_actual_payment_rate.configured_paid_states.join("، ")} محاسبه شده است.`
                  : chequeQuality?.issued_rate_limitation ||
                    "اتصال وضعیت قطعی SQL برقرار نشده است؛ جزئیات خطا در بخش چک‌ها نمایش داده می‌شود."}
              </p>
            </article>
          </section>
          <article className="fd-panel">
            <Heading
              h="ریز Snapshotهای ماه"
              p="مبالغ به تومان؛ فایل جدید همان روز جایگزین نسخه قبلی می‌شود."
            />
            <div className="excel-table">
              <table>
                <thead>
                  <tr>
                    <th>تاریخ</th>
                    <th>موجودی</th>
                    <th>چک معوق</th>
                    <th>چک پیش‌رو</th>
                    <th>کل تعهد</th>
                    <th>مانده بعد از تعهد</th>
                    <th>فشار</th>
                    <th>وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((x: any) => (
                    <tr key={x.jalali_date}>
                      <td>
                        <b>{x.jalali_date}</b>
                      </td>
                      <td>{money(x.liquidity_rial)}</td>
                      <td>{money(x.overdue_cheques_rial)}</td>
                      <td>{money(x.upcoming_cheques_rial)}</td>
                      <td>{money(x.obligations_rial)}</td>
                      <td>{money(x.remaining_cash_rial)}</td>
                      <td>{fa(x.pressure_percent)}٪</td>
                      <td>
                        <Risk
                          x={
                            x.shortfall_rial > 0
                              ? "critical"
                              : x.pressure_percent >= 30
                                ? "danger"
                                : "safe"
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </>
      ) : (
        <div className="fd-empty">
          اولین فایل Excel را داخل پوشه ورودی قرار بده و «بررسی همین حالا» را
          بزن.
        </div>
      )}
      {viewer && (
        <div
          className="excel-viewer-backdrop"
          onMouseDown={() => setViewer(null)}
        >
          <section
            className="excel-viewer"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <small>نمایش فایل Excel</small>
                <h2>{viewer.snapshot?.filename}</h2>
                <p>{viewer.snapshot?.jalali_date} • Snapshot معتبر</p>
              </div>
              <button onClick={() => setViewer(null)}>×</button>
            </header>
            <nav>
              {viewer.sheets?.map((sheet: any, i: number) => (
                <button
                  key={sheet.name}
                  className={activeSheet === i ? "active" : ""}
                  onClick={() => setActiveSheet(i)}
                >
                  {sheet.name}
                </button>
              ))}
            </nav>
            {viewer.sheets?.[activeSheet] && (
              <>
                <div className="excel-sheet-meta">
                  <span>
                    {fa(viewer.sheets[activeSheet].total_row_count)} ردیف
                  </span>
                  {viewer.sheets[activeSheet].truncated && (
                    <em>
                      برای سرعت نمایش، فقط ۲۵۰ ردیف و ۴۰ ستون اول نشان داده
                      می‌شود.
                    </em>
                  )}
                </div>
                <div className="excel-sheet-table">
                  <table>
                    <tbody>
                      {viewer.sheets[activeSheet].rows.map(
                        (row: any[], ri: number) => (
                          <tr key={ri}>
                            <th>{fa(ri + 1)}</th>
                            {row.map((cell: any, ci: number) => (
                              <td key={ci}>
                                {cell == null
                                  ? ""
                                  : typeof cell === "number"
                                    ? fa(cell)
                                    : String(cell)}
                              </td>
                            ))}
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <footer>
              <button onClick={() => downloadWorkbook(viewer.snapshot)}>
                دانلود اصل فایل
              </button>
              <button className="secondary" onClick={() => setViewer(null)}>
                بستن
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

function Management({
  manager,
  agents,
  customers,
  cheques,
  cash,
  alerts,
}: {
  manager?: Analysis;
  agents?: Record<string, AgentResult>;
  customers: Customer[];
  cheques: Cheque[];
  cash?: any;
  alerts: Alert[];
}) {
  let open = customers.reduce((s, c) => s + (c.open_exposure || 0), 0),
    overdue = customers.reduce((s, c) => s + (c.overdue_open_amount || 0), 0);
  return (
    <>
      <div className="fd-kpis">
        <K t="چک‌های دریافتی باز" v={money(open)} n="تومان" c="teal" />
        <K
          t="بازِ سررسیدگذشته"
          v={money(overdue)}
          n={`${fa(open ? (overdue / open) * 100 : 0)}٪ از چک‌های باز`}
          c="red"
        />
        <K
          t="چک پرریسک آینده"
          v={fa(cheques.filter((x) => x.risk_level === "high").length)}
          n="نیازمند پیگیری"
          c="amber"
        />
        <K t="هشدار باز" v={fa(alerts.length)} n="مرکز عملیات" c="blue" />
      </div>
      <ExecutiveCharts customers={customers} cheques={cheques} cash={cash} />
      <ManagerPanel a={manager} />
      <div className="agent-grid">
        {Object.entries(agents || {}).map(([key, value]) => (
          <AgentCard key={key} agent={value} />
        ))}
      </div>
      <div className="fd-grid">
        <article className="fd-panel">
          <Heading
            h="تصمیم‌های امروز"
            p="اولویت پیشنهادی Finance Manager Agent"
          />
          <ol className="decision-list">
            {(manager?.decisions_today || manager?.recommended_actions || [])
              .slice(0, 5)
              .map((x, i) => (
                <li key={i}>
                  <i>{fa(i + 1)}</i>
                  <span>{textOf(x)}</span>
                </li>
              ))}
          </ol>
        </article>
        <article className="fd-panel">
          <Heading
            h="برنامه هفت‌روزه"
            p="اقدامات هماهنگ بین واحد مالی، وصول و فروش"
          />
          <ol className="decision-list week">
            {(manager?.seven_day_plan || []).map((x, i) => (
              <li key={i}>
                <i>{fa(i + 1)}</i>
                <span>{textOf(x)}</span>
              </li>
            ))}
          </ol>
        </article>
      </div>
      {cash && (
        <article className="fd-panel chart-wide">
          <Heading
            h="روند مانده نقدینگی"
            p={`${fa(cash.negative_cash_pressure_days)} روز فشار منفی؛ داده واقعی پیش‌بینی`}
          />
          <CashChart days={cash.timeline || []} />
        </article>
      )}
    </>
  );
}
function ExecutiveCharts({
  customers,
  cheques,
  cash,
}: {
  customers: Customer[];
  cheques: Cheque[];
  cash?: any;
}) {
  const riskRows = [
      {
        label: "بحرانی",
        value: customers.filter((c) => risk(c) === "critical").length,
        tone: "red",
      },
      {
        label: "نیازمند توجه",
        value: customers.filter((c) => risk(c) === "danger").length,
        tone: "amber",
      },
      {
        label: "مناسب",
        value: customers.filter((c) => risk(c) === "safe").length,
        tone: "green",
      },
    ],
    top = customers.slice(0, 6).map((c) => ({
      label: cname(c),
      value: c.open_exposure || 0,
      tone:
        risk(c) === "critical"
          ? "red"
          : risk(c) === "danger"
            ? "amber"
            : "teal",
    })),
    due = [
      {
        label: "سررسید گذشته",
        value: cheques.filter((c) => (daysToDue(c) ?? 1) < 0).length,
        tone: "red",
      },
      {
        label: "تا ۳۰ روز",
        value: cheques.filter((c) => {
          const d = daysToDue(c);
          return d !== undefined && d >= 0 && d <= 30;
        }).length,
        tone: "amber",
      },
      {
        label: "۳۱ تا ۹۰ روز",
        value: cheques.filter((c) => {
          const d = daysToDue(c);
          return d !== undefined && d > 30 && d <= 90;
        }).length,
        tone: "teal",
      },
      {
        label: "بیش از ۹۰ روز",
        value: cheques.filter((c) => (c.term_days || 0) > 90).length,
        tone: "violet",
      },
    ],
    days = (cash?.timeline || []).slice(0, 10) as CashDay[];
  return (
    <section className="executive-charts">
      <article className="fd-panel visual-card">
        <Heading h="توزیع ریسک مشتریان" p="تعداد مشتری در هر سطح ریسک" />
        <DonutChart rows={riskRows} />
      </article>
      <article className="fd-panel visual-card">
        <Heading h="بزرگ‌ترین چک‌های باز" p="۶ مشتری اول؛ مبلغ به تومان" />
        <HorizontalBars rows={top} moneyMode />
      </article>
      <article className="fd-panel visual-card">
        <Heading h="وضعیت زمانی چک‌ها" p="کنترل سیاست سررسید ۹۰ روزه" />
        <VerticalBars rows={due} />
      </article>
      <article className="fd-panel visual-card cash-bars-card">
        <Heading
          h="ورودی و خروجی ۱۰ روز آینده"
          p="سبز: ورودی، قرمز: خروجی؛ تومان"
        />
        <CashBars days={days} />
      </article>
    </section>
  );
}
type ChartRow = {
  label: string;
  value: number;
  tone: string;
  records?: InsightRecord[];
};
function HorizontalBars({
  rows,
  moneyMode = false,
}: {
  rows: ChartRow[];
  moneyMode?: boolean;
}) {
  const max = Math.max(...rows.map((x) => x.value), 1),
    total = rows.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className="h-bars">
      {rows.length ? (
        rows.map((x, i) => (
          <button
            type="button"
            className="h-bar drillable"
            key={i}
            onClick={() =>
              openInsight({
                title: x.label,
                subtitle: "جزئیات میله انتخاب‌شده",
                tone: x.tone,
                stats: [
                  {
                    label: "مقدار",
                    value: moneyMode ? `${money(x.value)} تومان` : fa(x.value),
                  },
                  {
                    label: "سهم از نمودار",
                    value: `${fa((x.value / total) * 100)}٪`,
                  },
                  {
                    label: "بیشترین مقدار نمودار",
                    value: moneyMode ? `${money(max)} تومان` : fa(max),
                  },
                ],
              })
            }
          >
            <span title={x.label}>{x.label}</span>
            <div>
              <i
                className={x.tone}
                style={{ width: `${Math.max(4, (x.value / max) * 100)}%` }}
              />
            </div>
            <b>{moneyMode ? money(x.value) : fa(x.value)}</b>
          </button>
        ))
      ) : (
        <div className="chart-empty">داده‌ای برای نمایش نیست.</div>
      )}
    </div>
  );
}
function VerticalBars({ rows }: { rows: ChartRow[] }) {
  const max = Math.max(...rows.map((x) => x.value), 1),
    total = rows.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div className="v-bars">
      {rows.map((x, i) => (
        <button
          type="button"
          className="drillable"
          key={i}
          onClick={() =>
            openInsight({
              title: x.label,
              subtitle: x.records?.length
                ? "فهرست چک‌های این بازه"
                : "جزئیات ستون انتخاب‌شده",
              tone: x.tone,
              stats: [
                { label: "تعداد", value: fa(x.value) },
                {
                  label: "سهم از کل",
                  value: `${fa((x.value / total) * 100)}٪`,
                },
                { label: "کل موارد نمودار", value: fa(total) },
              ],
              records: x.records,
            })
          }
        >
          <b>{fa(x.value)}</b>
          <span>
            <i
              className={x.tone}
              style={{
                height: `${Math.max(x.value ? 8 : 2, (x.value / max) * 100)}%`,
              }}
            />
          </span>
          <small>{x.label}</small>
        </button>
      ))}
    </div>
  );
}
function DonutChart({ rows }: { rows: ChartRow[] }) {
  const total = rows.reduce((s, x) => s + x.value, 0) || 1,
    critical = rows[0]?.value || 0,
    danger = rows[1]?.value || 0,
    p1 = (critical / total) * 100,
    p2 = (danger / total) * 100;
  return (
    <div className="risk-donut-wrap">
      <button
        type="button"
        className="risk-donut drillable"
        onClick={() =>
          openInsight({
            title: "توزیع ریسک مشتریان",
            subtitle: "جمع کل مشتریان موجود در نمودار",
            stats: rows.map((x) => ({
              label: x.label,
              value: `${fa(x.value)} مشتری — ${fa((x.value / total) * 100)}٪`,
            })),
          })
        }
        style={{
          background: `conic-gradient(#ef4444 0 ${p1}%,#f59e0b ${p1}% ${p1 + p2}%,#10b981 ${p1 + p2}% 100%)`,
        }}
      >
        <span>
          <b>{fa(total)}</b>
          <small>مشتری</small>
        </span>
      </button>
      <div className="chart-legend">
        {rows.map((x, i) => (
          <button
            type="button"
            className="drillable"
            key={i}
            onClick={() =>
              openInsight({
                title: x.label,
                tone: x.tone,
                stats: [
                  { label: "تعداد مشتری", value: fa(x.value) },
                  {
                    label: "سهم از کل",
                    value: `${fa((x.value / total) * 100)}٪`,
                  },
                ],
              })
            }
          >
            <i className={x.tone} />
            <span>{x.label}</span>
            <b>{fa(x.value)}</b>
          </button>
        ))}
      </div>
    </div>
  );
}
function CashBars({ days }: { days: CashDay[] }) {
  const max = Math.max(
    ...days.flatMap((d) => [d.projected_inflow || 0, d.projected_outflow || 0]),
    1,
  );
  return (
    <div className="cash-bars">
      {days.length ? (
        days.map((d, i) => (
          <div key={i}>
            <div className="cash-bar-pair">
              <i
                className="in"
                style={{
                  height: `${Math.max(3, ((d.projected_inflow || 0) / max) * 100)}%`,
                }}
                title={`ورودی ${money(d.projected_inflow || 0)} تومان`}
              />
              <i
                className="out"
                style={{
                  height: `${Math.max(3, ((d.projected_outflow || 0) / max) * 100)}%`,
                }}
                title={`خروجی ${money(d.projected_outflow || 0)} تومان`}
              />
            </div>
            <small>{d.date_jalali || String(d.date || "").slice(5)}</small>
          </div>
        ))
      ) : (
        <div className="chart-empty">پیش‌بینی نقدینگی هنوز آماده نیست.</div>
      )}
    </div>
  );
}
function LegacyManagerPanel({ a }: { a?: Analysis }) {
  const p = a?.prediction || {},
    s = a?.scenarios || {};
  return (
    <article className="manager-panel decision-manager">
      <div className="manager-head">
        <i>✦</i>
        <div>
          <small>Finance Manager Agent</small>
          <h2>{textOf(a?.headline) || "تیم Agentها هنوز اجرا نشده است"}</h2>
        </div>
        <Status x={a?.management_status || "attention"} />
      </div>
      <p>
        {textOf(a?.summary) ||
          "دکمه اجرای همه Agentها را بزنید تا خلاصه مدیریتی، پیش‌بینی و برنامه اقدام ساخته شود."}
      </p>
      {a && (
        <>
          <div className="manager-prediction">
            <section>
              <small>چشم‌انداز ۷ روزه</small>
              <p>{textOf(p.next_7_days)}</p>
            </section>
            <section>
              <small>پیش‌بینی پایان ماه</small>
              <p>{textOf(p.end_of_month)}</p>
            </section>
            <section>
              <small>سطح اطمینان</small>
              <strong>
                {p.confidence === "high"
                  ? "زیاد"
                  : p.confidence === "medium"
                    ? "متوسط"
                    : "کم"}
              </strong>
            </section>
          </div>
          {Object.keys(s).length > 0 && (
            <div className="manager-scenarios">
              {(["optimistic", "base", "pessimistic"] as const).map((k, i) => (
                <section key={k}>
                  <b>
                    {i === 0
                      ? "خوش‌بینانه"
                      : i === 1
                        ? "مسیر پیشنهادی"
                        : "بدبینانه"}
                  </b>
                  <span>{textOf(s[k])}</span>
                </section>
              ))}
            </div>
          )}
        </>
      )}
      <div className="manager-columns">
        <div>
          <b>نقاط مثبت</b>
          {(a?.good_signals || []).slice(0, 4).map((x, i) => (
            <span key={i}>✓ {textOf(x)}</span>
          ))}
        </div>
        <div>
          <b>ریسک‌های اصلی</b>
          {(a?.risks || []).slice(0, 4).map((x, i) => (
            <span key={i}>! {textOf(x)}</span>
          ))}
        </div>
      </div>
      {a?.next_best_action && (
        <div className="next-action">
          <b>بهترین اقدام بعدی</b>
          {textOf(a.next_best_action)}
        </div>
      )}
    </article>
  );
}
function LegacyAgentPanel({ agent }: { agent?: AgentResult }) {
  let a = agent?.analysis,
    p = a?.prediction || {},
    s = a?.scenarios || {},
    actions = a?.recommended_actions || [];
  return (
    <article className="section-agent decision-agent">
      <div>
        <i>✦</i>
        <span>
          <small>{agent?.metadata?.agent_name || "Agent تخصصی این بخش"}</small>
          <b>{textOf(a?.headline) || "تحلیل Agent هنوز آماده نیست"}</b>
        </span>
        <em>
          {agent?.metadata?.mode === "llm" ||
          agent?.metadata?.agent_mode === "llm"
            ? "LLM فعال"
            : "موتور تصمیم‌یار"}
        </em>
      </div>
      <p>
        {textOf(a?.summary) ||
          textOf(a?.human_summary) ||
          "دکمه اجرای همه Agentها را بزنید تا پیش‌بینی و راهکار ساخته شود."}
      </p>
      {a && (
        <>
          <section className="decision-forecast">
            <div>
              <small>۷ روز آینده</small>
              <b>{textOf(p.next_7_days) || "در انتظار داده"}</b>
            </div>
            <div>
              <small>پیش‌بینی پایان ماه</small>
              <b>
                {textOf(p.end_of_month) ||
                  textOf(a.future_outlook) ||
                  "در انتظار داده"}
              </b>
            </div>
            <div>
              <small>اطمینان</small>
              <b>
                {p.confidence === "high"
                  ? "زیاد"
                  : p.confidence === "medium"
                    ? "متوسط"
                    : "کم"}
              </b>
            </div>
          </section>
          <section className="scenario-strip">
            {(["optimistic", "base", "pessimistic"] as const).map((key, i) => (
              <div className={key} key={key}>
                <small>
                  {i === 0
                    ? "خوش‌بینانه"
                    : i === 1
                      ? "سناریوی پایه"
                      : "بدبینانه"}
                </small>
                <span>{textOf(s[key]) || "—"}</span>
              </div>
            ))}
          </section>
          <div className="decision-risks">
            {(a.risks || a.bad_signals || []).slice(0, 3).map((x, i) => (
              <span key={i}>! {textOf(x)}</span>
            ))}
          </div>
          <section className="decision-actions">
            {actions.slice(0, 4).map((x, i) => (
              <article key={i}>
                <header>
                  <b>{x.action}</b>
                  <em className={x.priority}>
                    {x.priority === "critical"
                      ? "فوری"
                      : x.priority === "high"
                        ? "بالا"
                        : "متوسط"}
                  </em>
                </header>
                <p>{x.why}</p>
                <footer>
                  <span>اثر: {x.expected_effect || "کاهش ریسک"}</span>
                  <span>
                    {x.owner || "مدیر مالی"} • {x.deadline || "این هفته"}
                  </span>
                </footer>
              </article>
            ))}
          </section>
          {a.next_best_action && (
            <div className="next-action">
              <b>بهترین اقدام بعدی</b>
              {textOf(a.next_best_action)}
            </div>
          )}
        </>
      )}
    </article>
  );
}
function LegacyAgentCard({ agent }: { agent: AgentResult }) {
  return (
    <article>
      <div>
        <i>⬡</i>
        <span>
          <b>{agent.metadata?.agent_name}</b>
          <small>
            {agent.metadata?.mode === "llm" ||
            agent.metadata?.agent_mode === "llm"
              ? "هوش مصنوعی فعال"
              : "تحلیل قاعده‌محور"}
          </small>
        </span>
      </div>
      <p>{textOf(agent.analysis?.headline)}</p>
      <em>{textOf(agent.analysis?.next_best_action)}</em>
    </article>
  );
}

function Customers({
  customers,
  agent,
  open,
}: {
  customers: Customer[];
  agent?: AgentResult;
  open: (c: Customer) => void;
}) {
  return (
    <>
      <AgentPanel agent={agent} />
      <article className="fd-panel">
        <Heading
          h="پرونده مالی مشتریان"
          p="برای مشاهده علت ریسک، پیشنهاد اعتبار و ساخت پرونده وصول روی مشتری کلیک کنید."
        />
        <div className="fd-table">
          <table>
            <thead>
              <tr>
                <th>مشتری</th>
                <th>مانده باز</th>
                <th>معوق</th>
                <th>بیش از ۹۰ روز</th>
                <th>ریسک دیرکرد</th>
                <th>احتمال برگشت</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((c) => (
                <tr key={c.counterpart_ref || cname(c)} onClick={() => open(c)}>
                  <td>
                    <b>{cname(c)}</b>
                  </td>
                  <td>{money(c.open_exposure)}</td>
                  <td>{money(c.overdue_open_amount)}</td>
                  <td>{fa(policy(c))}</td>
                  <td>{fa(c.late_payment_risk?.value)}٪</td>
                  <td>{fa(c.cheque_return_probability?.value)}٪</td>
                  <td>
                    <Risk x={risk(c)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}
function Cheques({ rows, agent }: { rows: Cheque[]; agent?: AgentResult }) {
  return (
    <>
      <AgentPanel agent={agent} />
      <article className="fd-panel">
        <Heading
          h="چک‌های آینده و دلایل ریسک"
          p="قانون شرکت: سررسید حداکثر ۹۰ روز"
        />
        <div className="cheque-enterprise">
          {rows.map((c) => {
            const remaining = daysToDue(c);
            return (
              <div
                key={c.cheque_id}
                className={(c.term_days || 0) > 90 ? "bad" : ""}
              >
                <header>
                  <div>
                    <b>{c.counterpart_name}</b>
                    <small>
                      تاریخ سررسید: {c.due_date_jalali || c.due_date} • مدت کل
                      چک: {fa(c.term_days)} روز
                    </small>
                  </div>
                  <Risk
                    x={
                      c.risk_level === "critical"
                        ? "critical"
                        : c.risk_level === "high" || (c.term_days || 0) > 90
                          ? "danger"
                          : "safe"
                    }
                  />
                </header>
                <div className="cheque-time-row">
                  <span
                    className={`due-count ${remaining === undefined ? "unknown" : remaining < 0 ? "overdue" : remaining <= 7 ? "soon" : "normal"}`}
                  >
                    ◷ {remainingLabel(c)}
                  </span>
                  <span>مدت کل: {fa(c.term_days)} روز</span>
                </div>
                <strong>{money(c.amount)} تومان</strong>
                <em>
                  احتمال برگشت {fa(c.estimated_return_probability_percent)}٪
                </em>
                <section>
                  <b>چرا پرریسک است؟</b>
                  {(c.reasons || ["ریسک از سابقه مشتری محاسبه شده است."]).map(
                    (x, i) => (
                      <p key={i}>! {x}</p>
                    ),
                  )}
                </section>
              </div>
            );
          })}
        </div>
      </article>
    </>
  );
}
function Cashflow({ cash, agent }: { cash?: any; agent?: AgentResult }) {
  const days: CashDay[] = cash?.timeline || [],
    summary = cash?.reliance_summary || {},
    weighted = days.reduce(
      (s: any, x: any) => s + Number(x.weighted_received_cheques || 0),
      0,
    ),
    issued = days.reduce(
      (s: any, x: any) => s + Number(x.issued_cheques_due || 0),
      0,
    );
  return (
    <>
      <AgentPanel agent={agent} />
      <div className="fd-kpis">
        <K
          t="موجودی افتتاحیه Excel"
          v={
            cash?.opening_cash == null
              ? "در انتظار فایل"
              : money(cash.opening_cash)
          }
          n={
            cash?.opening_cash == null
              ? "فایل معتبر ثبت نشده"
              : "تومان • آخرین Snapshot"
          }
          c="blue"
        />
        <K
          t="چک دریافتی قابل اتکا"
          v={money(weighted)}
          n={`${fa(summary.portfolio_reliance_percent || 0)}٪ مبلغ اسمی`}
          c="teal"
        />
        <K
          t="چک پرداختی افق"
          v={money(issued)}
          n="تومان • سررسیدهای SQL"
          c="amber"
        />
        <K
          t="اولین کسری احتمالی"
          v={cash?.first_predicted_shortage_date_jalali || "پیش‌بینی نشده"}
          n="براساس مانده واقعی"
          c={cash?.first_predicted_shortage_date_jalali ? "red" : "teal"}
        />
      </div>
      <article className="fd-panel reliance-cashflow">
        <Heading
          h={`چرا فقط ${fa(summary.portfolio_reliance_percent || 0)}٪ چک‌ها قابل اتکا محاسبه شد؟`}
          p="توضیح قابل حسابرسی درصد اتکای سبد چک‌های دریافتی"
        />
        <div className="cash-reliance-numbers">
          <span>
            <small>مبلغ اسمی</small>
            <b>{money(summary.nominal_received_cheques_rial || 0)} تومان</b>
          </span>
          <i>←</i>
          <span>
            <small>کاهش احتیاطی ریسک</small>
            <b>{money(summary.risk_reduction_rial || 0)} تومان</b>
          </span>
          <i>←</i>
          <span>
            <small>مبلغ قابل اتکا</small>
            <b>
              {money(summary.risk_adjusted_received_cheques_rial || 0)} تومان
            </b>
          </span>
        </div>
        <p>
          {summary.why_fa ||
            "پس از اجرای Agent، علت درصد اتکا نمایش داده می‌شود."}
        </p>
        <div className="cash-improvements">
          <b>برای افزایش مبلغ قابل اتکا چه کار کنیم؟</b>
          {(summary.how_to_improve_fa || []).map((x: string, i: number) => (
            <span key={i}>
              <i>{fa(i + 1)}</i>
              {x}
            </span>
          ))}
        </div>
      </article>
      <article className="fd-panel">
        <Heading
          h="پیش‌بینی واقعی نقدینگی"
          p="موجودی Excel + چک‌های دریافتی تعدیل‌شده − چک‌های پرداختی SQL"
        />
        <CashChart days={days} />
        <CashTable days={days} />
      </article>
    </>
  );
}
function Collections({
  cases,
  agent,
  refresh,
}: {
  cases: Case[];
  agent?: AgentResult;
  refresh: () => void;
}) {
  const [newCase, setNewCase] = useState({
    counterpart_name: "",
    assignee: "",
    due_at: "",
    priority: "high",
  });
  const create = async () => {
    if (!newCase.counterpart_name) return;
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newCase),
    });
    setNewCase({
      counterpart_name: "",
      assignee: "",
      due_at: "",
      priority: "high",
    });
    refresh();
  };
  return (
    <>
      <AgentPanel agent={agent} />
      <article className="fd-panel">
        <Heading
          h="ساخت پرونده وصول"
          p="برای هر مشتری مسئول، اولویت و مهلت تعیین کنید."
        />
        <div className="case-form">
          <input
            placeholder="نام مشتری"
            value={newCase.counterpart_name}
            onChange={(e) =>
              setNewCase({ ...newCase, counterpart_name: e.target.value })
            }
          />
          <input
            placeholder="مسئول پیگیری"
            value={newCase.assignee}
            onChange={(e) =>
              setNewCase({ ...newCase, assignee: e.target.value })
            }
          />
          <input
            type="date"
            value={newCase.due_at}
            onChange={(e) => setNewCase({ ...newCase, due_at: e.target.value })}
          />
          <select
            value={newCase.priority}
            onChange={(e) =>
              setNewCase({ ...newCase, priority: e.target.value })
            }
          >
            <option value="critical">بحرانی</option>
            <option value="high">زیاد</option>
            <option value="medium">متوسط</option>
          </select>
          <button onClick={create}>ایجاد پرونده</button>
        </div>
      </article>
      <article className="fd-panel">
        <Heading
          h="صف عملیات وصول"
          p={`${fa(cases.length)} پرونده فعال و تاریخی`}
        />
        <div className="case-grid">
          {cases.map((c) => (
            <div key={c.case_id}>
              <header>
                <Risk
                  x={
                    c.priority === "critical"
                      ? "critical"
                      : c.priority === "high"
                        ? "danger"
                        : "safe"
                  }
                />
                <b>{c.counterpart_name}</b>
              </header>
              <p>
                مسئول: {c.assignee || "تعیین نشده"} • مهلت: {c.due_at || "—"}
              </p>
              <small>
                {fa(c.followups?.length)} پیگیری • {fa(c.promises?.length)} قول
                پرداخت
              </small>
              <CaseActions c={c} refresh={refresh} />
            </div>
          ))}
        </div>
      </article>
    </>
  );
}

function CaseActions({ c, refresh }: { c: Case; refresh: () => void }) {
  const [note, setNote] = useState(""),
    [amount, setAmount] = useState(""),
    [date, setDate] = useState("");
  const post = async (kind: "followups" | "promises") => {
    let body =
      kind === "followups"
        ? { channel: "call", result: "contacted", note, created_by: c.assignee }
        : {
            amount: Number(amount) * 10,
            promise_date: date,
            status: "pending",
          };
    await request(`/collection-cases/${c.case_id}/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setNote("");
    setAmount("");
    setDate("");
    refresh();
  };
  const status = async (x: string) => {
    await request(`/collection-cases/${c.case_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: x }),
    });
    refresh();
  };
  return (
    <div className="case-actions">
      <div>
        <input
          placeholder="یادداشت تماس"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button onClick={() => post("followups")}>ثبت پیگیری</button>
      </div>
      <div>
        <input
          inputMode="numeric"
          placeholder="مبلغ قول پرداخت (تومان)"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <button onClick={() => post("promises")}>ثبت قول</button>
      </div>
      <footer>
        <button onClick={() => status("in_progress")}>در حال پیگیری</button>
        <button onClick={() => status("resolved")}>حل‌شده</button>
      </footer>
    </div>
  );
}
function Representatives({
  reps,
  unmapped,
  agent,
}: {
  reps: Rep[];
  unmapped?: number;
  agent?: AgentResult;
}) {
  return (
    <>
      <AgentPanel agent={agent} />
      <div className="fd-kpis">
        <K t="نماینده فعال" v={fa(reps.length)} n="دارای Mapping" c="teal" />
        <K
          t="مشتری بدون نماینده"
          v={fa(unmapped)}
          n="نیازمند تکمیل فایل"
          c="amber"
        />
        <K
          t="نماینده بحرانی"
          v={fa(reps.filter((x) => x.status === "critical").length)}
          n="پرتفوی پرریسک"
          c="red"
        />
      </div>
      <div className="rep-grid">
        {reps.map((r) => (
          <article key={r.representative_id}>
            <Risk
              x={
                r.status === "critical"
                  ? "critical"
                  : r.status === "attention"
                    ? "danger"
                    : "safe"
              }
            />
            <h3>{r.representative_name}</h3>
            <p>
              {fa(r.customer_count)} مشتری • {fa(r.high_risk_customer_count)}{" "}
              پرریسک
            </p>
            <b>{money(r.open_exposure)} تومان مانده باز</b>
            <small>{r.human_analysis}</small>
          </article>
        ))}
      </div>
    </>
  );
}
function Simulator({
  result,
  setResult,
}: {
  result: any;
  setResult: (x: any) => void;
}) {
  const [rate, setRate] = useState(75),
    [delay, setDelay] = useState(0),
    [opening, setOpening] = useState("");
  const run = async () =>
    setResult(
      await request("/cashflow/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_rate_percent: rate,
          payment_delay_days: delay,
          opening_cash: opening ? Number(opening) * 10 : null,
        }),
      }),
    );
  return (
    <>
      <article className="fd-panel">
        <Heading
          h="اگر چه اتفاقی بیفتد؟"
          p="نرخ وصول، جابه‌جایی پرداخت و موجودی افتتاحیه را تغییر دهید."
        />
        <div className="scenario-controls">
          <label>
            نرخ وصول چک‌ها <b>{fa(rate)}٪</b>
            <input
              type="range"
              min="0"
              max="100"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
            />
          </label>
          <label>
            تعویق پرداخت‌ها <b>{fa(delay)} روز</b>
            <input
              type="range"
              min="0"
              max="30"
              value={delay}
              onChange={(e) => setDelay(Number(e.target.value))}
            />
          </label>
          <label>
            موجودی افتتاحیه (تومان)
            <input
              inputMode="numeric"
              placeholder="مثلاً ۵۰۰٬۰۰۰٬۰۰۰"
              value={opening}
              onChange={(e) => setOpening(e.target.value)}
            />
          </label>
          <button onClick={run}>محاسبه سناریو</button>
        </div>
      </article>
      {result && (
        <>
          <div className="fd-kpis">
            <K
              t="نرخ وصول سناریو"
              v={`${fa(result.inputs?.collection_rate_percent)}٪`}
              n="ورودی انتخابی"
              c="teal"
            />
            <K
              t="اولین کسری"
              v={result.first_shortage_date || "ندارد"}
              n="با موجودی ثبت‌شده"
              c="red"
            />
            <K
              t="بدترین مانده"
              v={
                result.worst_projected_cash == null
                  ? "نامشخص"
                  : money(result.worst_projected_cash)
              }
              n="تومان"
              c="amber"
            />
          </div>
          <article className="fd-panel">
            <CashChart days={result.timeline || []} />
            <CashTable days={result.timeline || []} />
            <div className="scenario-advice">✦ {result.management_advice}</div>
          </article>
        </>
      )}
    </>
  );
}
function Alerts({ rows, refresh }: { rows: Alert[]; refresh: () => void }) {
  const update = async (id: string, status: string) => {
    await request(`/customer-alerts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    refresh();
  };
  return (
    <article className="fd-panel">
      <Heading h="مرکز هشدارها" p="تأیید، ارجاع، پیگیری و بستن هشدار" />
      <div className="alert-enterprise">
        {rows.map((a) => (
          <div key={a.alert_id}>
            <i>!</i>
            <section>
              <Risk x={a.level === "critical" ? "critical" : "danger"} />
              <h3>{a.title}</h3>
              <p>{a.payload?.description || a.payload?.reason}</p>
              <b>{a.payload?.recommended_action}</b>
            </section>
            <aside>
              <button onClick={() => update(a.alert_id, "acknowledged")}>
                تأیید
              </button>
              <button onClick={() => update(a.alert_id, "in_progress")}>
                ارجاع به پیگیری
              </button>
              <button onClick={() => update(a.alert_id, "resolved")}>
                حل‌شده
              </button>
            </aside>
          </div>
        ))}
      </div>
    </article>
  );
}
function History({ rows }: { rows: any[] }) {
  return (
    <article className="fd-panel">
      <Heading
        h="تاریخچه گزارش‌های Agent"
        p="مقایسه روند تصمیم‌ها و ریسک‌ها در اجرای روزانه"
      />
      <div className="timeline-list">
        {rows.map((r, i) => (
          <div key={r.report_id}>
            <i>{fa(rows.length - i)}</i>
            <section>
              <b>
                {r.management_summary?.analysis?.headline ||
                  "گزارش تیم Agentها"}
              </b>
              <small>
                {new Date(r.created_at).toLocaleString("fa-IR")} •{" "}
                {r.trigger_type === "scheduled" ? "اجرای خودکار" : "اجرای دستی"}
              </small>
              <p>{r.management_summary?.analysis?.summary}</p>
            </section>
            <Status
              x={
                r.management_summary?.analysis?.management_status || "attention"
              }
            />
          </div>
        ))}
      </div>
    </article>
  );
}
function Performance({ data }: { data: any }) {
  const [type, setType] = useState("collection_amount"),
    [predicted, setPredicted] = useState(""),
    [actual, setActual] = useState(""),
    [saved, setSaved] = useState(false),
    isMoney = type !== "cheque_return";
  const save = async () => {
    const factor = isMoney ? 10 : 1;
    await request("/prediction-performance/outcomes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prediction_type: type,
        predicted_value: Number(predicted) * factor,
        actual_value: Number(actual) * factor,
      }),
    });
    setSaved(true);
  };
  const show = (value: number, rowType: string) =>
    rowType === "cheque_return" ? fa(value) : `${money(value)} تومان`;
  return (
    <>
      <div className="fd-kpis">
        <K
          t="پیش‌بینی ارزیابی‌شده"
          v={fa(data?.evaluated_predictions)}
          n="نتیجه واقعی ثبت‌شده"
          c="teal"
        />
        <K
          t="میانگین خطای مطلق"
          v={
            data?.mean_absolute_error == null
              ? "در انتظار داده"
              : fa(data.mean_absolute_error)
          }
          n="براساس واحد هر پیش‌بینی"
          c="amber"
        />
      </div>
      <article className="fd-panel">
        <Heading
          h="ثبت نتیجه واقعی"
          p="تمام مبلغ‌ها را به تومان وارد کنید؛ نتیجه برگشت بدون واحد پولی ثبت می‌شود."
        />
        <div className="outcome-form">
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="collection_amount">مبلغ وصول</option>
            <option value="cheque_return">برگشت چک</option>
            <option value="cash_balance">مانده نقدی</option>
          </select>
          <input
            placeholder={
              isMoney ? "مقدار پیش‌بینی‌شده (تومان)" : "مقدار پیش‌بینی‌شده"
            }
            value={predicted}
            onChange={(e) => setPredicted(e.target.value)}
          />
          <input
            placeholder={isMoney ? "مقدار واقعی (تومان)" : "مقدار واقعی"}
            value={actual}
            onChange={(e) => setActual(e.target.value)}
          />
          <button onClick={save}>ثبت نتیجه</button>
          {saved && (
            <span>ثبت شد؛ با نوسازی صفحه در محاسبه دقت دیده می‌شود.</span>
          )}
        </div>
      </article>
      <article className="fd-panel">
        <Heading
          h="کنترل کیفیت پیش‌بینی"
          p="مقایسه پیش‌بینی با وصول، برگشت و نقدینگی واقعی"
        />
        {data?.items?.length ? (
          <div className="fd-table">
            <table>
              <thead>
                <tr>
                  <th>نوع</th>
                  <th>مقدار پیش‌بینی</th>
                  <th>مقدار واقعی</th>
                  <th>زمان نتیجه</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((x: any) => (
                  <tr key={x.outcome_id}>
                    <td>{x.prediction_type}</td>
                    <td>{show(x.predicted_value, x.prediction_type)}</td>
                    <td>{show(x.actual_value, x.prediction_type)}</td>
                    <td>{x.outcome_at}</td>
                    <td>{x.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="fd-empty">
            {data?.message ||
              "بعد از رسیدن سررسیدها، نتیجه واقعی برای سنجش دقت ثبت می‌شود."}
          </div>
        )}
      </article>
    </>
  );
}
function Settings({
  values,
  setValues,
}: {
  values: Record<string, any>;
  setValues: (x: any) => void;
}) {
  const save = async () => {
    const j = await request("/policies", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    setValues(j.values);
  };
  return (
    <article className="fd-panel">
      <Heading
        h="قوانین مالی و اتوماسیون"
        p="بدون تغییر کد، آستانه‌ها و زمان اجرای روزانه را تنظیم کنید."
      />
      <div className="settings-grid">
        <Setting
          t="حداکثر مدت چک"
          unit="روز"
          k="allowed_term_days"
          values={values}
          set={setValues}
        />
        <Setting
          t="احتمال برگشت پرریسک"
          unit="درصد"
          k="high_return_probability_percent"
          values={values}
          set={setValues}
        />
        <Setting
          t="نسبت معوق بحرانی"
          unit="درصد"
          k="critical_overdue_ratio_percent"
          values={values}
          set={setValues}
        />
        <Setting
          t="آستانه روزهای فشار نقدی"
          unit="روز"
          k="cash_pressure_days_threshold"
          values={values}
          set={setValues}
        />
        <Setting
          t="ساعت اجرای روزانه"
          unit="ساعت"
          k="daily_run_hour"
          values={values}
          set={setValues}
        />
        <Setting
          t="دقیقه اجرای روزانه"
          unit="دقیقه"
          k="daily_run_minute"
          values={values}
          set={setValues}
        />
      </div>
      <div className="notification-settings">
        <b>کانال‌های هشدار</b>
        {["dashboard", "email", "sms"].map((x) => (
          <label key={x}>
            <input
              type="checkbox"
              checked={(values.notification_channels || []).includes(x)}
              onChange={(e) =>
                setValues({
                  ...values,
                  notification_channels: e.target.checked
                    ? [...(values.notification_channels || []), x]
                    : (values.notification_channels || []).filter(
                        (v: string) => v !== x,
                      ),
                })
              }
            />
            {x === "dashboard" ? "داشبورد" : x === "email" ? "ایمیل" : "پیامک"}
          </label>
        ))}
      </div>
      <button className="save-settings" onClick={save}>
        ذخیره قوانین
      </button>
    </article>
  );
}
function Setting({
  t,
  unit,
  k,
  values,
  set,
}: {
  t: string;
  unit: string;
  k: string;
  values: Record<string, any>;
  set: (x: any) => void;
}) {
  return (
    <label>
      <span>
        {t}
        <small>{unit}</small>
      </span>
      <input
        type="number"
        value={values[k] ?? ""}
        onChange={(e) => set({ ...values, [k]: Number(e.target.value) })}
      />
    </label>
  );
}
function Agents({
  agents,
  manager,
}: {
  agents?: Record<string, AgentResult>;
  manager?: AgentResult;
}) {
  return (
    <>
      <ManagerPanel a={manager?.analysis} />
      <div className="agent-grid large">
        {Object.entries(agents || {}).map(([key, a]) => (
          <AgentCard key={key} agent={a} />
        ))}
      </div>
      <article className="fd-panel agent-flow">
        <Heading
          h="نحوه همکاری Agentها"
          p="Finance Manager Agent عدد جدید تولید نمی‌کند؛ خروجی تخصصی Agentها را جمع‌بندی می‌کند."
        />
        <div>
          <span>رفتار مشتری</span>
          <span>ریسک چک</span>
          <span>نقدینگی</span>
          <span>وصول</span>
          <span>نمایندگان</span>
          <b>Finance Manager Agent</b>
        </div>
      </article>
    </>
  );
}

function LegacyCustomerProfile({
  c,
  close,
  refresh,
}: {
  c: Customer;
  close: () => void;
  refresh: () => void;
}) {
  const [detail, setDetail] = useState<Customer>(c),
    [loadingDetail, setLoadingDetail] = useState(true),
    [detailError, setDetailError] = useState("");
  useEffect(() => {
    let active = true;
    if (!c.counterpart_ref) {
      setLoadingDetail(false);
      return;
    }
    request(`/customer-intelligence/${c.counterpart_ref}`)
      .then((j) => {
        if (active && j.customer) setDetail(j.customer);
      })
      .catch((e) => {
        if (active)
          setDetailError(
            e instanceof Error ? e.message : "جزئیات چک‌ها دریافت نشد",
          );
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [c.counterpart_ref]);
  const create = async () => {
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        counterpart_ref: detail.counterpart_ref,
        counterpart_name: cname(detail),
        priority: risk(detail) === "critical" ? "critical" : "high",
      }),
    });
    refresh();
    close();
  };
  const total = detail.historical_total_cheque_amount || 0,
    collected = detail.collected_cheque_amount || 0,
    open = detail.open_exposure || 0,
    returned = detail.returned_cheque_amount || 0,
    percent = total ? Math.min(100, (collected / total) * 100) : 0;
  return (
    <div className="fd-backdrop" onClick={close}>
      <article
        className="customer-profile-expanded"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="profile-close" onClick={close}>
          ×
        </button>
        <div className="profile-title">
          <div>
            <Risk x={risk(detail)} />
            <h2>{cname(detail)}</h2>
            <p>ریز سوابق وصول و وضعیت تک‌تک چک‌های دریافتی باز</p>
          </div>
          <span className="profile-source">SQL Server • اطلاعات لحظه‌ای</span>
        </div>
        {detailError && <div className="profile-warning">{detailError}</div>}
        <div className="modal-metrics profile-metrics">
          <K
            t="کل چک‌های دریافت‌شده"
            v={money(total)}
            n={`${fa(detail.historical_cheque_count || 0)} فقره • تومان`}
            c="blue"
          />
          <K
            t="وصول‌شده قطعی"
            v={money(collected)}
            n={`${fa(detail.collected_cheque_count || 0)} فقره • State=3`}
            c="teal"
          />
          <K
            t="چک‌های دریافتی باز"
            v={money(open)}
            n={`${fa(detail.open_cheque_count || 0)} فقره • تومان`}
            c="amber"
          />
          <K
            t="برگشتی/واخواست‌شده"
            v={money(returned)}
            n={`${fa(detail.returned_cheque_count || 0)} فقره • تومان`}
            c="red"
          />
        </div>
        <section className="collection-progress">
          <header>
            <div>
              <b>نسبت وصول قطعی از کل سوابق</b>
              <small>
                مبلغ وصول‌شده تقسیم بر کل مبلغ چک‌های ثبت‌شده در بازه تحلیل
              </small>
            </div>
            <strong>{fa(percent)}٪</strong>
          </header>
          <div>
            <i style={{ width: `${percent}%` }} />
          </div>
          <footer>
            <span>وصول‌شده: {money(collected)} تومان</span>
            <span>هنوز باز: {money(open)} تومان</span>
          </footer>
        </section>
        <CustomerSqlAudit c={detail as CustomerAudit} />
        <section className="profile-cheques">
          <div className="profile-section-title">
            <div>
              <h3>ریز چک‌های باز این مشتری</h3>
              <p>مبلغ، تاریخ دریافت، تاریخ سررسید و زمان باقی‌مانده</p>
            </div>
            <b>
              {fa(detail.open_cheques?.length || detail.open_cheque_count || 0)}{" "}
              فقره
            </b>
          </div>
          {loadingDetail ? (
            <div className="profile-loading">
              در حال دریافت ریز چک‌ها از SQL…
            </div>
          ) : detail.open_cheques?.length ? (
            <div className="profile-cheque-table">
              <table>
                <thead>
                  <tr>
                    <th>شناسه چک</th>
                    <th>شماره چک</th>
                    <th>مبلغ</th>
                    <th>تاریخ دریافت</th>
                    <th>تاریخ سررسید</th>
                    <th>مدت چک</th>
                    <th>زمان باقی‌مانده</th>
                    <th>وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.open_cheques.map((x, i) => {
                    const d = daysToDue(x);
                    return (
                      <tr
                        key={x.cheque_id || i}
                        className={
                          d !== undefined && d < 0
                            ? "overdue-row"
                            : d !== undefined && d <= 7
                              ? "due-soon-row"
                              : ""
                        }
                      >
                        <td>{fa(x.cheque_id)}</td>
                        <td>
                          <b>
                            {fa(
                              x.serial_number ||
                                x.sayad_number ||
                                x.document_number ||
                                "—",
                            )}
                          </b>
                        </td>
                        <td>
                          <b>{money(x.amount || 0)} تومان</b>
                        </td>
                        <td>
                          {x.receipt_date_jalali || x.receipt_date || "—"}
                        </td>
                        <td>{x.due_date_jalali || x.due_date || "—"}</td>
                        <td>{fa(x.term_days)} روز</td>
                        <td>
                          <span
                            className={`profile-due ${d === undefined ? "unknown" : d < 0 ? "late" : d <= 7 ? "soon" : "normal"}`}
                          >
                            {remainingLabel(x)}
                          </span>
                        </td>
                        <td>{x.state_label || "باز"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="profile-loading">
              چک باز قابل نمایش برای این مشتری وجود ندارد.
            </div>
          )}
        </section>
        <div className="profile-bottom">
          <div>
            <h3>دلایل ارزیابی</h3>
            <ul>
              {[
                ...(detail.late_payment_risk?.reasons || []),
                ...(detail.evidence || []),
              ].map((x, i) => (
                <li key={i}>{textOf(x)}</li>
              ))}
            </ul>
          </div>
          <div className="credit-advice">
            <b>شرایط پیشنهادی چک بعدی</b>
            <span>
              {risk(detail) === "critical"
                ? "تا تأیید مدیر مالی و کاهش چک‌های سررسیدگذشته، چک جدید پذیرفته نشود."
                : risk(detail) === "danger"
                  ? "سررسید حداکثر ۹۰ روز و مبلغ محدود پذیرفته شود."
                  : "شرایط جاری با پایش ماهانه قابل ادامه است."}
            </span>
          </div>
        </div>
        <p className="profile-note">
          «وصول‌شده» براساس وضعیت قطعی چک در راهکاران است؛ این عدد لزوماً معادل
          تسویه کامل تمام فاکتورهای فروش مشتری نیست.
        </p>
        <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button>
      </article>
    </div>
  );
}
function CashChart({ days }: { days: CashDay[] }) {
  let shown = days.filter(
      (_, i) => i % Math.max(1, Math.ceil(days.length / 15)) === 0,
    ),
    vals = shown.map((x) => x.projected_cash ?? x.cumulative_net_change ?? 0),
    min = Math.min(...vals, 0),
    max = Math.max(...vals, 1),
    range = max - min || 1,
    pts = vals
      .map(
        (v, i) =>
          `${20 + (i * 560) / Math.max(vals.length - 1, 1)},${175 - ((v - min) / range) * 135}`,
      )
      .join(" ");
  return days.length ? (
    <svg className="cash-chart" viewBox="0 0 600 210">
      <line
        x1="20"
        y1={175 - ((0 - min) / range) * 135}
        x2="580"
        y2={175 - ((0 - min) / range) * 135}
      />
      <polyline points={pts} />
      {vals.map((v, i) => (
        <circle
          key={i}
          cx={20 + (i * 560) / Math.max(vals.length - 1, 1)}
          cy={175 - ((v - min) / range) * 135}
          r="4"
          className={v < 0 ? "neg" : ""}
        />
      ))}
    </svg>
  ) : (
    <div className="fd-empty">داده نقدینگی هنوز دریافت نشده است.</div>
  );
}
function CashTable({ days }: { days: CashDay[] }) {
  return (
    <div className="cash-table-wrap">
      <table className="cash-table">
        <thead>
          <tr>
            <th>تاریخ</th>
            <th>ورودی</th>
            <th>خروجی</th>
            <th>خالص روز</th>
            <th>خالص تجمعی</th>
            <th>مانده</th>
            <th>وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d, i) => {
            let n = d.daily_net_change || 0,
              s = d.cash_shortage ? "critical" : n < 0 ? "pressure" : "good";
            return (
              <tr key={d.date || i} className={s}>
                <td>
                  <b>{d.date_jalali || d.date}</b>
                </td>
                <td className="positive">+ {money(d.projected_inflow)}</td>
                <td className="negative">− {money(d.projected_outflow)}</td>
                <td className={n < 0 ? "negative" : "positive"}>{money(n)}</td>
                <td>{money(d.cumulative_net_change)}</td>
                <td>
                  {d.projected_cash == null
                    ? "تعریف نشده"
                    : money(d.projected_cash)}
                </td>
                <td>
                  <span className={`cash-status ${s}`}>
                    {s === "critical"
                      ? "کسری"
                      : s === "pressure"
                        ? "فشار نقدی"
                        : "مناسب"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
function K({
  t,
  v,
  n,
  c,
  detail,
}: {
  t: string;
  v: string;
  n: string;
  c: string;
  detail?: InsightPayload;
}) {
  return (
    <button
      type="button"
      className={`fd-kpi ${c} drillable`}
      onClick={() =>
        openInsight(
          detail || {
            title: t,
            tone: c,
            subtitle: "آمار شاخص انتخاب‌شده",
            stats: [
              { label: "مقدار فعلی", value: v },
              { label: "توضیح / واحد", value: n },
            ],
          },
        )
      }
    >
      <small>{t}</small>
      <b>{v}</b>
      <em>{n}</em>
    </button>
  );
}
function Heading({ h, p }: { h: string; p: string }) {
  return (
    <div className="fd-heading">
      <h2>{h}</h2>
      <p>{p}</p>
    </div>
  );
}
function Risk({ x }: { x: string }) {
  return (
    <span className={`fd-badge ${x}`}>
      {x === "critical" ? "بحرانی" : x === "danger" ? "نیازمند توجه" : "مناسب"}
    </span>
  );
}
function Status({ x }: { x: string }) {
  return (
    <span className={`management-status ${x}`}>
      {x === "critical" ? "بحرانی" : x === "healthy" ? "مناسب" : "نیازمند توجه"}
    </span>
  );
}
function label(v: View) {
  return v === "receivedCheques"
    ? "چک‌های دریافتی"
    : v === "issuedCheques"
      ? "چک‌های پرداختی / صادرشده"
      : menu.find((x) => x[0] === v)?.[2] || v;
}
function description(v: View) {
  return (
    {
      management: "جمع‌بندی یکپارچه همه Agentهای مالی برای تصمیم مدیر",
      customers: "رفتار، اعتبار، ریسک و پرونده وصول هر مشتری",
      cheques: "انتخاب جریان دریافتی یا پرداختی و ورود از خلاصه به جزئیات",
      cashBank:
        "ریز دریافت و پرداخت نقدی و بانکی، حواله‌ها و انتقال‌های داخلی همراه Agent مستقل",
      receivedCheques: "مطالبات، وصول، ریسک و سررسید چک‌های دریافتی",
      issuedCheques: "تعهدات و سررسید چک‌های پرداختی و صادرشده",
      cashflow: "Forecast روزانه همراه Cash Flow Agent",
      monthlyExcel:
        "آپلود Excel روزانه، تشخیص خودکار ماه شمسی و تحلیل از ابتدای همان ماه",
      collections: "مسئول، مهلت، تماس، قول پرداخت و نتیجه پیگیری",
      representatives: "کیفیت پرتفوی و وصول به تفکیک نماینده",
      simulator: "بررسی اثر نرخ وصول و جابه‌جایی پرداخت‌ها",
      alerts: "هشدارهای قابل ارجاع و قابل بستن",
      history: "روند تغییر گزارش‌های مدیریتی در طول زمان",
      performance: "مقایسه پیش‌بینی‌ها با نتایج واقعی",
      settings: "مدیریت آستانه‌ها و زمان اجرای اتوماسیون",
      agents: "وضعیت و خروجی همه Agentهای تخصصی",
    } as Record<View, string>
  )[v];
}

function metricRows(value: any, limit = 5): ChartRow[] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value)
    .filter(([, v]) => typeof v === "number" && Number.isFinite(v))
    .slice(0, limit)
    .map(([key, v], i) => ({
      label: fieldFa[key] || key.replaceAll("_", " "),
      value: Number(v),
      tone: ["teal", "blue", "amber", "red", "green"][i % 5],
    }));
}
function HorizontalMetrics({ rows }: { rows: ChartRow[] }) {
  const max = Math.max(...rows.map((x) => Math.abs(x.value)), 1);
  return (
    <div className="agent-hbars">
      {rows.map((x, i) => (
        <div className="agent-hbar" key={`${x.label}-${i}`}>
          <header>
            <span>{x.label}</span>
            <b>
              {textOf(
                x.value,
                x.label.includes("مبلغ") ||
                  x.label.includes("نقد") ||
                  x.label.includes("وصول")
                  ? "amount_rial"
                  : "",
              )}
            </b>
          </header>
          <div>
            <i
              className={x.tone}
              style={{
                width: `${Math.max(4, (Math.abs(x.value) / max) * 100)}%`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
function CompactDonut({ good, risk }: { good: number; risk: number }) {
  const total = Math.max(good + risk, 1),
    riskPct = (risk / total) * 100;
  return (
    <div className="agent-donut-layout">
      <div
        className="agent-donut"
        style={{
          background: `conic-gradient(#ef6461 0 ${riskPct}%,#18a98b ${riskPct}% 100%)`,
        }}
      >
        <span>
          <b>{fa(good + risk)}</b>
          <small>سیگنال</small>
        </span>
      </div>
      <div>
        <p>
          <i className="good" />
          مثبت <b>{fa(good)}</b>
        </p>
        <p>
          <i className="risk" />
          ریسک <b>{fa(risk)}</b>
        </p>
      </div>
    </div>
  );
}
function AgentVisualSummary({ agent }: { agent?: AgentResult }) {
  const a = agent?.analysis || {},
    p = a.prediction || {},
    rule = agent?.rule_output || {},
    assessments = Array.isArray(rule.assessments) ? rule.assessments : [];
  const hasCheque =
    assessments.length > 0 || Number(rule.processed_cheque_count) > 0;
  if (hasCheque) {
    const levels = ["low", "medium", "high", "critical"].map((level, i) => ({
      label:
        level === "low"
          ? "کم"
          : level === "medium"
            ? "متوسط"
            : level === "high"
              ? "بالا"
              : "بحرانی",
      value: assessments.filter((x: any) => x.risk_level === level).length,
      tone: ["green", "amber", "red", "critical"][i],
    }));
    const due = [
      {
        label: "سررسیدگذشته",
        value: assessments.filter((x: any) => Number(x.days_to_due) < 0).length,
        tone: "critical",
      },
      {
        label: "تا ۷ روز",
        value: assessments.filter(
          (x: any) => Number(x.days_to_due) >= 0 && Number(x.days_to_due) <= 7,
        ).length,
        tone: "red",
      },
      {
        label: "۸ تا ۳۰ روز",
        value: assessments.filter(
          (x: any) => Number(x.days_to_due) > 7 && Number(x.days_to_due) <= 30,
        ).length,
        tone: "amber",
      },
      {
        label: "بیش از ۳۰ روز",
        value: assessments.filter((x: any) => Number(x.days_to_due) > 30)
          .length,
        tone: "teal",
      },
    ];
    const total =
        Number(rule.processed_cheque_count) || assessments.length || 1,
      over = Number(rule.over_policy_count) || 0;
    return (
      <section className="agent-visual-grid">
        <article className="agent-visual-card">
          <header>
            <b>توزیع سطح ریسک چک‌ها</b>
            <small>براساس خروجی موتور قواعد</small>
          </header>
          <VerticalBars rows={levels} />
        </article>
        <article className="agent-visual-card">
          <header>
            <b>فاصله تا سررسید</b>
            <small>از نزدیک‌ترین موعد تا دوره‌های بعد</small>
          </header>
          <HorizontalMetrics rows={due} />
        </article>
        <article className="agent-visual-card policy-card">
          <header>
            <b>کنترل سیاست ۹۰ روزه</b>
            <small>سهم چک‌های خارج از سیاست شرکت</small>
          </header>
          <div
            className="policy-ring"
            style={{
              background: `conic-gradient(#ef6461 0 ${Math.min(100, (over / total) * 100)}%,#e5edf0 ${Math.min(100, (over / total) * 100)}% 100%)`,
            }}
          >
            <span>
              <b>{fa(Math.round((over / total) * 100))}٪</b>
              <small>
                {fa(over)} از {fa(total)} چک
              </small>
            </span>
          </div>
        </article>
      </section>
    );
  }
  const next = metricRows(p.next_7_days),
    month = metricRows(p.end_of_month);
  return (
    <section className="agent-visual-grid generic">
      <article className="agent-visual-card">
        <header>
          <b>شاخص‌های ۷ روز آینده</b>
          <small>خروجی عددی پیش‌بینی Agent</small>
        </header>
        {next.length ? (
          <HorizontalMetrics rows={next} />
        ) : (
          <div className="agent-empty-chart">هنوز شاخص عددی ثبت نشده است</div>
        )}
      </article>
      <article className="agent-visual-card">
        <header>
          <b>تصویر پایان ماه</b>
          <small>مقایسه شاخص‌های کلیدی</small>
        </header>
        {month.length ? (
          <HorizontalMetrics rows={month} />
        ) : (
          <div className="agent-empty-chart">در انتظار داده پایان ماه</div>
        )}
      </article>
      <article className="agent-visual-card">
        <header>
          <b>تراز سیگنال‌ها</b>
          <small>نقاط مثبت در برابر ریسک‌ها</small>
        </header>
        <CompactDonut
          good={(a.good_signals || []).length}
          risk={(a.risks || a.bad_signals || []).length}
        />
      </article>
    </section>
  );
}
function ManagerPanel({ a }: { a?: Analysis }) {
  const p = a?.prediction || {},
    s = a?.scenarios || {},
    next = metricRows(p.next_7_days),
    month = metricRows(p.end_of_month),
    kpis = a?.executive_kpis || [],
    actions = a?.recommended_actions || [];
  const kpiValue = (item: (typeof kpis)[number]) => {
    if (item.available === false) return "داده کافی نیست";
    if (item.format === "percent") return `${fa(item.value || 0)}٪`;
    if (item.format === "count") return fa(item.value || 0);
    if (item.format === "money_signed") {
      const value = item.value_rial || 0;
      return `${money(Math.abs(value))} تومان ${value >= 0 ? "مثبت" : "منفی"}`;
    }
    return `${money(item.value_rial || 0)} تومان`;
  };
  return (
    <article className="manager-panel decision-manager manager-visual">
      <div className="manager-head">
        <i>✦</i>
        <div>
          <small>Finance Manager Agent</small>
          <h2>{textOf(a?.headline) || "تیم Agentها هنوز اجرا نشده است"}</h2>
        </div>
        <Status x={a?.management_status || "attention"} />
      </div>
      <p>
        {textOf(a?.summary) ||
          "دکمه اجرای همه Agentها را بزنید تا خلاصه مدیریتی، پیش‌بینی و برنامه اقدام ساخته شود."}
      </p>
      {a && (
        <>
          {!!kpis.length && (
            <section className="manager-executive-kpis">
              {kpis.map((item, index) => (
                <article className={item.tone || "blue"} key={index}>
                  <small>{item.label}</small>
                  <b>{kpiValue(item)}</b>
                  <span>
                    {item.available === false
                      ? "نیازمند تکمیل ورودی"
                      : "آخرین اجرای تیم Agentها"}
                  </span>
                </article>
              ))}
            </section>
          )}
          <div className="manager-chart-grid">
            <section>
              <header>
                <b>چشم‌انداز ۷ روزه</b>
                <small>{textOf(p.next_7_days)}</small>
              </header>
              {next.length ? (
                <HorizontalMetrics rows={next} />
              ) : (
                <div className="agent-empty-chart">در انتظار داده</div>
              )}
            </section>
            <section>
              <header>
                <b>پیش‌بینی پایان ماه</b>
                <small>{textOf(p.end_of_month)}</small>
              </header>
              {month.length ? (
                <HorizontalMetrics rows={month} />
              ) : (
                <div className="agent-empty-chart">در انتظار داده</div>
              )}
            </section>
            <section>
              <header>
                <b>تراز تصمیم</b>
                <small>
                  سطح اطمینان:{" "}
                  {p.confidence === "high"
                    ? "زیاد"
                    : p.confidence === "medium"
                      ? "متوسط"
                      : "کم"}
                </small>
              </header>
              <CompactDonut
                good={(a.good_signals || []).length}
                risk={(a.risks || []).length}
              />
            </section>
          </div>
          {Object.keys(s).length > 0 && (
            <div className="manager-scenarios">
              {(["optimistic", "base", "pessimistic"] as const).map((k, i) => (
                <section key={k}>
                  <b>
                    {i === 0
                      ? "خوش‌بینانه"
                      : i === 1
                        ? "مسیر پیشنهادی"
                        : "بدبینانه"}
                  </b>
                  <span>{textOf(s[k])}</span>
                </section>
              ))}
            </div>
          )}
        </>
      )}
      <div className="manager-columns">
        <div>
          <b>نقاط مثبت</b>
          {(a?.good_signals || []).slice(0, 4).map((x, i) => (
            <span key={i}>✓ {textOf(x)}</span>
          ))}
        </div>
        <div>
          <b>ریسک‌های اصلی</b>
          {(a?.risks || []).slice(0, 4).map((x, i) => (
            <span key={i}>! {textOf(x)}</span>
          ))}
        </div>
      </div>
      {!!actions.length && (
        <section className="manager-action-board">
          <header>
            <div>
              <b>برنامه اقدام اجرایی مدیر</b>
              <small>
                مرتب‌شده براساس فوریت؛ همراه مسئول، مهلت، دلیل و اثر مورد انتظار
              </small>
            </div>
            <em>{fa(actions.length)} اقدام</em>
          </header>
          <div>
            {actions.slice(0, 6).map((item, index) => (
              <article key={index} className={item.priority || "medium"}>
                <i>{fa(index + 1)}</i>
                <section>
                  <header>
                    <b>{item.action || "اقدام نیازمند تعیین عنوان"}</b>
                    <em>
                      {item.priority === "critical"
                        ? "فوری"
                        : item.priority === "high"
                          ? "مهم"
                          : "متوسط"}
                    </em>
                  </header>
                  <p>{item.why || "دلیل در اجرای بعدی تکمیل می‌شود."}</p>
                  <footer>
                    <span>
                      مسئول: <b>{item.owner || "مدیر مالی"}</b>
                    </span>
                    <span>
                      مهلت: <b>{item.deadline || "این هفته"}</b>
                    </span>
                    <span>
                      اثر: <b>{item.expected_effect || "کاهش ریسک"}</b>
                    </span>
                  </footer>
                </section>
              </article>
            ))}
          </div>
        </section>
      )}
      {a?.next_best_action && (
        <div className="next-action">
          <b>بهترین اقدام بعدی</b>
          {textOf(a.next_best_action)}
        </div>
      )}
    </article>
  );
}
function AgentPanel({ agent }: { agent?: AgentResult }) {
  const a = agent?.analysis,
    p = a?.prediction || {},
    s = a?.scenarios || {},
    actions = a?.recommended_actions || [];
  return (
    <article className="section-agent decision-agent agent-panel-v2">
      <div className="agent-title-row">
        <i>✦</i>
        <span>
          <small>{agent?.metadata?.agent_name || "Agent تخصصی این بخش"}</small>
          <b>{textOf(a?.headline) || "تحلیل Agent هنوز آماده نیست"}</b>
        </span>
        <em>
          {agent?.metadata?.mode === "llm" ||
          agent?.metadata?.agent_mode === "llm"
            ? "LLM فعال"
            : "موتور تصمیم‌یار"}
        </em>
      </div>
      <p>
        {textOf(a?.summary) ||
          textOf(a?.human_summary) ||
          "دکمه اجرای همه Agentها را بزنید تا پیش‌بینی و راهکار ساخته شود."}
      </p>
      {a && (
        <>
          <AgentVisualSummary agent={agent} />
          <section className="decision-forecast">
            <div>
              <small>۷ روز آینده</small>
              <b>{textOf(p.next_7_days) || "در انتظار داده"}</b>
            </div>
            <div>
              <small>پیش‌بینی پایان ماه</small>
              <b>
                {textOf(p.end_of_month) ||
                  textOf(a.future_outlook) ||
                  "در انتظار داده"}
              </b>
            </div>
            <div>
              <small>اطمینان</small>
              <b>
                {p.confidence === "high"
                  ? "زیاد"
                  : p.confidence === "medium"
                    ? "متوسط"
                    : "کم"}
              </b>
            </div>
          </section>
          <section className="scenario-strip">
            {(["optimistic", "base", "pessimistic"] as const).map((key, i) => (
              <div className={key} key={key}>
                <small>
                  {i === 0
                    ? "خوش‌بینانه"
                    : i === 1
                      ? "سناریوی پایه"
                      : "بدبینانه"}
                </small>
                <span>{textOf(s[key]) || "—"}</span>
              </div>
            ))}
          </section>
          <div className="decision-risks">
            {(a.risks || a.bad_signals || []).slice(0, 4).map((x, i) => (
              <span key={i}>! {textOf(x)}</span>
            ))}
          </div>
          <section className="decision-actions">
            {actions.slice(0, 4).map((x, i) => (
              <article key={i}>
                <header>
                  <b>{textOf(x.action)}</b>
                  <em className={x.priority}>
                    {x.priority === "critical"
                      ? "فوری"
                      : x.priority === "high"
                        ? "بالا"
                        : "متوسط"}
                  </em>
                </header>
                <p>{textOf(x.why)}</p>
                <footer>
                  <span>اثر: {textOf(x.expected_effect) || "کاهش ریسک"}</span>
                  <span>
                    {textOf(x.owner) || "مدیر مالی"} •{" "}
                    {textOf(x.deadline) || "این هفته"}
                  </span>
                </footer>
              </article>
            ))}
          </section>
          {a.next_best_action && (
            <div className="next-action">
              <b>بهترین اقدام بعدی</b>
              {textOf(a.next_best_action)}
            </div>
          )}
        </>
      )}
    </article>
  );
}
function AgentCard({ agent }: { agent: AgentResult }) {
  const a = agent.analysis || {},
    good = (a.good_signals || []).length,
    risk = (a.risks || a.bad_signals || []).length,
    actions = (a.recommended_actions || []).length,
    total = Math.max(good + risk + actions, 1);
  return (
    <button
      type="button"
      className="agent-card-v2 drillable"
      onClick={() =>
        openInsight({
          title: agent.metadata?.agent_name || "Agent مالی",
          subtitle: textOf(a.headline),
          tone: a.management_status,
          stats: [
            { label: "سیگنال مثبت", value: fa(good) },
            { label: "ریسک شناسایی‌شده", value: fa(risk) },
            { label: "اقدام پیشنهادی", value: fa(actions) },
            {
              label: "نوع تحلیل",
              value:
                agent.metadata?.mode === "llm" ||
                agent.metadata?.agent_mode === "llm"
                  ? "هوش مصنوعی"
                  : "قاعده‌محور",
            },
          ],
          notes: [
            ...(a.risks || a.bad_signals || []).slice(0, 3).map(textOf),
            ...(a.recommended_actions || [])
              .slice(0, 2)
              .map((x) => textOf(x.action)),
          ],
        })
      }
    >
      <div>
        <i>⬡</i>
        <span>
          <b>{agent.metadata?.agent_name}</b>
          <small>
            {agent.metadata?.mode === "llm" ||
            agent.metadata?.agent_mode === "llm"
              ? "هوش مصنوعی فعال"
              : "تحلیل قاعده‌محور"}
          </small>
        </span>
        <Status x={a.management_status || "attention"} />
      </div>
      <p>{textOf(a.headline)}</p>
      <div className="agent-card-bars">
        <span>
          <i className="good" style={{ width: `${(good / total) * 100}%` }} />
          مثبت {fa(good)}
        </span>
        <span>
          <i className="risk" style={{ width: `${(risk / total) * 100}%` }} />
          ریسک {fa(risk)}
        </span>
        <span>
          <i
            className="action"
            style={{ width: `${(actions / total) * 100}%` }}
          />
          اقدام {fa(actions)}
        </span>
      </div>
      <em>{textOf(a.next_best_action)}</em>
    </button>
  );
}

const behaviorFa: Record<string, string> = {
  excellent: "بسیار خوش‌قول",
  good: "خوش‌قول",
  review: "نیازمند بررسی",
  weak: "بدقول",
  high_risk: "پرریسک",
  unknown: "در انتظار سابقه",
};
const creditPolicyFa: Record<string, string> = {
  accept_normal: "پذیرش عادی",
  accept_with_monitoring: "پذیرش همراه با پایش",
  accept_with_guarantee: "پذیرش فقط با تضمین تکمیلی",
  manual_approval_required: "نیازمند تأیید مدیر مالی",
  review: "نیازمند بررسی",
};
function CustomerReliability({ c }: { c: Customer }) {
  const behavior: any = c.customer_behavior || {},
    decision: any = c.credit_decision || {};
  const score = Math.max(
    0,
    Math.min(100, Number(behavior.reliability_score ?? 50)),
  );
  const collection = Math.max(
    0,
    Math.min(100, Number(behavior.historical_collection_rate_percent ?? 0)),
  );
  const returned = Math.max(
    0,
    Math.min(100, Number(behavior.historical_return_rate_percent ?? 0)),
  );
  const reliance = Math.max(
    0,
    Math.min(100, Number(decision.recommended_reliance_percent ?? 0)),
  );
  const tone = score >= 70 ? "#18a98b" : score >= 50 ? "#eea63b" : "#df6269";
  const confidence = behavior.history_confidence || "low";
  const policy = decision.policy || "review";
  const reasons = (decision.reasons || c.evidence || []).slice(0, 4);
  const breakdown = behavior.score_breakdown || [],
    improvements = decision.improvement_actions || [],
    calc = decision.reliance_calculation || {};
  return (
    <section className="reliability-panel">
      <div className="reliability-head">
        <div>
          <h3>سابقه خوش‌قولی و پیشنهاد اعتبار</h3>
          <p>تحلیل سابقه وصول، برگشت، چک‌های عقب‌افتاده و مبلغ تاریخی مشتری</p>
        </div>
        <span className={`history-confidence ${confidence}`}>
          اطمینان سابقه:{" "}
          {confidence === "high"
            ? "زیاد"
            : confidence === "medium"
              ? "متوسط"
              : "کم"}
        </span>
      </div>
      <div className="reliability-main">
        <div
          className="reliability-ring"
          style={{
            background: `conic-gradient(${tone} 0 ${score}%,#e6edef ${score}% 100%)`,
          }}
        >
          <span>
            <b>{fa(score)}</b>
            <small>امتیاز از ۱۰۰</small>
            <em style={{ color: tone }}>
              {behaviorFa[behavior.behavior_level || "unknown"] ||
                "نیازمند بررسی"}
            </em>
          </span>
        </div>
        <div className="reliability-bars">
          <div className="reliability-bar collection">
            <header>
              <span>نرخ وصول تاریخی</span>
              <b>{fa(collection)}٪</b>
            </header>
            <div>
              <i style={{ width: `${collection}%` }} />
            </div>
          </div>
          <div className="reliability-bar return">
            <header>
              <span>نرخ برگشت تاریخی</span>
              <b>{fa(returned)}٪</b>
            </header>
            <div>
              <i style={{ width: `${returned}%` }} />
            </div>
          </div>
          <div className="reliability-bar reliance">
            <header>
              <span>درصد پیشنهادی اتکا به چک</span>
              <b>{fa(reliance)}٪</b>
            </header>
            <div>
              <i style={{ width: `${reliance}%` }} />
            </div>
          </div>
        </div>
      </div>
      <div className="credit-decision-grid">
        <div
          className={`policy ${policy === "manual_approval_required" ? "block" : policy === "accept_with_guarantee" ? "review" : ""}`}
        >
          <small>سیاست پیشنهادی پذیرش چک</small>
          <b>{creditPolicyFa[policy] || "نیازمند بررسی"}</b>
        </div>
        <div>
          <small>سقف پیشنهادی چک جدید</small>
          <b>
            {decision.recommended_max_new_cheque_amount_rial == null
              ? "پس از تکمیل سابقه تعیین می‌شود"
              : `${money(decision.recommended_max_new_cheque_amount_rial)} تومان`}
          </b>
        </div>
        <div>
          <small>سوابق قطعی بررسی‌شده</small>
          <b>{fa(behavior.resolved_cheque_count || 0)} فقره</b>
        </div>
      </div>
      {reasons.length > 0 && (
        <div className="reliability-reasons">
          <b>چرا این پیشنهاد ساخته شده است؟</b>
          <ul>
            {reasons.map((x, i) => (
              <li key={i}>{textOf(x)}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="reliance-explanation">
        <section>
          <b>این درصد دقیقاً چگونه ساخته شد؟</b>
          <p>{behavior.score_explanation}</p>
          <div className="score-components">
            {breakdown.map((x: any, i: number) => (
              <div key={i}>
                <span>{x.title}</span>
                <b>{fa(x.observed_percent)}٪</b>
                <small>
                  وزن {fa(x.weight_percent)}٪ • سهم امتیاز{" "}
                  {fa(x.score_contribution)}
                </small>
              </div>
            ))}
          </div>
          <div className="reliance-formula">
            <span>
              {calc.formula_fa || "نرخ وصول مورد انتظار × ضریب اطمینان سابقه"}
            </span>
            <b>
              {fa(calc.expected_collection_rate_percent || 0)}٪ ×{" "}
              {fa(calc.history_confidence_factor_percent || 0)}٪ ={" "}
              {fa(calc.final_reliance_percent ?? reliance)}٪
            </b>
          </div>
        </section>
        <section className="improvement-list">
          <b>برای بهترشدن امتیاز چه کار کنیم؟</b>
          {improvements.map((x: any, i: number) => (
            <article key={i}>
              <i>{fa(i + 1)}</i>
              <div>
                <strong>{x.action}</strong>
                <p>{x.why}</p>
                <small>اثر مورد انتظار: {x.expected_improvement}</small>
              </div>
            </article>
          ))}
        </section>
      </div>
      <div className="reliability-note">
        این امتیاز تصمیم‌یار است و جایگزین تأیید مدیر مالی نیست. سابقه کم، سطح
        اطمینان و درصد اتکا را کاهش می‌دهد.
      </div>
    </section>
  );
}

function CustomerProfile({
  c,
  close,
  refresh,
}: {
  c: Customer;
  close: () => void;
  refresh: () => void;
}) {
  const [detail, setDetail] = useState<Customer>(c);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [predictionWarning, setPredictionWarning] = useState("");
  useEffect(() => {
    let active = true;
    if (!c.counterpart_ref) {
      setLoadingDetail(false);
      return;
    }
    Promise.allSettled([
      request(`/customer-intelligence/${c.counterpart_ref}`),
      request(`/predictions/customers/${c.counterpart_ref}`),
    ])
      .then((results) => {
        if (!active) return;
        const detailResult =
          results[0].status === "fulfilled"
            ? results[0].value?.customer
            : undefined;
        const predictionResult =
          results[1].status === "fulfilled"
            ? results[1].value?.customers?.[0] || results[1].value?.customer
            : undefined;
        setDetail((previous) => ({
          ...previous,
          ...detailResult,
          ...predictionResult,
          open_cheques: detailResult?.open_cheques || previous.open_cheques,
        }));
        if (results[0].status === "rejected")
          setDetailError(
            results[0].reason instanceof Error
              ? results[0].reason.message
              : "جزئیات چک‌ها دریافت نشد",
          );
        if (results[1].status === "rejected")
          setPredictionWarning(
            "تحلیل خوش‌قولی دریافت نشد؛ Backend نسخه ۲۹ را اجرا کنید.",
          );
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [c.counterpart_ref]);
  const create = async () => {
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        counterpart_ref: detail.counterpart_ref,
        counterpart_name: cname(detail),
        priority: risk(detail) === "critical" ? "critical" : "high",
      }),
    });
    refresh();
    close();
  };
  const total = detail.historical_total_cheque_amount || 0,
    collected = detail.collected_cheque_amount || 0,
    open = detail.open_exposure || 0,
    returned = detail.returned_cheque_amount || 0,
    percent = total ? Math.min(100, (collected / total) * 100) : 0;
  return (
    <div className="fd-backdrop" onClick={close}>
      <article
        className="customer-profile-expanded"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="profile-close" onClick={close}>
          ×
        </button>
        <div className="profile-title">
          <div>
            <Risk x={risk(detail)} />
            <h2>{cname(detail)}</h2>
            <p>ریز سوابق وصول، خوش‌قولی و وضعیت تک‌تک چک‌های دریافتی باز</p>
          </div>
          <span className="profile-source">SQL Server • اطلاعات لحظه‌ای</span>
        </div>
        {detailError && <div className="profile-warning">{detailError}</div>}
        {predictionWarning && (
          <div className="profile-prediction-warning">{predictionWarning}</div>
        )}
        <div className="modal-metrics profile-metrics">
          <K
            t="کل چک‌های دریافت‌شده"
            v={money(total)}
            n={`${fa(detail.historical_cheque_count || 0)} فقره • تومان`}
            c="blue"
          />
          <K
            t="وصول‌شده قطعی"
            v={money(collected)}
            n={`${fa(detail.collected_cheque_count || 0)} فقره`}
            c="teal"
          />
          <K
            t="چک‌های دریافتی باز"
            v={money(open)}
            n={`${fa(detail.open_cheque_count || 0)} فقره • تومان`}
            c="amber"
          />
          <K
            t="برگشتی/واخواست‌شده"
            v={money(returned)}
            n={`${fa(detail.returned_cheque_count || 0)} فقره • تومان`}
            c="red"
          />
        </div>
        <section className="collection-progress">
          <header>
            <div>
              <b>نسبت وصول قطعی از کل سوابق</b>
              <small>مبلغ وصول‌شده تقسیم بر کل مبلغ چک‌های ثبت‌شده</small>
            </div>
            <strong>{fa(percent)}٪</strong>
          </header>
          <div>
            <i style={{ width: `${percent}%` }} />
          </div>
          <footer>
            <span>وصول‌شده: {money(collected)} تومان</span>
            <span>هنوز باز: {money(open)} تومان</span>
          </footer>
        </section>
        <CustomerReliability c={detail} />
        <CustomerSqlAudit c={detail as CustomerAudit} />
        <section className="profile-cheques">
          <div className="profile-section-title">
            <div>
              <h3>ریز چک‌های باز این مشتری</h3>
              <p>مبلغ، تاریخ دریافت، تاریخ سررسید و زمان باقی‌مانده</p>
            </div>
            <b>
              {fa(detail.open_cheques?.length || detail.open_cheque_count || 0)}{" "}
              فقره
            </b>
          </div>
          {loadingDetail ? (
            <div className="profile-loading">
              در حال دریافت ریز چک‌ها از SQL…
            </div>
          ) : detail.open_cheques?.length ? (
            <div className="profile-cheque-table">
              <table>
                <thead>
                  <tr>
                    <th>شناسه چک</th>
                    <th>شماره چک</th>
                    <th>مبلغ</th>
                    <th>تاریخ دریافت</th>
                    <th>تاریخ سررسید</th>
                    <th>مدت چک</th>
                    <th>زمان باقی‌مانده</th>
                    <th>وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.open_cheques.map((x, i) => {
                    const d = daysToDue(x);
                    return (
                      <tr
                        key={x.cheque_id || i}
                        className={
                          d !== undefined && d < 0
                            ? "overdue-row"
                            : d !== undefined && d <= 7
                              ? "due-soon-row"
                              : ""
                        }
                      >
                        <td>{fa(x.cheque_id)}</td>
                        <td>
                          <b>
                            {fa(
                              x.serial_number ||
                                x.sayad_number ||
                                x.document_number ||
                                "—",
                            )}
                          </b>
                        </td>
                        <td>
                          <b>{money(x.amount || 0)} تومان</b>
                        </td>
                        <td>
                          {x.receipt_date_jalali || x.receipt_date || "—"}
                        </td>
                        <td>{x.due_date_jalali || x.due_date || "—"}</td>
                        <td>{fa(x.term_days)} روز</td>
                        <td>
                          <span
                            className={`profile-due ${d === undefined ? "unknown" : d < 0 ? "late" : d <= 7 ? "soon" : "normal"}`}
                          >
                            {remainingLabel(x)}
                          </span>
                        </td>
                        <td>{x.state_label || "باز"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="profile-loading">
              چک باز قابل نمایش برای این مشتری وجود ندارد.
            </div>
          )}
        </section>
        <div className="profile-bottom">
          <div>
            <h3>دلایل ارزیابی</h3>
            <ul>
              {[
                ...(detail.late_payment_risk?.reasons || []),
                ...(detail.evidence || []),
              ].map((x, i) => (
                <li key={i}>{textOf(x)}</li>
              ))}
            </ul>
          </div>
          <div className="credit-advice">
            <b>شرایط پیشنهادی چک بعدی</b>
            <span>
              {creditPolicyFa[detail.credit_decision?.policy || ""] ||
                "برای این مشتری هنوز پیشنهاد اعتباری کامل ثبت نشده است."}
            </span>
          </div>
        </div>
        <p className="profile-note">
          «وصول‌شده» براساس وضعیت قطعی چک در راهکاران است؛ امتیاز خوش‌قولی
          پیش‌بینی توضیح‌پذیر است و تصمیم قطعی اعتباری نیست.
        </p>
        <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button>
      </article>
    </div>
  );
}
