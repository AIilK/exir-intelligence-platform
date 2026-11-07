// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (management).
import ExecutiveOverview, { type ChequeBucket } from "../management/executive-overview";
import { Status } from "./widgets";
import { JALALI_MONTH_NAMES, chequeDueJalali, currentJalali, daysToDue, fa, fullToman, openInsight, textOf } from "./shared";
import type { Alert, Analysis, Cheque, Customer, InsightRecord, TreasuryCheque, View } from "./types";

export function Management({
  manager,
  customers,
  cheques,
  alerts,
  received,
  issued,
  openChequePage,
  openAgent,
  openView,
  go,
}: {
  manager?: Analysis;
  customers: Customer[];
  cheques: Cheque[];
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
export type ChartRow = {
  label: string;
  value: number;
  tone: string;
  format?: "money" | "number";
  records?: InsightRecord[];
};
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
