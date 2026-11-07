// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (shared).
// توابع و اجزای مشترک داشبورد مالی: آدرس API، قالب‌بندی مبلغ و تاریخ، کمک‌کننده‌های چک.
import { useEffect, useState } from "react";
import { label } from "./agents";
import { ALERT_TERM_AMOUNT_RIAL, ALERT_TERM_DAYS, chequeTermDays } from "./collections";
import type { Cheque, Customer, InsightPayload, InsightRecord, TreasuryCheque, View } from "./types";

export const openInsight = (payload: InsightPayload) => {
  if (typeof window !== "undefined")
    window.dispatchEvent(new CustomEvent("exir:insight", { detail: payload }));
};

export function InsightCenter() {
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

export const API = () => `/api/v1/finance`;
export const TREASURY_API = () => `/api/v1/treasury`;
export const fa = (v: number = 0) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 }).format(v);
// تمام مبالغ Backend بر حسب ریال هستند. تنها نقطه تبدیل رابط کاربری همین
// تابع است تا هیچ کارت یا نموداری ریال و تومان را با هم مخلوط نکند.
export const money = (rial: number = 0) => {
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
export const fieldFa: Record<string, string> = {
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
export const textOf = (value: unknown, key = ""): string => {
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
export const cname = (c: Customer) =>
  c.counterpart_name || c.customer_name || "مشتری نامشخص";
export const policy = (c: Customer) =>
  c.over_policy_count ?? c.outside_policy_count ?? 0;
export const risk = (c: Customer) => {
  const score = c.risk_score ?? c.late_payment_risk?.value ?? 0;
  const severeEvidence =
    policy(c) >= 10 || (c.current_overdue_open_ratio_percent || 0) >= 60;
  return score >= 85 && severeEvidence
    ? "critical"
    : score >= 40 || policy(c) >= 3
      ? "danger"
      : "safe";
};
export const daysToDue = (c: Cheque) => {
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
export const JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
export const persianCalendarParts = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", { year: "numeric", month: "numeric", timeZone: "UTC" });
// سال و ماه شمسی سررسید؛ اول از due_date_jalali، وگرنه تبدیل due_date میلادی با تقویم فارسی مرورگر.
export const chequeDueJalali = (c: Cheque): { year: number; month: number } | undefined => {
  const text = String(c.due_date_jalali || "").replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)));
  const m = text.match(/^(1[34]\d\d)[/-](\d{1,2})/);
  if (m) return { year: Number(m[1]), month: Number(m[2]) };
  if (!c.due_date) return undefined;
  const date = new Date(`${String(c.due_date).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return undefined;
  const parts = persianCalendarParts.formatToParts(date);
  const year = Number(parts.find((p) => p.type === "year")?.value), month = Number(parts.find((p) => p.type === "month")?.value);
  return year && month ? { year, month } : undefined;
};
export const remainingLabel = (c: Cheque) => {
  const d = daysToDue(c);
  return d === undefined
    ? "زمان باقی‌مانده نامشخص"
    : d < 0
      ? `${fa(Math.abs(d))} روز از سررسید گذشته`
      : d === 0
        ? "سررسید امروز"
        : `${fa(d)} روز تا سررسید`;
};

export type ReceivedChequeHolding = "all" | "collector" | "bank" | "pending" | "assigned" | "cashbox" | "returned_cashbox_plain" | "returned_cashbox_yeh" | "returned_customer";
export type ReceivedChequeHoldingBucket = Exclude<ReceivedChequeHolding, "all"> | "other";
export const receivedChequeHoldingBucket = (c: TreasuryCheque): ReceivedChequeHoldingBucket => {
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
export const receivedChequeHoldingLabel = (c: TreasuryCheque) => {
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
export const chequeInsightRows = (rows: TreasuryCheque[]): InsightRecord[] =>
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
// Cheque term (receipt → due) over 90 days and amount over 100M toman — the company's review rule.
export const isLongTermLargeCheque = (x: TreasuryCheque) =>
  (chequeTermDays(x) ?? 0) > ALERT_TERM_DAYS && (x.amount || 0) > ALERT_TERM_AMOUNT_RIAL;
// Every long-term large cheque (no 50-row cap), largest first, with full amounts and the term.
export const longTermChequeInsight = (rows: TreasuryCheque[], incoming: boolean): InsightPayload => {
  const total = rows.reduce((s, x) => s + (x.amount || 0), 0);
  return {
    title: `چک‌های ${incoming ? "دریافتی" : "پرداختی"} با مدت بیش از ۹۰ روز و مبلغ بالای ۱۰۰ میلیون`,
    subtitle: "مدت چک = فاصله تاریخ دریافت/ثبت تا سررسید. همه موارد، از بزرگ‌ترین مبلغ.",
    tone: "amber",
    stats: [{ label: "تعداد چک", value: fa(rows.length) }, { label: "مبلغ کل", value: `${fullToman(total)} تومان` }],
    records: [...rows].sort((a, b) => (b.amount || 0) - (a.amount || 0)).map((x) => ({
      name: x.counterpart_name || "طرف حساب نامشخص",
      number: String(x.serial_number || x.document_number || x.cheque_id || "—"),
      amount: `${fullToman(x.amount || 0)} تومان`,
      due: x.due_date_jalali || String(x.due_date || "—").slice(0, 10),
      timing: `${remainingLabel(x)} • مدت ${fa(chequeTermDays(x) || 0)} روز`,
    })),
  };
};
export const fullToman = (rial: number = 0) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 }).format(rial / 10);

export function RahkaranChequeTotals({ rows, kind }: { rows: TreasuryCheque[]; kind: "received" | "issued" }) {
  const selected = rows.filter((x) => x.source_system === "rahkaran");
  const groups = [
    { title: "کل آینده", items: selected.filter((x) => (daysToDue(x) ?? -1) > 0) },
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

export function IssuedChequeTotals({ rows }: { rows: TreasuryCheque[] }) {
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

export async function request(path: string, options?: RequestInit) {
  const r = await fetch(`${API()}${path}`, options);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
export async function treasuryRequest(path: string) {
  const r = await fetch(`${TREASURY_API()}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
export async function treasuryMutation(path: string, options: RequestInit) {
  const r = await fetch(`${TREASURY_API()}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

export const menu: [View, string, string][] = [
  ["overview", "★", "نمای مدیر"],
  ["management", "✦", "خلاصه مدیریتی مالی"],
  ["sales", "◈", "خلاصه مدیریتی فروش"],
  ["customers", "◎", "پرونده مشتری"],
  ["cheques", "◷", "چک و سررسید"],
  ["cashBank", "⇄", "نقد و حواله"],
  ["companyPayments", "↗", "حواله‌های پرداختی شرکت"],
  ["payables", "◧", "پرداخت تجاری"],
  ["liquidity", "₪", "نقدینگی"],
  ["inventoryPricing", "▦", "قیمت‌گذاری انبار"],
  ["purchaseDocs", "▤", "اسناد خرید"],
  ["pnl", "∑", "سود و زیان (P&L)"],
  ["collections", "✓", "مرکز عملیات وصول"],
  ["distribution", "⛟", "توزیع بار"],
  ["performance", "◉", "دقت پیش‌بینی"],
  ["settings", "⚙", "قوانین و اتوماسیون"],
  ["alerts", "🔔", "مرکز الارم‌ها"],
  ["users", "👥", "مدیریت کاربران"],
];


// «توزیع و وصول فاکتورهای ماه» — the finance team's monthly report, rebuilt from Karamad SQL.
export const JALALI_MONTH_NAMES = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
export const currentJalali = () => {
  const p = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric" }).formatToParts(new Date());
  return { year: Number(p.find((x) => x.type === "year")?.value), month: Number(p.find((x) => x.type === "month")?.value) };
};
export type YearMonth = { year: number; month: number };
// ۱۲ ماه اخیر (جدیدترین اول) برای انتخاب ماه در کل صفحه توزیع بار.
export const recentJalaliMonths = (count = 12): YearMonth[] => {
  const now = currentJalali();
  return Array.from({ length: count }, (_, i) => {
    const index = now.year * 12 + (now.month - 1) - i;
    return { year: Math.floor(index / 12), month: (index % 12) + 1 };
  });
};
export const monthLabel = (m: YearMonth) => `${JALALI_MONTH_NAMES[m.month - 1]} ${fa(m.year).replace(/٬/g, "")}`;

export const boldToman = (rial: any) => <b>{fullToman(Number(rial || 0))}</b>;
export const sumOf = (rows: any[], k: string) => rows.reduce((s, x) => s + Number(x[k] || 0), 0);

// ۱. توزیع و وصول فاکتورهای ماه (کل ← جزء: جدول هیبریدها، با کلیک: مشتریان و توزیع‌نشده‌های همان هیبرید).
