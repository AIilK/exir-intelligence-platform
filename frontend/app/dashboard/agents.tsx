// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (agents).
import { VerticalBars } from "./management";
import type { ChartRow } from "./management";
import { fa, fieldFa, fullToman, menu, openInsight, risk, textOf } from "./shared";
import type { AgentResult, Analysis, InsightPayload, View } from "./types";

export function LegacyAgentPanel({ agent }: { agent?: AgentResult }) {
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
export function LegacyAgentCard({ agent }: { agent: AgentResult }) {
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
export function K({
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
export function Heading({ h, p }: { h: string; p: string }) {
  return (
    <div className="fd-heading">
      <h2>{h}</h2>
      <p>{p}</p>
    </div>
  );
}
export function Risk({ x }: { x: string }) {
  return (
    <span className={`fd-badge ${x}`}>
      {x === "critical" ? "بحرانی" : x === "danger" ? "نیازمند توجه" : "مناسب"}
    </span>
  );
}
export function Status({ x }: { x: string }) {
  return (
    <span className={`management-status ${x}`}>
      {x === "critical" ? "بحرانی" : x === "healthy" ? "مناسب" : "نیازمند توجه"}
    </span>
  );
}
export function label(v: View) {
  return v === "receivedCheques"
    ? "چک‌های دریافتی"
    : v === "issuedCheques"
      ? "چک‌های پرداختی / صادرشده"
      : menu.find((x) => x[0] === v)?.[2] || v;
}
export function description(v: View) {
  return (
    {
      overview: "ترکیب خلاصه مدیریتی مالی و فروش، با تصمیم‌های امروز و رتبه هیبریدها",
      management: "چک‌ها، پرداخت تجاری، نقدینگی و توزیع بار در یک نگاه",
      sales: "فروش خالص ماه و سال، هیبریدها، توزیع و وصول و شبکه فروش کارآمد در یک نگاه",
      users: "تعریف کاربر، نام کاربری و رمز، و ماژول‌هایی که هر شخص می‌بیند",
      customers: "خرید، ویزیتور، مطالبات، چک‌ها و احتمال برگشت هر مشتری",
      cheques: "انتخاب جریان دریافتی یا پرداختی و ورود از خلاصه به جزئیات",
      payables: "حساب‌های پرداختنی تجاری (۵۱۱۰۰۲) و غیرتجاری (۵۱۲۰۰۱) راهکاران؛ با کلیک روی هر طرف حساب ریز گردشش باز می‌شود",
      pnl: "سود و زیان سه کانال (هیبرید، B2B، صادرات): لایو از SQL راهکاران و کارآمد، با مقایسه فایل‌های اکسل مالی",
      purchaseDocs: "زنده از راهکاران: اسناد خرید ثبت‌حسابداری‌نشده (عملیات گروهی اسناد) و مرور تدارکات با تطبیق رسید موقت و دائم",
      inventoryPricing: "اسناد انبار راهکاران که کالایشان ثبت شده ولی قیمت‌گذاری نشده‌اند — به تفکیک انبار کارخانه",
      cashBank:
        "ریز دریافت و پرداخت نقدی و بانکی، حواله‌ها و انتقال‌های داخلی همراه Agent مستقل",
      receivedCheques: "مطالبات، وصول، ریسک و سررسید چک‌های دریافتی",
      issuedCheques: "تعهدات و سررسید چک‌های پرداختی و صادرشده",
      cashflow: "Forecast روزانه همراه Cash Flow Agent",
      monthlyExcel:
        "آپلود Excel روزانه، تشخیص خودکار ماه شمسی و تحلیل از ابتدای همان ماه",
      collections: "مسئول، مهلت، تماس، قول پرداخت و نتیجه پیگیری",
      distribution: "فاکتورهای توزیع‌نشده، سرعت خروج بار و عملکرد موزعان — کارآمد",
      representatives: "کیفیت پرتفوی و وصول به تفکیک نماینده",
      simulator: "بررسی اثر نرخ وصول و جابه‌جایی پرداخت‌ها",
      alerts: "الارم‌های فعال ماژول‌های شما با سطح اهمیت و اقدام پیشنهادی",
      history: "روند تغییر گزارش‌های مدیریتی در طول زمان",
      performance: "مقایسه پیش‌بینی‌ها با نتایج واقعی",
      settings: "مدیریت آستانه‌ها و زمان اجرای اتوماسیون",
      agents: "وضعیت و خروجی همه Agentهای تخصصی",
    } as Record<View, string>
  )[v];
}

export function metricRows(value: any, limit = 5): ChartRow[] {
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
export function HorizontalMetrics({ rows }: { rows: ChartRow[] }) {
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
export function CompactDonut({ good, risk }: { good: number; risk: number }) {
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
export function AgentVisualSummary({ agent }: { agent?: AgentResult }) {
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
export function ManagerPanel({ a }: { a?: Analysis }) {
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
export function AgentPanel({ agent }: { agent?: AgentResult }) {
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
export function AgentCard({ agent }: { agent: AgentResult }) {
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
