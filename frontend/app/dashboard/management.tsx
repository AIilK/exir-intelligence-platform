// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (management).
import ExecutiveOverview, { type ChequeBucket } from "../management/executive-overview";
import { Heading, Status, label } from "./agents";
import { JALALI_MONTH_NAMES, chequeDueJalali, cname, currentJalali, daysToDue, fa, fullToman, money, openInsight, risk, textOf } from "./shared";
import type { AgentResult, Alert, Analysis, CashDay, Cheque, Customer, InsightRecord, TreasuryCheque, View } from "./types";

export function FutureCashflowExecutive({
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

export function Management({
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
  openView,
  go,
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
  openView?: (view: View) => void;
  go?: (view: string) => void;
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
  // نمای کلان: همان اعداد کارت‌های سررسید، به‌اضافه تفکیک منبع و سررسید ماهانه برای نمودار.
  const bySource = (data: { amount: number; count: number; sources: any }, items: TreasuryCheque[]) => {
    const part = (sys: string) => Number(data.sources?.[sys]?.amount_rial ?? items.filter((x) => x.source_system === sys).reduce((s, x) => s + (x.amount || 0), 0));
    return { amount: data.amount, count: data.count, rahkaran: part("rahkaran"), karamad: part("karamad") };
  };
  const chequeBuckets: ChequeBucket[] = (() => {
    const sum = (items: TreasuryCheque[]) => items.reduce((s, x) => s + (x.amount || 0), 0);
    const now = currentJalali();
    const months = Array.from({ length: 6 }, (_, i) => { const idx = now.year * 12 + now.month - 1 + i; return { year: Math.floor(idx / 12), month: (idx % 12) + 1 }; });
    const inMonth = (items: TreasuryCheque[], m: { year: number; month: number }) => items.filter((x) => { const j = chequeDueJalali(x); return j && j.year === m.year && j.month === m.month; });
    return [
      { label: "سررسیدگذشته", received: receivedOverdue.amount, issued: issuedOverdue.amount, receivedCount: receivedOverdue.count, issuedCount: issuedOverdue.count, overdue: true },
      ...months.map((m) => {
        const r = inMonth(fallbackReceivedFuture, m), s2 = inMonth(fallbackIssuedFuture, m);
        return { label: `${JALALI_MONTH_NAMES[m.month - 1]}${m.year !== now.year ? ` ${String(m.year).slice(2).replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)])}` : ""}`,
          received: sum(r), issued: sum(s2), receivedCount: r.length, issuedCount: s2.length };
      }),
    ];
  })();
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
      <ExecutiveOverview
        cheques={{
          receivedFuture: bySource(receivedFuture, fallbackReceivedFuture), receivedOverdue: bySource(receivedOverdue, fallbackReceivedOverdue),
          issuedFuture: bySource(issuedFuture, fallbackIssuedFuture), issuedOverdue: bySource(issuedOverdue, fallbackIssuedOverdue),
          buckets: chequeBuckets,
          ready: Object.keys(portfolio).length > 0,
        }}
        open={(v) => v === "receivedCheques" || v === "issuedCheques" ? openChequePage(v === "receivedCheques" ? "received" : "issued") : openView?.(v)}
        go={go}
      />
    </>
  );
}
export function ExecutiveCharts({
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
export type ChartRow = {
  label: string;
  value: number;
  tone: string;
  format?: "money" | "number";
  records?: InsightRecord[];
};
export function HorizontalBars({
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
export function VerticalBars({ rows }: { rows: ChartRow[] }) {
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
export function DonutChart({ rows }: { rows: ChartRow[] }) {
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
export function CashBars({ days }: { days: CashDay[] }) {
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
export function LegacyManagerPanel({ a }: { a?: Analysis }) {
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
