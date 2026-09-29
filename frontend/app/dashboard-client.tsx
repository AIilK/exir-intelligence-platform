"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./functional.css";
import "./cheque-totals.css";
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
import "./ui-polish-v69.css";
import "./management-v109.css";
import "./theme-stability-v137.css";
import "./customer-file.css";

type View =
  | "management"
  | "customers"
  | "cheques"
  | "receivedCheques"
  | "issuedCheques"
  | "cashflow"
  | "cashBank"
  | "companyPayments"
  | "b2bRemittances"
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
  cheque_portfolio?: any;
  report_context?: any;
  alarms?: Array<{
    level?: string; code?: string; title?: string; message?: string; impact?: string;
    owner?: string; deadline?: string; agent?: string; priority?: number; evidence?: Array<{label?: string; value?: any}>;
  }>;
  alarm_summary?: { critical?: number; high?: number; total?: number };
  future_outlook?: any;
  agent_requests?: Array<{agent?: string; required?: string[]}>;
  data_quality?: any;
  drilldowns?: Record<string,string>;
  executive_kpis?: Array<{
    label: string;
    value?: number | null;
    value_rial?: number | null;
    format: string;
    tone?: string;
    available?: boolean;
    group?: string;
    note?: string;
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
  data_context?: any;
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
  future_open_cheque_count?: number;
  future_open_cheque_amount?: number;
  open_cheques?: Cheque[];
  returned_cheques?: Cheque[];
  all_cheques?: Cheque[];
  b2b_remittances?: any;
  b2b_behavior?: any;
  b2b_risk_adjustment?: number;
  account_position?: any;
  collection_position?: any;
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
  data_source?: "rahkaran" | "karamad";
  karamad_activity?: {
    branches?: string[];
    movement_count?: number;
    inflow_rial?: number;
    outflow_rial?: number;
    received_cheque_count?: number;
    received_cheque_amount_rial?: number;
    received_cheque_future_count?: number;
    received_cheque_future_amount_rial?: number;
    received_cheque_returned_count?: number;
    received_cheque_returned_amount_rial?: number;
    issued_cheque_count?: number;
    issued_cheque_amount_rial?: number;
    received_transfer_count?: number;
    received_transfer_amount_rial?: number;
    paid_transfer_count?: number;
    paid_transfer_amount_rial?: number;
    selected_branch?: string;
    dl_refs?: number[];
    detail?: any;
  };
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
  state_code?: number;
  is_posted?: boolean;
  cashflow_open?: boolean;
  estimated_return_probability_percent?: number;
  risk_level?: string;
  reasons?: string[];
};
type CashDay = {
  date?: string;
  date_jalali?: string;
  reliable_received_cheques?: number;
  reliable_received_cheque_count?: number;
  issued_cheques_due?: number;
  salary_reserve?: number;
  historical_other_expenses?: number;
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
  document_date_jalali?: string;
  registration_date?: string;
  registration_date_jalali?: string;
  transfer_date?: string;
  transfer_date_jalali?: string;
  transfer_number?: string;
  bank_name?: string;
  description?: string;
  counterpart_ref?: number;
  cheque_item_id?: number;
  source_system?: "rahkaran" | "karamad";
  source_label?: string;
  branch?: string;
  branch_name?: string;
  bank_branch_name?: string;
  cheque_status?: string;
  cheque_location?: string;
  last_operation_account?: string;
  last_operation_level4?: string;
  assignment_date_jalali?: string;
  collection_date_jalali?: string;
  return_reason?: string;
  master_state_code?: number;
  current_status_description?: string;
  current_status_date_jalali?: string;
  current_status_document_date_jalali?: string;
  current_status_transaction_id?: number;
  status_source?: string;
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
  data_hub?: any;
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
  operational_inflow_rial: "دریافت عملیاتی قطعی",
  operational_outflow_rial: "پرداخت عملیاتی قطعی",
  operational_net_rial: "خالص گردش عملیاتی",
  actual_inflow_rial: "دریافت قطعی",
  actual_outflow_rial: "پرداخت قطعی",
  actual_net_rial: "خالص گردش قطعی",
  cash_receipt_rial: "دریافت نقدی",
  bank_receipt_rial: "دریافت بانکی",
  cash_payment_rial: "پرداخت نقدی",
  bank_payment_rial: "پرداخت بانکی",
  approved_future_commitment_rial: "تعهد تأییدشدهٔ آینده",
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

type ReceivedChequeHolding = "all" | "collector" | "bank" | "pending" | "assigned" | "cashbox" | "returned_cashbox_plain" | "returned_cashbox_yeh" | "returned_customer";
type ReceivedChequeHoldingBucket = Exclude<ReceivedChequeHolding, "all"> | "other";
const receivedChequeHoldingBucket = (c: TreasuryCheque): ReceivedChequeHoldingBucket => {
  // اگه state_label و cheque_status عین هم باشن (مثل سرویس Live SQL کارآمد)، جمع کردنشون با
  // فاصله متن رو دوبار تکرار می‌کنه («غیرقطعی غیرقطعی») و چک‌های exact-match رو می‌شکنه؛
  // پس فقط وقتی واقعاً متفاوتن به هم می‌چسبونیم.
  const status = (
    c.state_label && c.cheque_status && c.state_label === c.cheque_status
      ? [c.cheque_status]
      : [c.state_label, c.cheque_status].filter(Boolean)
  )
    .join(" ")
    .replaceAll("ي", "ی")
    .replaceAll("ك", "ک")
    .replaceAll("نزذ", "نزد") // غلط تایپی موجود در فایل خروجی کارآمد («نزذ» به‌جای «نزد»)
    .toLocaleLowerCase("fa-IR");
  const context = [c.cheque_location, c.last_operation_account, c.last_operation_level4, c.current_status_description, c.description]
    .filter(Boolean)
    .join(" ")
    .replaceAll("ي", "ی")
    .replaceAll("ك", "ک")
    .replaceAll("نزذ", "نزد")
    .toLocaleLowerCase("fa-IR");
  const trimmedStatus = status.trim();

  const combined = `${status} ${context}`;
  // چک‌های برگشتی هنوز غیرقطعی‌اند (نه وصول قطعی و نه واخواست نهایی)، پس باید قبل از
  // بقیه قوانین بررسی بشن؛ وگرنه توی سطل «other» می‌افتن و کلاً از صفحه حذف می‌شن.
  if (/برگشتی\s*نزد\s*مشتری/.test(combined)) return "returned_customer";
  // کارآمد دو وضعیت متفاوت برگشتی «نزد صندوق» دارد (کد ۶ بدون «ی» و کد ۱۰ با «ی»)؛
  // چون کدهای جدا و متمایزی در دیتابیس‌اند، هر کدام دکمه فیلتر جدای خودش را دارد.
  if (/^برگشتی\s*نزد\s*صندوق$/.test(trimmedStatus)) return "returned_cashbox_yeh";
  if (/^برگشت\s*نزد\s*صندوق$/.test(trimmedStatus)) return "returned_cashbox_plain";
  // مأمور وصول فقط با شاهد صریح متنی جدا می‌شود تا چک بانکی اشتباه طبقه‌بندی نشود.
  if (/(?:مأمور|مامور)\s*وصول/.test(combined) && !/در\s*انتظار|منتظر/.test(combined)) return "collector";
  // در کارآمد «واگذار شده» یک وضعیت غیرقطعی مستقل است، جدا از «نزد بانک قطعی».
  if (/(?:^|\s)واگذار\s*شده(?:\s|$)/.test(status)) return "assigned";
  // «غیرقطعی» (کد ۱ کارآمد) یک وضعیت مستقل است؛ نه هنوز واگذار شده نه جای مشخصی دارد.
  if (trimmedStatus === "غیرقطعی") return "pending";
  // در راهکاران State=2 / in_collection یعنی در جریان وصول بانکی.
  if (c.state_code === 2 || /in[_ -]?collection|در\s*جریان\s*وصول|درجریان\s*وصول|نزد\s*بانک/.test(status)) return "bank";
  // V129: در چک دریافتی کارآمد، وضعیت خالی/نامشخص طبق قانون کسب‌وکار «نزد صندوق» است.
  const karamadBlankStatus = c.source_system === "karamad" && (!trimmedStatus || /وضعیت\s*نامشخص|^نامشخص$|karamad_imported|ثبت.?شده\s*در\s*کارآمد/.test(trimmedStatus));
  // State=1 راهکاران (registered/نزد شرکت) و وضعیت صریح/خالی کارآمد به‌عنوان نزد صندوق/شرکت نمایش داده می‌شود.
  if (karamadBlankStatus || c.state_code === 1 || /registered|نزد\s*شرکت|نزد\s*صندوق/.test(status)) return "cashbox";
  return "other";
};
const receivedChequeHoldingLabel = (c: TreasuryCheque) => {
  const bucket = receivedChequeHoldingBucket(c);
  switch (bucket) {
    case "collector": return "نزد مأمور وصول";
    case "bank": return "نزد بانک / در جریان وصول";
    case "assigned": return "واگذار شده";
    case "pending": return "غیرقطعی";
    case "cashbox": return "نزد صندوق";
    case "returned_cashbox_plain": return "برگشت نزد صندوق";
    case "returned_cashbox_yeh": return "برگشتی نزد صندوق";
    case "returned_customer": return "برگشتی نزد مشتری";
    default: return "وضعیت نگهداری نامشخص";
  }
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
const fullToman = (rial: number = 0) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(rial / 10);

function RahkaranChequeTotals({ rows, kind }: { rows: TreasuryCheque[]; kind: "received" | "issued" }) {
  const selected = rows.filter((x) => x.source_system === "rahkaran");
  const groups = [
    { title: "از فردا به بعد", items: selected.filter((x) => (daysToDue(x) ?? -1) > 0) },
    { title: "امروز", items: selected.filter((x) => daysToDue(x) === 0) },
    { title: "معوق حداکثر ۲۰ روز", items: selected.filter((x) => { const d = daysToDue(x); return d !== undefined && d < 0 && d >= -20; }) },
    { title: "معوق بیش از ۲۰ روز", items: selected.filter((x) => { const d = daysToDue(x); return d !== undefined && d < -20; }), unavailable: kind === "issued" },
    ...(selected.some((x) => daysToDue(x) === undefined) ? [{ title: "بدون سررسید", items: selected.filter((x) => daysToDue(x) === undefined) }] : []),
    { title: "جمع کل در دامنهٔ گزارش", items: selected },
  ];
  return <div className="rahkaran-cheque-totals" aria-label={`تفکیک چک‌های ${kind === "received" ? "دریافتی" : "پرداختی"} راهکاران`}>
    <table>
      <thead><tr><th>سررسید</th><th>تعداد چک</th><th>مبلغ کامل (تومان)</th></tr></thead>
      <tbody>{groups.map((group) => <tr key={group.title}>
        <th scope="row">{group.title}</th>
        <td>{group.unavailable ? "—" : fa(group.items.length)}</td>
        <td>{group.unavailable ? "خارج از دامنهٔ گزارش" : fullToman(group.items.reduce((sum, x) => sum + (x.amount || 0), 0))}</td>
      </tr>)}</tbody>
    </table>
    <p>فقط راهکاران · مبالغ اسمی قبل از تعدیل وصول · مطابق فیلترهای این نما</p>
    {kind === "issued" && <p>چک‌های پرداختیِ معوق بیش از ۲۰ روز در ورودی این گزارش نیستند؛ «—» به معنی صفر نیست و این گروه در جمع لحاظ نشده است.</p>}
  </div>;
}

function IssuedChequeTotals({ rows }: { rows: TreasuryCheque[] }) {
  const future = rows.filter((x) => { const d = daysToDue(x); return d !== undefined && d >= 0; });
  const overdue = rows.filter((x) => { const d = daysToDue(x); return d !== undefined && d < 0 && d >= -20; });
  const other = rows.filter((x) => { const d = daysToDue(x); return d === undefined || d < -20; });
  const groups = [
    { title: "چک‌های امروز و آینده", items: future, tone: "future" },
    { title: "معوق حداکثر ۲۰روزه", items: overdue, tone: "overdue" },
    ...(other.length ? [{ title: "قدیمی‌تر یا بدون سررسید — نیازمند بررسی", items: other, tone: "overdue" }] : []),
    { title: "جمع کل چک‌های پرداختی باز", items: rows, tone: "total" },
  ];
  return <div className="issued-exact-totals" aria-label="تفکیک مبلغ چک‌های پرداختی">
    {groups.map(({ title, items, tone }) => <div className={`issued-exact-total ${tone}`} key={title}>
      <span>{title}</span>
      <b dir="rtl">{fullToman(items.reduce((sum, x) => sum + (x.amount || 0), 0))}</b>
      <small>تومان · {fa(items.length)} فقره</small>
    </div>)}
    <p>مبالغ بر اساس فیلترهای همین نما هستند؛ معوق‌ها در جمع کل باقی می‌مانند.</p>
  </div>;
}

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
  const scopedReceived = received;
  const scopedIssued = issued;
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
            <h2>{incoming ? "چک‌های دریافتی" : "چک‌های پرداختی باز"}</h2>
            <p>
              {incoming
                ? "مطالبات، وصول، برگشتی و ریسک مشتری"
                : "فقط چک‌های فعال؛ پرداخت‌شده و تضمینی حذف شده‌اند"}
            </p>
          </div>
          <i>انتخاب راهکاران یا کارآمد ←</i>
        </header>
        <strong>{fullToman(total)} <small>تومان</small></strong>
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
        <span>سبد یکپارچه خزانه • راهکاران + کارآمد</span>
      </section>
      {error && <div className="profile-warning">{error}</div>}
      <section className="cheque-flow-grid">
        {card("received", scopedReceived)}
        {card("issued", scopedIssued)}
      </section>
      <article className="fd-panel cheque-flow-guide">
        <Heading h="مسیر بررسی" p="از تصویر کلان تا ریز هر چک" />
        <div>
          <span>انتخاب دریافتی یا پرداختی</span>
          <i>←</i>
          <span>انتخاب راهکاران یا کارآمد</span>
          <i>←</i>
          <span>ریز چک و روز باقی‌مانده</span>
          <i>←</i>
          <span>هشدار و اقدام پیشنهادی</span>
        </div>
      </article>
    </>
  );
}
// Company-wide picture of received cheques across both systems, shown before choosing a source.
// Uses the same open portfolio as the detail pages (V117 holding filter), so totals match «همه وضعیت‌ها».
function ReceivedChequeOverview({ rows }: { rows: TreasuryCheque[] }) {
  const portfolio = rows.filter((x) => receivedChequeHoldingBucket(x) !== "other");
  const systems = [["rahkaran", "راهکاران"], ["karamad", "کارآمد"]] as const;
  const sum = (items: TreasuryCheque[]) => items.reduce((s, x) => s + (x.amount || 0), 0);
  const bySystem = (items: TreasuryCheque[]) => systems.map(([k]) => items.filter((x) => x.source_system === k));
  const total = sum(portfolio);
  const isReturned = (x: TreasuryCheque) => receivedChequeHoldingBucket(x).startsWith("returned");

  const overdue = portfolio.filter((x) => (daysToDue(x) ?? 0) < 0);
  const today = portfolio.filter((x) => daysToDue(x) === 0);
  const future = portfolio.filter((x) => (daysToDue(x) ?? -1) > 0);
  const returned = portfolio.filter(isReturned);
  const kpis = [
    { label: "کل سبد چک‌های دریافتی", icon: "▣", tone: "total", items: portfolio },
    { label: "سررسید گذشته", icon: "!", tone: "danger", items: overdue },
    { label: "سررسید امروز", icon: "◷", tone: "warn", items: today },
    { label: "سررسید آینده", icon: "→", tone: "ok", items: future },
    { label: "برگشتی (نزد صندوق یا مشتری)", icon: "↺", tone: "danger", items: returned },
  ];

  const dueGroups = [
    { title: "معوقات", items: overdue },
    { title: "امروز", items: today },
    { title: "آینده", items: future },
    ...(portfolio.some((x) => daysToDue(x) === undefined) ? [{ title: "بدون سررسید", items: portfolio.filter((x) => daysToDue(x) === undefined) }] : []),
  ];

  const shareValue = (items: TreasuryCheque[]) => total ? (sum(items) / total) * 100 : 0;
  const share = (items: TreasuryCheque[]) => total ? `${fa(Math.round(shareValue(items) * 10) / 10)}٪` : "—";
  const splitTable = (groups: { title: string; items: TreasuryCheque[] }[], head: string) => <div className="cf-table"><table>
    <thead><tr><th>{head}</th>{systems.map(([, l]) => <th key={l}>{l}</th>)}<th>جمع دو سیستم</th><th>سهم از مبلغ کل</th></tr></thead>
    <tbody>
      {groups.map((g) => <tr key={g.title}>
        <td><b>{g.title}</b></td>
        {bySystem(g.items).map((part, i) => <td key={i}>{fullToman(sum(part))}<small>{fa(part.length)} فقره</small></td>)}
        <td><b>{fullToman(sum(g.items))}</b><small>{fa(g.items.length)} فقره</small></td>
        <td>{share(g.items)}</td>
      </tr>)}
      <tr>
        <td><b>جمع کل</b></td>
        {bySystem(portfolio).map((part, i) => <td key={i}><b>{fullToman(sum(part))}</b><small>{fa(part.length)} فقره</small></td>)}
        <td><b>{fullToman(total)}</b><small>{fa(portfolio.length)} فقره</small></td>
        <td>{total ? "۱۰۰٪" : "—"}</td>
      </tr>
    </tbody>
  </table></div>;

  return <>
    <section className="cf-section">
      <div className="cf-title"><div><h3>گزارش کلی چک‌های دریافتی شرکت</h3><p>جمع دو سیستم راهکاران و کارآمد؛ همان سبد باز صفحات جزئیات. مبالغ به تومان و اسمی، قبل از تعدیل وصول هستند. برای ریز چک‌ها و فیلترها، یکی از دو منبع پایین را انتخاب کنید.</p></div></div>
      <div className="rco-kpis">
        {kpis.map((k) => <article key={k.label} className={`rco-kpi ${k.tone}`} title={`${fullToman(sum(k.items))} تومان`}>
          <header><i aria-hidden="true">{k.icon}</i><small>{k.label}</small></header>
          <b>{money(sum(k.items))} <em>تومان</em></b>
          <p><span>{fa(k.items.length)} فقره</span>{k.tone !== "total" && <span>{share(k.items)} از کل</span>}</p>
          {k.tone !== "total" && <div className="rco-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, shareValue(k.items))}%` }} /></div>}
          <dl>
            {bySystem(k.items).map((part, i) => <div key={systems[i][0]} className={systems[i][0]}>
              <dt>{systems[i][1]}</dt>
              <dd><b>{money(sum(part))}</b><small>{fa(part.length)} فقره</small></dd>
            </div>)}
          </dl>
        </article>)}
      </div>
    </section>
    <section className="cf-section">
      <div className="cf-title"><div><h3>تفکیک سررسید</h3><p>مبلغ کامل (تومان) و تعداد چک معوق، امروز و آینده، جدا برای هر سیستم.</p></div></div>
      {splitTable(dueGroups, "سررسید")}
    </section>
  </>;
}

function ChequeSourcePage({ kind, rows, error, back, onUpdated }: {
  kind: "received" | "issued";
  rows: TreasuryCheque[];
  error: string;
  back: () => void;
  onUpdated?: () => Promise<void>;
}) {
  const [source, setSource] = useState<"rahkaran" | "karamad" | null>(null);
  const [branch, setBranch] = useState("");
  const label = kind === "received" ? "دریافتی" : "پرداختی";
  const scope = (system: "rahkaran" | "karamad") => rows.filter((x) => {
    const days = daysToDue(x);
    return x.source_system === system && (kind === "received" || system === "karamad" || (days !== undefined && days >= -20));
  });
  if (source) return <>
    {error && <div className="profile-warning">{error}</div>}
    <section className="cheque-hub-intro"><div><small>جزئیات منبع انتخاب‌شده</small><h2>چک‌های {label} — {source === "rahkaran" ? "راهکاران" : "کارآمد"}</h2></div></section>
    <ChequeDetails key={source} kind={kind} rows={scope(source)} source={source}
      branch={branch} setBranch={setBranch} onUpdated={onUpdated} back={() => { setSource(null); setBranch(""); }} />
  </>;
  return <>
    <button className="cheque-back" onClick={back}>→ بازگشت به انتخاب نوع چک</button>
    {error && <div className="profile-warning">{error}</div>}
    {kind === "received" && <ReceivedChequeOverview rows={[...scope("rahkaran"), ...scope("karamad")]} />}
    <section className="cheque-hub-intro"><div><small>چک‌های {label}</small><h2>منبع اطلاعات را انتخاب کنید</h2><p>روی هر جمع کلیک کنید تا فیلترها، آمار سررسید و ریز کامل همان منبع باز شود.</p></div></section>
    <section className="cheque-source-grid">
      {(["rahkaran", "karamad"] as const).map((system) => {
        const items = scope(system);
        const title = system === "rahkaran" ? "راهکاران" : "کارآمد";
        return <button type="button" className={`cheque-source-card ${system}`} key={system}
          onClick={() => { setBranch(system === "rahkaran" ? "__rahkaran__" : ""); setSource(system); }}>
          <span>جمع کل چک‌های {label}</span><h2>{title}</h2>
          <strong>{fullToman(items.reduce((sum, x) => sum + (x.amount || 0), 0))}</strong>
          <small>تومان · {fa(items.length)} فقره</small>
          {kind === "received" && system === "karamad" && items.length > 0 && (
            <div className="karamad-status-mini">
              {Array.from(new Set(items.map((x) => x.state_label || x.cheque_status || "وضعیت نامشخص"))).slice(0, 6).map((status) => (
                <span key={status}>{status}: {fa(items.filter((x) => (x.state_label || x.cheque_status || "وضعیت نامشخص") === status).length)}</span>
              ))}
            </div>
          )}
          <p>{kind === "issued" ? (system === "karamad" ? "چک‌های پرداختی ثبت‌شده تا آخرین فایل؛ داده آینده فعلاً کامل نیست" : "چک‌های باز، شامل معوق حداکثر ۲۰ روز") : "کل سبد به‌روز چک‌های دریافتی موجود در گزارش"}</p>
          {!items.length && <p>در ورودی فعلی چکی برای این منبع موجود نیست.</p>}
          <b>مشاهدهٔ جزئیات {title} ←</b>
        </button>;
      })}
    </section>
  </>;
}

function ChequeDetails({
  kind,
  source,
  rows,
  agent,
  back,
  branch,
  setBranch,
  onUpdated,
}: {
  kind: "received" | "issued";
  source: "rahkaran" | "karamad";
  rows: TreasuryCheque[];
  agent?: AgentResult;
  back: () => void;
  branch: string;
  setBranch: (value: string) => void;
  onUpdated?: () => Promise<void>;
}) {
  const incoming = kind === "received";
  const [period, setPeriod] = useState("all"),
    [selectedDay, setSelectedDay] = useState(""),
    [search, setSearch] = useState(""),
    [portfolioFile, setPortfolioFile] = useState<File | null>(null),
    [portfolioBusy, setPortfolioBusy] = useState(false),
    [portfolioMessage, setPortfolioMessage] = useState(""),
    [holdingStatus, setHoldingStatus] = useState<ReceivedChequeHolding>("all");
  const replaceKaramadChequePortfolio = async () => {
    if (!portfolioFile) return;
    setPortfolioBusy(true);
    setPortfolioMessage("");
    try {
      const body = new FormData();
      body.append("file", portfolioFile);
      const endpoint = incoming ? "/karamad-manual/received-cheques/replace" : "/karamad-manual/issued-cheques/replace";
      const result = await request(endpoint, { method: "POST", body });
      setPortfolioMessage(result.message || (incoming ? "سبد چک‌های دریافتی کارآمد به‌روز شد." : "چک‌های پرداختی ثبت‌شده کارآمد به‌روز شد."));
      setPortfolioFile(null);
      if (onUpdated) await onUpdated();
    } catch (e) {
      setPortfolioMessage(e instanceof Error ? `خطا: ${e.message}` : "به‌روزرسانی فایل ناموفق بود");
    } finally {
      setPortfolioBusy(false);
    }
  };
  const branchOptions = useMemo(() => Array.from(new Set(rows
    .filter((x) => x.source_system === "karamad")
    .map((x) => x.branch_name || x.bank_branch_name || x.branch)
    .filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b, "fa")), [rows]);
  const sourceBranchRows = branch === "__rahkaran__"
    ? rows.filter((x) => x.source_system === "rahkaran")
    : branch
      ? rows.filter((x) => x.source_system === "karamad" && (x.branch_name || x.bank_branch_name || x.branch) === branch)
      : rows;
  // V117: the received open portfolio is strictly limited to the three approved holdings.
  const branchScopedRows = incoming
    ? sourceBranchRows.filter((x) => receivedChequeHoldingBucket(x) !== "other")
    : sourceBranchRows;
  const holdingCounts = incoming ? {
    all: branchScopedRows.length,
    collector: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "collector").length,
    bank: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "bank").length,
    assigned: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "assigned").length,
    pending: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "pending").length,
    cashbox: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "cashbox").length,
    returned_cashbox_plain: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_cashbox_plain").length,
    returned_cashbox_yeh: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_cashbox_yeh").length,
    returned_customer: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_customer").length,
  } : null;
  const holdingScopedRows = incoming && holdingStatus !== "all"
    ? branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === holdingStatus)
    : branchScopedRows;
  const portfolioOverdue = holdingScopedRows.filter((x) => (daysToDue(x) ?? 0) < 0),
    portfolioToday = holdingScopedRows.filter((x) => daysToDue(x) === 0),
    portfolioFuture = holdingScopedRows.filter((x) => (daysToDue(x) ?? -1) > 0),
    portfolioOverdueAmount = portfolioOverdue.reduce((sum, x) => sum + (x.amount || 0), 0),
    portfolioTodayAmount = portfolioToday.reduce((sum, x) => sum + (x.amount || 0), 0),
    portfolioFutureAmount = portfolioFuture.reduce((sum, x) => sum + (x.amount || 0), 0);
  const periodRows = holdingScopedRows.filter((x) => {
    const days = daysToDue(x);
    const dueDate = x.due_date ? String(x.due_date).slice(0, 10) : "";
    if (period === "day") return Boolean(selectedDay) && dueDate === selectedDay;
    if (period === "overdue20") return days !== undefined && days < 0 && days >= -20;
    if (period === "future") return days !== undefined && days >= 0;
    if (period === "all") return incoming || source === "karamad" ? true : days !== undefined && days >= -20;
    if (period === "after6m") return days !== undefined && days > 180;
    if (period === "12m") return days !== undefined && days >= 0 && days <= 365;
    const horizon = period === "7d" ? 7 : period === "20d" ? 20 : period === "1m" ? 30 : period === "3m" ? 90 : 180;
    return days !== undefined && days >= 0 && days <= horizon;
  });
  const normalizedSearch = search.trim().toLocaleLowerCase("fa-IR");
  const viewRows = !normalizedSearch ? periodRows : periodRows.filter((x) =>
    [x.counterpart_name, x.counterpart_code, x.document_number, x.serial_number, x.sayad_number, x.account_number, x.bank_name, x.branch_name, x.branch, x.description, x.cheque_status, x.cheque_location, x.last_operation_account, x.last_operation_level4, x.amount]
      .filter((value) => value !== null && value !== undefined)
      .some((value) => String(value).toLocaleLowerCase("fa-IR").includes(normalizedSearch)),
  );
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
    futureDueDays = viewRows
      .map((x) => daysToDue(x))
      .filter((d): d is number => d !== undefined && d >= 0),
    averageDueDays = futureDueDays.length
      ? futureDueDays.reduce((sum, d) => sum + d, 0) / futureDueDays.length
      : 0,
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
        label: "۳۱ تا ۹۰ روز",
        value: viewRows.filter((x) => {
          const d = daysToDue(x);
          return d !== undefined && d > 30 && d <= 90;
        }).length,
        tone: "violet",
        records: chequeInsightRows(
          viewRows.filter((x) => {
            const d = daysToDue(x);
            return d !== undefined && d > 30 && d <= 90;
          }),
        ),
      },
      {
        label: "بیشتر از ۹۰ روز",
        value: viewRows.filter((x) => (daysToDue(x) ?? -1) > 90).length,
        tone: "violet",
        records: chequeInsightRows(
          viewRows.filter((x) => (daysToDue(x) ?? -1) > 90),
        ),
      },
    ];
  return (
    <>
      <button className="cheque-back" onClick={back}>
        → بازگشت به انتخاب راهکاران یا کارآمد
      </button>
      {source === "karamad" && (
        <section className="karamad-cheque-update">
          <div>
            <small>{incoming ? "به‌روزرسانی سبد چک دریافتی کارآمد" : "به‌روزرسانی چک‌های پرداختی ثبت‌شده کارآمد"}</small>
            <h3>فایل جدید را بده؛ نسخه قبلی کامل جایگزین می‌شود</h3>
            <p>{incoming ? "وضعیت واقعی چک مثل «نزد صندوق»، «واگذار شده» و «برگشتی نزد مشتری» مستقیماً از آخرین Excel خوانده می‌شود." : "این فایل فقط چک‌های پرداختی ثبت‌شده تا آخرین آپدیت را پوشش می‌دهد. اطلاعات آینده فعلاً کامل نیست و برگشتی گزارش نشده است."}</p>
          </div>
          <label>
            <span>{portfolioFile ? portfolioFile.name : "انتخاب Excel جدید"}</span>
            <input type="file" accept=".xlsx" onChange={(e) => setPortfolioFile(e.target.files?.[0] || null)} />
          </label>
          <button type="button" disabled={!portfolioFile || portfolioBusy} onClick={replaceKaramadChequePortfolio}>
            {portfolioBusy ? "در حال به‌روزرسانی…" : "جایگزینی و به‌روزرسانی"}
          </button>
          {portfolioMessage && <em>{portfolioMessage}</em>}
        </section>
      )}
      {!incoming && source === "karamad" && (
        <section className="profile-warning">
          <b>وضعیت پوشش داده:</b> چک‌های پرداختی ثبت‌شده نمایش داده می‌شوند؛ داده آینده هنوز کامل در دسترس نیست و در فایل فعلی چک برگشتی نداریم. جمع آینده را تعهد کامل شرکت در نظر نگیرید.
        </section>
      )}
      {source === "karamad" && (
        <section className="cheque-period-filter branch-filter-panel">
          <div>
            <b>آمار شهر / شعبه کارآمد</b>
            <small>با انتخاب شعبه، تمام مبلغ‌ها، تعدادها، معوق‌ها، نمودار و ریز چک فقط برای همان شعبه محاسبه می‌شود.</small>
          </div>
          <label className="cheque-date-filter">
            <span>شعبه</span>
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              <option value="">همه شعب کارآمد</option>
              {branchOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          {branch && <button className="active" onClick={() => setBranch("")}>پاک کردن فیلتر شعبه</button>}
        </section>
      )}
      {incoming && source === "karamad" && (
        <section className="karamad-portfolio-timing">
          <div className="karamad-timing-card overdue">
            <small>سررسید گذشته</small>
            <strong>{fullToman(portfolioOverdueAmount)} تومان</strong>
            <span>{fa(portfolioOverdue.length)} فقره</span>
          </div>
          <div className="karamad-timing-card today">
            <small>سررسید امروز</small>
            <strong>{fullToman(portfolioTodayAmount)} تومان</strong>
            <span>{fa(portfolioToday.length)} فقره</span>
          </div>
          <div className="karamad-timing-card future">
            <small>سررسید آینده</small>
            <strong>{fullToman(portfolioFutureAmount)} تومان</strong>
            <span>{fa(portfolioFuture.length)} فقره</span>
          </div>
          <div className="karamad-timing-card total">
            <small>کل سبد کارآمد</small>
            <strong>{fullToman(holdingScopedRows.reduce((sum, x) => sum + (x.amount || 0), 0))} تومان</strong>
            <span>{fa(holdingScopedRows.length)} فقره</span>
          </div>
        </section>
      )}
      {incoming && holdingCounts && (
        <section className="cheque-period-filter cheque-holding-filter">
          <div>
            <b>فیلتر محل / وضعیت چک دریافتی</b>
            <small>این فیلتر برای راهکاران و کارآمد یکسان است و آمار، نمودار و ریز چک‌ها را هم‌زمان به‌روزرسانی می‌کند.</small>
          </div>
          {[
            ["all", "همه وضعیت‌ها", holdingCounts.all],
            ["assigned", "واگذار شده", holdingCounts.assigned],
            ["pending", "غیرقطعی", holdingCounts.pending],
            ["cashbox", "نزد صندوق", holdingCounts.cashbox],
            ["returned_cashbox_plain", "برگشت نزد صندوق", holdingCounts.returned_cashbox_plain],
            ["returned_cashbox_yeh", "برگشتی نزد صندوق", holdingCounts.returned_cashbox_yeh],
            ["returned_customer", "برگشتی نزد مشتری", holdingCounts.returned_customer],
          ].map(([id, title, count]) => (
            <button
              key={String(id)}
              type="button"
              className={holdingStatus === id ? "active" : ""}
              onClick={() => setHoldingStatus(id as ReceivedChequeHolding)}
            >
              {title} · {fa(Number(count))}
            </button>
          ))}
        </section>
      )}
      <section className="cheque-period-filter">
        <div>
          <b>{incoming ? "فیلتر سررسید چک‌های دریافتی" : "فیلتر سررسید چک‌های پرداختی"}</b>
          <small>فیلتر روزانه و بازه‌های زمانی برای هر دو نوع چک یکسان است؛ آمار، نمودار و ریز جدول هم‌زمان به‌روزرسانی می‌شوند.</small>
        </div>
        {[["all", incoming ? "همه سررسیدها (بدون سقف تاریخ)" : "همه (تا ۲۰ روز معوق)"], ["future", "کل آینده"], ["day", "روز مشخص"], ["overdue20", "معوق ۲۰ روز اخیر"], ["7d", "۷ روز آینده"], ["20d", "۲۰ روز آینده"], ["1m", "یک ماه آینده"], ["3m", "سه ماه آینده"], ["6m", "شش ماه آینده"], ["after6m", "بعد از ۶ ماه"], ["12m", "تا ۱۲ ماه"]].map(([id, title]) => (
          <button key={id} className={period === id ? "active" : ""} onClick={() => setPeriod(id)}>{title}</button>
        ))}
        {period === "day" && (
          <label className="cheque-date-filter">
            <span>روز سررسید</span>
            <input type="date" value={selectedDay} onChange={(e) => setSelectedDay(e.target.value)} />
          </label>
        )}
      </section>
      {incoming && branch !== "__rahkaran__" && <AgentPanel agent={agent} />}
      {branch === "__rahkaran__" ? <RahkaranChequeTotals rows={viewRows} kind={kind} /> : !incoming && <IssuedChequeTotals rows={viewRows} />}
      {(
      <div className="fd-kpis">
        <K
          t={incoming ? "مبلغ چک‌های دریافتی" : source === "karamad" ? "مبلغ چک‌های پرداختی ثبت‌شده" : "مبلغ چک‌های پرداختی باز"}
          v={fullToman(total)}
          n="تومان"
          c={incoming ? "teal" : "blue"}
          detail={{ title: incoming ? "جزئیات مبلغ چک‌های دریافتی" : "جزئیات مبلغ چک‌های پرداختی", subtitle: "ریز کامل مبنای جمع این شاخص", tone: incoming ? "teal" : "blue", stats: [{ label: "تعداد", value: fa(viewRows.length) }, { label: "مبلغ کل", value: `${fullToman(total)} تومان` }], records: chequeInsightRows(viewRows) }}
        />
        <K t="تعداد چک" v={fa(viewRows.length)} n="فقره" c="blue" detail={{ title: "جزئیات چک‌های این جمع", subtitle: "با انتخاب هر شاخص، ریز موارد نمایش داده می‌شود.", tone: "blue", stats: [{ label: "تعداد", value: fa(viewRows.length) }, { label: "مبلغ", value: `${fullToman(total)} تومان` }], records: chequeInsightRows(viewRows) }} />
        <K
          t="سررسیدگذشته"
          v={fa(overdue.length)}
          n={fullToman(overdue.reduce((s, x) => s + (x.amount || 0), 0)) + " تومان"}
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
                value: `${fullToman(overdue.reduce((s, x) => s + (x.amount || 0), 0))} تومان`,
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
      )}
      <section className="cheque-detail-grid">
        <article className="fd-panel visual-card cheque-chart-panel">
          <Heading
            h="توزیع سررسید"
            p={
              incoming
                ? "زمان‌بندی وصول چک‌های دریافتی"
                : "زمان‌بندی پرداخت چک‌های صادرشده"
            }
          />
          {incoming && (
            <div className="due-average-summary">
              میانگین سررسید چک‌ها: <strong>{fa(Math.round(averageDueDays))} روز</strong>
            </div>
          )}
          <VerticalBars rows={due} />
        </article>
        <article
          className={`fd-panel cheque-side-note ${incoming ? "received" : "issued"}`}
        >
          <small>{incoming ? "Collection View" : "Payment View"}</small>
          <h3>
            {incoming
              ? "اولویت با وصول چک‌های معوق و نزدیک است."
              : source === "karamad" ? "این بخش فقط چک‌های پرداختی ثبت‌شده در آخرین فایل کارآمد را نشان می‌دهد." : "فقط چک‌های باز و سندنخورده باید در برنامه نقدینگی پوشش داده شوند."}
          </h3>
          <p>
            {incoming
              ? "چک‌های پرریسک و خارج از سیاست ۹۰ روز قبل از پذیرش اعتبار جدید بررسی شوند."
              : source === "karamad" ? "اطلاعات آینده کامل نیست و برگشتی هم فعلاً نداریم؛ بنابراین این سبد برای مشاهده ثبت‌هاست، نه برآورد کامل تعهدات آینده." : "با تغییر وضعیت راهکاران از بلندمدت به روز، چک سندخورده/برداشت‌شده محسوب و از Cash Flow آینده حذف می‌شود."}
          </p>
          <div>
            <span>{fa(soon.length)} فقره تا ۷ روز</span>
            <span>{fa(overdue.length)} فقره معوق</span>
          </div>
        </article>
      </section>
      <article className="fd-panel cheque-table-panel">
          <Heading
          h={incoming ? "ریز چک‌های دریافتی" : source === "karamad" ? "ریز چک‌های پرداختی ثبت‌شده" : "ریز چک‌های پرداختی باز"}
          p={incoming ? "فیلترشده بر اساس تاریخ سررسید؛ مرتب از نزدیک‌ترین موعد به دورترین موعد" : source === "karamad" ? "ثبت‌های موجود در آخرین فایل کارآمد؛ داده آینده ممکن است ناقص باشد" : "مرتب‌شده از سررسیدگذشته و نزدیک‌ترین موعد به دورترین موعد"}
        />
        <section className="cash-bank-toolbar cheque-list-search">
          <div>
            <b>{incoming ? "جست‌وجو در همه چک‌های دریافتی" : "جست‌وجو در همه چک‌های پرداختی"}</b>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره سند، طرف حساب، شماره چک، صیاد، بانک یا مبلغ" />
          </div>
          <small>{fa(viewRows.length)} نتیجه از {fa(periodRows.length)} چکِ نمایش‌داده‌شده</small>
        </section>
        <div className="cheque-detail-table">
          <table>
            <thead>
              <tr>
                <th>طرف حساب</th>
                <th>تاریخ ثبت</th>
                <th>تاریخ حواله / سررسید</th>
                <th>{incoming && source === "karamad" ? "شماره چک / سند" : "شماره حواله / سند"}</th>
                <th>مبلغ</th>
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
                    <td>{x.registration_date_jalali || x.document_date_jalali || x.document_date || "—"}</td>
                    <td>{x.transfer_date_jalali || x.due_date_jalali || x.due_date || "—"}</td>
                    <td>{incoming && source === "karamad" ? (x.serial_number || x.transfer_number || x.document_number || "—") : (x.transfer_number || x.document_number || "—")}</td>
                    <td>{fullToman(x.amount || 0)} تومان</td>
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
                      {[x.bank_name, x.branch_name || x.bank_branch_name || x.branch]
                        .filter(Boolean)
                        .join(" / ") || "—"}
                    </td>
                    <td>
                      {incoming ? (
                        <span className={`cheque-business-status ${x.source_system === "rahkaran" ? "rahkaran" : "karamad"}`}>
                          {receivedChequeHoldingLabel(x)}
                          <small>
                            {[
                              x.source_system === "karamad" ? (x.cheque_status || x.state_label) : x.state_label,
                              x.source_system === "karamad" ? (x.last_operation_level4 || x.cheque_location) : undefined,
                            ].filter(Boolean).join(" · ") || (x.source_system === "rahkaran" ? "راهکاران" : "کارآمد")}
                          </small>
                        </span>
                      ) : x.source_system === "rahkaran" ? (
                        <span className={`cheque-business-status ${x.is_posted ? "karamad" : "rahkaran"}`}>
                          {x.state_label || (x.state_code === 28 ? "سند خورده / برداشت‌شده" : "باز / سند نخورده")}
                        </span>
                      ) : (
                        <span className="cheque-business-status karamad">ثبت‌شده در کارآمد<small>برگشتی: ندارد · آینده: ناقص</small></span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!viewRows.length && (
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
async function treasuryMutation(path: string, options: RequestInit) {
  const r = await fetch(`${TREASURY_API()}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const menu: [View, string, string][] = [
  ["management", "✦", "خلاصه مدیریتی"],
  ["customers", "◎", "پرونده مشتری"],
  ["cheques", "◷", "چک و سررسید"],
  ["cashBank", "⇄", "نقد و حواله"],
  ["companyPayments", "↗", "حواله‌های پرداختی شرکت"],
  ["b2bRemittances", "⇢", "حواله‌های مشتریان B2B"],
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


function B2BCustomerRemittances() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("B2B");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [source, setSource] = useState("rahkaran");
  useEffect(() => {
    setLoading(true);
    treasuryRequest(`/customer-b2b-remittances?limit=20000&source=${source}`)
      .then(setData).catch((e) => setError(e instanceof Error ? e.message : "خطا در دریافت حواله‌های B2B"))
      .finally(() => setLoading(false));
  }, [source]);
  const rows = data?.rows || [];
  const q = search.trim().toLowerCase();
  const viewRows = rows.filter((x:any) => {
    const d = String(x.deposit_date || "").slice(0,10);
    const text = `${x.customer_name || ""} ${x.customer_code || ""} ${x.receipt_number || ""} ${x.deposit_number || ""} ${x.description || ""}`.toLowerCase();
    const catOk = category === "همه" ? true : category === "B2B" ? x.is_b2b_customer_payment : x.category === category;
    return (!q || text.includes(q)) && catOk && (!dateFrom || d >= dateFrom) && (!dateTo || d <= dateTo);
  });
  const total = viewRows.reduce((a:number,x:any)=>a+Number(x.amount_rial||0),0);
  const customers = new Set(viewRows.filter((x:any)=>x.is_b2b_customer_payment).map((x:any)=>x.counterpart_ref)).size;
  const direct = viewRows.filter((x:any)=>x.is_b2b_customer_payment && !x.is_returned_cheque_settlement);
  const returned = viewRows.filter((x:any)=>x.is_returned_cheque_settlement);
  const categories = Array.from(new Set(rows.map((x:any)=>x.category).filter(Boolean))) as string[];
  if (loading) return <article className="fd-panel b2b-page"><p>در حال دریافت حواله‌های مشتریان B2B…</p></article>;
  return <article className="fd-panel b2b-page">
    <Heading h="حواله‌ها و واریزهای مشتریان B2B" p={`دریافت‌های بانکی ${source === "rahkaran" ? "راهکاران" : source === "karamad" ? "کارآمد" : "راهکاران و کارآمد"}؛ انتقال داخلی، بازگشت پرداخت و نقد کردن چک از پرداخت واقعی B2B جدا شده‌اند.`} />
    {error && <div className="profile-warning">{error}</div>}
    <div className="modal-metrics b2b-kpis">
      <K t="تعداد تراکنش" v={fa(viewRows.length)} n="ReceiptDeposit" c="blue" />
      <K t="مبلغ بازه" v={fullToman(total)} n="تومان" c="teal" />
      <K t="مشتریان B2B" v={fa(customers)} n="طرف حساب" c="blue" />
      <K t="واریز مستقیم" v={fa(direct.length)} n={fullToman(direct.reduce((a:number,x:any)=>a+Number(x.amount_rial||0),0)) + " تومان"} c="teal" />
      <K t="تسویه چک برگشتی" v={fa(returned.length)} n={fullToman(returned.reduce((a:number,x:any)=>a+Number(x.amount_rial||0),0)) + " تومان"} c="amber" />
    </div>
    <div className="b2b-toolbar">
      <select value={source} onChange={e=>setSource(e.target.value)} aria-label="منبع داده" title="منبع داده">
        <option value="rahkaran">راهکاران</option>
        <option value="karamad">کارآمد</option>
        <option value="all">هر دو</option>
      </select>
      <input placeholder="جستجو مشتری، رسید، حواله یا شرح…" value={search} onChange={e=>setSearch(e.target.value)} />
      <select value={category} onChange={e=>setCategory(e.target.value)}><option value="B2B">فقط پرداخت‌های B2B</option><option value="همه">همه دریافت‌های بانکی</option>{categories.map(x=><option key={x} value={x}>{x}</option>)}</select>
      <label>از <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} /></label>
      <label>تا <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} /></label>
    </div>
    <div className="b2b-table-wrap"><table><thead><tr><th>تاریخ</th><th>مشتری</th><th>شماره رسید</th><th>شماره حواله</th><th>مبلغ (تومان)</th><th>بانک/شعبه</th><th>وضعیت</th><th>نوع</th><th>شرح</th></tr></thead><tbody>
      {viewRows.map((x:any)=><tr key={x.receipt_deposit_id} className={!x.is_b2b_customer_payment ? "non-b2b" : ""}><td>{x.deposit_date_jalali || String(x.deposit_date||"").slice(0,10)}</td><td><b>{x.customer_name || "—"}</b><small>{x.customer_code || ""}</small></td><td>{x.receipt_number || "—"}</td><td>{x.deposit_number || "—"}</td><td>{fullToman(Number(x.amount_rial||0))}</td><td>{x.bank_branch_name || `حساب ${x.bank_account_ref || "—"}`}</td><td>{x.approve_state_label}</td><td><span className="b2b-category">{x.category}</span></td><td className="b2b-desc">{x.description || "—"}</td></tr>)}
    </tbody></table></div>
  </article>;
}

function CompanyPaymentOrders() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("همه");
  const [state, setState] = useState("همه");
  const [method, setMethod] = useState("همه");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [monthsBack, setMonthsBack] = useState("همه");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    treasuryRequest("/payment-orders/company?limit=5000")
      .then(setData).catch((e) => setError(e instanceof Error ? e.message : "خطا در دریافت حواله‌ها"))
      .finally(() => setLoading(false));
  }, []);
  const rows = data?.rows || [];
  const categories = ["همه", ...Array.from(new Set(rows.map((x:any) => x.category))).filter(Boolean)] as string[];
  const states = ["همه", ...Array.from(new Set(rows.map((x:any) => String(x.state)))).filter(Boolean)] as string[];
  const paymentOrderStateFa = (value:any) => {
    const code = String(value ?? "");
    const labels: Record<string,string> = {
      "1": "در انتظار تأیید",
      "2": "تأییدشده",
      "4": "وضعیت نهایی",
      "5": "وضعیت نهایی",
    };
    return labels[code] || (code ? `وضعیت ${fa(code)}` : "نامشخص");
  };
  const viewRows = rows.filter((x:any) => {
    const q = search.trim().toLowerCase();
    const hay = `${x.payment_order_number || ""} ${x.counterpart_name || ""} ${x.counterpart_code || ""} ${x.description || ""}`.toLowerCase();
    const orderDate = String(x.order_date || "").slice(0,10);
    let monthsOk = true;
    if (monthsBack !== "همه" && orderDate) {
      const d = new Date(`${orderDate}T00:00:00`);
      const cutoff = new Date();
      cutoff.setHours(0,0,0,0);
      cutoff.setMonth(cutoff.getMonth() - Number(monthsBack));
      monthsOk = d >= cutoff;
    }
    const dateOk = (!dateFrom || (orderDate && orderDate >= dateFrom)) && (!dateTo || (orderDate && orderDate <= dateTo));
    return (!q || hay.includes(q)) && (category === "همه" || x.category === category) &&
      (state === "همه" || String(x.state) === state) && (method === "همه" || x.payment_method === method) && dateOk && monthsOk;
  });
  const filteredAmount = viewRows.reduce((a:number,x:any)=>a+Number(x.calculated_amount||0),0);
  const filteredApproved = viewRows.filter((x:any) => Boolean(x.approve_date)).length;
  const filteredWaiting = viewRows.filter((x:any) => !x.approve_date).length;
  const filteredBankCash = viewRows.filter((x:any) => x.payment_method === "نقد/بانکی" || x.payment_method === "ترکیبی").length;
  const filteredCheque = viewRows.filter((x:any) => Number(x.cheque_amount || 0) > 0).length;
  const filteredCategories = viewRows.reduce((acc:Record<string,{count:number,amount:number}>, x:any) => {
    const key = x.category || "سایر";
    if (!acc[key]) acc[key] = {count:0, amount:0};
    acc[key].count += 1;
    acc[key].amount += Number(x.calculated_amount || 0);
    return acc;
  }, {});
  return <section className="company-payments-page">
    <div className="section-head"><div><small>RAHKARAN · RPA3.PaymentOrder</small><h2>حواله‌های پرداختی شرکت</h2><p>نمای یکپارچه حواله‌های پرداخت راهکاران با تفکیک طرف حساب، دسته، وضعیت و روش پرداخت.</p></div></div>
    {error && <div className="fd-errors"><span>{error}</span></div>}
    {loading ? <div className="panel">در حال دریافت حواله‌های راهکاران…</div> : <>
      <div className="company-payment-kpis">
        <K t="کل حواله‌ها" v={fa(viewRows.length)} n="مطابق فیلتر فعلی" c="blue" />
        <K t="مبلغ کل" v={fullToman(filteredAmount)} n="تومان · مطابق فیلتر فعلی" c="teal" />
        <K t="دارای تاریخ تأیید" v={fa(filteredApproved)} n="مطابق فیلتر فعلی" c="green" />
        <K t="در انتظار تأیید" v={fa(filteredWaiting)} n="مطابق فیلتر فعلی" c="amber" />
        <K t="نقد / بانکی" v={fa(filteredBankCash)} n="تعداد حواله در فیلتر فعلی" c="blue" />
        <K t="چکی" v={fa(filteredCheque)} n="تعداد حواله در فیلتر فعلی" c="red" />
      </div>
      <div className="company-payment-categories">
        {Object.entries(filteredCategories).map(([name, v]:any) => <button key={name} className={category===name?"active":""} onClick={()=>setCategory(category===name?"همه":name)}><span>{name}</span><b>{fa(v.count)}</b><small>{fullToman(Number(v.amount||0))} تومان</small></button>)}
      </div>
      <div className="company-payment-filters">
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="جستجو: شماره حواله، طرف حساب، شرح…" />
        <select value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(x=><option key={x}>{x}</option>)}</select>
        <select value={state} onChange={e=>setState(e.target.value)}>{states.map(x=><option key={x} value={x}>{x==="همه"?"همه وضعیت‌ها":paymentOrderStateFa(x)}</option>)}</select>
        <select value={monthsBack} onChange={e=>setMonthsBack(e.target.value)} aria-label="بازه چندماهه" title="بازه چندماهه">
          <option value="همه">همه بازه‌ها</option>
          <option value="1">۱ ماه اخیر</option>
          <option value="2">۲ ماه اخیر</option>
          <option value="3">۳ ماه اخیر</option>
          <option value="6">۶ ماه اخیر</option>
          <option value="12">۱۲ ماه اخیر</option>
          <option value="24">۲۴ ماه اخیر</option>
        </select>
        <input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)} aria-label="از تاریخ" title="از تاریخ" />
        <input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)} aria-label="تا تاریخ" title="تا تاریخ" />
        <select value={method} onChange={e=>setMethod(e.target.value)}>{["همه","نقد/بانکی","چکی","ترکیبی","نامشخص"].map(x=><option key={x}>{x}</option>)}</select>
      </div>
      <div className="company-payment-filter-summary"><b>{fa(viewRows.length)} حواله</b><span>{fullToman(filteredAmount)} تومان در فیلتر فعلی</span></div>
      <div className="table-wrap"><table><thead><tr><th>تاریخ</th><th>شماره حواله</th><th>طرف حساب</th><th>دسته</th><th>وضعیت</th><th>روش</th><th>بانکی</th><th>نقد</th><th>چک</th><th>مبلغ</th><th>شرح</th></tr></thead><tbody>
        {viewRows.map((x:any)=><tr key={x.payment_order_id}><td>{x.order_date_jalali || x.order_date?.slice(0,10) || "—"}</td><td><b>{x.payment_order_number}</b></td><td>{x.counterpart_name || `#${x.counterpart_ref || "—"}`}</td><td><span className="payment-category-chip">{x.category}</span></td><td>{paymentOrderStateFa(x.state)}</td><td>{x.payment_method}</td><td>{fullToman(Number(x.deposit_amount||0))}</td><td>{fullToman(Number(x.cash_amount||0))}</td><td>{fullToman(Number(x.cheque_amount||0))}</td><td><b>{fullToman(Number(x.calculated_amount||0))}</b></td><td className="payment-description">{x.description || "—"}</td></tr>)}
      </tbody></table></div>
      <p className="company-payment-note">دسته‌بندی فعلی مدیریتی و مبتنی بر شرح حواله است. وضعیت‌های ۴ و ۵ هر دو به‌عنوان «وضعیت نهایی» نمایش داده می‌شوند. فیلتر چندماهه نیز در کنار بازه تاریخ دستی قابل استفاده است.</p>
    </>}
  </section>;
}

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
    [chequeQuality, setChequeQuality] = useState<any>(null),
    [agentFocus, setAgentFocus] = useState<string | null>(null);
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
      };
      const leave = () => {
        card.style.setProperty("--mx", "50%");
        card.style.setProperty("--my", "50%");
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
  const refreshTreasuryCheques = useCallback(async () => {
    const [r, i, q] = await Promise.allSettled([
      treasuryRequest("/cheques/received/open?period=all"),
      treasuryRequest("/cheques/issued/open"),
      treasuryRequest("/cheques/status-quality"),
    ]);
    const errors: string[] = [];
    if (r.status === "fulfilled") setReceived(r.value.cheques || []);
    else errors.push(`چک دریافتی: ${r.reason?.message || "خطای نامشخص"}`);
    if (i.status === "fulfilled") setIssued(i.value.cheques || []);
    else errors.push(`چک پرداختی: ${i.reason?.message || "خطای نامشخص"}`);
    if (q.status === "fulfilled") setChequeQuality(q.value);
    else errors.push(`وضعیت قطعی: ${q.reason?.message || "خطای نامشخص"}`);
    setTreasuryError(errors.join(" | "));
  }, []);
  useEffect(() => { void refreshTreasuryCheques(); }, [refreshTreasuryCheques]);
  const refreshAfterKaramadUpdate = useCallback(async () => {
    // V128: the upload endpoint rebuilds the agent report on the backend, but the
    // old UI only refreshed the cheque REST rows. Reload both sources so KPI cards,
    // management summary, customer behavior and cash-flow numbers change immediately.
    await refreshTreasuryCheques();
    await load();
  }, [refreshTreasuryCheques, load]);
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
            received={received.length ? received : cheques}
            issued={issued}
            openChequePage={(kind) => setView(kind === "received" ? "receivedCheques" : "issuedCheques")}
            openAgent={(key) => { setAgentFocus(key); setView("agents"); }}
          />
        )}
        {view === "customers" && (selected ? (
          <CustomerProfile c={selected} close={() => setSelected(null)} refresh={load} embedded />
        ) : (
          <Customers customers={customers} agent={pack?.agents?.customer_behavior} open={setSelected} />
        ))}
        {view === "cheques" && (
          <ChequeHub
            received={received.length ? received : cheques}
            issued={issued}
            error={treasuryError}
            open={setView}
          />
        )}
        {view === "receivedCheques" && (
          <ChequeSourcePage kind="received" rows={received.length ? received : cheques}
            error={treasuryError} back={() => setView("cheques")} onUpdated={refreshAfterKaramadUpdate} />
        )}
        {view === "issuedCheques" && (
          <ChequeSourcePage kind="issued" rows={issued}
            error={treasuryError} back={() => setView("cheques")} onUpdated={refreshAfterKaramadUpdate} />
        )}
        {view === "cashflow" && (
          <Cashflow cash={cash} agent={pack?.agents?.cashflow} openAgent={(key) => { setAgentFocus(key); setView("agents"); }} />
        )}
        {view === "cashBank" && (
          <CashBankMovements agent={pack?.agents?.cash_bank_movement} />
        )}
        {view === "companyPayments" && <CompanyPaymentOrders />}
        {view === "b2bRemittances" && <B2BCustomerRemittances />}
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
          <Agents agents={pack?.agents} manager={pack?.management_summary} focusKey={agentFocus} />
        )}
      </section>

      <InsightCenter />
    </main>
  );
}

function CashBankMovements({ agent }: { agent?: AgentResult }) {
  const movementRequestId = useRef(0);
  const [period, setPeriod] = useState("month"),
    [approval, setApproval] = useState("approved"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [offset, setOffset] = useState(0),
    [report, setReport] = useState<any>(null),
    [transfers, setTransfers] = useState<any>(null),
    [pettyCash, setPettyCash] = useState<any>(null),
    [commitments, setCommitments] = useState<any>(null),
    [karamad, setKaramad] = useState<any>(null),
    [karamadFolder, setKaramadFolder] = useState<any>(null),
    [karamadFile, setKaramadFile] = useState<File | null>(null),
    [karamadMonth, setKaramadMonth] = useState(""),
    [karamadSearch, setKaramadSearch] = useState(""),
    [movementSearchInput, setMovementSearchInput] = useState(""),
    [movementSearch, setMovementSearch] = useState(""),
    [karamadBranch, setKaramadBranch] = useState(""),
    [branchFilter, setBranchFilter] = useState(""),
    [sourceFilter, setSourceFilter] = useState("all"),
    [karamadMessage, setKaramadMessage] = useState(""),
    [tab, setTab] = useState<"movements" | "transfers" | "petty" | "commitments" | "karamad">("movements"),
    [busy, setBusy] = useState(false),
    [decisionBusy, setDecisionBusy] = useState<number | null>(null),
    [decisionMessage, setDecisionMessage] = useState(""),
    [error, setError] = useState("");
  const limit = 500;
  const loadMovements = useCallback(async () => {
    const requestId = ++movementRequestId.current;
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const dates =
        period === "custom" ? `&date_from=${from}&date_to=${to}` : "";
      const branchParam = branchFilter ? `&branch=${encodeURIComponent(branchFilter)}` : "";
      const searchParam = movementSearch.trim() ? `&search=${encodeURIComponent(movementSearch.trim())}` : "";
      const [movementResult, transferResult, pettyResult, commitmentResult] = await Promise.all([
        treasuryRequest(
          `/cash-bank/movements?period=${period}&approval_status=all&source=${sourceFilter}&limit=${limit}&offset=${offset}${dates}${branchParam}${searchParam}`,
        ),
        sourceFilter === "karamad" || branchFilter ? Promise.resolve(null) : treasuryRequest(
          `/cash-bank/transfers?period=${period}&limit=${limit}&offset=${offset}${dates}`,
        ),
        sourceFilter === "karamad" || branchFilter ? Promise.resolve(null) : treasuryRequest(
          `/cash-bank/petty-cash?period=${period}&limit=${limit}&offset=${offset}${dates}`,
        ),
        treasuryRequest(`/cash-bank/commitments?horizon_days=365&limit=${limit}&offset=0`),
      ]);
      if (requestId !== movementRequestId.current) return;
      setReport(movementResult);
      setTransfers(transferResult);
      setPettyCash(pettyResult);
      setCommitments(commitmentResult);
    } catch (e) {
      if (requestId !== movementRequestId.current) return;
      setError(
        e instanceof Error ? e.message : "دریافت گردش نقد و حواله ناموفق بود",
      );
    } finally {
      if (requestId === movementRequestId.current) setBusy(false);
    }
  }, [period, approval, from, to, offset, branchFilter, sourceFilter, movementSearch]);
  useEffect(() => {
    if (period !== "custom" || (from && to)) loadMovements();
  }, [loadMovements, period, from, to]);
  const loadKaramad = useCallback(async (nextOffset = offset) => {
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(nextOffset) });
      if (karamadMonth) params.set("month", karamadMonth);
      if (karamadSearch.trim()) params.set("search", karamadSearch.trim());
      if (karamadBranch) params.set("branch", karamadBranch);
      const [rows, folder] = await Promise.all([
        request(`/karamad-manual/movements?${params.toString()}`),
        request("/karamad-manual/folder/status"),
      ]);
      setKaramad(rows);
      setKaramadFolder(folder);
    } catch (e) {
      setError(e instanceof Error ? e.message : "دریافت حواله‌های کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  }, [karamadMonth, karamadSearch, karamadBranch, limit, offset]);
  useEffect(() => {
    Promise.all([
      request(`/karamad-manual/movements?limit=${limit}&offset=0`),
      request("/karamad-manual/folder/status"),
    ])
      .then(([rows, folder]) => { setKaramad(rows); setKaramadFolder(folder); })
      .catch(() => undefined);
  }, []);
  const uploadKaramad = async () => {
    if (!karamadFile) return;
    setBusy(true);
    setKaramadMessage("");
    setError("");
    try {
      const body = new FormData();
      body.append("file", karamadFile);
      const result = await request("/karamad-manual/upload", { method: "POST", body });
      setKaramadMessage(result.message || "فایل کارآمد ثبت و یکتاسازی شد.");
      setOffset(0);
      await loadKaramad(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ورود فایل کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const scanKaramadFolder = async () => {
    setBusy(true);
    setKaramadMessage("");
    setError("");
    try {
      const result = await request("/karamad-manual/folder/scan", { method: "POST" });
      setKaramadMessage(`${fa(result.imported_count || 0)} فایل وارد شد؛ ${fa(result.skipped_count || 0)} فایل تکراری بود و ${fa(result.error_count || 0)} خطا ثبت شد.`);
      await loadKaramad(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "بررسی پوشه کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const decideCommitment = useCallback(
    async (item: any, decision: "pending_review" | "paid" | "cancelled" | "still_due") => {
      const labels: Record<string, string> = {
        pending_review: "نیازمند بررسی",
        paid: "پرداخت‌شده",
        cancelled: "لغوشده",
        still_due: "همچنان بدهکار",
      };
      if (
        decision !== "pending_review" &&
        !window.confirm(`وضعیت این قسط روی «${labels[decision]}» ثبت شود؟`)
      )
        return;
      setDecisionBusy(item.installment_id);
      setDecisionMessage("");
      setError("");
      try {
        await treasuryMutation(
          `/cash-bank/commitments/${item.installment_id}/decision`,
          {
            method: "PUT",
            body: JSON.stringify({
              payment_order_id: item.payment_order_id,
              decision,
            }),
          },
        );
        const refreshed = await treasuryRequest(
          `/cash-bank/commitments?horizon_days=365&limit=${limit}&offset=0`,
        );
        setCommitments(refreshed);
        setDecisionMessage(`وضعیت قسط ${item.installment_id} روی «${labels[decision]}» ثبت شد.`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "ثبت وضعیت تعهد ناموفق بود");
      } finally {
        setDecisionBusy(null);
      }
    },
    [limit],
  );
  const summary = report?.summary || {};
  const approvalCaption =
    approval === "approved"
      ? "اسناد قطعی"
      : approval === "pending"
        ? "اسناد غیرقطعی"
        : "همه وضعیت‌ها";
  const pageInfo =
    tab === "movements" ? report?.pagination : tab === "transfers" ? transfers?.pagination : tab === "petty" ? pettyCash?.pagination : tab === "karamad" ? karamad?.pagination : commitments?.pagination;
  const approvedFuture = commitments?.summary?.approved_future || {};
  const draftFuture = commitments?.summary?.draft_future || {};
  const currentOverdue = commitments?.summary?.current_year_overdue || {};
  const historicalBacklog = commitments?.summary?.historical_backlog || {};
  const commitmentReview = commitments?.manual_review_summary || {};
  const reviewCounts = commitmentReview?.counts || {};
  const reviewAmounts = commitmentReview?.amounts_rial || {};
  const karamadSummary = karamad?.summary || {};
  const movementLabel: Record<string, string> = {
    cash_receipt: "دریافت نقدی",
    bank_receipt: "واریز / حواله ورودی",
    cash_payment: "پرداخت نقدی",
    bank_payment: "برداشت / حواله خروجی",
  };
  // Status normalization is intentionally defensive because Rahkaran and Karamad
  // expose approval state with different field names.
  const normalizedApproval = (x: any): "approved" | "pending" | "rejected" | "unknown" => {
    const raw = x?.approve_state ?? x?.approval_state ?? x?.approval_status ?? x?.status_ref ?? x?.status;
    if (raw === 3 || raw === "3" || raw === true || raw === "approved" || raw === "confirmed" || raw === "قطعی") return "approved";
    if (raw === 4 || raw === "4" || raw === "rejected" || raw === "ردشده") return "rejected";
    if (raw === 2 || raw === "2" || raw === false || raw === "pending" || raw === "unconfirmed" || raw === "غیرقطعی") return "pending";
    // Karamad Excel has no explicit approval column; "وجوه در راه=true"
    // is the authoritative pending/unsettled signal for those imported rows.
    if (x?.in_transit === true || x?.cash_in_transit === true || x?.funds_in_transit === true || x?.وجوه_در_راه === true || x?.["وجوه در راه"] === true) return "pending";
    if (x?.source_system === "karamad" || x?.source_label === "کارآمد") return "approved";
    return "unknown";
  };
  const visibleMovements = (report?.movements || []).filter((x: any) => {
    if (approval === "all") return true;
    const state = normalizedApproval(x);
    return approval === "approved" ? state === "approved" : state === "pending";
  });
  const visibleKaramadMovements = (karamad?.movements || []).filter((x: any) => {
    if (approval === "all") return true;
    const state = normalizedApproval(x);
    return approval === "approved" ? state === "approved" : state === "pending";
  });
  const corporateTransferRows = branchFilter || sourceFilter === "karamad"
    ? [...(report?.company_bank_transfers || [])]
    : [...(transfers?.transfers || []), ...(report?.company_bank_transfers || [])];
  const pettyCashRows = branchFilter || sourceFilter === "karamad"
    ? [...(report?.petty_cash_movements || [])]
    : [...(pettyCash?.transfers || []), ...(report?.petty_cash_movements || [])];
  const cashBranchOptions: string[] = summary.available_branches || [];
  return (
    <div className="cash-bank-page">
      <AgentPanel agent={agent} />
      {<section className="cash-bank-toolbar fd-panel">
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
        <div className="approval-filter-group">
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
        <div className="cash-branch-filter">
          <b>منبع حواله‌ها</b>
          <select aria-label="منبع حواله‌ها" value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setBranchFilter(""); setOffset(0); }}>
            <option value="all">همه منابع</option>
            <option value="rahkaran">فقط راهکاران</option>
            <option value="karamad">فقط کارآمد</option>
          </select>
        </div>
        <label className="cash-bank-search-filter">
          <b>جستجو در گردش</b>
          <input
            value={movementSearchInput}
            onChange={(e) => setMovementSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setMovementSearch(movementSearchInput.trim());
                setOffset(0);
              }
            }}
            placeholder="شماره سند، طرف حساب، شرح، مبلغ، بانک یا صندوق"
            aria-label="جستجو در گردش نقد و حواله"
          />
          <button
            type="button"
            className="search-apply"
            onClick={() => {
              setMovementSearch(movementSearchInput.trim());
              setOffset(0);
            }}
          >جستجو</button>
          {movementSearch && (
            <button
              type="button"
              className="search-clear"
              onClick={() => { setMovementSearchInput(""); setMovementSearch(""); setOffset(0); }}
            >پاک کردن</button>
          )}
        </label>
        <div>
          <b>شهر / شعبه کارآمد</b>
          <select disabled={sourceFilter === "rahkaran"} value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setOffset(0); }}>
            <option value="">{sourceFilter === "all" ? "همه شعب + راهکاران" : sourceFilter === "rahkaran" ? "برای راهکاران کاربرد ندارد" : "همه شعب کارآمد"}</option>
            {cashBranchOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          {branchFilter && <small>آمار و ریز حواله‌ها فقط برای شعبه «{branchFilter}» از کارآمد نمایش داده می‌شود.</small>}
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
      </section>}
      {error && <div className="fd-errors">{error}</div>}
      {decisionMessage && <div className="commitment-success">{decisionMessage}</div>}
      <section className="fd-kpis cash-bank-kpis">
        <K t="حواله دریافتی" v={summary.bank_receipt_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_receipt_rial))} n={`تومان؛ ورودی بانکی واقعی · ${approvalCaption}`} c="blue" />
        <K t="حواله پرداختی" v={summary.bank_payment_total_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_payment_total_rial))} n={`تومان؛ شامل انتقال بانکی و تنخواه · ${approvalCaption}`} c="amber" />
        <K t="حواله پرداختی بدون انتقال بانکی" v={summary.bank_payment_excluding_transfer_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_payment_excluding_transfer_rial))} n={`تومان؛ کل حواله منهای انتقال بانک‌به‌بانک؛ تنخواه در این عدد باقی است · ${approvalCaption}`} c="red" />
      </section>
      <article className="fd-panel commitment-summary">
        <Heading
          h="تعهدات پرداخت و اثر آن‌ها بر نقدینگی"
          p="تعداد دستور پرداخت از تعداد اقساط چکی جداست؛ تضمینی‌ها و موارد اجراشده دوباره شمرده نمی‌شوند"
        />
        <div className="commitment-cards">
          <div className="commitment-card approved">
            <span>تعهد تأییدشده آینده</span>
            <strong>{money(approvedFuture.amount_rial || 0)} تومان</strong>
            <small>{fa(approvedFuture.payment_order_count || 0)} دستور · {fa(approvedFuture.installment_count || 0)} قسط · وارد Cash Flow پایه</small>
          </div>
          <div className="commitment-card draft">
            <span>در انتظار تأیید</span>
            <strong>{money(draftFuture.amount_rial || 0)} تومان</strong>
            <small>{fa(draftFuture.payment_order_count || 0)} دستور · {fa(draftFuture.installment_count || 0)} قسط · فقط سناریوی محتاطانه</small>
          </div>
          <div className="commitment-card overdue">
            <span>سررسیدگذشته سال جاری</span>
            <strong>{money(currentOverdue.amount_rial || 0)} تومان</strong>
            <small>{fa(currentOverdue.payment_order_count || 0)} دستور · {fa(currentOverdue.installment_count || 0)} قسط · نیازمند تعیین‌تکلیف</small>
          </div>
          <div className="commitment-card history">
            <span>مانده تاریخی کنارگذاشته‌شده</span>
            <strong>{money(historicalBacklog.amount_rial || 0)} تومان</strong>
            <small>{fa(historicalBacklog.payment_order_count || 0)} دستور · وارد پیش‌بینی نمی‌شود</small>
          </div>
        </div>
        <div className="commitment-review-strip">
          <span><b>{fa(reviewCounts.pending_review || 0)}</b> قسط منتظر بررسی</span>
          <span><b>{fa(reviewCounts.paid || 0)}</b> پرداخت‌شده</span>
          <span><b>{fa(reviewCounts.cancelled || 0)}</b> لغوشده</span>
          <span className="still-due"><b>{fa(reviewCounts.still_due || 0)}</b> همچنان بدهکار · {money(reviewAmounts.still_due || 0)} تومان وارد Cash Flow امروز</span>
        </div>
      </article>
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
          انتقال بانک‌به‌بانک
        </button>
        <button
          className={tab === "petty" ? "active" : ""}
          onClick={() => setTab("petty")}
        >
          تنخواه
        </button>
        <button
          className={tab === "commitments" ? "active" : ""}
          onClick={() => setTab("commitments")}
        >
          تعهدات پرداخت
        </button>
      </section>
      {tab === "movements" ? (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز دریافت و پرداخت نقدی و بانکی"
            p={`${fa(visibleMovements.length)} ردیف در وضعیت انتخاب‌شده؛ ${approvalCaption}؛ مبالغ نمایشی به تومان`}
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
                  <th>شعبه</th>
                  <th>عامل Cash Flow</th>
                  <th>وضعیت</th>
                  <th>شرح</th>
                  <th>منبع</th>
                </tr>
              </thead>
              <tbody>
                {visibleMovements.map((x: any) => (
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
                    <td>{x.branch_name || x.branch || "—"}</td>
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
                    <td><span className={`source-badge ${x.source_system || "rahkaran"}`}>{x.source_label || (x.source_system === "karamad" ? "کارآمد" : "راهکاران")}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : tab === "transfers" ? (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز انتقال‌های داخلی"
            p="حواله‌های شرکتی بانک‌به‌بانک؛ در سطح کل شرکت اثر صفر و خارج از Cash Flow"
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
                  <th>شعبه</th>
                  <th>مبلغ خروج</th>
                  <th>مبلغ ورود</th>
                  <th>State</th>
                  <th>شرح</th>
                  <th>منبع</th>
                </tr>
              </thead>
              <tbody>
                {corporateTransferRows.map((x: any, index: number) => (
                  <tr key={`${x.transfer_type || x.movement_type}-${x.transfer_id || x.movement_id}-${index}`}>
                    <td>
                      <b>{x.date_jalali || x.document_date_jalali || x.date?.slice(0, 10) || x.document_date?.slice(0, 10)}</b>
                    </td>
                    <td>{x.number || x.document_number}</td>
                    <td>
                      {x.classification === "company_bank_transfer"
                        ? "حواله شرکتی"
                        : x.transfer_type === "bank_transfer"
                        ? "انتقال بانکی"
                        : "انتقال صندوق"}
                    </td>
                    <td>
                      {x.source_bank_account_ref
                        ? `حساب ${x.source_bank_account_ref}`
                        : x.source_cash_ref
                          ? `صندوق ${x.source_cash_ref}`
                          : x.counterpart_name || "—"}
                    </td>
                    <td>
                      {x.destination_bank_account_ref
                        ? `حساب ${x.destination_bank_account_ref}`
                        : x.destination_cash_ref
                          ? `صندوق ${x.destination_cash_ref}`
                          : x.bank_account_number || x.counterpart_name || "—"}
                    </td>
                    <td>{x.branch_name || x.branch || "—"}</td>
                    <td>{money(x.payment_amount_rial ?? (x.direction === "outflow" ? x.amount_rial : 0))} تومان</td>
                    <td>{money(x.receipt_amount_rial ?? (x.direction === "inflow" ? x.amount_rial : 0))} تومان</td>
                    <td>{x.state || x.approve_state || "—"}</td>
                    <td>{x.description || "—"}</td>
                    <td><span className={`source-badge ${x.source_system || "rahkaran"}`}>{x.source_label || (x.source_system === "karamad" ? "کارآمد" : "راهکاران")}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : tab === "petty" ? (
        <article className="fd-panel cash-bank-table">
          <Heading h="تنخواه‌های شرکت" p="تأمین تنخواه یک انتقال داخلی است و در Cash Flow دریافت/پرداخت عملیاتی محاسبه نمی‌شود." />
          <div className="table-scroll"><table><thead><tr><th>تاریخ</th><th>شماره انتقال</th><th>تنخواه مقصد</th><th>مبدأ</th><th>مبلغ</th><th>شرح</th></tr></thead>
            <tbody>{pettyCashRows.map((x: any, index: number) => <tr key={`${x.transfer_type || x.movement_type}-${x.transfer_id || x.movement_id}-${index}`}>
              <td><b>{x.date_jalali || x.document_date_jalali || x.date?.slice(0, 10) || x.document_date?.slice(0, 10)}</b></td><td>{x.number || x.document_number}</td><td>{x.destination_petty_cash_ref ? `تنخواه ${x.destination_petty_cash_ref}` : x.counterpart_name || "تنخواه"}</td>
              <td>{x.source_bank_account_ref ? `حساب ${x.source_bank_account_ref}` : x.source_cash_ref ? `صندوق ${x.source_cash_ref}` : x.bank_account_number || "—"}</td><td>{money(x.payment_amount_rial ?? x.amount_rial)} تومان</td><td>{x.description || "—"}</td>
            </tr>)}</tbody></table></div>
          {!pettyCashRows.length && <div className="fd-empty">در این بازه انتقالی یا پرداختِ دارای برچسب تنخواه ثبت نشده است.</div>}
        </article>
      ) : tab === "karamad" ? (
        <article className="fd-panel cash-bank-table karamad-panel">
          <Heading
            h="چهار ورودی دستی کارآمد"
            p="چک دریافتی، چک پرداختی، حواله دریافت و حواله پرداخت؛ هم‌پوشانی با کلید جهت و شناسه حواله حذف می‌شود."
          />
          <div className="karamad-folder-box">
            <div><span>محل قرار دادن فایل‌ها</span><b dir="ltr">{karamadFolder?.inbox || "KaramadInbox"}</b></div>
            <div><span>بررسی خودکار</span><b>هر {fa(karamadFolder?.scan_minutes || 15)} دقیقه</b></div>
            <div><span>فایل منتظر</span><b>{fa(karamadFolder?.waiting_count || 0)}</b></div>
            <button onClick={scanKaramadFolder} disabled={busy}>{busy ? "در حال بررسی…" : "بررسی همین حالا"}</button>
          </div>
          <div className="karamad-import">
            <div className="karamad-upload">
              <label>
                <span>ورود فوری یکی از چهار Excel</span>
                <input
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(e) => setKaramadFile(e.target.files?.[0] || null)}
                />
              </label>
              <button disabled={!karamadFile || busy} onClick={uploadKaramad}>
                {busy ? "در حال ورود…" : "ورود و یکتاسازی"}
              </button>
              <small>{karamadFile?.name || "فایلی انتخاب نشده است"}</small>
            </div>
            {karamadMessage && <div className="karamad-message">{karamadMessage}</div>}
          </div>
          <div className="karamad-filters">
            <label>
              ماه ثبت
              <select value={karamadMonth} onChange={(e) => setKaramadMonth(e.target.value)}>
                <option value="">همه ماه‌ها</option>
                {(karamadSummary.available_months || []).map((item: any) => (
                  <option key={item.month} value={item.month}>
                    {item.month} · {fa(item.count || 0)} ردیف
                  </option>
                ))}
              </select>
            </label>
            <label>
              شعبه
              <select value={karamadBranch} onChange={(e) => setKaramadBranch(e.target.value)}>
                <option value="">همه شعب</option>
                {(karamadSummary.available_branches || []).map((item: string) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label>
              جست‌وجو
              <input
                value={karamadSearch}
                onChange={(e) => setKaramadSearch(e.target.value)}
                placeholder="شناسه، شماره، بانک، بابت یا شرح"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setOffset(0);
                    loadKaramad(0);
                  }
                }}
              />
            </label>
            <button onClick={() => { setOffset(0); loadKaramad(0); }} disabled={busy}>
              اعمال فیلتر
            </button>
          </div>
          <div className="karamad-summary">
            <div><span>کل حواله دریافت</span><b>{money(karamadSummary.received_transfer_total_rial || 0)} تومان · {fa(karamadSummary.received_transfer_total_count || 0)} ردیف</b></div>
            <div><span>کل حواله پرداخت</span><b>{money(karamadSummary.paid_transfer_total_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_total_count || 0)} ردیف</b></div>
            <div><span>انتقال بانک‌به‌بانک پرداخت</span><b>{money(karamadSummary.paid_transfer_bank_to_bank_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_bank_to_bank_count || 0)} ردیف</b></div>
            <div><span>سایر حواله‌های پرداخت</span><b>{money(karamadSummary.paid_transfer_other_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_other_count || 0)} ردیف</b></div>
            <div><span>دریافت عملیاتی قطعی</span><b>{money(karamadSummary.operational_inflow_rial || 0)} تومان</b></div>
            <div><span>پرداخت عملیاتی قطعی</span><b>{money(karamadSummary.operational_outflow_rial || 0)} تومان</b></div>
            <div><span>کل انتقال بانک‌به‌بانک حذف‌شده</span><b>{money(karamadSummary.bank_transfer_rial || 0)} تومان</b></div>
            <div><span>بازه ثبت</span><b>{karamadSummary.min_date_jalali || "—"} تا {karamadSummary.max_date_jalali || "—"}</b></div>
          </div>
          <div className="karamad-rule">در حواله پرداخت، انتقال‌های بانک‌به‌بانک داخلی جدا گزارش می‌شوند و در خالص Cash Flow اثر صفر دارند؛ «سایر حواله‌های پرداخت» شامل همه ردیف‌های پرداخت به‌جز انتقال داخلی است.</div>
          <div className="karamad-rule">فایل‌های فعلی ساختار گردش قطعی دارند و تاریخ سررسید چک ندارند؛ بنابراین ۱۰۰٪ در عملکرد واقعی می‌آیند، اما وارد Cash Flow آینده نمی‌شوند. سیاست وصول ۷۵٪ فقط برای چک باز دارای سررسید است.</div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>تاریخ ثبت</th><th>منبع فایل</th><th>جهت</th><th>شناسه حواله</th><th>شماره حواله</th><th>شعبه</th><th>شماره سند</th><th>بانک</th><th>مبلغ</th><th>وضعیت</th><th>طبقه‌بندی</th><th>بابت</th><th>توضیحات</th></tr></thead>
              <tbody>
                {visibleKaramadMovements.map((x: any) => (
                  <tr key={`${x.direction}-${x.transfer_id}`}>
                    <td><b>{x.registration_date_jalali || "—"}</b></td>
                    <td>{x.source_label || "کارآمد"}</td>
                    <td><span className={`movement-kind ${x.direction}`}>{x.direction === "inflow" ? "دریافت" : "پرداخت"}</span></td>
                    <td>{x.transfer_id}</td>
                    <td>{x.transfer_number || "—"}</td>
                    <td>{x.branch || "—"}</td>
                    <td>{x.document_number || "—"}</td>
                    <td>{x.bank || "—"}</td>
                    <td className={x.direction}>{money(x.amount_rial)} تومان</td>
                    <td><span className={`approve-state s${normalizedApproval(x) === "approved" ? 3 : normalizedApproval(x) === "pending" ? 2 : 4}`}>{normalizedApproval(x) === "approved" ? "قطعی" : normalizedApproval(x) === "pending" ? "غیرقطعی" : "ردشده"}</span></td>
                    <td>{x.classification === "operational" ? "عملیاتی" : x.classification === "company_bank_transfer" ? "انتقال داخلی" : "تنخواه"}</td>
                    <td>{x.purpose || "—"}</td>
                    <td>{x.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visibleKaramadMovements.length && <div className="fd-empty">برای وضعیت انتخاب‌شده، داده‌ای وجود ندارد.</div>}
        </article>
      ) : (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز تعهدات و دستورهای پرداخت"
            p="آینده تأییدشده وارد Cash Flow می‌شود؛ سررسیدگذشته تا بررسی خزانه فقط هشدار است"
          />
          <div className="table-scroll">
            <table>
              <thead><tr><th>سررسید</th><th>طبقه</th><th>شماره دستور</th><th>طرف حساب</th><th>مبلغ قسط</th><th>تعداد</th><th>شرح</th><th>تعیین تکلیف خزانه</th></tr></thead>
              <tbody>
                {(commitments?.commitments || []).map((x: any) => (
                  <tr key={x.installment_id}>
                    <td><b>{x.due_date_jalali || x.due_date?.slice(0, 10)}</b></td>
                    <td><span className={`commitment-kind ${x.commitment_class}`}>
                      {x.commitment_class === "approved_future" ? "تأییدشده آینده" : x.commitment_class === "draft_future" ? "در انتظار تأیید" : x.commitment_class === "current_year_overdue" ? "سررسیدگذشته سال جاری" : "مانده تاریخی"}
                    </span></td>
                    <td>{x.payment_order_number}</td>
                    <td>{x.counterpart_name || x.counterpart_code || x.counterpart_ref || "—"}</td>
                    <td>{money(x.amount_rial)} تومان</td>
                    <td>۱ قسط از دستور {x.payment_order_number}</td>
                    <td>{x.description || "—"}</td>
                    <td>
                      {x.commitment_class === "current_year_overdue" ? (
                        <div className="commitment-decisions">
                          <span className={`review-status ${x.review_decision || "pending_review"}`}>
                            {x.review_decision === "paid" ? "پرداخت‌شده" : x.review_decision === "cancelled" ? "لغوشده" : x.review_decision === "still_due" ? "همچنان بدهکار" : "نیازمند بررسی"}
                          </span>
                          <div>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "paid")}>پرداخت‌شده</button>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "cancelled")}>لغوشده</button>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "still_due")}>همچنان بدهکار</button>
                            {x.review_decision && x.review_decision !== "pending_review" && (
                              <button className="reset" disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "pending_review")}>بازنشانی</button>
                            )}
                          </div>
                        </div>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
      {tab !== "commitments" && <footer className="cash-bank-pagination">
        <button
          disabled={offset === 0 || busy}
          onClick={() => {
            const nextOffset = Math.max(0, offset - limit);
            setOffset(nextOffset);
            if (tab === "karamad") loadKaramad(nextOffset);
          }}
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
          onClick={() => {
            const nextOffset = offset + limit;
            setOffset(nextOffset);
            if (tab === "karamad") loadKaramad(nextOffset);
          }}
        >
          صفحه بعد
        </button>
      </footer>}
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


function FutureCashflowExecutive({
  cash,
  openAgent,
  compact = false,
}: {
  cash?: any;
  openAgent: (key: string) => void;
  compact?: boolean;
}) {
  const timeline = (cash?.timeline || []) as CashDay[];
  const inflow = timeline.reduce((sum, row) => sum + Number(row.projected_inflow || 0), 0);
  const outflow = timeline.reduce((sum, row) => sum + Number(row.projected_outflow || 0), 0);
  const net = inflow - outflow;
  const days = Number(cash?.forecast_days || timeline.length || 0);
  const cards = [
    {
      key: "collection",
      label: "ورودی احتمالی آینده",
      value: inflow,
      tone: "inflow",
      note: "چک‌ها و مطالبات قابل وصول + ورودی‌های برنامه‌ریزی‌شده",
      detail: "جزئیات در Agent وصول و مطالبات",
    },
    {
      key: "cheque_payment",
      label: "خروجی قطعی و احتمالی آینده",
      value: outflow,
      tone: "outflow",
      note: "چک‌های پرداختی + تعهدات پرداخت + ذخیره حقوق",
      detail: "جزئیات در Agent پرداخت و تعهدات",
    },
    {
      key: "cashflow",
      label: "خالص نقدینگی آینده",
      value: net,
      tone: net >= 0 ? "net-positive" : "net-negative",
      note: "ورودی احتمالی آینده منهای خروجی قطعی و احتمالی",
      detail: "جزئیات در Cash Flow Agent",
    },
  ];
  return (
    <article className={`fd-panel future-cashflow-executive ${compact ? "compact" : ""}`}>
      <div className="future-cashflow-head">
        <div>
          <small>چشم‌انداز نقدینگی</small>
          <h2>تصویر تمیز آینده مالی</h2>
          <p>{days ? `جمع پیش‌بینی ${fa(days)} روز آینده؛ برای ریز محاسبات روی هر کارت کلیک کن.` : "برای ریز محاسبات روی هر کارت کلیک کن."}</p>
        </div>
        <span className={net >= 0 ? "positive" : "negative"}>{net >= 0 ? "خالص مثبت" : "فشار نقدینگی"}</span>
      </div>
      <div className="future-cashflow-cards">
        {cards.map((card) => (
          <button key={card.label} type="button" className={`future-cashflow-card ${card.tone}`} onClick={() => openAgent(card.key)}>
            <small>{card.label}</small>
            <strong>{money(Math.abs(card.value))} <em>تومان</em></strong>
            {card.key === "cashflow" && <b>{card.value >= 0 ? "+ مثبت" : "− منفی"}</b>}
            <p>{card.note}</p>
            <span>{card.detail} ←</span>
          </button>
        ))}
      </div>
      <div className="future-cashflow-rule">
        <span>قاعده گزارش</span>
        <p>انتقال بانک‌به‌بانک و تنخواه در خالص شرکت اثر صفر دارند؛ داده آینده چک پرداختی کارآمد فقط به اندازه ثبت‌های موجود قابل اتکاست.</p>
      </div>
    </article>
  );
}

function Management({
  manager,
  agents,
  customers,
  cheques,
  cash,
  alerts,
  received,
  issued,
  openChequePage,
  openAgent,
}: {
  manager?: Analysis;
  agents?: Record<string, AgentResult>;
  customers: Customer[];
  cheques: Cheque[];
  cash?: any;
  alerts: Alert[];
  received: TreasuryCheque[];
  issued: TreasuryCheque[];
  openChequePage: (kind: "received" | "issued") => void;
  openAgent: (key: string) => void;
}) {
  const portfolio = (manager?.cheque_portfolio || {}) as any;
  const fallbackReceivedFuture = received.filter((x) => { const d = daysToDue(x); return d !== undefined && d >= 0; });
  const fallbackIssuedFuture = issued.filter((x) => { const d = daysToDue(x); return d !== undefined && d >= 0; });
  const fallbackReceivedOverdue = received.filter((x) => { const d = daysToDue(x); return d !== undefined && d < 0; });
  const fallbackIssuedOverdue = issued.filter((x) => { const d = daysToDue(x); return d !== undefined && d < 0; });
  const metric = (key: string, fallbackItems: TreasuryCheque[]) => ({
    amount: Number(portfolio?.[`${key}_amount_rial`] ?? fallbackItems.reduce((sum, x) => sum + (x.amount || 0), 0)),
    count: Number(portfolio?.[`${key}_count`] ?? fallbackItems.length),
    sources: portfolio?.[`${key}_sources`] || null,
  });
  const receivedFuture = metric("received_future_open", fallbackReceivedFuture);
  const issuedFuture = metric("issued_future_open", fallbackIssuedFuture);
  const receivedOverdue = metric("received_overdue", fallbackReceivedOverdue);
  const issuedOverdue = metric("issued_overdue", fallbackIssuedOverdue);
  const sourceText = (sources: any) => {
    if (!sources) return "راهکاران + کارامد";
    const parts = [];
    if (sources.rahkaran) parts.push(`راهکاران ${fa(sources.rahkaran.count || 0)}`);
    if (sources.karamad) parts.push(`کارامد ${fa(sources.karamad.count || 0)}`);
    return parts.join(" · ") || "راهکاران + کارامد";
  };
  const dueCard = (title: string, data: {amount:number;count:number;sources:any}, kind: "received" | "issued", tone: "future" | "overdue") => (
    <button type="button" className={`management-due-card ${tone} ${kind}`} onClick={() => openChequePage(kind)}>
      <span>{kind === "received" ? "چک‌های دریافتی" : "چک‌های پرداختی"}</span>
      <h3>{title}</h3>
      <strong>{fullToman(data.amount)} <small>تومان</small></strong>
      <p className="management-source-split">{sourceText(data.sources)}</p>
      <div><b>{fa(data.count)} فقره</b><i>مشاهده جزئیات ←</i></div>
    </button>
  );
  return (
    <>
      <section className="management-due-board">
        <header>
          <div><small>اولویت نقدینگی</small><h2>سررسیدهای باز آینده</h2><p>اول اقلامی که باید برای روزهای آینده برنامه‌ریزی شوند.</p></div>
        </header>
        <div className="management-due-grid">
          {dueCard("بازِ امروز و آینده", receivedFuture, "received", "future")}
          {dueCard("بازِ امروز و آینده", issuedFuture, "issued", "future")}
        </div>
        <header className="overdue-title">
          <div><small>پیگیری فوری</small><h2>سررسیدگذشته</h2><p>بعد از آینده، اقلامی که موعدشان گذشته و هنوز باز هستند.</p></div>
        </header>
        <div className="management-due-grid">
          {dueCard("سررسیدگذشته", receivedOverdue, "received", "overdue")}
          {dueCard("سررسیدگذشته", issuedOverdue, "issued", "overdue")}
        </div>
      </section>
      <ManagerPanel a={manager} />
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
  format?: "money" | "number";
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
            {actions.slice(0, 6).map((x, i) => (
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

// Karamad sales network: هیبرید من (per branch) → ویزیتور. Customer names are never shown.
function SalesNetwork({ data, error, onBack }: { data: any; error: string; onBack: () => void }) {
  const [branchId, setBranchId] = useState<number | null>(null);
  const [visitorId, setVisitorId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  if (visitorId != null) return <NetworkFile kind="visitor" id={visitorId} onBack={() => setVisitorId(null)} backLabel={branchId != null ? "→ بازگشت به پرونده هیبرید" : "→ بازگشت به هیبرید من‌ها"} />;
  if (branchId != null) return <NetworkFile kind="branch" id={branchId} onBack={() => setBranchId(null)} onOpenVisitor={setVisitorId} backLabel="→ بازگشت به هیبرید من‌ها" />;

  const cy = data?.current_year_label || "سال جاری", py = data?.previous_year_label || "سال قبل";
  const q = search.trim().toLocaleLowerCase("fa-IR");
  const rows: any[] = (data?.branches || []).filter((b: any) => !q || [b.branch_name, ...(b.hybrids || [])].join(" ").toLocaleLowerCase("fa-IR").includes(q));
  const sm = data?.summary || {};
  return <>
    <button className="cheque-back" onClick={onBack}>→ بازگشت به انتخاب راهکاران یا کارآمد</button>
    <article className="fd-panel unified-customer-directory">
      <Heading h="هیبرید من‌ها و ویزیتورها — کارآمد" p="هر ردیف یک شعبه و هیبرید من‌های آن است؛ برای دیدن ویزیتورها، فروش، مطالبات و چک‌ها روی ردیف کلیک کنید." />
      {error && <div className="profile-warning">{error}</div>}
      {!data && !error ? <div className="profile-loading">در حال دریافت شبکه فروش کارآمد...</div> : <>
        <div className="cf-kpis cf-directory-kpis">
          <article><small>هیبرید من</small><b>{fa(sm.hybrid_count || 0)}</b><span>در {fa(sm.branch_count || 0)} شعبه</span></article>
          <article><small>ویزیتور فعال</small><b>{fa(sm.active_visitor_count || 0)}</b><span>نفر</span></article>
          <article><small>فروش {cy}</small><b>{money(sm.current_year_sales_rial || 0)}</b><span>تومان</span></article>
          <article><small>فروش {py}</small><b>{money(sm.previous_year_sales_rial || 0)}</b><span>تومان</span></article>
          <article className="cf-accent-red"><small>مطالبات مشتریان شعب</small><b>{money(sm.open_account_receivable_rial || 0)}</b><span>تومان • مانده دفتر کل</span></article>
        </div>
        <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar">
          <div><b>جستجوی هیبرید من یا شعبه</b><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="مثلاً رییسی یا اصفهان..." /></div>
          <small>{fa(rows.length)} شعبه</small>
        </section>
        <div className="cf-table cf-clickable"><table>
          <thead><tr><th>هیبرید من</th><th>شعبه</th><th>ویزیتور فعال</th><th>فروش {cy}</th><th>فروش {py}</th><th>مطالبات</th><th>چک باز</th></tr></thead>
          <tbody>{rows.map((b) => <tr key={b.branch_id} onClick={() => setBranchId(b.branch_id)}>
            <td className="cf-wrap"><b>{(b.hybrids || []).join("، ") || "—"}</b></td>
            <td>{b.branch_name}</td>
            <td>{fa(b.active_visitor_count || 0)}<small>{fa(b.active_supervisor_count || 0)} سرپرست</small></td>
            <td><b>{money(b.current_year_sales_rial || 0)}</b><small>{fa(b.current_year_invoice_count || 0)} فاکتور</small></td>
            <td><b>{money(b.previous_year_sales_rial || 0)}</b><small>{fa(b.previous_year_invoice_count || 0)} فاکتور</small></td>
            <td className="cf-debt">{money(b.debt?.open_account_receivable_rial || 0)}<small>{fa(b.debt?.debtor_customer_count || 0)} مشتری بدهکار</small></td>
            <td>{money(b.open_cheque_amount_rial || 0)}<small>{fa(b.open_cheque_count || 0)} فقره</small></td>
          </tr>)}</tbody>
        </table></div>
        <small className="cf-note">{data?.debt_note}</small>
      </>}
    </article>
  </>;
}

// Open cheques with a long term (due more than 90 days after receipt) and a large amount need a closer look.
const REVIEW_TERM_DAYS = 90;
const REVIEW_AMOUNT_RIAL = 1_000_000_000; // 100M toman
const needsChequeReview = (x: any) =>
  x.return_risk?.state === "open"
  && typeof x.receipt_to_due_days === "number" && x.receipt_to_due_days > REVIEW_TERM_DAYS
  && Number(x.amount_rial || 0) > REVIEW_AMOUNT_RIAL;

function NetworkFile({ kind, id, onBack, onOpenVisitor, backLabel }: { kind: "branch" | "visitor"; id: number; onBack: () => void; onOpenVisitor?: (id: number) => void; backLabel: string }) {
  const [file, setFile] = useState<any>(null);
  const [error, setError] = useState("");
  const [riskFilter, setRiskFilter] = useState<"open" | "high" | "medium" | "low" | "returned" | "review">("open");
  useEffect(() => {
    let active = true;
    setFile(null); setError("");
    request(`/sales-network/${kind === "branch" ? "branches" : "visitors"}/${id}`)
      .then((d) => { if (active) setFile(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت پرونده ناموفق بود"); });
    return () => { active = false; };
  }, [kind, id]);

  const back = <button className="cheque-back" onClick={onBack}>{backLabel}</button>;
  if (error) return <>{back}<div className="profile-warning">{error}</div></>;
  if (!file) return <>{back}<div className="profile-loading">در حال دریافت پرونده {kind === "branch" ? "هیبرید" : "ویزیتور"}...</div></>;

  const cy = file.current_year_label || "سال جاری", py = file.previous_year_label || "سال قبل";
  const s = file.sales_stats || {}, d = file.debt || {}, ch = file.cheques || { rows: [], summary: {} };
  const reviewRows = (ch.rows || []).filter(needsChequeReview);
  const reviewAmount = reviewRows.reduce((sum: number, x: any) => sum + Number(x.amount_rial || 0), 0);
  const chequeRows = riskFilter === "review" ? reviewRows : (ch.rows || []).filter((x: any) => {
    const r = x.return_risk || {};
    return riskFilter === "open" ? r.state === "open" : riskFilter === "returned" ? r.state === "returned" : r.level === riskFilter;
  });
  const title = kind === "branch" ? (file.hybrids || []).join("، ") || file.branch_name : file.visitor_name;
  return <>
    {back}
    <article className="customer-profile-expanded customer-profile-page">
      <div className="profile-title">
        <div>
          <span className="fd-badge safe">{kind === "branch" ? "هیبرید من" : file.active ? "ویزیتور فعال" : "ویزیتور غیرفعال"}</span>
          <h2>{title}</h2>
          <p>{kind === "branch"
            ? `شعبه ${file.branch_name} • سرپرست: ${(file.supervisors || []).join("، ") || "—"}`
            : `شعبه ${file.branch_name || "—"} • سرپرست: ${file.supervisor || "—"} • هیبرید من: ${(file.hybrids || []).join("، ") || "—"}`}</p>
        </div>
        <span className="profile-source">کارآمد</span>
      </div>

      <section className="cf-section">
        <div className="cf-title">
          <div><h3>فروش</h3><p>{kind === "branch" ? "همه فاکتورهای فروش این شعبه" : "فاکتورهای فروشی که این ویزیتور زده است"}</p></div>
          {s.last_invoice_date_jalali && <small>آخرین فاکتور: {s.last_invoice_date_jalali}</small>}
        </div>
        <div className="cf-kpis">
          <article><small>تعداد کل فاکتور فروش</small><b>{fa(s.invoice_count || 0)}</b><span>از {s.first_invoice_date_jalali || "—"}</span></article>
          <article><small>کل مبلغ فروش تا امروز</small><b>{money(s.sales_amount_rial || 0)}</b><span>تومان</span></article>
          <article><small>فروش {cy}</small><b>{money(s.current_year_sales_rial || 0)}</b><span>{fa(s.current_year_invoice_count || 0)} فاکتور</span></article>
          <article><small>فروش {py}</small><b>{money(s.previous_year_sales_rial || 0)}</b><span>{fa(s.previous_year_invoice_count || 0)} فاکتور</span></article>
        </div>
      </section>

      {kind === "branch" && <section className="cf-section">
        <div className="cf-title"><div><h3>ویزیتورها</h3><p>ویزیتورهای فعال و ویزیتورهایی که در {cy} یا {py} فروش داشته‌اند؛ برای پرونده ویزیتور کلیک کنید.</p></div></div>
        {(file.visitors || []).length ? <div className="cf-table cf-clickable"><table>
          <thead><tr><th>ویزیتور</th><th>سرپرست</th><th>فروش {cy}</th><th>فروش {py}</th><th>مطالبات مشتریانش</th><th>آخرین فاکتور</th></tr></thead>
          <tbody>{file.visitors.map((v: any) => <tr key={v.visitor_id} onClick={() => onOpenVisitor?.(v.visitor_id)}>
            <td><b>{v.visitor_name}</b>{!v.active && <small className="cf-muted">غیرفعال</small>}</td>
            <td>{v.supervisor || "—"}</td>
            <td><b>{money(v.current_year_sales_rial || 0)}</b><small>{fa(v.current_year_invoice_count || 0)} فاکتور</small></td>
            <td><b>{money(v.previous_year_sales_rial || 0)}</b><small>{fa(v.previous_year_invoice_count || 0)} فاکتور</small></td>
            <td className="cf-debt">{money(v.debt?.open_account_receivable_rial || 0)}<small>{fa(v.debt?.debtor_customer_count || 0)} مشتری بدهکار</small></td>
            <td>{v.last_invoice_date_jalali || "—"}</td>
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">ویزیتوری برای این شعبه ثبت نشده است.</div>}
      </section>}

      <section className="cf-section">
        <div className="cf-title"><div><h3>۵ فاکتور آخر {cy}</h3><p>مانده و ریز وصول هر فاکتور از تسویه فاکتور در کارآمد؛ اگر یک چک چند فاکتور را تسویه کرده باشد، سهم همین فاکتور نمایش داده می‌شود.</p></div></div>
        {(file.last_invoices || []).length ? <LastInvoicesTable invoices={file.last_invoices} showVisitor={kind === "branch"} /> : <div className="invoice-source-pending">در {cy} فاکتوری ثبت نشده است.</div>}
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3>مطالبات</h3><p>{kind === "branch" ? "مانده دفتر کل مشتریانی که شعبه اصلی‌شان همین شعبه است." : "مانده دفتر کل مشتریانی که آخرین فاکتورشان را همین ویزیتور زده است (هر مشتری فقط یک‌بار شمرده می‌شود)."}</p></div></div>
        <div className="cf-kpis">
          <article className="cf-accent-red"><small>مانده بدهی مشتریان</small><b>{money(d.open_account_receivable_rial || 0)}</b><span>{fa(d.debtor_customer_count || 0)} مشتری بدهکار از {fa(d.customer_count || 0)}</span></article>
          <article><small>بستانکاری مشتریان</small><b>{money(d.customer_credit_rial || 0)}</b><span>تومان</span></article>
          <article><small>مانده تسویه‌نشده فاکتورهای {cy}</small><b>{money(d.current_year_unpaid_invoice_rial || 0)}</b><span>{fa(d.current_year_unpaid_invoice_count || 0)} فاکتور</span></article>
          <article><small>چک باز در دست شرکت</small><b>{money(ch.summary?.open?.amount_rial || 0)}</b><span>{fa(ch.summary?.open?.count || 0)} فقره</span></article>
        </div>
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3>چک‌های باز و احتمال برگشت</h3><p>احتمال برگشت هر چک از سابقه چک‌های همان مشتری (وصول و برگشت) به‌علاوه مبلغ، مدت و سررسید چک محاسبه شده است؛ برای دلایل، نشانگر را روی درصد نگه دارید.</p></div></div>
        <section className="customer-cheque-scope-cards">
          {([["open", "همه چک‌های باز"], ["high", "احتمال برگشت بالا"], ["medium", "احتمال برگشت متوسط"], ["low", "احتمال برگشت کم"], ["returned", "برگشتی"]] as const).map(([k, l]) => <button key={k} className={riskFilter === k ? "active" : ""} onClick={() => setRiskFilter(k)}>
            <small>{l}</small><b>{fa(ch.summary?.[k]?.count || 0)} فقره</b><span>{money(ch.summary?.[k]?.amount_rial || 0)} تومان</span>
          </button>)}
          <button className={`cf-review-card${riskFilter === "review" ? " active" : ""}`} onClick={() => setRiskFilter("review")}>
            <small>نیازمند بررسی بیشتر</small><b>{fa(reviewRows.length)} فقره</b><span>{money(reviewAmount)} تومان</span>
          </button>
        </section>
        {reviewRows.length > 0 && <div className="cf-review-alert">
          ⚠ {fa(reviewRows.length)} فقره چک به مبلغ {money(reviewAmount)} تومان سررسیدشان بیش از {fa(REVIEW_TERM_DAYS)} روز بعد از تاریخ دریافت است و مبلغشان بالای {money(REVIEW_AMOUNT_RIAL)} تومان است؛ نیازمند بررسی بیشتر هستند.
        </div>}
        {chequeRows.length ? <div className="cf-table"><table>
          <thead><tr><th>شماره چک</th><th>صیاد</th><th>مبلغ</th><th>تاریخ دریافت</th><th>سررسید</th><th>زمان سررسید</th><th>وضعیت</th><th>احتمال برگشت</th><th>بانک</th>{kind === "branch" && <th>ویزیتور</th>}</tr></thead>
          <tbody>{chequeRows.map((x: any) => <tr key={x.cheque_id} className={needsChequeReview(x) ? "cf-review-row" : undefined}>
            <td><b>{x.cheque_number || "—"}</b></td>
            <td>{x.sayad_number || "—"}</td>
            <td><b>{money(x.amount_rial || 0)}</b><small>تومان</small>{needsChequeReview(x) && <span className="cf-review-badge">⚠ نیازمند بررسی بیشتر</span>}</td>
            <td>{x.registration_date_jalali || "—"}</td>
            <td>{x.due_date_jalali || "—"}</td>
            <td>{typeof x.days_until_due !== "number" ? "—" : x.days_until_due < 0 ? `${fa(-x.days_until_due)} روز گذشته` : x.days_until_due === 0 ? "امروز" : `${fa(x.days_until_due)} روز مانده`}</td>
            <td>{x.cheque_status || "—"}</td>
            <td><ChequeReturnRisk risk={x.return_risk} /></td>
            <td>{x.bank || "—"}</td>
            {kind === "branch" && <td>{x.visitor_name || "—"}</td>}
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">چکی در این دسته وجود ندارد.</div>}
      </section>
    </article>
  </>;
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
  const [branch, setBranch] = useState("");
  const [search, setSearch] = useState("");
  const [customerSource, setCustomerSource] = useState<"rahkaran" | "karamad" | null>(null);
  const [karamad, setKaramad] = useState<any>({ customers: [], available_branches: [], summary: {} });
  const [karamadError, setKaramadError] = useState("");
  const [portfolio, setPortfolio] = useState<any>({ summary: {}, customers: [] });
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [debtFilter, setDebtFilter] = useState<"all" | "debtor" | "uncovered" | "cheque" | "creditor">("all");
  const [network, setNetwork] = useState<any>(null);
  const [networkError, setNetworkError] = useState("");
  useEffect(() => {
    let active = true;
    request("/sales-network")
      .then((d) => { if (active) setNetwork(d); })
      .catch((e) => { if (active) setNetworkError(e instanceof Error ? e.message : "دریافت شبکه فروش کارآمد ناموفق بود"); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    // Karamad has its own view (هیبرید من / ویزیتور); the debt portfolio is only for Rahkaran customers.
    if (customerSource !== "rahkaran") return;
    let active = true;
    setPortfolioLoading(true);
    request(`/customer-collection-portfolio?limit=1000&source=rahkaran`)
      .then((d) => { if (active) setPortfolio(d); })
      .catch(() => { if (active) setPortfolio({ summary: {}, customers: [] }); })
      .finally(() => { if (active) setPortfolioLoading(false); });
    return () => { active = false; };
  }, [customerSource, branch]);
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (branch) params.set("branch", branch);
    request(`/karamad-manual/customer-summary${params.toString() ? `?${params}` : ""}`)
      .then((data) => { if (active) { setKaramad(data); setKaramadError(""); } })
      .catch((e) => { if (active) setKaramadError(e instanceof Error ? e.message : "دریافت داده کارآمد ناموفق بود"); });
    return () => { active = false; };
  }, [branch]);

  const normalizeName = (value?: string) => String(value || "")
    .replace(/[يى]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/\u200c/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("fa-IR");

  const customerPortfolioAmount = (c: Customer) => {
    const k: any = c.karamad_activity || {};
    return Number(c.open_exposure || 0)
      + Number(k.received_cheque_amount_rial || 0)
      + Number(k.issued_cheque_amount_rial || 0)
      + Number(k.received_transfer_amount_rial || 0)
      + Number(k.paid_transfer_amount_rial || 0);
  };

  const customerStatus = (c: Customer) => {
    const k: any = c.karamad_activity || {};
    const overdue = Number(c.overdue_open_amount || 0) + Number(k.received_cheque_overdue_amount_rial || 0);
    const today = Number(k.received_cheque_today_amount_rial || 0);
    const future = Number(k.received_cheque_future_amount_rial || 0);
    if (overdue > 0) return { label: "دارای سررسید گذشته", tone: "danger" };
    if (today > 0) return { label: "سررسید امروز", tone: "critical" };
    if (future > 0) return { label: "دارای سررسید آینده", tone: "safe" };
    const r = c.counterpart_ref ? risk(c) : "safe";
    if (r === "critical") return { label: "پرریسک", tone: "critical" };
    if (r === "danger") return { label: "نیازمند توجه", tone: "danger" };
    return { label: "عادی / بدون معوق", tone: "safe" };
  };

  const merged = useMemo(() => {
    const byName = new Map<string, Customer>();
    customers.forEach((c) => {
      const key = normalizeName(cname(c));
      if (!key) return;
      byName.set(key, { ...c, data_source: "rahkaran" });
    });
    (karamad?.customers || []).forEach((k: any) => {
      const key = normalizeName(k.customer_name);
      if (!key) return;
      const existing = byName.get(key);
      byName.set(key, existing
        ? { ...existing, karamad_activity: k }
        : { customer_name: k.customer_name, data_source: "karamad", karamad_activity: k } as Customer);
    });
    let rows = [...byName.values()];
    if (branch) rows = rows.filter((c) => Boolean(c.karamad_activity));
    const q = normalizeName(search);
    if (q) rows = rows.filter((c) => normalizeName(cname(c)).includes(q));
    return rows.sort((a, b) => {
      const diff = customerPortfolioAmount(b) - customerPortfolioAmount(a);
      return diff !== 0 ? diff : cname(a).localeCompare(cname(b), "fa");
    });
  }, [customers, karamad, branch, search]);

  const rahkaranCustomers = merged.filter((c) => Boolean(c.counterpart_ref));
  // Karamad is shown as the sales network (هیبرید من / ویزیتور), never as a customer list.
  const sourceRows = customerSource === "rahkaran" ? rahkaranCustomers : [];
  const positions = useMemo(() => {
    const map = new Map<string, any>();
    (portfolio?.customers || []).forEach((p: any) => {
      const key = customerSource === "rahkaran" ? String(p.counterpart_ref) : normalizeName(p.customer_name || cname(p));
      map.set(key, p);
    });
    return map;
  }, [portfolio, customerSource]);
  const positionOf = (c: Customer): any => positions.get(customerSource === "rahkaran" ? String(c.counterpart_ref) : normalizeName(cname(c)))?.collection_position || {};
  const accountStateOf = (c: Customer): string => positions.get(customerSource === "rahkaran" ? String(c.counterpart_ref) : normalizeName(cname(c)))?.account_position?.balance_status || "unknown";
  const visibleRows = sourceRows.filter((c) => {
    const cp = positionOf(c);
    const debt = Number(cp.open_account_receivable_rial || 0), cheque = Number(cp.open_cheque_amount_rial || 0);
    if (debtFilter === "debtor") return debt > 0;
    if (debtFilter === "uncovered") return debt > 0 && cheque <= 0;
    if (debtFilter === "cheque") return cheque > 0;
    if (debtFilter === "creditor") return Number(cp.customer_credit_rial || 0) > 0;
    return true;
  });
  const debtSummary = portfolio?.summary || {};

  if (!customerSource) return (
    <>
      <AgentPanel agent={agent} />
      <section className="cheque-hub-intro customer-source-intro">
        <div>
          <small>پرونده مشتری</small>
          <h2>ابتدا منبع اطلاعات مشتری را انتخاب کنید</h2>
          <p>مثل بخش چک‌ها، ابتدا راهکاران یا کارآمد را باز کنید؛ سپس فهرست مشتریان همان منبع و در مرحله بعد ریز پرونده نمایش داده می‌شود.</p>
        </div>
        <span>راهکاران + کارآمد</span>
      </section>
      {karamadError && <div className="profile-warning">{karamadError}</div>}
      <section className="cheque-source-grid customer-source-grid">
        <button type="button" className="cheque-source-card rahkaran" onClick={() => { setCustomerSource("rahkaran"); setBranch(""); setSearch(""); }}>
          <span>پرونده‌های مشتری</span><h2>راهکاران</h2>
          <strong>{fa(rahkaranCustomers.length)}</strong><small>مشتری</small>
          <p>مشتریان شناسایی‌شده از راهکاران؛ آماده برای نمایش ریز چک، مانده، ریسک و سوابق مالی.</p>
          <b>مشاهده مشتریان راهکاران ←</b>
        </button>
        <button type="button" className="cheque-source-card karamad" onClick={() => { setCustomerSource("karamad"); setBranch(""); setSearch(""); }}>
          <span>شبکه فروش</span><h2>کارآمد</h2>
          <strong>{network ? fa(network.summary?.hybrid_count || 0) : "…"}</strong><small>هیبرید من · {network ? fa(network.summary?.active_visitor_count || 0) : "…"} ویزیتور فعال</small>
          <p>هیبرید من‌ها و ویزیتورهای کارآمد؛ فروش، مطالبات و چک‌های هر شعبه و هر ویزیتور.</p>
          <b>مشاهده هیبرید من‌ها و ویزیتورها ←</b>
        </button>
      </section>
    </>
  );

  if (customerSource === "karamad") return (
    <>
      <AgentPanel agent={agent} />
      <SalesNetwork data={network} error={networkError} onBack={() => setCustomerSource(null)} />
    </>
  );

  return (
    <>
      <AgentPanel agent={agent} />
      <button className="cheque-back" onClick={() => { setCustomerSource(null); setBranch(""); setSearch(""); setDebtFilter("all"); }}>→ بازگشت به انتخاب راهکاران یا کارآمد</button>
      <article className="fd-panel unified-customer-directory">
        <Heading
          h="پرونده مشتریان — راهکاران"
          p="فهرست مشتریان راهکاران؛ برای ورود به ریز پرونده روی مشتری کلیک کنید."
        />
        <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar">
          <div>
            <b>جستجو با نام مشتری</b>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="مثلاً نام شرکت یا مشتری را بنویسید..."
            />
          </div>
          <small>{fa(visibleRows.length)} مشتری پیدا شد</small>
        </section>
        <div className="cf-kpis cf-directory-kpis">
          <article className="cf-accent-red"><small>کل مانده بدهی مشتریان</small><b>{portfolioLoading ? "…" : money(debtSummary.open_account_receivable_rial || 0)}</b><span>تومان</span></article>
          <article><small>چک باز در دست شرکت</small><b>{portfolioLoading ? "…" : money(debtSummary.open_cheque_amount_rial || 0)}</b><span>تومان</span></article>
          <article><small>بستانکاری مشتریان</small><b>{portfolioLoading ? "…" : money(debtSummary.customer_credit_rial || 0)}</b><span>تومان</span></article>
        </div>
        <div className="collection-module-filters cf-debt-filters">
          {([["all", "همه"], ["debtor", "مانده بدهکار"], ["uncovered", "بدهکار بدون چک"], ["cheque", "دارای چک باز"], ["creditor", "بستانکار"]] as const).map(([k, l]) => <button key={k} className={debtFilter === k ? "active" : ""} onClick={() => setDebtFilter(k)}>{l}</button>)}
        </div>
        {karamadError && <div className="profile-warning">{karamadError}</div>}
        <div className="fd-table">
          <table>
            <thead>
              <tr>
                <th>مشتری</th>
                <th>مانده بدهی</th>
                <th>ارزش پرونده</th>
                <th>مانده باز</th>
                <th>معوق</th>
                <th>چک برگشتی</th>
                <th>چک آینده</th>
                <th>چک‌های ثبت‌شده</th>
                <th>حواله‌های ثبت‌شده</th>
                <th>شعبه / فعالیت</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((c) => {
                const k: any = c.karamad_activity || {};
                const chequeCount = Number(c.historical_cheque_count || 0) + Number(k.received_cheque_count || 0) + Number(k.issued_cheque_count || 0);
                const transferCount = Number(k.received_transfer_count || 0) + Number(k.paid_transfer_count || 0);
                return <tr key={`${c.counterpart_ref || "no-ref"}-${normalizeName(cname(c))}`} onClick={() => open({ ...c, data_source: "rahkaran", karamad_activity: undefined })}>
                  <td><b>{cname(c)}</b></td>
                  <td>{portfolioLoading ? "…" : <><b>{money(positionOf(c).open_account_receivable_rial || 0)}</b> <span className={`collection-account-state ${accountStateOf(c)}`}>{({ debtor: "بدهکار", creditor: "بستانکار", settled: "تسویه" } as any)[accountStateOf(c)] || "—"}</span></>}</td>
                  <td><b>{money(customerPortfolioAmount(c))}</b></td>
                  <td>{c.counterpart_ref ? money(c.open_exposure) : "—"}</td>
                  <td>{c.counterpart_ref ? money(c.overdue_open_amount) : money(k.received_cheque_overdue_amount_rial || 0)}</td>
                  <td><b>{fa(c.counterpart_ref ? (c.returned_cheque_count || 0) : (k.received_cheque_returned_count || 0))}</b> فقره · {money(c.counterpart_ref ? (c.returned_cheque_amount || 0) : (k.received_cheque_returned_amount_rial || 0))}</td>
                  <td><b>{fa(c.counterpart_ref ? (c.future_open_cheque_count || 0) : (k.received_cheque_future_count || 0))}</b> فقره · {money(c.counterpart_ref ? (c.future_open_cheque_amount || 0) : (k.received_cheque_future_amount_rial || 0))}</td>
                  <td><b>{fa(chequeCount)}</b> فقره</td>
                  <td><b>{fa(transferCount)}</b> ردیف</td>
                  <td>{k.movement_count ? `${fa(k.movement_count)} گردش · ${(k.branches || []).join("، ") || "بدون شعبه"}` : (c.counterpart_ref ? "اطلاعات راهکاران" : "—")}</td>
                  <td>{(() => { const s = customerStatus(c); return <span className={`fd-badge ${s.tone}`}>{s.label}</span>; })()}</td>
                </tr>;
              })}
            </tbody>
          </table>
          {!visibleRows.length && <div className="profile-loading">مشتری با این نام یا فیلتر پیدا نشد.</div>}
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
function Cashflow({ cash, agent, openAgent }: { cash?: any; agent?: AgentResult; openAgent: (key: string) => void }) {
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
      <AgentPanel agent={agent} />
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
  focusKey,
}: {
  agents?: Record<string, AgentResult>;
  manager?: AgentResult;
  focusKey?: string | null;
}) {
  const hub = manager?.data_context?.karamad || {};
  const paid = hub?.paid_transfers || {};
  const agentEntries = Object.entries(agents || {}).sort(([a], [b]) => {
    if (a === focusKey) return -1;
    if (b === focusKey) return 1;
    return 0;
  });
  return (
    <>
      <ManagerPanel a={manager?.analysis} />
      {hub?.record_count !== undefined && (
        <article className="fd-panel agent-data-hub">
          <Heading h="Snapshot داده متصل به Agentها" p="همه Agentهای مالی این نسخه داده را به‌صورت مشترک می‌خوانند؛ با آپلود Snapshot جدید، گزارش Agentها دوباره ساخته می‌شود." />
          <div className="audit-status-grid">
            <article><small>کل رکورد کارآمد</small><b>{fa(hub.record_count || 0)}</b><em>Snapshot فعلی</em></article>
            <article><small>چک دریافتی</small><b>{fa(hub?.received_cheques?.count || 0)}</b><em>{money(hub?.received_cheques?.amount_rial || 0)}</em></article>
            <article><small>چک پرداختی ثبت‌شده</small><b>{fa(hub?.issued_cheques?.count || 0)}</b><em>آینده کامل نیست</em></article>
            <article><small>حواله دریافت</small><b>{fa(hub?.received_transfers?.count || 0)}</b><em>{money(hub?.received_transfers?.amount_rial || 0)}</em></article>
            <article><small>حواله پرداخت</small><b>{fa(paid?.count || 0)}</b><em>{money(paid?.amount_rial || 0)}</em></article>
            <article><small>انتقال بانک‌به‌بانک</small><b>{fa(paid?.bank_to_bank_count || 0)}</b><em>اثر خالص صفر</em></article>
            <article><small>مشتری کارآمد</small><b>{fa(hub?.customer_count || 0)}</b><em>پرونده یکپارچه</em></article>
          </div>
        </article>
      )}
      {focusKey && agents?.[focusKey] && (
        <div className="agent-focus-note">
          <span>Agent انتخاب‌شده برای جزئیات گزارش</span>
          <b>{agents[focusKey]?.metadata?.agent_name || focusKey}</b>
        </div>
      )}
      <div className="agent-grid large">
        {agentEntries.map(([key, a]) => (
          <div key={key} className={key === focusKey ? "agent-focused-wrap" : ""}>
            <AgentCard agent={a} />
          </div>
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
        if (active && j.customer) setDetail({ ...j.customer, karamad_activity: c.karamad_activity });
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
  const kd: any = detail.karamad_activity?.detail || {};
  const ks: any = kd.summary || {};
  const total = (detail.historical_total_cheque_amount || 0) + (ks.received_cheque_amount_rial || 0),
    collected = detail.collected_cheque_amount || 0,
    open = (detail.open_exposure || 0) + (ks.received_cheque_future_amount_rial || 0) + (ks.received_cheque_overdue_amount_rial || 0) + (ks.received_cheque_today_amount_rial || 0),
    returned = (detail.returned_cheque_amount || 0) + (ks.received_cheque_returned_amount_rial || 0),
    returnedCount = Number(detail.returned_cheque_count || 0) + Number(ks.received_cheque_returned_count || 0),
    futureAmount = Number(detail.future_open_cheque_amount || 0) + Number(ks.received_cheque_future_amount_rial || 0),
    futureCount = Number(detail.future_open_cheque_count || 0) + Number(ks.received_cheque_future_count || 0),
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
            n={`${fa(returnedCount)} فقره • تومان`}
            c="red"
          />
          <K
            t="چک‌های آینده"
            v={money(futureAmount)}
            n={`${fa(futureCount)} فقره • تومان`}
            c="blue"
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
        {detail.counterpart_ref ? <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button> : null}
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
function CashFlowCompositionChart({ summary }: { summary: any }) {
  const rows = [
    { label: "وصول چک", value: Number(summary.reliable_received_cheques_rial || 0), tone: "#19a974" },
    { label: "چک پرداختی", value: Number(summary.issued_cheques_rial || 0), tone: "#f59e0b" },
    { label: "حقوق", value: Number(summary.salary_reserve_rial || 0), tone: "#ef4444" },
  ];
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <section className="cash-composition-chart">
      <b>ترکیب مهم‌ترین ورودی و خروجی‌های بازه</b>
      {rows.map((row) => <div key={row.label}>
        <span>{row.label}</span>
        <i><em style={{ width: `${(row.value / max) * 100}%`, background: row.tone }} /></i>
        <strong>{money(row.value)} تومان</strong>
      </div>)}
    </section>
  );
}
function CashTable({ days }: { days: CashDay[] }) {
  return (
    <div className="cash-table-wrap">
      <table className="cash-table">
        <thead>
          <tr>
            <th>تاریخ</th>
            <th>چک دریافتی ≥۸۵٪</th>
            <th>چک پرداختی</th>
            <th>حقوق</th>
            <th>خالص روز</th>
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
                <td className="positive">+ {money(d.reliable_received_cheques || 0)}</td>
                <td className="negative">− {money(d.issued_cheques_due || 0)}</td>
                <td className="negative">− {money(d.salary_reserve || 0)}</td>
                <td className={n < 0 ? "negative" : "positive"}>{money(n)}</td>
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
      customers: "خرید، ویزیتور، مطالبات، چک‌ها و احتمال برگشت هر مشتری",
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
      format: key.includes("rial") || key.includes("amount") ? "money" : "number",
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
                x.format === "money" ? "amount_rial" : "",
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
  const isCashBankMovement = agent?.metadata?.agent_name === "Cash & Bank Movement Agent";
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
  if (isCashBankMovement) {
    const actual = metricRows(p.actual_period, 3);
    return (
      <section className="agent-visual-grid generic cash-bank-agent-visual">
        <article className="agent-visual-card">
          <header>
            <b>گردش قطعی نقد و بانک؛ ۳۰ روز اخیر</b>
            <small>فقط دریافت و پرداخت عملیاتیِ تأییدشده؛ نه چک، نه انتقال داخلی و نه تنخواه</small>
          </header>
          {actual.length ? <HorizontalMetrics rows={actual} /> : <div className="agent-empty-chart">دادهٔ گردش قطعی در دسترس نیست</div>}
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
  const context = a?.report_context;
  const dateLabel = (value?: string) => {
    if (!value) return "تعیین نشده";
    if (/^1[34]/.test(value)) return value;
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString("fa-IR", { timeZone: "Asia/Tehran" });
  };
  const valueLabel = (item: NonNullable<Analysis["executive_kpis"]>[number]) => {
    if (item.available === false || (item.value_rial == null && item.value == null)) return "در انتظار داده معتبر";
    if (item.format === "percent") return `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(item.value!)}٪`;
    if (item.format === "count") return fa(item.value!);
    return `${fullToman(item.value_rial!)} تومان`;
  };
  if (!context || context.version !== "v113") return <article className="executive-report-v109"><h2>گزارش مدیریتی نقدینگی و تعهدات</h2><p>برای دریافت گزارش با ساختار جدید، «اجرای همه Agentها» را انتخاب کنید.</p></article>;
  const groups = [
    { key: "actual", title: "نقد و حواله", detail: `${dateLabel(context.actual_from)} تا ${dateLabel(context.actual_to)} · اسناد قطعی · بدون اثر انتقال داخلی در خالص` },
    { key: "cheques", title: "مانده چک‌های باز", detail: "سبد یکپارچه راهکاران و کارآمد؛ تفکیک امروز و آینده از سررسیدگذشته" },
    { key: "forecast", title: "پیش‌بینی نقدینگی", detail: `${dateLabel(context.forecast_from)} تا ${dateLabel(context.forecast_to)} · ${context.decision_basis}` },
  ];
  return <article className="executive-report-v109">
    <header className="executive-title"><div><small>گزارش مدیر مالی · {dateLabel(context.generated_at)}</small><h2>{a?.headline}</h2></div><Status x={a?.management_status || "attention"} /></header>
    <div className={`executive-conclusion ${a?.management_status}`}><b>ارزیابی وضعیت نقدینگی</b><p>{textOf(a?.summary)}</p></div>
    {!!(a?.alarms || []).length && <section className="executive-section executive-alarm-section">
      <header><h3>هشدارهای مدیریتی</h3><p>فقط مواردی که نیازمند تصمیم یا پیگیری هستند</p></header>
      <div className="executive-alarms">{(a?.alarms || []).filter(x => x.level !== "info").slice(0,4).map((alarm, index) => <article key={alarm.code || index} className={`executive-alarm ${alarm.level || "warning"}`}>
        <div className="executive-alarm-icon">!</div>
        <div><header><b>{alarm.title}</b><span>{alarm.level === "critical" ? "بحرانی" : alarm.level === "high" ? "مهم" : "هشدار"}</span></header><p>{alarm.message}</p><small>{alarm.impact}</small><footer><span>مسئول: {alarm.owner || "تعیین نشده"}</span><span>مهلت: {alarm.deadline || "تعیین نشده"}</span><span>جزئیات: {alarm.agent || "Agent تخصصی"}</span></footer></div>
      </article>)}</div>
    </section>}
    {groups.map(group => <section className="executive-section" key={group.key}>
      <header><h3>{group.title}</h3><p>{group.detail}</p></header>
      <div className="executive-metrics">{(a?.executive_kpis || []).filter(item => item.group === group.key).map(item => <div key={item.label} className={`executive-metric ${item.tone || "blue"}`}><span>{item.label}</span><strong dir="rtl">{valueLabel(item)}</strong>{item.note && <small>{item.note}</small>}</div>)}</div>
      {group.key === "forecast" && <p className="executive-shortage"><b>اولین روز کسری احتمالی: </b>{!context.opening_available ? "نیازمند موجودی شروع معتبر" : context.first_shortage ? dateLabel(context.first_shortage) : context.forecast_to ? "در بازه محاسبه‌شده گزارش نشده" : "پیش‌بینی در دسترس نیست"}</p>}
    </section>)}
    {a?.future_outlook && <section className="executive-section"><header><h3>تصویر آینده</h3><p>۷ / ۳۰ / ۹۰ روز؛ خلاصه تصمیمی، جزئیات در Cash Flow Agent</p></header><div className="executive-future-grid">{[["۷ روز", a.future_outlook["7_days"]],["۳۰ روز", a.future_outlook["30_days"]],["۹۰ روز", a.future_outlook["90_days"]]].map(([label, item]: any) => <article key={label}><span>{label}</span><strong>{item?.available ? `${fullToman(item.net_rial || 0)} تومان` : "داده کافی نیست"}</strong><small>{item?.shortage ? "ریسک کسری در این افق" : item?.available ? "کسری قطعی گزارش نشده" : "پیش‌بینی در دسترس نیست"}</small></article>)}</div></section>}
    <section className="executive-section"><header><h3>سه اقدام اولویت‌دار</h3><p>مسئول اجرا و مهلت پیگیری</p></header><div className="executive-actions">{(a?.recommended_actions || []).slice(0, 3).map((item, index) => <article key={index}><span className="executive-action-number">{fa(index + 1)}</span><div><h4>{item.action}</h4><p>{item.why}</p><footer><span>{item.owner}</span><span>{item.deadline}</span></footer></div></article>)}</div></section>
  </article>;
}
function AgentPanel({ agent }: { agent?: AgentResult }) {
  const a = agent?.analysis,
    p = a?.prediction || {},
    s = a?.scenarios || {},
    actions = a?.recommended_actions || [];
  const isCashBankMovement = agent?.metadata?.agent_name === "Cash & Bank Movement Agent";
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
          {!isCashBankMovement && <>
            <section className="decision-forecast">
              <div>
                <small>۷ روز آینده</small>
                <b>{textOf(p.next_7_days) || "در انتظار داده"}</b>
              </div>
              <div>
                <small>پیش‌بینی پایان ماه</small>
                <b>{textOf(p.end_of_month) || textOf(a.future_outlook) || "در انتظار داده"}</b>
              </div>
              <div>
                <small>اطمینان</small>
                <b>{p.confidence === "high" ? "زیاد" : p.confidence === "medium" ? "متوسط" : "کم"}</b>
              </div>
            </section>
            <section className="scenario-strip">
              {(["optimistic", "base", "pessimistic"] as const).map((key, i) => (
                <div className={key} key={key}>
                  <small>{i === 0 ? "خوش‌بینانه" : i === 1 ? "سناریوی پایه" : "بدبینانه"}</small>
                  <span>{textOf(s[key]) || "—"}</span>
                </div>
              ))}
            </section>
          </>}
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

function ChequeReturnRisk({ risk }: { risk?: any }) {
  if (!risk) return <span className="cf-muted">—</span>;
  if (risk.state !== "open") return <span className={`cf-risk ${risk.state}`}>{risk.label}</span>;
  return <span className={`cf-risk ${risk.level}`} title={(risk.reasons || []).join("\n")}>
    <b>{fa(risk.probability_percent)}٪</b> {risk.label.replace("احتمال برگشت ", "")}
  </span>;
}

function UnifiedCustomerActivityTables({ c }: { c: Customer }) {
  const kdetail: any = c.karamad_activity?.detail || {};
  const rahkaranChecks: any[] = ((c.all_cheques && c.all_cheques.length ? c.all_cheques : c.open_cheques) || []).map((x: any) => ({
    ...x,
    activity_type: /برگشت|واخواست/.test(String(x.state_label || "")) ? "چک برگشتی" : "چک دریافتی",
    source_system: "rahkaran",
    source_label: "راهکاران",
    cheque_number: x.serial_number || x.document_number || x.receipt_number,
    sayad_number: x.sayad_number,
    amount_rial: x.amount || 0,
    registration_date_jalali: x.receipt_date_jalali || x.receipt_date,
    due_date_jalali: x.due_date_jalali || x.due_date,
    cheque_status: x.state_label || "نامشخص",
    days_until_due: typeof x.days_to_due === "number" ? x.days_to_due : daysToDue(x),
    bank: x.bank_name,
    branch: x.bank_branch_name,
    description: x.description,
  }));
  // V146: all_cheques already contains returned historical rows.  Keep the old
  // returned endpoint only as a compatibility fallback for older API payloads.
  const rahkaranReturned: any[] = (c.all_cheques && c.all_cheques.length ? [] : (c.returned_cheques || [])).map((x: any) => ({
    ...x, activity_type: "چک برگشتی", source_system: "rahkaran", source_label: "راهکاران",
    cheque_number: x.serial_number || x.receipt_number, amount_rial: x.amount || 0, cheque_status: x.state_label || "برگشتی / واخواست‌شده",
  }));
  const karamadReceived: any[] = (kdetail.received_cheques || []).map((x: any) => ({ ...x, activity_type: "چک دریافتی" }));
  const karamadIssued: any[] = (kdetail.issued_cheques || []).map((x: any) => ({ ...x, activity_type: "چک پرداختی" }));
  // Oldest due date first; rows without any date go last.
  const chequeRows = [...rahkaranChecks, ...rahkaranReturned, ...karamadReceived, ...karamadIssued].sort((a, b) => {
    const da = String(a.due_date_jalali || a.registration_date_jalali || ""), db = String(b.due_date_jalali || b.registration_date_jalali || "");
    return !da ? (db ? 1 : 0) : !db ? -1 : da.localeCompare(db, "fa");
  });
  const transferRows = [
    ...(kdetail.received_transfers || []).map((x: any) => ({ ...x, activity_type: "حواله دریافتی" })),
    ...(kdetail.paid_transfers || []).map((x: any) => ({ ...x, activity_type: "حواله پرداختی" })),
  ].sort((a, b) => String(b.registration_date_jalali || b.transfer_date_jalali || "").localeCompare(String(a.registration_date_jalali || a.transfer_date_jalali || ""), "fa"));

  const [chequeScope, setChequeScope] = useState<"all" | "collected" | "returned" | "future" | "overdue" | "risk">("all");
  const [activitySearch, setActivitySearch] = useState("");
  const isReturnedCheque = (x: any) => /برگشت|واخواست|مسترد/.test(String(x.cheque_status || x.state_label || x.activity_type || ""));
  const chequeDay = (x: any) => typeof x.days_until_due === "number" ? x.days_until_due : daysToDue(x);
  const returnedRows = chequeRows.filter(isReturnedCheque);
  // return_risk (backend) knows the real final state; «در جریان وصول» is not collected.
  const collectedRows = chequeRows.filter((x: any) => x.return_risk ? x.return_risk.state === "collected" : /وصول‌?\s?شده/.test(String(x.cheque_status || x.state_label || "")));
  const riskRows = chequeRows.filter((x: any) => x.return_risk?.state === "open" && x.return_risk.level !== "low");
  // V162: a collected cheque is never overdue, whatever its historical due date.
  const isCollectedCheque = (x: any) => collectedRows.includes(x);
  const futureRows = chequeRows.filter((x: any) => { const d = chequeDay(x); return !isReturnedCheque(x) && !isCollectedCheque(x) && d !== undefined && d >= 0; });
  const overdueRows = chequeRows.filter((x: any) => { const d = chequeDay(x); return !isReturnedCheque(x) && !isCollectedCheque(x) && d !== undefined && d < 0; });
  // Rahkaran cheques with status «وصول شده» are hidden from «کل چک‌ها»; they stay reachable via the «وصول‌شده» card.
  const isRahkaranCollected = (x: any) => x.source_system === "rahkaran" && (x.master_state === 3 || /^وصول[‌\s]?شده$/.test(String(x.cheque_status || "").trim()));
  const visibleChequeRows = chequeRows.filter((x: any) => !isRahkaranCollected(x));
  const scopeRows = chequeScope === "collected" ? collectedRows : chequeScope === "returned" ? returnedRows : chequeScope === "future" ? futureRows : chequeScope === "overdue" ? overdueRows : chequeScope === "risk" ? riskRows : visibleChequeRows;
  const q = activitySearch.trim().toLocaleLowerCase("fa-IR");
  const filteredChequeRows = !q ? scopeRows : scopeRows.filter((x: any) => [x.cheque_number, x.sayad_number, x.cheque_status, x.state_label, x.bank, x.bank_name, x.branch, x.description, x.return_reason, x.amount_rial].filter(Boolean).some((v) => String(v).toLocaleLowerCase("fa-IR").includes(q)));
  const filteredChequeAmount = filteredChequeRows.reduce((sum: number, x: any) => sum + Number(x.amount_rial || x.amount || 0), 0);

  const dueLabel = (x: any) => {
    const d = typeof x.days_until_due === "number" ? x.days_until_due : undefined;
    if (d === undefined) return "نامشخص";
    if (d < 0) return `${fa(Math.abs(d))} روز گذشته`;
    if (d === 0) return "امروز";
    return `${fa(d)} روز مانده`;
  };
  const dueClass = (x: any) => {
    const d = typeof x.days_until_due === "number" ? x.days_until_due : undefined;
    return d === undefined ? "unknown" : d < 0 ? "late" : d <= 7 ? "soon" : "normal";
  };

  return (
    <section className="unified-customer-activity">
      <div className="profile-section-title">
        <div>
          <h3>چک و سررسید این مشتری</h3>
          <p>همان الگوی صفحه چک و سررسید: جمع، فیلتر وضعیت/زمان، جستجو و سپس ریز کامل چک.</p>
        </div>
        <b>{fa(filteredChequeRows.length)} فقره · {money(filteredChequeAmount)} تومان</b>
      </div>
      <section className="customer-cheque-scope-cards">
        {[
          ["all", "کل چک‌ها", visibleChequeRows],
          ["collected", "وصول‌شده", collectedRows],
          ["returned", "برگشتی / واخواست", returnedRows],
          ["future", "آینده", futureRows],
          ["overdue", "سررسیدگذشته", overdueRows],
          ["risk", "احتمال برگشت دارد", riskRows],
        ].map(([id, title, items]: any) => <button key={id} className={chequeScope === id ? "active" : ""} onClick={() => setChequeScope(id)}>
          <small>{title}</small><b>{fa(items.length)} فقره</b><span>{money(items.reduce((sum: number, x: any) => sum + Number(x.amount_rial || x.amount || 0), 0))} تومان</span>
        </button>)}
      </section>
      <section className="cash-bank-toolbar cheque-list-search customer-activity-search">
        <div><b>جستجو در چک‌های مشتری</b><input value={activitySearch} onChange={(e) => setActivitySearch(e.target.value)} placeholder="شماره چک، صیاد، بانک، وضعیت، مبلغ یا توضیحات..." /></div>
        <small>{fa(filteredChequeRows.length)} نتیجه</small>
      </section>
      {filteredChequeRows.length ? <div className="profile-cheque-table"><table>
        <thead><tr><th>نوع</th><th>شماره چک</th><th>صیاد</th><th>مبلغ</th><th>تاریخ ثبت/دریافت</th><th>سررسید</th><th>زمان سررسید</th><th>وضعیت</th><th>احتمال برگشت</th><th>بانک / شعبه</th><th>توضیحات</th><th>منبع</th></tr></thead>
        <tbody>{filteredChequeRows.map((x: any, i: number) => <tr key={`unified-cheque-${x.cheque_id || x.transfer_id || i}`} className={typeof x.days_until_due === "number" && x.days_until_due < 0 ? "overdue-row" : typeof x.days_until_due === "number" && x.days_until_due <= 7 ? "due-soon-row" : ""}>
          <td><b>{x.activity_type}</b></td>
          <td><b>{fa(x.cheque_number || x.transfer_number || x.serial_number || "—")}</b></td>
          <td>{fa(x.sayad_number || "—")}</td>
          <td><b>{money(x.amount_rial || x.amount || 0)} تومان</b></td>
          <td>{x.registration_date_jalali || x.receipt_date_jalali || x.registration_date || x.receipt_date || "—"}</td>
          <td>{x.due_date_jalali || x.effective_date_jalali || x.due_date || "—"}</td>
          <td><span className={`profile-due ${dueClass(x)}`}>{dueLabel(x)}</span></td>
          <td><span className={`cheque-business-status ${x.source_system === "rahkaran" ? "rahkaran" : "karamad"}`}>{x.cheque_status || x.state_label || "ثبت‌شده"}</span>{x.cheque_location ? <small className="customer-row-sub">{x.cheque_location}</small> : null}</td>
          <td><ChequeReturnRisk risk={x.return_risk} /></td>
          <td>{[x.bank || x.bank_name, x.branch || x.bank_branch_name || x.bank_and_branch].filter(Boolean).join(" / ") || "—"}</td>
          <td>{[x.purpose, x.description, x.return_reason].filter(Boolean).join(" — ") || "—"}</td>
          <td><span className={`source-badge ${x.source_system || "karamad"}`}>{x.source_label || (x.source_system === "rahkaran" ? "راهکاران" : "کارآمد")}</span></td>
        </tr>)}</tbody>
      </table></div> : <div className="profile-loading">ریز چک قابل نمایش برای این مشتری وجود ندارد.</div>}

      <div className="profile-section-title unified-transfer-title">
        <div>
          <h3>ریز حواله‌های مشتری</h3>
          <p>حواله‌های دریافتی و پرداختی ثبت‌شده در یک جدول جدا.</p>
        </div>
        <b>{fa(transferRows.length)} ردیف</b>
      </div>
      {transferRows.length ? <div className="profile-cheque-table"><table>
        <thead><tr><th>نوع</th><th>شماره حواله</th><th>تاریخ ثبت</th><th>تاریخ حواله</th><th>مبلغ</th><th>بانک</th><th>شعبه</th><th>بابت / توضیحات</th><th>منبع</th></tr></thead>
        <tbody>{transferRows.map((x: any, i: number) => <tr key={`unified-transfer-${x.transfer_id || i}`}>
          <td><b>{x.activity_type}</b></td>
          <td><b>{fa(x.transfer_number || x.document_number || x.transfer_id || "—")}</b></td>
          <td>{x.registration_date_jalali || "—"}</td>
          <td>{x.transfer_date_jalali || x.effective_date_jalali || "—"}</td>
          <td><b>{money(x.amount_rial || 0)} تومان</b></td>
          <td>{x.bank || "—"}</td>
          <td>{x.branch || "—"}</td>
          <td>{[x.purpose, x.description].filter(Boolean).join(" — ") || "—"}</td>
          <td><span className="source-badge karamad">کارآمد</span></td>
        </tr>)}</tbody>
      </table></div> : <div className="profile-loading">ریز حواله ثبت‌شده برای این مشتری وجود ندارد.</div>}
    </section>
  );
}

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
      {c.data_source === "karamad" && c.karamad_activity && (
        <div className="karamad-summary">
          <div><span>شعبه‌های کارآمد</span><b>{(c.karamad_activity.branches || []).join("، ") || "—"}</b></div>
          <div><span>گردش کارآمد</span><b>{fa(c.karamad_activity.movement_count || 0)} ردیف</b></div>
          <div><span>چک دریافتی کارآمد</span><b>{fa(c.karamad_activity.received_cheque_count || 0)} فقره · {money(c.karamad_activity.received_cheque_amount_rial || 0)} تومان</b></div>
          <div><span>حواله دریافتی کارآمد</span><b>{fa(c.karamad_activity.received_transfer_count || 0)} فقره · {money(c.karamad_activity.received_transfer_amount_rial || 0)} تومان</b></div>
        </div>
      )}
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

function customerFilePath(c: Customer): string | null {
  if (c.data_source === "rahkaran" && c.counterpart_ref) return `/customer-file/rahkaran/${c.counterpart_ref}`;
  const dlRefs = c.karamad_activity?.dl_refs || c.karamad_activity?.detail?.account_position?.dl_refs || [];
  if (c.data_source === "karamad" && dlRefs.length) return `/customer-file/karamad?dl_refs=${dlRefs.join(",")}`;
  return null;
}

function LastInvoicesTable({ invoices, showVisitor = false }: { invoices: any[]; showVisitor?: boolean }) {
  return <div className="cf-table"><table>
    <thead><tr><th>شماره فاکتور</th><th>تاریخ</th>{showVisitor && <th>ویزیتور</th>}<th>مبلغ فروش</th><th>مانده بدهی</th><th>جریان وصول</th></tr></thead>
    <tbody>{invoices.map((inv) => {
      const pct = Math.max(0, Math.min(100, Number(inv.collected_percent ?? 0)));
      return <tr key={inv.invoice_id}>
        <td><b>{/^\d+$/.test(inv.number || "") ? Number(inv.number).toLocaleString("fa-IR", { useGrouping: false }) : inv.number || "—"}</b></td>
        <td>{inv.date_jalali || "—"}</td>
        {showVisitor && <td>{inv.visitor_name || "—"}</td>}
        <td><b>{money(inv.amount_rial || 0)}</b><small>تومان</small></td>
        <td className={Number(inv.remaining_rial || 0) > 0 ? "cf-debt" : "cf-settled"}>{inv.remaining_rial == null ? "نامشخص" : Number(inv.remaining_rial) > 0 ? `${money(inv.remaining_rial)} تومان` : "تسویه شده"}</td>
        <td className="cf-flow">
          {inv.collected_percent == null ? "—" : <>
            <div className="cf-bar"><i style={{ width: `${pct}%` }} /></div>
            <small>{fa(pct)}٪ وصول شده · {money(inv.collected_rial || 0)} تومان</small>
            {(inv.collection_breakdown || []).length > 0 && <div className="cf-chips">{inv.collection_breakdown.map((b: any) => <span key={b.method}>{b.method}: {money(b.amount_rial)}</span>)}</div>}
          </>}
        </td>
      </tr>;
    })}</tbody>
  </table></div>;
}

function CustomerFileOverview({ c }: { c: Customer }) {
  const path = customerFilePath(c);
  const [file, setFile] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!path) return;
    let active = true;
    setFile(null); setError("");
    request(path)
      .then((d) => { if (active) setFile(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت فاکتورهای مشتری ناموفق بود"); });
    return () => { active = false; };
  }, [path]);

  if (!path) return <div className="profile-warning">شناسه این مشتری برای خواندن فاکتورها پیدا نشد.</div>;
  if (error) return <div className="profile-warning">{error}</div>;
  if (!file) return <div className="profile-loading">در حال دریافت فاکتورهای خرید مشتری...</div>;

  const s = file.purchase_stats || {};
  const cy = file.current_year_label || "سال جاری";
  const py = file.previous_year_label || "سال قبل";
  const network = file.sales_network || {};
  const invoices: any[] = file.last_invoices || [];
  return (
    <>
      <section className="cf-section">
        <div className="cf-title">
          <div><h3>خرید مشتری</h3><p>{file.source === "karamad" ? "فاکتورهای فروش کارآمد (tblFactorF)" : "فاکتورهای فروش قطعی راهکاران (SLS3.Invoice)"}</p></div>
          {s.last_invoice_date_jalali && <small>آخرین فاکتور: {s.last_invoice_date_jalali}</small>}
        </div>
        <div className="cf-kpis">
          <article><small>تعداد کل فاکتور خرید</small><b>{fa(s.invoice_count || 0)}</b><span>از {s.first_invoice_date_jalali || "—"}</span></article>
          <article><small>کل مبلغ خرید تا امروز</small><b>{money(s.purchase_amount_rial || 0)}</b><span>تومان</span></article>
          <article><small>تعداد فاکتور خرید {cy}</small><b>{fa(s.current_year_invoice_count || 0)}</b><span>{money(s.current_year_amount_rial || 0)} تومان</span></article>
          <article><small>تعداد فاکتور خرید {py}</small><b>{fa(s.previous_year_invoice_count || 0)}</b><span>{money(s.previous_year_amount_rial || 0)} تومان</span></article>
        </div>
        {Number(s.draft_invoice_count || 0) > 0 && <small className="cf-note">{fa(s.draft_invoice_count)} فاکتور پیش‌نویس/غیرقطعی راهکاران در این آمار شمرده نشده است.</small>}
      </section>

      <section className="cf-section">
        <div className="cf-title">
          <div><h3>فروش ویزیتور</h3><p>هیبرید ← سرپرست ← ویزیتوری که به این مشتری فروخته است</p></div>
        </div>
        {network.visitors?.length ? <div className="cf-table"><table>
          <thead><tr><th>ویزیتور</th><th>شعبه</th><th>سرپرست</th><th>هیبرید من</th><th>فروش ویزیتور {cy}</th><th>فروش ویزیتور {py}</th><th>خرید این مشتری از او {cy}</th><th>خرید این مشتری از او {py}</th><th>آخرین فاکتور</th></tr></thead>
          <tbody>{network.visitors.map((v: any) => <tr key={v.visitor_id}>
            <td><b>{v.visitor_name || "—"}</b>{!v.active && <small className="cf-muted">غیرفعال</small>}</td>
            <td>{v.branch || "—"}</td>
            <td>{v.supervisor || "—"}</td>
            <td className="cf-wrap">{(v.hybrids || []).join("، ") || "—"}</td>
            <td><b>{money(v.visitor_sales_current_year_rial || 0)}</b><small>{fa(v.visitor_invoice_count_current_year || 0)} فاکتور</small></td>
            <td><b>{money(v.visitor_sales_previous_year_rial || 0)}</b><small>{fa(v.visitor_invoice_count_previous_year || 0)} فاکتور</small></td>
            <td>{money(v.customer_sales_current_year_rial || 0)}</td>
            <td>{money(v.customer_sales_previous_year_rial || 0)}</td>
            <td>{v.last_invoice_date_jalali || "—"}</td>
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">{network.note || "برای این مشتری ویزیتوری ثبت نشده است."}</div>}
      </section>

      <section className="cf-section">
        <div className="cf-title">
          <div><h3>۵ فاکتور آخر {cy}</h3><p>{file.remaining_note}</p></div>
        </div>
        {invoices.length ? <LastInvoicesTable invoices={invoices} /> : <div className="invoice-source-pending">این مشتری در {cy} فاکتور خرید ندارد.</div>}
      </section>
    </>
  );
}

function CustomerReceivables({ detail }: { detail: Customer }) {
  const isKaramad = detail.data_source === "karamad";
  const kd: any = detail.karamad_activity?.detail || {};
  const ap: any = (isKaramad ? kd.account_position : detail.account_position) || {};
  const cp: any = (isKaramad ? kd.collection_position : detail.collection_position) || {};
  if (!ap.found && !cp.total_collection_exposure_rial) return null;
  const breakdown: any[] = ap.account_breakdown || [];
  const monthly: any[] = isKaramad ? kd.monthly_summary || [] : [];
  const ledger: any[] = isKaramad ? kd.ledger_entries || [] : [];
  return (
    <section className="cf-section">
      <div className="cf-title">
        <div><h3>مطالبات مشتری</h3><p>{isKaramad ? "مانده از دفتر کل کارآمد (tblVoucherLines) سال مالی جاری روی تفصیلی مشتری" : "مانده از گردش سند سال مالی روی حساب‌های دریافتنی تجاری، برگشتی و اشخاص"}</p></div>
        <span className={`collection-account-state ${ap.balance_status || "unknown"}`}>{ap.balance_status === "debtor" ? "بدهکار" : ap.balance_status === "creditor" ? "بستانکار" : ap.balance_status === "settled" ? "تسویه" : "فاقد حساب"}</span>
      </div>
      <div className="cf-kpis">
        <article className="cf-accent-red"><small>مانده بدهی فعلی</small><b>{money(cp.open_account_receivable_rial || 0)}</b><span>تومان • بدون چک</span></article>
        <article><small>چک باز در دست شرکت</small><b>{money(cp.open_cheque_amount_rial || 0)}</b><span>تومان</span></article>
        <article><small>کل مطالبات درگیر وصول</small><b>{money(cp.total_collection_exposure_rial || 0)}</b><span>مانده + چک باز</span></article>
        <article><small>پوشش با چک</small><b>{fa(cp.cheque_coverage_percent || 0)}٪</b><span>{fa(cp.uncovered_percent || 0)}٪ بدون چک</span></article>
        {Number(cp.customer_credit_rial || 0) > 0 && <article><small>بستانکاری مشتری</small><b>{money(cp.customer_credit_rial)}</b><span>تومان</span></article>}
      </div>
      {breakdown.length > 0 && <div className="cf-table"><table>
        <thead><tr><th>حساب</th><th>بدهکار</th><th>بستانکار</th><th>مانده</th></tr></thead>
        <tbody>{breakdown.map((a: any, i: number) => <tr key={`${a.account_id}-${i}`}><td>{a.account_name || a.sl_title || a.account_id}</td><td>{fullToman(a.debit_balance_rial || 0)}</td><td>{fullToman(a.credit_balance_rial || 0)}</td><td><b>{fullToman(a.balance_rial || 0)}</b></td></tr>)}</tbody>
      </table></div>}
      {monthly.length > 0 && <details className="cf-details"><summary>خلاصه ماهانه حساب ({fa(monthly.length)} ماه)</summary><div className="cf-table"><table>
        <thead><tr><th>ماه</th><th>بدهکار</th><th>بستانکار</th><th>مانده پایان ماه</th><th>تعداد تراکنش</th></tr></thead>
        <tbody>{monthly.map((m: any) => <tr key={m.jalali_month}><td>{m.jalali_month}</td><td>{fullToman(m.debit_rial || 0)}</td><td>{fullToman(m.credit_rial || 0)}</td><td>{fullToman(m.closing_balance_rial || 0)}</td><td>{fa(m.transaction_count || 0)}</td></tr>)}</tbody>
      </table></div></details>}
      {ledger.length > 0 && <details className="cf-details"><summary>ریز گردش حساب ({fa(ledger.length)} ردیف)</summary><div className="cf-table"><table>
        <thead><tr><th>تاریخ</th><th>شعبه</th><th>معین</th><th>بدهکار</th><th>بستانکار</th><th>مانده تجمعی</th><th>شرح</th></tr></thead>
        <tbody>{ledger.map((e: any, i: number) => <tr key={e.voucher_ref || i}><td>{e.date_jalali || e.date || "—"}</td><td>{e.branch_name || "—"}</td><td>{e.sl_name || "—"}</td><td>{fullToman(e.debit_rial || 0)}</td><td>{fullToman(e.credit_rial || 0)}</td><td>{fullToman(e.running_balance_rial || 0)}</td><td className="cf-wrap">{e.description || "—"}</td></tr>)}</tbody>
      </table></div></details>}
    </section>
  );
}

function CustomerProfile({
  c,
  close,
  refresh,
  embedded = false,
}: {
  c: Customer;
  close: () => void;
  refresh: () => void;
  embedded?: boolean;
}) {
  const [detail, setDetail] = useState<Customer>(c);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [predictionWarning, setPredictionWarning] = useState("");
  useEffect(() => {
    let active = true;
    setLoadingDetail(true);
    const jobs: Promise<any>[] = [];
    const kinds: string[] = [];
    if (c.data_source === "rahkaran" && c.counterpart_ref) {
      jobs.push(request(`/customer-intelligence/${c.counterpart_ref}`)); kinds.push("detail");
      jobs.push(request(`/predictions/customers/${c.counterpart_ref}`)); kinds.push("prediction");
    }
    const customerName = cname(c);
    if (c.data_source === "karamad" && customerName) {
      const params = new URLSearchParams({ customer_name: customerName });
      const selectedBranch = c.karamad_activity?.selected_branch;
      if (selectedBranch) params.set("branch", selectedBranch);
      jobs.push(request(`/karamad-manual/customer-detail?${params.toString()}`)); kinds.push("karamad");
    }
    Promise.allSettled(jobs)
      .then((results) => {
        if (!active) return;
        let detailResult: any = undefined;
        let predictionResult: any = undefined;
        let karamadDetail: any = undefined;
        results.forEach((result, index) => {
          const kind = kinds[index];
          if (result.status === "fulfilled") {
            if (kind === "detail") detailResult = result.value?.customer;
            if (kind === "prediction") predictionResult = result.value?.customers?.[0] || result.value?.customer;
            if (kind === "karamad") karamadDetail = result.value;
          } else if (kind === "detail") {
            setDetailError(result.reason instanceof Error ? result.reason.message : "جزئیات چک‌های راهکاران دریافت نشد");
          } else if (kind === "prediction") {
            setPredictionWarning("تحلیل خوش‌قولی راهکاران دریافت نشد.");
          }
        });
        setDetail((previous) => ({
          ...previous,
          ...detailResult,
          ...predictionResult,
          open_cheques: detailResult?.open_cheques || previous.open_cheques,
          karamad_activity: { ...(previous.karamad_activity || {}), detail: karamadDetail },
        }));
      })
      .finally(() => { if (active) setLoadingDetail(false); });
    return () => { active = false; };
  }, [c.counterpart_ref, c.customer_name, c.counterpart_name, c.data_source, c.karamad_activity?.selected_branch]);
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
  const kd: any = detail.karamad_activity?.detail || {};
  const ks: any = kd.summary || {};
  const total = (detail.historical_total_cheque_amount || 0) + (ks.received_cheque_amount_rial || 0),
    collected = detail.collected_cheque_amount || 0,
    open = (detail.open_exposure || 0) + (ks.received_cheque_future_amount_rial || 0) + (ks.received_cheque_overdue_amount_rial || 0) + (ks.received_cheque_today_amount_rial || 0),
    returned = (detail.returned_cheque_amount || 0) + (ks.received_cheque_returned_amount_rial || 0),
    returnedCount = Number(detail.returned_cheque_count || 0) + Number(ks.received_cheque_returned_count || 0),
    futureAmount = Number(detail.future_open_cheque_amount || 0) + Number(ks.received_cheque_future_amount_rial || 0),
    futureCount = Number(detail.future_open_cheque_count || 0) + Number(ks.received_cheque_future_count || 0),
    percent = total ? Math.min(100, (collected / total) * 100) : 0;
  const content = (
      <article className={`customer-profile-expanded ${embedded ? "customer-profile-page" : ""}`} onClick={(e) => e.stopPropagation()}>
        {embedded ? <button className="cheque-back customer-profile-back" onClick={close}>→ بازگشت به فهرست مشتریان</button> : <button className="profile-close" onClick={close}>×</button>}
        <div className="profile-title">
          <div>
            {detail.counterpart_ref ? <Risk x={risk(detail)} /> : <span className="fd-badge safe">دارای سابقه</span>}
            <h2>{cname(detail)}</h2>
            <p>خرید، ویزیتور، ۵ فاکتور آخر، مطالبات، چک‌ها و احتمال برگشت — از منبع انتخاب‌شده</p>
          </div>
          <span className="profile-source">{detail.data_source === "karamad" ? "کارآمد" : "راهکاران"}</span>
        </div>
        {detailError && <div className="profile-warning">{detailError}</div>}
        {predictionWarning && (
          <div className="profile-prediction-warning">{predictionWarning}</div>
        )}
        <CustomerFileOverview c={detail} />
        <CustomerReceivables detail={detail} />
        <div className="cf-title cf-cheques-title">
          <div><h3>چک‌های مشتری</h3><p>کل سوابق چک، وصول، برگشتی و احتمال برگشت چک‌های باز</p></div>
          {loadingDetail && <small>در حال دریافت ریز چک‌ها...</small>}
        </div>
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
            n={`${fa(returnedCount)} فقره • تومان`}
            c="red"
          />
          <K
            t="چک‌های آینده"
            v={money(futureAmount)}
            n={`${fa(futureCount)} فقره • تومان`}
            c="blue"
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
        <UnifiedCustomerActivityTables c={detail} />
        {detail.counterpart_ref ? <CustomerReliability c={detail} /> : null}
        {detail.data_source === "rahkaran" && detail.b2b_remittances ? <section className="customer-b2b-detail">
          <Heading h="حواله‌ها و واریزهای B2B این مشتری" p="این داده‌ها علاوه بر نمایش، در ارزیابی رفتار مالی مشتری نیز لحاظ شده‌اند." />
          <div className="modal-metrics b2b-kpis">
            <K t="کل حواله B2B" v={fa(detail.b2b_remittances.count || 0)} n={fullToman(detail.b2b_remittances.amount_rial || 0) + " تومان"} c="blue" />
            <K t="واریز مستقیم" v={fa(detail.b2b_remittances.direct_count || 0)} n={fullToman(detail.b2b_remittances.direct_amount_rial || 0) + " تومان"} c="teal" />
            <K t="تسویه برگشتی" v={fa(detail.b2b_remittances.returned_cheque_settlement_count || 0)} n={`${fa(detail.b2b_remittances.returned_settlement_ratio_percent || 0)}٪ از مبلغ`} c="amber" />
            <K t="میانگین حواله" v={fullToman(detail.b2b_remittances.average_amount_rial || 0)} n="تومان" c="blue" />
          </div>
          <div className="b2b-table-wrap"><table><thead><tr><th>تاریخ</th><th>رسید</th><th>حواله</th><th>مبلغ (تومان)</th><th>بانک/شعبه</th><th>نوع</th><th>شرح</th></tr></thead><tbody>
          {(detail.b2b_remittances.rows || []).map((x:any)=><tr key={x.receipt_deposit_id}><td>{x.deposit_date_jalali || String(x.deposit_date||"").slice(0,10)}</td><td>{x.receipt_number || "—"}</td><td>{x.deposit_number || "—"}</td><td>{fullToman(Number(x.amount_rial||0))}</td><td>{x.bank_branch_name || `حساب ${x.bank_account_ref || "—"}`}</td><td><span className="b2b-category">{x.category}</span></td><td className="b2b-desc">{x.description || "—"}</td></tr>)}
          </tbody></table></div>
        </section> : null}
        {detail.counterpart_ref ? <CustomerSqlAudit c={detail as CustomerAudit} /> : null}
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
          این پرونده فقط از منبع انتخاب‌شده نمایش داده می‌شود تا تعداد، مبلغ و ریز چک‌های برگشتی و آینده با منبع دیگر مخلوط نشود.
        </p>
        {detail.counterpart_ref ? <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button> : null}
      </article>
  );
  return embedded ? content : <div className="fd-backdrop" onClick={close}>{content}</div>;
}
