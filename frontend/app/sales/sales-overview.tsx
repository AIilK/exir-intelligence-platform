"use client";
// خلاصه مدیریتی فروش — هم‌شکل «نمای کلان مالی»: هر کارت = عنوان کوتاه + عدد + یک خط راهنما؛ با کلیک پنل جزئیات کوتاه باز می‌شود.
// منبع: گزارش ماهانه توزیع و وصول (/finance/distribution/monthly) و شبکه فروش کارآمد (/finance/sales-network).
// کنار هر بلوک الارم‌های فروش همان بخش (به‌جای Agent).
import { useCallback, useEffect, useMemo, useState } from "react";
import { ModuleAlarms } from "../alarms/alarms";
import { PeekContext, PeekPanel, type Peek } from "../management/peek-panel";
import { ChartCard, DivergingRows, FlowCompare, MonthBars, PALETTE, StackBar } from "../management/mini-charts";
import { Stat, jumpTo, peekRows } from "../management/executive-overview";
import "../management/executive-overview.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const FIN = () => `http://${apiHost()}:8000/api/v1/finance`;
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const shortToman = (rial: number | null | undefined) => {
  const t = Number(rial || 0) / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const pct = (a: any, b: any) => (Number(b || 0) ? Math.round((100 * Number(a || 0)) / Number(b)) : 0);
const growth = (cur: number, prev: number) => (prev > 0 ? ((cur - prev) / prev) * 100 : null);
const signed = (g: number | null) => (g === null ? "—" : `${g >= 0 ? "▲" : "▼"} ${nf1.format(Math.abs(g))}٪`);
async function getJson(url: string) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
type YM = { year: number; month: number };
function currentYM(): YM {
  const p = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric" }).formatToParts(new Date());
  return { year: Number(p.find((x) => x.type === "year")?.value), month: Number(p.find((x) => x.type === "month")?.value) };
}
const shift = (m: YM, d: number): YM => { const i = m.year * 12 + m.month - 1 + d; return { year: Math.floor(i / 12), month: (i % 12) + 1 }; };
const faDigits = (v: unknown) => String(v ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const monthDays = (m: YM) => (m.month <= 6 ? 31 : m.month <= 11 ? 30 : 29);
function todayDay(): number {
  const p = new Intl.DateTimeFormat("en-US-u-ca-persian", { day: "numeric" }).formatToParts(new Date());
  return Math.max(1, Number(p.find((x) => x.type === "day")?.value) || 1);
}
const ymLabel = (m: YM) => `${MONTHS[m.month - 1]} ${nf.format(m.year).replace(/٬/g, "")}`;
type View = "distribution" | "customers";
type PeekSpec = Omit<Peek, "onGo" | "title" | "tone" | "unit"> & { title?: string };

export default function SalesOverview({ go }: { go: (view: string) => void }) {
  const [peek, setPeek] = useState<Peek | null>(null);
  const closePeek = useCallback(() => setPeek(null), []);
  const months = useMemo(() => { const now = currentYM(); return [shift(now, -2), shift(now, -1), now]; }, []);
  const [reports, setReports] = useState<(any | null)[]>([null, null, null]);
  const [error, setError] = useState("");
  const [network, setNetwork] = useState<any>(null);
  const [networkError, setNetworkError] = useState("");
  useEffect(() => {
    months.forEach((m, i) => getJson(`${FIN()}/distribution/monthly?year=${m.year}&month=${m.month}`)
      .then((d) => setReports((cur) => cur.map((x, j) => (j === i ? d : x))))
      .catch((e) => { setReports((cur) => cur.map((x, j) => (j === i ? {} : x))); if (i === 2) setError(e instanceof Error ? e.message : "خطا"); }));
    getJson(`${FIN()}/sales-network`).then(setNetwork).catch((e) => setNetworkError(e instanceof Error ? e.message : "خطا"));
  }, [months]);
  const open = (v: View) => go(v);
  return <PeekContext.Provider value={setPeek}><section className="xo">
    <header className="xo-head">
      <h2>نمای کلان فروش</h2>
      <p>فروش خالص، هیبریدها، توزیع و وصول و شبکه فروش کارآمد در یک نگاه؛ برای جزئیات روی هر کارت بزنید.</p>
      <div className="xo-jump" role="navigation" aria-label="پرش به بخش">
        {([["xs-month", "فروش ماه"], ["xs-hybrids", "هیبریدها و وصول"], ["xs-network", "شبکه فروش"]] as [string, string][]).map(([id, label]) =>
          <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); jumpTo(id); }}>{label}</a>)}
      </div>
    </header>
    <MonthBlock months={months} reports={reports} error={error} open={open} go={go} />
    <HybridBlock month={months[2]} report={reports[2]} error={error} open={open} go={go} />
    <NetworkBlock data={network} error={networkError} open={open} go={go} />
    <PeekPanel peek={peek} onClose={closePeek} />
  </section></PeekContext.Provider>;
}

// ------------------------------------------------------------------ فروش ماه
function MonthBlock({ months, reports, error, open, go }: { months: YM[]; reports: (any | null)[]; error: string; open: (v: View) => void; go: (v: string) => void }) {
  const cur = reports[2], prev = reports[1];
  const c = cur?.company_sales || {}, p = prev?.company_sales || {};
  const net = Number(c.net_rial ?? cur?.totals?.sales_rial ?? 0), prevNet = Number(p.net_rial ?? prev?.totals?.sales_rial ?? 0);
  // ماه جاری هنوز تمام نشده: سرعت فروش (میانگین روزانه) با میانگین روزانه کل ماه قبل مقایسه می‌شود.
  const day = todayDay(), curDaily = net / day, prevDaily = prevNet / monthDays(months[1]);
  const g = prev ? growth(curDaily, prevDaily) : null;
  const label = ymLabel(months[2]);
  const byBranch: any[] = [...(c.by_branch || [])].sort((a, b) => Number(b.net_rial || 0) - Number(a.net_rial || 0));
  const monthSeries = months.map((m, i) => {
    const r = reports[i]?.company_sales || {};
    return { label: MONTHS[m.month - 1], values: [Number(r.net_rial || 0), Number(r.returns_rial || 0)], counts: [0, 0] };
  });
  const peekOf = (value: string, extra: Partial<PeekSpec>): PeekSpec => ({ value, page: "توزیع بار", ...extra });
  return <article className="xo-block" id="xs-month">
    <div className="xo-block-title"><h3>فروش ماه</h3><small>{label} · همه شعب (کارآمد) · مقایسه با ماه قبل</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error && !cur?.totals ? <div className="profile-warning">{error}</div> : !cur ? <div className="xo-loading">در حال ساخت گزارش فروش ماه…</div> : <>
          <div className="xo-stats four">
            <Stat label="فروش خالص ماه" value={shortToman(net)} hint={`فاکتور ${shortToman(c.invoices_rial)} منهای برگشتی ${shortToman(c.returns_rial)}`} go={() => open("distribution")}
              peek={peekOf(shortToman(net), {
                facts: [{ label: "فاکتور فروش", value: shortToman(c.invoices_rial) }, { label: "برگشتی", value: shortToman(c.returns_rial) },
                  { label: `ماه قبل (${MONTHS[months[1].month - 1]})`, value: prev ? shortToman(prevNet) : "…" }, { label: "سرعت فروش نسبت به ماه قبل", value: signed(g) }],
                list: { title: "بیشترین فروش خالص شعب", rows: peekRows(byBranch, (b: any) => b.branch_name, (b: any) => Number(b.net_rial || 0)) }, note: c.rule })} />
            <Stat tone={g === null ? "neutral" : g >= 0 ? "good" : "watch"} label="سرعت فروش نسبت به ماه قبل" value={prev ? signed(g) : <span className="xo-wait">…</span>} unit=""
              hint={prev ? `میانگین روزانه ${shortToman(curDaily)} (${fa(day)} روز) در برابر ${shortToman(prevDaily)} در ${MONTHS[months[1].month - 1]}` : "در حال دریافت"} />
            <Stat tone={pct(c.returns_rial, c.invoices_rial) > 8 ? "watch" : "neutral"} label="سهم برگشتی" value={`${fa(pct(c.returns_rial, c.invoices_rial))}٪`} unit=""
              hint={`${shortToman(c.returns_rial)} تومان برگشتی ثبت‌شده در ماه`} go={() => open("distribution")} />
            <Stat label="فروش هیبریدها" value={shortToman(cur?.totals?.sales_rial)} hint={`${fa((cur?.branches || []).filter((b: any) => Number(b.sales_rial) > 0).length)} هیبرید فعال در ماه`} go={() => open("distribution")} />
          </div>
          <div className="mc-grid">
            <ChartCard title="روند سه ماه اخیر" note="فروش خالص و برگشتی هر ماه (ماه جاری تا امروز)." legend={[{ label: "فروش خالص", color: PALETTE.teal }, { label: "برگشتی", color: PALETTE.amber }]}>
              <MonthBars items={monthSeries} series={[{ label: "فروش خالص", color: PALETTE.teal }, { label: "برگشتی", color: PALETTE.amber }]} />
            </ChartCard>
            <ChartCard title="سهم شعب از فروش خالص ماه" note="۸ شعبه اول؛ بقیه در «سایر».">
              <StackBar segments={[
                ...byBranch.slice(0, 5).map((b: any, i: number) => ({ label: b.branch_name, value: Number(b.net_rial || 0), color: [PALETTE.teal, PALETTE.violet, PALETTE.amber, "#2563eb", "#db2777"][i] })),
                { label: "سایر", value: byBranch.slice(5).reduce((s, b) => s + Number(b.net_rial || 0), 0), color: PALETTE.slate },
              ]} />
              <FlowCompare rows={byBranch.slice(0, 8).map((b: any) => ({ label: b.branch_name, parts: [{ label: "فروش خالص", value: Number(b.net_rial || 0), color: PALETTE.teal }] }))} />
            </ChartCard>
          </div>
        </>}
      </div>
      <div className="xo-side"><ModuleAlarms agents={["sales_manager", "sales_pace"]} title="فروش" onGo={go} /></div>
    </div>
  </article>;
}

// ------------------------------------------------------------------ هیبریدها: توزیع و وصول
function HybridBlock({ month, report, error, open, go }: { month: YM; report: any | null; error: string; open: (v: View) => void; go: (v: string) => void }) {
  const t = report?.totals || {};
  const branches: any[] = (report?.branches || []).filter((b: any) => Number(b.sales_rial || 0) > 0);
  const bySales = [...branches].sort((a, b) => Number(b.sales_rial) - Number(a.sales_rial));
  const distPct = pct(t.distributed_rial, t.sales_rial), collPct = pct(t.collected_rial, t.distributed_rial);
  const peekOf = (value: string, extra: Partial<PeekSpec>): PeekSpec => ({ value, page: "توزیع بار", ...extra });
  return <article className="xo-block" id="xs-hybrids">
    <div className="xo-block-title"><h3>هیبریدها: توزیع و وصول</h3><small>فاکتورهای {ymLabel(month)}</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error && !report?.totals ? <div className="profile-warning">{error}</div> : !report ? <div className="xo-loading">در حال دریافت…</div> : <>
          <div className="xo-stats four">
            <Stat tone={distPct < 70 ? "watch" : "good"} label="توزیع شده" value={`${fa(distPct)}٪`} unit="" hint={`${shortToman(t.distributed_rial)} از ${shortToman(t.sales_rial)}`} go={() => open("distribution")}
              peek={peekOf(`${fa(distPct)}٪`, { list: { title: "کمترین درصد توزیع", rows: [...branches].sort((a, b) => pct(a.distributed_rial, a.sales_rial) - pct(b.distributed_rial, b.sales_rial)).slice(0, 5)
                .map((b) => ({ label: b.branch_name, sub: `${shortToman(b.distributed_rial)} از ${shortToman(b.sales_rial)}`, value: `${fa(pct(b.distributed_rial, b.sales_rial))}٪`, share: pct(b.distributed_rial, b.sales_rial) })) } })} />
            <Stat tone="follow" label="توزیع نشده" value={shortToman(t.undistributed_rial)} hint={`${fa(t.undistributed_count)} فاکتور بدون حواله خروج`} go={() => open("distribution")} goLabel="پیگیری خروج بار"
              peek={peekOf(shortToman(t.undistributed_rial), { list: { title: "بیشترین توزیع‌نشده", rows: peekRows([...branches].sort((a, b) => Number(b.undistributed_rial || 0) - Number(a.undistributed_rial || 0)),
                (b: any) => b.branch_name, (b: any) => Number(b.undistributed_rial || 0), (b: any) => `${fa(b.undistributed_count)} فاکتور`) } })} />
            <Stat tone={collPct < 50 ? "watch" : "good"} label="وصول از توزیع‌شده" value={`${fa(collPct)}٪`} unit="" hint={`${shortToman(t.collected_rial)} وصول شده`} go={() => open("distribution")} />
            <Stat tone="watch" label="مانده وصول ماه" value={shortToman(t.remaining_rial)} hint="فاکتورهای توزیع‌شده و وصول‌نشده" go={() => open("distribution")}
              peek={peekOf(shortToman(t.remaining_rial), { list: { title: "بیشترین مانده وصول", rows: peekRows([...branches].sort((a, b) => Number(b.remaining_rial || 0) - Number(a.remaining_rial || 0)),
                (b: any) => b.branch_name, (b: any) => Number(b.remaining_rial || 0), (b: any) => `وصول ${shortToman(b.collected_rial)}`) } })} />
          </div>
          <div className="mc-grid">
            <ChartCard title="هیبریدها: توزیع‌شده و توزیع‌نشده" legend={[{ label: "توزیع‌شده", color: PALETTE.teal }, { label: "توزیع‌نشده", color: PALETTE.amber }]} note="۸ هیبرید با بیشترین فروش ماه.">
              <FlowCompare rows={bySales.slice(0, 8).map((b) => ({ label: b.branch_name, parts: [
                { label: "توزیع‌شده", value: Number(b.distributed_rial || 0), color: PALETTE.teal },
                { label: "توزیع‌نشده", value: Number(b.undistributed_rial || 0), color: PALETTE.amber },
              ] }))} />
            </ChartCard>
            <ChartCard title="وصول در برابر مانده" note="راست: وصول‌شده؛ چپ: مانده فاکتورهای توزیع‌شده ماه." legend={[{ label: "وصول", color: PALETTE.teal }, { label: "مانده", color: PALETTE.violet }]}>
              <DivergingRows left={{ label: "مانده", color: PALETTE.violet }} right={{ label: "وصول", color: PALETTE.teal }}
                rows={bySales.slice(0, 6).map((b) => ({ label: b.branch_name, left: Number(b.remaining_rial || 0), right: Number(b.collected_rial || 0) }))} />
            </ChartCard>
          </div>
        </>}
      </div>
      <div className="xo-side"><ModuleAlarms agents={["sales_requests", "distribution"]} title="درخواست و توزیع" onGo={go} /></div>
    </div>
  </article>;
}

// ------------------------------------------------------------------ شبکه فروش کارآمد
function NetworkBlock({ data, error, open, go }: { data: any; error: string; open: (v: View) => void; go: (v: string) => void }) {
  const sm = data?.summary || {};
  const cy = faDigits(data?.current_year_label || "سال جاری"), py = faDigits(data?.previous_year_label || "سال قبل");
  const branches: any[] = data?.branches || [];
  const cur = Number(sm.current_year_sales_rial || 0), prev = Number(sm.previous_year_sales_rial || 0);
  const byDebt = [...branches].sort((a, b) => Number(b.debt?.open_account_receivable_rial || 0) - Number(a.debt?.open_account_receivable_rial || 0));
  const bySales = [...branches].sort((a, b) => Number(b.current_year_sales_rial || 0) - Number(a.current_year_sales_rial || 0));
  const name = (b: any) => (b.hybrids || []).join("، ") || b.branch_name;
  const dso = cur > 0 ? Math.round((Number(sm.open_account_receivable_rial || 0) / cur) * 365) : null;
  return <article className="xo-block" id="xs-network">
    <div className="xo-block-title"><h3>شبکه فروش کارآمد</h3><small>هیبرید من‌ها، ویزیتورها و مطالبات · {cy} در برابر {py}</small></div>
    <div className="xo-grid">
      <div className="xo-main">
        {error ? <div className="profile-warning">{error}</div> : !data ? <div className="xo-loading">در حال دریافت شبکه فروش…</div> : <>
          <div className="xo-stats four">
            <Stat label={`فروش خالص ${cy}`} value={shortToman(cur)} hint={`ناخالص ${shortToman(sm.current_year_gross_sales_rial)} · ${py}: ${shortToman(prev)}`} go={() => open("customers")} goLabel="پرونده هیبریدها"
              peek={{ value: shortToman(cur), page: "پرونده مشتری", facts: [{ label: `فروش ${py}`, value: shortToman(prev) }, { label: "هیبرید من", value: fa(sm.hybrid_count) }, { label: "شعبه", value: fa(sm.branch_count) }],
                list: { title: "بیشترین فروش سال", rows: peekRows(bySales, name, (b: any) => Number(b.current_year_sales_rial || 0), (b: any) => b.branch_name) } }} />
            <Stat tone="watch" label="مطالبات مشتریان شعب" value={shortToman(sm.open_account_receivable_rial)} hint={dso !== null ? `حدود ${fa(dso)} روز فروش` : "مانده دفتر کل"} go={() => open("customers")}
              peek={{ value: shortToman(sm.open_account_receivable_rial), page: "پرونده مشتری", facts: [{ label: "دوره وصول تقریبی", value: dso !== null ? `${fa(dso)} روز` : "—" }],
                list: { title: "بیشترین مطالبات", rows: peekRows(byDebt, name, (b: any) => Number(b.debt?.open_account_receivable_rial || 0), (b: any) => `${fa(b.debt?.debtor_customer_count || 0)} مشتری بدهکار`) },
                note: data?.debt_note }} />
            <Stat label="مشتری فعال" value={fa(sm.active_customer_count)} unit="نفر" hint={`${fa(sm.active_customer_current_year_count)} نفر خرید ${cy}`} go={() => open("customers")} />
            <Stat label="ویزیتور فعال" value={fa(sm.active_visitor_count)} unit="نفر" hint={`در ${fa(sm.branch_count)} شعبه`} go={() => open("customers")} />
          </div>
          <div className="mc-grid">
            <ChartCard title={`فروش ${cy} در برابر ${py}`} note="۸ هیبرید با بیشترین فروش امسال." legend={[{ label: py, color: PALETTE.slate }, { label: cy, color: PALETTE.teal }]}>
              <DivergingRows left={{ label: py, color: PALETTE.slate }} right={{ label: cy, color: PALETTE.teal }}
                rows={bySales.slice(0, 8).map((b) => ({ label: name(b), sub: b.branch_name, left: Number(b.previous_year_sales_rial || 0), right: Number(b.current_year_sales_rial || 0) }))} />
            </ChartCard>
            <ChartCard title="بیشترین مطالبات و چک باز" legend={[{ label: "مطالبات", color: PALETTE.amber }, { label: "چک باز", color: PALETTE.violet }]}>
              <FlowCompare rows={byDebt.slice(0, 8).map((b) => ({ label: name(b), parts: [
                { label: "مطالبات", value: Number(b.debt?.open_account_receivable_rial || 0), color: PALETTE.amber },
                { label: "چک باز", value: Number(b.open_cheque_amount_rial || 0), color: PALETTE.violet },
              ] }))} />
            </ChartCard>
          </div>
        </>}
      </div>
      <div className="xo-side"><ModuleAlarms agents={["sales_finance_bridge"]} title="فروش و مالی" onGo={go} /></div>
    </div>
  </article>;
}
