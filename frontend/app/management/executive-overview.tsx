"use client";
// خلاصه مدیریتی — نمای کلان با متن کوتاه: هر کارت = عنوان چندکلمه‌ای + عدد + یک خط راهنما + «مشاهده ←».
// چک‌ها: دریافتی (آینده / برگشتی = راهکاران «واخواست» + کارآمد «برگشتی نزد مشتری/صندوق» / تعیین تکلیف نشده = هر سررسیدگذشته دیگر) و پرداختی (آینده / گذشته تا ۲۰ روز / وضعیت به‌روزنشده).
// لحن: واژه «بحرانی» استفاده نمی‌شود؛ اولویت‌ها با «اولویت اول/دوم» و «نیازمند پیگیری» بیان می‌شوند.
import { useCallback, useEffect, useMemo, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import { AgentInsight } from "../page-agents";
import ChequeStatusDrawer, { type ChequeStatusKind } from "./cheque-status-drawer";
import { PeekContext, PeekPanel, usePeek, type Peek } from "./peek-panel";
import { ChartCard, DivergingRows, FlowCompare, MonthBars, NetWeeks, PALETTE, StackBar } from "./mini-charts";
import "./executive-overview.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const fullToman = (rial: number | null | undefined) => nf.format(Math.round(Number(rial || 0) / 10));
/** ریال ← «۱۲٫۳ میلیارد» تومان */
const shortToman = (rial: number | null | undefined) => {
  const t = Number(rial || 0) / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const faDigits = (v: string | null | undefined) => String(v || "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
async function getJson(url: string) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
const LIQ = () => `http://${apiHost()}:8000/api/v1/liquidity`;

// رنگ‌ها: دسته‌ای ثابت (اعتبارسنجی‌شده روی سطح تیره #0f1d2a): دریافتی/قطعی، پرداختی/اتکا، بدبینانه.
const C_RECEIVED = "#0d9488", C_ISSUED = "#d97706", C_THIRD = "#8b5cf6";

export type ChequeBucket = { label: string; received: number; issued: number; receivedCount: number; issuedCount: number; overdue?: boolean };
export type ChequeTotals = { amount: number; count: number; rahkaran: number; karamad: number };
export type ChequeOverview = {
  receivedFuture: ChequeTotals; receivedOverdue: ChequeTotals; issuedFuture: ChequeTotals; issuedOverdue: ChequeTotals; buckets: ChequeBucket[];
  /** false تا وقتی سبد رسمی چک (همان عدد صفحه چک‌ها) نرسیده؛ تا آن موقع «…» نشان داده می‌شود نه یک عدد موقت. */
  ready: boolean;
};
type View = "receivedCheques" | "issuedCheques" | "payables" | "liquidity" | "distribution";
type Tone = "neutral" | "good" | "watch" | "follow";

type PeekSpec = Omit<Peek, "onGo" | "title" | "tone" | "unit"> & { title?: string };
const PAGE_NAMES: Record<View, string> = {
  receivedCheques: "چک‌های دریافتی", issuedCheques: "چک‌های پرداختی", payables: "پرداخت تجاری", liquidity: "نقدینگی", distribution: "توزیع بار",
};
/** ردیف‌های فهرست کوتاه پنل با نوار سهم نسبت به بزرگ‌ترین مورد. */
function peekRows<T>(items: T[], label: (x: T) => string, amount: (x: T) => number, sub?: (x: T) => string, n = 5) {
  const top = items.slice(0, n);
  const max = Math.max(1, ...top.map(amount));
  return top.map((x) => ({ label: label(x) || "—", sub: sub?.(x), value: shortToman(amount(x)), share: (100 * amount(x)) / max }));
}

/** کارت ساده: عنوان کوتاه، عدد، یک خط راهنما. با peek اول خلاصه کوتاه باز می‌شود و دکمه آن به صفحه کامل می‌رود. */
function Stat({ label, value, unit = "تومان", hint, go, goLabel = "مشاهده", tone = "neutral", dot, peek }: {
  label: string; value: ReactNode; unit?: string; hint?: ReactNode; go?: () => void; goLabel?: string; tone?: Tone; dot?: string; peek?: PeekSpec | null;
}) {
  const showPeek = usePeek();
  const body = <>
    <small>{dot && <i style={{ background: dot }} />}{label}</small>
    <b>{value}</b>
    {unit && <span>{unit}</span>}
    {hint && <em>{hint}</em>}
    {go && <u>{peek ? "جزئیات" : goLabel} ←</u>}
  </>;
  const onClick = peek ? () => showPeek({ ...peek, title: peek.title || label, unit: unit || undefined, tone, onGo: go }) : go;
  return onClick ? <button type="button" className={`xo-stat ${tone}`} onClick={onClick}>{body}</button> : <div className={`xo-stat ${tone} static`}>{body}</div>;
}

/** فقط نزدیک‌ترین ظرف اسکرول‌شونده را جابه‌جا می‌کند (scrollIntoView کل صفحه و منو را هم می‌کشد). */
function jumpTo(id: string) {
  const target = document.getElementById(id);
  if (!target) return;
  let box: HTMLElement | null = target.parentElement;
  while (box && !(box.scrollHeight > box.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  const scroller = box || (document.scrollingElement as HTMLElement);
  const offset = target.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 12;
  scroller.scrollTo({ top: scroller.scrollTop + offset, behavior: "smooth" });
}

export default function ExecutiveOverview({ cheques, open }: { cheques: ChequeOverview; open: (view: View) => void }) {
  const [peek, setPeek] = useState<Peek | null>(null);
  const closePeek = useCallback(() => setPeek(null), []);
  return <PeekContext.Provider value={setPeek}><section className="xo">
    <header className="xo-head">
      <h2>نمای کلان مالی</h2>
      <p>برای جزئیات، روی هر کارت بزنید.</p>
      {/* نه <nav>: استایل سراسری منوی کناری روی nav اعمال می‌شود. */}
      <div className="xo-jump" role="navigation" aria-label="پرش به بخش">
        {([["xo-cheques", "چک‌ها"], ["xo-payables", "پرداخت تجاری"], ["xo-liquidity", "نقدینگی"], ["xo-distribution", "توزیع بار"]] as [string, string][]).map(([id, label]) =>
          // محتوای اپ داخل ظرف اسکرول خودش است؛ لینک «#» صفحه را جابه‌جا نمی‌کند، پس مستقیم اسکرول می‌کنیم.
          <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); jumpTo(id); }}>{label}</a>)}
      </div>
    </header>
    <ChequeBlock data={cheques} open={open} />
    <PayablesBlock open={open} />
    <LiquidityBlock open={open} />
    <DistributionBlock open={open} />
    <PeekPanel peek={peek} onClose={closePeek} />
  </section></PeekContext.Provider>;
}

// ------------------------------------------------------------------ cheques
function ChequeBlock({ data, open }: { data: ChequeOverview; open: (view: View) => void }) {
  const [rec, setRec] = useState<any>(null);
  const [iss, setIss] = useState<any>(null);
  const [drawer, setDrawer] = useState<ChequeStatusKind | null>(null);
  const [retRows, setRetRows] = useState<any[] | null>(null);
  const [undDetail, setUndDetail] = useState<any>(null);
  useEffect(() => {
    getJson(`${LIQ()}/received-cheques/status/returned`).then((j) => setRetRows(j.cheques || [])).catch(() => setRetRows([]));
    getJson(`${LIQ()}/received-cheques/status/undetermined`).then(setUndDetail).catch(() => setUndDetail({}));
    getJson(`${LIQ()}/received-cheques?horizon_days=30`).then((j) => setRec(j.data)).catch(() => setRec({}));
    getJson(`${LIQ()}/issued-cheques?horizon_days=30`).then((j) => setIss(j.data)).catch(() => setIss({}));
  }, []);
  const returned = rec?.returned_open, overdue = rec?.overdue;
  const bySys = (sys: string) => (returned?.by_system || []).find((x: any) => x.system === sys);
  const recent = (overdue?.age_buckets || [])[0];
  const issuedRecent = iss?.overdue, issuedReview = iss?.needs_status_review;
  const wait = <span className="xo-wait">…</span>;
  const undeterminedAmount = Number(overdue?.definite_rial || 0) + Number(overdue?.other_state_rial || 0);
  // برگشتی‌های ۱۴۰۵ به تفکیک ماه سررسید (راهکاران / کارآمد)
  const returnedMonths = (() => {
    if (!retRows) return [];
    const map = new Map<string, { values: number[]; counts: number[] }>();
    retRows.forEach((r) => {
      const key = String(r.due_date_jalali || "").slice(0, 7);
      if (!key) return;
      const m = map.get(key) || { values: [0, 0], counts: [0, 0] };
      const k = r.system === "rahkaran" ? 0 : 1;
      m.values[k] += r.amount_rial; m.counts[k] += 1;
      map.set(key, m);
    });
    const names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, m]) => ({ label: names[Number(key.slice(5, 7)) - 1] || key, values: m.values, counts: m.counts }));
  })();
  const undStatus: any[] = undDetail?.by_status || [];
  const days = (v: any) => `${fa(Number(v || 0))} روز`;
  const recFuturePeek: PeekSpec | null = data.ready ? {
    value: shortToman(data.receivedFuture.amount), page: PAGE_NAMES.receivedCheques,
    facts: [
      { label: "تعداد چک", value: fa(data.receivedFuture.count) },
      { label: "۷ روز آینده", value: rec?.kpis ? `${shortToman(rec.kpis.next_7_days?.definite_rial)} (${fa(rec.kpis.next_7_days?.count)} چک)` : "…" },
      { label: "راهکاران (B2B)", value: shortToman(data.receivedFuture.rahkaran) },
      { label: "کارآمد (هیبرید)", value: shortToman(data.receivedFuture.karamad) },
    ],
    list: { title: "بزرگ‌ترین مشتریان ۳۰ روز آینده", rows: peekRows([...(rec?.customers || [])].sort((a: any, b: any) => b.definite_rial - a.definite_rial),
      (c: any) => c.customer_name, (c: any) => Number(c.definite_rial || 0), (c: any) => `${fa(c.count)} چک · اتکا ${nf1.format(c.reliance_percent || 0)}٪`) },
  } : null;
  const issFuturePeek: PeekSpec | null = data.ready ? {
    value: shortToman(data.issuedFuture.amount), page: PAGE_NAMES.issuedCheques,
    facts: [
      { label: "تعداد چک", value: fa(data.issuedFuture.count) },
      { label: "۳۰ روز آینده", value: iss?.kpis ? `${shortToman(iss.kpis.horizon?.amount_rial)} (${fa(iss.kpis.horizon?.count)} چک)` : "…" },
      { label: "۷ روز آینده", value: iss?.kpis ? shortToman(iss.kpis.next_7_days?.amount_rial) : "…" },
      { label: "سنگین‌ترین روز", value: iss?.kpis?.peak_day?.date_jalali ? `${faDigits(iss.kpis.peak_day.date_jalali)} · ${shortToman(iss.kpis.peak_day.amount_rial)}` : "—" },
    ],
    list: { title: "بزرگ‌ترین دریافت‌کنندگان", rows: peekRows(iss?.top_payees || [], (p: any) => p.payee_name, (p: any) => Number(p.amount_rial || 0), (p: any) => `${fa(p.count)} چک`) },
  } : null;
  const issOverduePeek: PeekSpec | null = issuedRecent ? {
    value: shortToman(issuedRecent.amount_rial), page: PAGE_NAMES.issuedCheques,
    facts: [{ label: "تعداد چک", value: fa(issuedRecent.count) }, { label: "بازه", value: "۱ تا ۲۰ روز گذشته" }],
    list: { title: "به تفکیک حساب بانکی", rows: peekRows([...(iss?.by_bank_account || [])].filter((b: any) => b.overdue_rial > 0).sort((a: any, b: any) => b.overdue_rial - a.overdue_rial),
      (b: any) => b.bank_name, (b: any) => Number(b.overdue_rial || 0), (b: any) => faDigits(b.account_number)) },
    note: "این چک‌ها در خروجی امروز حساب می‌شوند؛ اگر پاس شده‌اند وضعیتشان در راهکاران به‌روز شود.",
  } : null;
  const issReviewPeek: PeekSpec | null = issuedReview ? {
    value: shortToman(issuedReview.amount_rial), page: PAGE_NAMES.issuedCheques,
    facts: [
      { label: "تعداد چک", value: fa(issuedReview.count) },
      ...(issuedReview.age_buckets || []).map((b: any) => ({ label: b.label, value: `${shortToman(b.amount_rial)} (${fa(b.count)})` })),
    ].slice(0, 4),
    list: { title: "بزرگ‌ترین چک‌ها", rows: peekRows([...(issuedReview.cheques || [])].sort((a: any, b: any) => b.amount_rial - a.amount_rial),
      (c: any) => c.payee_name, (c: any) => Number(c.amount_rial || 0), (c: any) => `سررسید ${faDigits(c.due_date_jalali)} · ${days(-c.days_to_due)} گذشته`) },
    note: "بیش از ۲۰ روز از سررسید گذشته و هنوز باز است؛ احتمالاً پاس شده ولی در راهکاران ثبت نشده.",
  } : null;
  return <article className="xo-block" id="xo-cheques">
    <div className="xo-block-title"><h3>چک‌ها</h3></div>
    <div className="xo-grid">
      <div className="xo-main">
        <div className="xo-row-label">دریافتی</div>
        <div className="xo-stats">
          <Stat dot={C_RECEIVED} label="دریافتی آینده" value={data.ready ? shortToman(data.receivedFuture.amount) : wait}
            hint={data.ready ? `${fa(data.receivedFuture.count)} چک · امروز به بعد` : "در حال دریافت"} go={() => open("receivedCheques")} peek={recFuturePeek} />
          <Stat tone="follow" label="برگشتی" value={returned ? shortToman(returned.amount_rial) : wait}
            hint={returned ? `${fa(returned.count)} چک از ${faDigits(returned.from_date_jalali || "ابتدای سال")} · راهکاران (واخواست) ${shortToman(bySys("rahkaran")?.amount_rial)} · کارآمد (برگشتی نزد مشتری/صندوق) ${shortToman(bySys("karamad")?.amount_rial)}` : "در حال دریافت"}
            go={() => setDrawer("returned")} goLabel="جزئیات و پیگیری وصول" />
          <Stat tone="watch" label="تعیین تکلیف نشده" value={overdue ? shortToman(Number(overdue.definite_rial || 0) + Number(overdue.other_state_rial || 0)) : wait}
            hint={overdue ? `${fa(Number(overdue.count || 0) + Number(overdue.other_state_count || 0))} چک سررسیدگذشته · نه وصول شده، نه برگشتی${recent ? ` · ${fa(recent.count)} چک تا ۳۰ روز` : ""}` : "در حال دریافت"}
            go={() => setDrawer("undetermined")} goLabel="جزئیات و تعیین وضعیت" />
        </div>
        <div className="xo-row-label">پرداختی</div>
        <div className="xo-stats">
          <Stat dot={C_ISSUED} label="پرداختی آینده" value={data.ready ? shortToman(data.issuedFuture.amount) : wait}
            hint={data.ready ? `${fa(data.issuedFuture.count)} چک · امروز به بعد` : "در حال دریافت"} go={() => open("issuedCheques")} peek={issFuturePeek} />
          <Stat tone="watch" label="سررسید گذشته (تا ۲۰ روز)" value={issuedRecent ? shortToman(issuedRecent.amount_rial) : wait}
            hint={issuedRecent ? `${fa(issuedRecent.count)} چک · در خروجی امروز` : "در حال دریافت"} go={() => open("issuedCheques")} peek={issOverduePeek} />
          <Stat tone="follow" label="وضعیت به‌روز نشده" value={issuedReview ? shortToman(issuedReview.amount_rial) : wait}
            hint={issuedReview ? `${fa(issuedReview.count)} چک بیش از ۲۰ روز گذشته · احتمالاً پاس شده` : "در حال دریافت"}
            go={() => open("issuedCheques")} goLabel="بررسی در راهکاران" peek={issReviewPeek} />
        </div>
        <div className="mc-grid">
          <ChartCard title="ترکیب چک‌های دریافتی" note="از هر ۱۰۰ تومان چک دریافتی باز، چقدر سالم، چقدر برگشتی و چقدر بلاتکلیف است."
            legend={[{ label: "آینده", color: PALETTE.teal }, { label: "تعیین تکلیف نشده", color: PALETTE.violet }, { label: "برگشتی ۱۴۰۵", color: PALETTE.amber }]}>
            {data.ready && returned && overdue ? <StackBar segments={[
              { label: "آینده", value: data.receivedFuture.amount, color: PALETTE.teal, hint: `${fa(data.receivedFuture.count)} چک` },
              { label: "تعیین تکلیف نشده", value: undeterminedAmount, color: PALETTE.violet, hint: `${fa(Number(overdue.count || 0) + Number(overdue.other_state_count || 0))} چک` },
              { label: "برگشتی ۱۴۰۵", value: Number(returned.amount_rial || 0), color: PALETTE.amber, hint: `${fa(returned.count)} چک` },
            ]} /> : <div className="xo-loading">در حال دریافت…</div>}
          </ChartCard>
          <ChartCard title="برگشتی‌های ۱۴۰۵ به تفکیک ماه سررسید" legend={[{ label: "راهکاران (واخواست)", color: PALETTE.teal }, { label: "کارآمد", color: PALETTE.amber }]}>
            {retRows ? <MonthBars items={returnedMonths} series={[{ label: "راهکاران (واخواست)", color: PALETTE.teal }, { label: "کارآمد", color: PALETTE.amber }]} />
              : <div className="xo-loading">در حال دریافت…</div>}
          </ChartCard>
          <ChartCard title="تعیین تکلیف نشده: الان کجاست؟" note="سررسید گذشته ولی نه وصول شده نه برگشتی؛ باید وضعیتش در سیستم ثبت شود.">
            {undDetail ? <FlowCompare rows={undStatus.map((g: any) => ({ label: `${g.label} (${fa(g.count)})`, parts: [{ label: g.label, value: g.amount_rial, color: PALETTE.violet }] }))} />
              : <div className="xo-loading">در حال دریافت…</div>}
          </ChartCard>
          <ChequeMonthsChart buckets={data.buckets} />
        </div>
      </div>
      <div className="xo-side">
        <AgentInsight agentKey="received_cheques" title="چک‌های دریافتی" compact />
        <AgentInsight agentKey="issued_cheques" title="چک‌های پرداختی" compact />
      </div>
    </div>
    <ChequeStatusDrawer kind={drawer} onClose={() => setDrawer(null)} onOpenPage={() => { setDrawer(null); open("receivedCheques"); }} />
  </article>;
}

function ChequeMonthsChart({ buckets }: { buckets: ChequeBucket[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, padL = 8, padR = 56, padT = 14, padB = 34;
  const max = Math.max(1, ...buckets.map((b) => Math.max(b.received, b.issued)));
  const ticks = [0, 0.5, 1].map((f) => f * max);
  const band = (W - padL - padR) / Math.max(buckets.length, 1);
  const barW = Math.min(22, band / 2 - 5);
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / max);
  const h = hover !== null ? buckets[hover] : null;
  return <figure className="xo-chart">
    <figcaption>سررسید چک‌های باز به تفکیک ماه <span className="xo-legend"><i style={{ background: C_RECEIVED }} />دریافتی <i style={{ background: C_ISSUED }} />پرداختی</span></figcaption>
    <div className="xo-chart-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="سررسید چک‌های دریافتی و پرداختی در هر ماه">
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="xo-grid-line" />
          <text x={W - padR + 6} y={y(t) + 4} className="xo-axis">{shortToman(t)}</text></g>)}
        {buckets.map((b, i) => {
          const cx = padL + band * i + band / 2;
          return <g key={b.label} onMouseEnter={() => setHover(i)}>
            <rect x={padL + band * i} y={padT} width={band} height={H - padT - padB} fill="transparent" />
            {hover === i && <rect x={padL + band * i + 2} y={padT} width={band - 4} height={H - padT - padB} className="xo-hover-band" />}
            <path d={barPath(cx - barW - 1, y(b.received), barW, H - padB - y(b.received))} fill={C_RECEIVED} />
            <path d={barPath(cx + 1, y(b.issued), barW, H - padB - y(b.issued))} fill={C_ISSUED} />
            <text x={cx} y={H - padB + 16} className={`xo-axis center${b.overdue ? " warn" : ""}`}>{b.label}</text>
          </g>;
        })}
        <line x1={padL} x2={W - padR} y1={H - padB} y2={H - padB} className="xo-base-line" />
      </svg>
      {h && <div className="xo-tooltip" style={{ left: `${((padL + band * (hover as number) + band / 2) / W) * 100}%` }}>
        <b>{h.label}</b>
        <span><i style={{ background: C_RECEIVED }} />دریافتی: {fullToman(h.received)} تومان ({fa(h.receivedCount)} فقره)</span>
        <span><i style={{ background: C_ISSUED }} />پرداختی: {fullToman(h.issued)} تومان ({fa(h.issuedCount)} فقره)</span>
      </div>}
    </div>
  </figure>;
}
/** میله با سر گرد ۴px و پایه صاف روی خط مبنا */
function barPath(x: number, top: number, w: number, h: number) {
  if (h <= 0.5) return "";
  const r = Math.min(4, w / 2, h);
  return `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + w - r} Q${x + w},${top} ${x + w},${top + r} V${top + h} Z`;
}


// ------------------------------------------------------------------ payables
function PayablesBlock({ open }: { open: (view: View) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getJson(`http://${apiHost()}:8000/api/v1/finance/payables`).then(setData).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);
  const m = data?.modules;
  const top = useMemo(() => {
    if (!m) return [];
    return [...m.trade.counterparties.map((p: any) => ({ ...p, module: "تجاری" })), ...m.nontrade.counterparties.map((p: any) => ({ ...p, module: "غیرتجاری" }))]
      .filter((p: any) => p.credit_balance_rial > 0).sort((a: any, b: any) => b.credit_balance_rial - a.credit_balance_rial).slice(0, 5);
  }, [m]);
  const maxTop = Math.max(1, ...top.map((p: any) => p.credit_balance_rial));
  const topAdvance = useMemo(() => {
    if (!m) return [];
    return [...m.trade.counterparties.map((p: any) => ({ ...p, module: "تجاری" })), ...m.nontrade.counterparties.map((p: any) => ({ ...p, module: "غیرتجاری" }))]
      .filter((p: any) => p.debit_balance_rial > 0).sort((a: any, b: any) => b.debit_balance_rial - a.debit_balance_rial).slice(0, 5);
  }, [m]);
  const maxAdvance = Math.max(1, ...topAdvance.map((p: any) => p.debit_balance_rial));
  const creditorPeek = (mod: any, name: string): PeekSpec => ({
    value: shortToman(mod.credit_balance_rial), page: PAGE_NAMES.payables,
    facts: [
      { label: "طرف حساب بستانکار", value: fa(mod.creditor_count) },
      { label: "سهم ۵ طرف اول", value: `${fa(Math.round((100 * [...mod.counterparties].sort((a: any, b: any) => b.credit_balance_rial - a.credit_balance_rial).slice(0, 5)
        .reduce((s2: number, p: any) => s2 + Math.max(0, p.credit_balance_rial), 0)) / Math.max(1, mod.credit_balance_rial)))}٪` },
    ],
    list: { title: `بزرگ‌ترین بدهی‌های ${name}`, rows: peekRows([...mod.counterparties].filter((p: any) => p.credit_balance_rial > 0).sort((a: any, b: any) => b.credit_balance_rial - a.credit_balance_rial),
      (p: any) => p.title, (p: any) => Number(p.credit_balance_rial || 0), (p: any) => faDigits(p.dl_code)) },
  });
  return <article className="xo-block" id="xo-payables">
    <div className="xo-block-title"><h3>پرداخت تجاری</h3><small>بدهی شرکت به تأمین‌کنندگان</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error ? <div className="profile-warning">{error}</div> : !m ? <div className="xo-loading">در حال دریافت…</div> : <>
          <div className="xo-stats">
            <Stat label="بدهی تجاری" value={shortToman(m.trade.credit_balance_rial)} hint={`${fa(m.trade.creditor_count)} طرف حساب`} go={() => open("payables")}
              peek={creditorPeek(m.trade, "تجاری (۵۱۱۰۰۲)")} />
            <Stat label="بدهی غیرتجاری" value={shortToman(m.nontrade.credit_balance_rial)} hint={`${fa(m.nontrade.creditor_count)} طرف حساب`} go={() => open("payables")}
              peek={creditorPeek(m.nontrade, "غیرتجاری (۵۱۲۰۰۱)")} />
            <Stat tone="watch" label="پیش‌پرداخت باز" value={shortToman(m.trade.debit_balance_rial + m.nontrade.debit_balance_rial)}
              hint={`${fa(m.trade.debtor_count + m.nontrade.debtor_count)} طرف حساب · کالا یا فاکتورش مانده`} go={() => open("payables")} goLabel="پیگیری با خرید"
              peek={{ value: shortToman(m.trade.debit_balance_rial + m.nontrade.debit_balance_rial), page: PAGE_NAMES.payables,
                facts: [{ label: "تجاری", value: `${shortToman(m.trade.debit_balance_rial)} (${fa(m.trade.debtor_count)})` },
                  { label: "غیرتجاری", value: `${shortToman(m.nontrade.debit_balance_rial)} (${fa(m.nontrade.debtor_count)})` }],
                list: { title: "بزرگ‌ترین پیش‌پرداخت‌ها", rows: peekRows(topAdvance, (p: any) => p.title, (p: any) => Number(p.debit_balance_rial || 0), (p: any) => p.module) },
                note: "پولی که داده شده و هنوز کالا یا فاکتورش ثبت نشده؛ با واحد خرید پیگیری شود." }} />
          </div>
          <div className="mc-grid">
          <ChartCard title="بدهی شرکت در برابر پیش‌پرداخت" note="راست: پیش‌پرداختی که داده‌ایم (کالا یا فاکتورش مانده)؛ چپ: بدهی‌ای که باید بپردازیم."
            legend={[{ label: "پیش‌پرداخت", color: PALETTE.teal }, { label: "بدهی شرکت", color: PALETTE.amber }]}>
            <DivergingRows left={{ label: "بدهی شرکت", color: PALETTE.amber }} right={{ label: "پیش‌پرداخت", color: PALETTE.teal }}
              rows={[
                { label: "تجاری", sub: "۵۱۱۰۰۲", left: m.trade.credit_balance_rial, right: m.trade.debit_balance_rial },
                { label: "غیرتجاری", sub: "۵۱۲۰۰۱", left: m.nontrade.credit_balance_rial, right: m.nontrade.debit_balance_rial },
                { label: "جمع", left: m.trade.credit_balance_rial + m.nontrade.credit_balance_rial, right: m.trade.debit_balance_rial + m.nontrade.debit_balance_rial },
              ]} />
          </ChartCard>
          <ChartCard title="بزرگ‌ترین پیش‌پرداخت‌ها" note="پولی که داده شده و هنوز کالا یا فاکتورش ثبت نشده.">
            <div className="xo-hbars">
              {topAdvance.map((p: any) => <button key={`${p.module}-${p.dl_code}`} className="xo-hbar" onClick={() => open("payables")} title={`${p.title}: ${fullToman(p.debit_balance_rial)} تومان`}>
                <span className="xo-hbar-label">{p.title}<small>{p.module}</small></span>
                <span className="xo-hbar-track"><i style={{ width: `${(100 * p.debit_balance_rial) / maxAdvance}%`, background: PALETTE.teal }} /></span>
                <span className="xo-hbar-value">{shortToman(p.debit_balance_rial)}</span>
              </button>)}
            </div>
          </ChartCard>
          </div>
          <figure className="xo-chart">
            <figcaption>بزرگ‌ترین بدهی‌ها</figcaption>
            <div className="xo-hbars">
              {top.map((p: any) => <button key={`${p.module}-${p.dl_code}`} className="xo-hbar" onClick={() => open("payables")} title={`${p.title}: ${fullToman(p.credit_balance_rial)} تومان`}>
                <span className="xo-hbar-label">{p.title}<small>{p.module}</small></span>
                <span className="xo-hbar-track"><i style={{ width: `${(100 * p.credit_balance_rial) / maxTop}%`, background: C_ISSUED }} /></span>
                <span className="xo-hbar-value">{shortToman(p.credit_balance_rial)}</span>
              </button>)}
              {!top.length && <p className="xo-loading">بدهی بازی ثبت نشده است.</p>}
            </div>
          </figure>
        </>}
      </div>
      <div className="xo-side"><AgentInsight agentKey="payables" title="پرداخت تجاری" compact /></div>
    </div>
  </article>;
}

// ------------------------------------------------------------------ liquidity
const SCENARIO_COLORS: Record<string, string> = { definite: C_RECEIVED, reliance: C_ISSUED, pessimistic: C_THIRD };
function LiquidityBlock({ open }: { open: (view: View) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getJson(`${LIQ()}/summary?horizon_days=30`).then((j) => setData(j.data)).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);
  const scenarios: any[] = data?.scenarios || [];
  const base = scenarios.find((s) => s.key === (data?.base_scenario || "reliance")) || scenarios[0];
  const short = base && base.financing_need_rial > 0;
  // خالص هفتگی سناریوی اتکا: روزهای پیش‌بینی در بسته‌های ۷ روزه
  const weeks = (() => {
    const days: any[] = base?.days || [];
    const out: { label: string; net: number; inflow: number; outflow: number }[] = [];
    for (let i = 0; i < days.length; i += 7) {
      const chunk = days.slice(i, i + 7);
      out.push({
        label: `هفته ${fa(out.length + 1)} · ${faDigits(String(chunk[0]?.date_jalali || "").slice(5))}`,
        net: chunk.reduce((s2, d) => s2 + Number(d.net_rial || 0), 0),
        inflow: chunk.reduce((s2, d) => s2 + Number(d.inflow_rial || 0), 0),
        outflow: chunk.reduce((s2, d) => s2 + Number(d.outflow_rial || 0), 0),
      });
    }
    return out;
  })();
  const tot = base?.totals || {};
  const flowFacts = base ? [
    { label: "سناریو", value: base.label },
    { label: "پوشش خروجی", value: `${nf1.format(base.coverage_percent || 0)}٪` },
  ] : [];
  const flowList = (title: string, parts: [string, number][]) => {
    const max = Math.max(1, ...parts.map(([, v]) => v));
    return { title, rows: parts.map(([label, v]) => ({ label, value: shortToman(v), share: (100 * v) / max })) };
  };
  const weekRows = (key: "inflow" | "outflow" | "net") => ({ title: "به تفکیک هفته", rows: weeks.map((w) => ({ label: w.label, value: `${w[key] < 0 ? "−" : ""}${shortToman(Math.abs(w[key]))}` })) });
  const liqPeek = (value: string, extra: Partial<PeekSpec>): PeekSpec => ({ value, page: PAGE_NAMES.liquidity, facts: flowFacts, ...extra });
  return <article className="xo-block" id="xo-liquidity">
    <div className="xo-block-title"><h3>نقدینگی ۳۰ روز آینده</h3><small>پیش‌بینی ورودی و خروجی (بدون موجودی بانک)</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error ? <div className="profile-warning">{error}</div> : !base ? <div className="xo-loading">در حال ساخت پیش‌بینی (حدود ۱۵ ثانیه)…</div> : <>
          <div className="xo-stats four">
            <Stat label="ورودی" value={shortToman(base.inflow_rial)} hint="چک دریافتی + نقد و حواله" go={() => open("liquidity")}
              peek={liqPeek(shortToman(base.inflow_rial), { list: flowList("از چه ساخته شده", [["چک دریافتی (با درصد اتکا)", tot.received_cheques_rial || 0], ["نقد و حواله (میانگین)", tot.estimated_inflow_rial || 0]]),
                note: weeks.map((w) => `${w.label}: ${shortToman(w.inflow)}`).join(" · ") })} />
            <Stat label="خروجی" value={shortToman(base.outflow_rial)} hint={`چک ${shortToman(base.totals?.issued_cheques_rial)} · حقوق ${shortToman(base.totals?.payroll_rial)}`} go={() => open("liquidity")}
              peek={liqPeek(shortToman(base.outflow_rial), { list: flowList("از چه ساخته شده", [["چک پرداختی", tot.issued_cheques_rial || 0], ["حقوق", tot.payroll_rial || 0], ["هزینه‌های روزانه (میانگین)", tot.estimated_outflow_rial || 0]]),
                note: weeks.map((w) => `${w.label}: ${shortToman(w.outflow)}`).join(" · ") })} />
            <Stat tone={base.coverage_percent < 100 ? "watch" : "good"} label="پوشش خروجی" value={`${nf1.format(base.coverage_percent || 0)}٪`} unit="" hint={base.coverage_percent < 100 ? "ورودی کمتر از خروجی" : "ورودی کافی است"} go={() => open("liquidity")}
              peek={liqPeek(`${nf1.format(base.coverage_percent || 0)}٪`, { facts: scenarios.map((s) => ({ label: `سناریوی ${s.label}`, value: `${nf1.format(s.coverage_percent || 0)}٪` })),
                list: weekRows("net"), note: "پوشش = ورودی ÷ خروجی ۳۰ روز. زیر ۱۰۰٪ یعنی بدون موجودی بانک، ورودی کفاف خروجی را نمی‌دهد." })} />
            <Stat tone={short ? "follow" : "good"} label={short ? "نیاز به تأمین" : "بدون کسری"} value={short ? shortToman(base.financing_need_rial) : "—"}
              hint={short && base.worst_balance?.date_jalali ? `کمترین مانده ${faDigits(base.worst_balance.date_jalali)}` : "در ۳۰ روز آینده"} go={() => open("liquidity")} goLabel="برنامه تأمین"
              peek={liqPeek(short ? shortToman(base.financing_need_rial) : "—", {
                facts: [
                  { label: "اولین روز کسری", value: base.first_shortage?.date_jalali ? faDigits(base.first_shortage.date_jalali) : "—" },
                  { label: "کمترین مانده", value: base.worst_balance?.date_jalali ? `${faDigits(base.worst_balance.date_jalali)}` : "—" },
                  ...scenarios.map((s) => ({ label: `نیاز در سناریوی ${s.label}`, value: s.financing_need_rial > 0 ? shortToman(s.financing_need_rial) : "بدون کسری" })),
                ],
                list: weekRows("net"), note: "بدون احتساب موجودی فعلی بانک؛ اگر موجودی بیش از این عدد باشد کسری پوشش داده می‌شود." })} />
          </div>
          <div className="mc-grid">
            <ChartCard title="ورودی در برابر خروجی ۳۰ روز" note="هر نوار از چه چیزی ساخته شده (سناریوی اتکا).">
              <FlowCompare rows={[
                { label: "ورودی", parts: [
                  { label: "چک دریافتی", value: base.totals?.received_cheques_rial || 0, color: PALETTE.teal },
                  { label: "نقد و حواله", value: base.totals?.estimated_inflow_rial || 0, color: PALETTE.violet },
                ] },
                { label: "خروجی", parts: [
                  { label: "چک پرداختی", value: base.totals?.issued_cheques_rial || 0, color: PALETTE.amber },
                  { label: "حقوق", value: base.totals?.payroll_rial || 0, color: "#2563eb" },
                  { label: "هزینه‌های روزانه", value: base.totals?.estimated_outflow_rial || 0, color: "#db2777" },
                ] },
              ]} />
            </ChartCard>
            <ChartCard title="خالص هر هفته" note="بالای خط: ورودی بیشتر؛ پایین خط: خروجی بیشتر.">
              <NetWeeks pos={PALETTE.teal} neg={PALETTE.amber} weeks={weeks} />
            </ChartCard>
          </div>
          <LiquidityChart scenarios={scenarios} />
        </>}
      </div>
      <div className="xo-side"><AgentInsight agentKey="liquidity" title="نقدینگی" compact /></div>
    </div>
  </article>;
}

function LiquidityChart({ scenarios }: { scenarios: any[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const days: any[] = scenarios[0]?.days || [];
  const W = 640, H = 240, padL = 8, padR = 64, padT = 14, padB = 30;
  const values = scenarios.flatMap((s) => (s.days || []).map((d: any) => d.closing_rial as number));
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values);
  const span = hi - lo || 1;
  const x = (i: number) => padL + ((W - padL - padR) * i) / Math.max(days.length - 1, 1);
  const y = (v: number) => padT + (H - padT - padB) * (1 - (v - lo) / span);
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i);
  const order = ["definite", "reliance", "pessimistic"];
  const sorted = [...scenarios].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - padL) / (W - padL - padR)) * (days.length - 1));
    setHover(Math.max(0, Math.min(days.length - 1, i)));
  };
  return <figure className="xo-chart">
    <figcaption>مانده تجمعی جریان نقد در سه سناریو
      <span className="xo-legend">{sorted.map((s) => <span key={s.key}><i style={{ background: SCENARIO_COLORS[s.key] || C_THIRD }} />{s.label}</span>)}</span>
    </figcaption>
    <div className="xo-chart-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="مانده تجمعی جریان نقد ۳۰ روز آینده در سناریوهای قطعی، اتکا و بدبینانه" onMouseMove={onMove}>
        {ticks.map((t) => <g key={t}><line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className={t === 0 ? "xo-zero-line" : "xo-grid-line"} />
          <text x={W - padR + 6} y={y(t) + 4} className="xo-axis">{t === 0 ? "صفر" : shortToman(t)}</text></g>)}
        {[0, Math.floor((days.length - 1) / 2), days.length - 1].filter((i) => days[i]).map((i) =>
          <text key={i} x={x(i)} y={H - 8} className="xo-axis center">{faDigits(days[i].date_jalali.slice(5))}</text>)}
        {sorted.map((s) => <polyline key={s.key} fill="none" stroke={SCENARIO_COLORS[s.key] || C_THIRD} strokeWidth={2} strokeLinejoin="round"
          points={(s.days || []).map((d: any, i: number) => `${x(i)},${y(d.closing_rial)}`).join(" ")} />)}
        {sorted.map((s) => { const last = (s.days || [])[days.length - 1]; return last ? <text key={`l-${s.key}`} x={x(days.length - 1) + 4} y={y(last.closing_rial) - 6} className="xo-direct">{s.label}</text> : null; })}
        {hover !== null && <g>
          <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} className="xo-crosshair" />
          {sorted.map((s) => s.days?.[hover] ? <circle key={s.key} cx={x(hover)} cy={y(s.days[hover].closing_rial)} r={4.5} fill={SCENARIO_COLORS[s.key] || C_THIRD} className="xo-dot" /> : null)}
        </g>}
      </svg>
      {hover !== null && days[hover] && <div className="xo-tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
        <b>{faDigits(days[hover].date_jalali)}</b>
        {sorted.map((s) => <span key={s.key}><i style={{ background: SCENARIO_COLORS[s.key] || C_THIRD }} />{s.label}: {s.days[hover].closing_rial < 0 ? "−" : ""}{shortToman(Math.abs(s.days[hover].closing_rial))}</span>)}
        <span className="muted">ورودی روز (اتکا): {shortToman(scenarios.find((s) => s.key === "reliance")?.days?.[hover]?.inflow_rial)} · خروجی: {shortToman(days[hover].outflow_rial)}</span>
      </div>}
    </div>
  </figure>;
}

// ------------------------------------------------------------------ distribution
const MONTHS_FA = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
function currentJalaliMonth() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric" }).formatToParts(new Date());
  return { year: Number(parts.find((x) => x.type === "year")?.value), month: Number(parts.find((x) => x.type === "month")?.value) };
}
function DistributionBlock({ open }: { open: (view: View) => void }) {
  const ym = useMemo(currentJalaliMonth, []);
  const [month, setMonth] = useState<any>(null);
  const [today, setToday] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const api = `http://${apiHost()}:8000/api/v1/finance`;
    getJson(`${api}/distribution/monthly?year=${ym.year}&month=${ym.month}`).then(setMonth).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
    getJson(`${api}/distribution`).then(setToday).catch(() => setToday({}));
  }, [ym.year, ym.month]);
  const t = month?.totals || {};
  const company = month?.company_sales || {};
  const undistributed: any[] = today?.undistributed || [];
  const staleList = undistributed.filter((x) => Number(x.days_waiting || 0) > 14);
  const lead: any[] = today?.lead_time || [];
  const leadCount = lead.reduce((s2, l) => s2 + Number(l.invoice_count || 0), 0);
  const avgLead = leadCount ? lead.reduce((s2, l) => s2 + Number(l.average_days || 0) * Number(l.invoice_count || 0), 0) / leadCount : 0;
  const sumAmount = (rows: any[]) => rows.reduce((s2, x) => s2 + Number(x.amount_rial || 0), 0);
  const branches: any[] = (month?.branches || []).filter((b: any) => Number(b.sales_rial || 0) > 0)
    .sort((a: any, b: any) => Number(b.sales_rial) - Number(a.sales_rial)).slice(0, 8);
  const label = `${MONTHS_FA[ym.month - 1]} ${faDigits(String(ym.year))}`;
  const distPct = t.sales_rial ? Math.round((100 * Number(t.distributed_rial || 0)) / Number(t.sales_rial)) : 0;
  const allBranches: any[] = (month?.branches || []).filter((b: any) => Number(b.sales_rial || 0) > 0);
  const byDesc = (key: string) => [...allBranches].sort((a, b) => Number(b[key] || 0) - Number(a[key] || 0));
  const pct = (a: any, b: any) => (Number(b || 0) ? Math.round((100 * Number(a || 0)) / Number(b)) : 0);
  const todayByBranch = (rows: any[]) => {
    const map = new Map<string, { branch: string; amount: number; count: number }>();
    rows.forEach((x) => { const g = map.get(x.branch_name) || { branch: x.branch_name, amount: 0, count: 0 }; g.amount += Number(x.amount_rial || 0); g.count += 1; map.set(x.branch_name, g); });
    return [...map.values()].sort((a, b) => b.amount - a.amount);
  };
  const distPeek = (value: string, extra: Partial<PeekSpec>): PeekSpec => ({ value, page: PAGE_NAMES.distribution, ...extra });
  return <article className="xo-block" id="xo-distribution">
    <div className="xo-block-title"><h3>فروش و توزیع بار</h3><small>{label} و وضعیت امروز (کارآمد)</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error ? <div className="profile-warning">{error}</div> : !month ? <div className="xo-loading">در حال ساخت گزارش ماه…</div> : <>
          <div className="xo-row-label">{label}</div>
          <div className="xo-stats four">
            <Stat label="فروش کل ماه" value={shortToman(company.net_rial ?? t.sales_rial)}
              hint={company.net_rial != null ? `همه شعب · فاکتور ${shortToman(company.invoices_rial)} منهای برگشتی ${shortToman(company.returns_rial)}` : "در حال دریافت"}
              go={() => open("distribution")}
              peek={distPeek(shortToman(company.net_rial ?? t.sales_rial), {
                facts: [{ label: "فاکتور فروش همه شعب", value: shortToman(company.invoices_rial) }, { label: "برگشتی ثبت‌شده در ماه", value: shortToman(company.returns_rial) },
                  { label: "فاکتور هیبریدها", value: shortToman(t.sales_rial) }, { label: "سهم برگشتی", value: `${fa(pct(company.returns_rial, company.invoices_rial))}٪` }],
                list: { title: "بیشترین فروش خالص شعب", rows: peekRows(company.by_branch || [], (b: any) => b.branch_name, (b: any) => Number(b.net_rial || 0)) },
                note: company.rule })} />
            <Stat tone={distPct < 70 ? "watch" : "good"} label="توزیع شده (هیبریدها)" value={`${fa(distPct)}٪`} unit=""
              hint={`${shortToman(t.distributed_rial)} از ${shortToman(t.sales_rial)} فاکتور هیبریدها`} go={() => open("distribution")}
              peek={distPeek(`${fa(distPct)}٪`, {
                facts: [{ label: "توزیع شده", value: shortToman(t.distributed_rial) }, { label: "فاکتور هیبریدها", value: shortToman(t.sales_rial) }],
                list: { title: "کمترین درصد توزیع (هیبریدها)", rows: [...allBranches].sort((a, b) => pct(a.distributed_rial, a.sales_rial) - pct(b.distributed_rial, b.sales_rial)).slice(0, 5)
                  .map((b) => ({ label: b.branch_name, sub: `${shortToman(b.distributed_rial)} از ${shortToman(b.sales_rial)}`, value: `${fa(pct(b.distributed_rial, b.sales_rial))}٪`, share: pct(b.distributed_rial, b.sales_rial) })) } })} />
            <Stat tone="follow" label="توزیع نشده" value={shortToman(t.undistributed_rial)} hint="فاکتور بدون حواله خروج" go={() => open("distribution")} goLabel="پیگیری خروج بار"
              peek={distPeek(shortToman(t.undistributed_rial), {
                facts: [{ label: "تعداد فاکتور", value: fa(allBranches.reduce((s2, b) => s2 + Number(b.undistributed_count || 0), 0)) },
                  { label: "سهم از فروش هیبریدها", value: `${fa(pct(t.undistributed_rial, t.sales_rial))}٪` }],
                list: { title: "بیشترین توزیع‌نشده ماه", rows: peekRows(byDesc("undistributed_rial"), (b: any) => b.branch_name, (b: any) => Number(b.undistributed_rial || 0), (b: any) => `${fa(b.undistributed_count)} فاکتور`) } })} />
            <Stat label="وصول / مانده ماه" value={shortToman(t.collected_rial)} hint={`مانده ${shortToman(t.remaining_rial)}`} go={() => open("distribution")}
              peek={distPeek(shortToman(t.collected_rial), {
                facts: [{ label: "وصول‌شده", value: shortToman(t.collected_rial) }, { label: "مانده فاکتورهای ماه", value: shortToman(t.remaining_rial) },
                  { label: "درصد وصول از توزیع‌شده", value: `${fa(pct(t.collected_rial, t.distributed_rial))}٪` }],
                list: { title: "بیشترین مانده وصول", rows: peekRows(byDesc("remaining_rial"), (b: any) => b.branch_name, (b: any) => Number(b.remaining_rial || 0), (b: any) => `وصول ${shortToman(b.collected_rial)}`) } })} />
          </div>
          <div className="xo-row-label">امروز</div>
          <div className="xo-stats">
            <Stat tone={staleList.length ? "follow" : "good"} label="مانده بیش از ۱۴ روز" value={today ? shortToman(sumAmount(staleList)) : <span className="xo-wait">…</span>}
              hint={today ? `${fa(staleList.length)} فاکتور از ${fa(undistributed.length)} توزیع‌نشده` : "در حال دریافت"} go={() => open("distribution")}
              peek={today ? distPeek(shortToman(sumAmount(staleList)), {
                facts: [{ label: "تعداد فاکتور", value: fa(staleList.length) }, { label: "قدیمی‌ترین", value: staleList.length ? `${fa(Math.max(...staleList.map((x) => Number(x.days_waiting || 0))))} روز` : "—" }],
                list: { title: "به تفکیک هیبرید", rows: peekRows(todayByBranch(staleList), (g) => g.branch, (g) => g.amount, (g) => `${fa(g.count)} فاکتور`) } }) : null} />
            <Stat tone="watch" label="کل توزیع‌نشده امروز" value={today ? shortToman(sumAmount(undistributed)) : <span className="xo-wait">…</span>}
              hint={today ? `${fa(undistributed.length)} فاکتور امسال · بدون حواله یا حواله «۰»` : "در حال دریافت"} go={() => open("distribution")}
              peek={today ? distPeek(shortToman(sumAmount(undistributed)), {
                facts: [{ label: "تعداد فاکتور", value: fa(undistributed.length) }, { label: "بیش از ۱۴ روز", value: `${shortToman(sumAmount(staleList))} (${fa(staleList.length)})` }],
                list: { title: "به تفکیک هیبرید", rows: peekRows(todayByBranch(undistributed), (g) => g.branch, (g) => g.amount, (g) => `${fa(g.count)} فاکتور`) } }) : null} />
            <Stat label="فاکتور تا خروج بار" value={today ? `${nf1.format(Math.round(avgLead * 10) / 10)} روز` : <span className="xo-wait">…</span>} unit=""
              hint={today ? `میانگین ${fa(leadCount)} فاکتور امسال` : "در حال دریافت"} go={() => open("distribution")}
              peek={today ? distPeek(`${nf1.format(Math.round(avgLead * 10) / 10)} روز`, {
                facts: [{ label: "فاکتورهای بررسی‌شده", value: fa(leadCount) }, { label: "بیش از ۷ روز", value: fa(lead.reduce((s2, l) => s2 + Number(l.over_7_days || 0), 0)) }],
                list: { title: "کندترین هیبریدها (میانگین روز)", rows: [...lead].sort((a, b) => b.average_days - a.average_days).slice(0, 5).map((l) => ({
                  label: l.branch_name, sub: `${fa(l.invoice_count)} فاکتور · ${nf1.format(l.within_3_days_percent || 0)}٪ تا ۳ روز`, value: `${nf1.format(l.average_days)} روز`,
                  share: (100 * l.average_days) / Math.max(1, ...lead.map((x) => x.average_days)) })) } }) : null} />
          </div>
          <div className="mc-grid">
            <ChartCard title={`فاکتورهای هیبریدها ${label}: توزیع‌شده و مانده`} legend={[{ label: "توزیع‌شده", color: PALETTE.teal }, { label: "توزیع‌نشده", color: PALETTE.amber }]}>
              <StackBar segments={[
                { label: "توزیع‌شده", value: Number(t.distributed_rial || 0), color: PALETTE.teal },
                { label: "توزیع‌نشده", value: Number(t.undistributed_rial || 0), color: PALETTE.amber },
              ]} />
              <FlowCompare rows={[
                { label: "وصول و مانده", parts: [
                  { label: "وصول‌شده", value: Number(t.collected_rial || 0), color: PALETTE.teal },
                  { label: "مانده ماه", value: Number(t.remaining_rial || 0), color: PALETTE.violet },
                ] },
              ]} />
            </ChartCard>
            <ChartCard title="هیبریدها: فروش ماه و سهم توزیع‌نشده" legend={[{ label: "توزیع‌شده", color: PALETTE.teal }, { label: "توزیع‌نشده", color: PALETTE.amber }]}
              note="۸ هیبرید با بیشترین فروش؛ برای جزئیات روی صفحه توزیع بار بروید.">
              <FlowCompare rows={branches.map((b: any) => ({ label: b.branch_name, parts: [
                { label: "توزیع‌شده", value: Number(b.distributed_rial || 0), color: PALETTE.teal },
                { label: "توزیع‌نشده", value: Number(b.undistributed_rial || 0), color: PALETTE.amber },
              ] }))} />
            </ChartCard>
          </div>
        </>}
      </div>
      <div className="xo-side"><AgentInsight agentKey="distribution" title="توزیع بار" compact /></div>
    </div>
  </article>;
}
