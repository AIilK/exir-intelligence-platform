"use client";
// نمای مدیر — ترکیب «خلاصه مدیریتی مالی» و «خلاصه مدیریتی فروش» در یک صفحه، هم‌شکل همان دو (کارت + پنل جزئیات + نمودار)
// و با انیمیشن: سربرگ زنده، حلقه‌های نبض کسب‌وکار، شاخص‌های شمارنده، دو ستون مالی/فروش، تصمیم‌های امروز (الارم‌ها) و رتبه هیبریدها.
// هر بخش فقط وقتی بارگذاری می‌شود که کاربر به ماژول آن دسترسی دارد (همان قواعد API در backend/app/auth/modules.py).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../auth/auth";
import { ModuleAlarms, useAlarms } from "../alarms/alarms";
import { PeekContext, PeekPanel, type Peek } from "./peek-panel";
import { ChartCard, FlowCompare, MonthBars, NetWeeks, PALETTE, StackBar } from "./mini-charts";
import { Stat, peekRows } from "./executive-overview";
import "./executive-overview.css";
import "./manager-overview.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const FIN = () => `http://${apiHost()}:8000/api/v1/finance`;
const LIQ = () => `http://${apiHost()}:8000/api/v1/liquidity`;
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const shortToman = (rial: number | null | undefined) => {
  const t = Number(rial || 0) / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const faDigits = (v: unknown) => String(v ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const pct = (a: unknown, b: unknown) => (Number(b || 0) ? Math.round((100 * Number(a || 0)) / Number(b)) : 0);
const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
type YM = { year: number; month: number };
function jalaliNow() {
  const p = new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric", month: "numeric", day: "numeric" }).formatToParts(new Date());
  const g = (t: string) => Number(p.find((x) => x.type === t)?.value);
  return { year: g("year"), month: g("month"), day: g("day") };
}
const shift = (m: YM, d: number): YM => { const i = m.year * 12 + m.month - 1 + d; return { year: Math.floor(i / 12), month: (i % 12) + 1 }; };
const monthDays = (m: YM) => (m.month <= 6 ? 31 : m.month <= 11 ? 30 : 29);
const reduceMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

async function getJson(url: string) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}
type Load<T> = { data: T | null; error: string };
/** url = null یعنی کاربر به این داده دسترسی ندارد (اصلاً درخواست نمی‌دهد). */
function useLoad<T = any>(url: string | null, pick: (j: any) => T = (j) => j): Load<T> & { off: boolean } {
  const [s, setS] = useState<Load<T>>({ data: null, error: "" });
  const pickRef = useRef(pick);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    getJson(url).then((j) => alive && setS({ data: pickRef.current(j), error: "" }))
      .catch((e) => alive && setS({ data: null, error: e instanceof Error ? e.message : "خطا" }));
    return () => { alive = false; };
  }, [url]);
  return { ...s, off: !url };
}

/** عدد شمارنده: از صفر تا مقدار در حدود یک ثانیه بالا می‌رود */
function CountUp({ value, format }: { value: number; format: (v: number) => string }) {
  const [shown, setShown] = useState(reduceMotion() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduceMotion()) { setShown(value); return; }
    const start = performance.now(), a = from.current, dur = 1100;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      setShown(a + (value - a) * e);
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    // تب پس‌زمینه requestAnimationFrame را متوقف می‌کند؛ عدد نهایی در هر حال نشان داده شود.
    const done = window.setTimeout(() => { cancelAnimationFrame(raf); setShown(value); from.current = value; }, dur + 150);
    return () => { cancelAnimationFrame(raf); window.clearTimeout(done); };
  }, [value]);
  return <>{format(shown)}</>;
}

/** حلقه درصد با پر شدن انیمیشنی */
function Ring({ value, label, sub, color, onClick }: { value: number | null; label: string; sub?: string; color: string; onClick?: () => void }) {
  const r = 38, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value ?? 0));
  return <button type="button" className="mo-ring" onClick={onClick} disabled={!onClick}>
    <svg viewBox="0 0 100 100" aria-hidden>
      <circle cx="50" cy="50" r={r} className="mo-ring-track" />
      <circle cx="50" cy="50" r={r} className="mo-ring-fill" stroke={color}
        style={{ strokeDasharray: c, strokeDashoffset: value === null ? c : c * (1 - v / 100) }} />
    </svg>
    <b>{value === null ? "…" : <CountUp value={value} format={(x) => `${nf.format(Math.round(x))}٪`} />}</b>
    <span>{label}</span>
    {sub && <small>{sub}</small>}
  </button>;
}

type Tile = { key: string; label: string; domain: "مالی" | "فروش"; value: number | null; format: (v: number) => string; unit?: string;
  hint?: ReactNode; tone?: "good" | "watch" | "follow" | "neutral"; go?: string; locked?: boolean; error?: string };

export default function ManagerOverview({ go }: { go: (view: string) => void }) {
  const { profile, can, hasModule } = useAuth();
  const { alarms, loaded: alarmsLoaded } = useAlarms();
  const [peek, setPeek] = useState<Peek | null>(null);
  const closePeek = useCallback(() => setPeek(null), []);
  const admin = profile.user.is_admin;
  const has = (...m: string[]) => admin || m.some((k) => hasModule(k));

  // ---------------------------------------------------------------- داده (فقط بخش‌های مجاز)
  const now = useMemo(jalaliNow, []);
  const cur: YM = { year: now.year, month: now.month };
  const prev = shift(cur, -1), prev2 = shift(cur, -2);
  const salesOk = has("management", "sales", "distribution");
  const mCur = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${cur.year}&month=${cur.month}` : null);
  const mPrev = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${prev.year}&month=${prev.month}` : null);
  const mPrev2 = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${prev2.year}&month=${prev2.month}` : null);
  const network = useLoad(has("sales", "customers") ? `${FIN()}/sales-network` : null);
  const liq = useLoad(has("management", "liquidity") ? `${LIQ()}/summary?horizon_days=30` : null, (j) => j.data);
  const chequesOk = has("management", "cheques", "collections");
  const rec = useLoad(chequesOk ? `${LIQ()}/received-cheques?horizon_days=30` : null, (j) => j.data);
  const iss = useLoad(chequesOk ? `${LIQ()}/issued-cheques?horizon_days=30` : null, (j) => j.data);
  const pay = useLoad(has("management", "payables") ? `${FIN()}/payables` : null, (j) => j.modules);

  // ---------------------------------------------------------------- محاسبه
  const cs = mCur.data?.company_sales || {}, ps = mPrev.data?.company_sales || {};
  const net = Number(cs.net_rial ?? mCur.data?.totals?.sales_rial ?? 0);
  const prevNet = Number(ps.net_rial ?? mPrev.data?.totals?.sales_rial ?? 0);
  const pace = mCur.data && mPrev.data && prevNet > 0 ? ((net / Math.max(1, now.day)) / (prevNet / monthDays(prev)) - 1) * 100 : null;
  const t = mCur.data?.totals || {};
  const distPct = mCur.data ? pct(t.distributed_rial, t.sales_rial) : null;
  const collPct = mCur.data ? pct(t.collected_rial, t.distributed_rial) : null;
  const scen: any[] = liq.data?.scenarios || [];
  const base = scen.find((s) => s.key === (liq.data?.base_scenario || "reliance")) || scen[0];
  const coverage = base ? Math.round(base.coverage_percent || 0) : null;
  const sm = network.data?.summary || {};
  const openAlarms = alarms.filter((a) => a.my_status === "open" || a.my_status === "seen");
  const hot = openAlarms.filter((a) => a.level === "critical" || a.level === "high");
  const recOverdue = Number(rec.data?.overdue?.definite_rial || 0) + Number(rec.data?.overdue?.other_state_rial || 0);
  const weeks = useMemo(() => {
    const days: any[] = base?.days || [];
    const out: { label: string; net: number; inflow: number; outflow: number }[] = [];
    for (let i = 0; i < days.length; i += 7) {
      const ch = days.slice(i, i + 7);
      out.push({ label: `هفته ${fa(out.length + 1)}`, net: ch.reduce((s, d) => s + Number(d.net_rial || 0), 0),
        inflow: ch.reduce((s, d) => s + Number(d.inflow_rial || 0), 0), outflow: ch.reduce((s, d) => s + Number(d.outflow_rial || 0), 0) });
    }
    return out;
  }, [base]);
  const branches: any[] = useMemo(() => {
    const debt = new Map<string, any>((network.data?.branches || []).map((b: any) => [String(b.branch_name || "").trim(), b]));
    return (mCur.data?.branches || []).filter((b: any) => Number(b.sales_rial || 0) > 0).map((b: any) => {
      const d = debt.get(String(b.branch_name || "").trim());
      return { ...b, debt_rial: Number(d?.debt?.open_account_receivable_rial || 0), dist: pct(b.distributed_rial, b.sales_rial), coll: pct(b.collected_rial, b.distributed_rial) };
    }).sort((a: any, b: any) => Number(b.sales_rial) - Number(a.sales_rial));
  }, [mCur.data, network.data]);
  const topSales = Math.max(1, ...branches.map((b) => Number(b.sales_rial || 0)));

  // ---------------------------------------------------------------- شاخص‌های شمارنده
  const allTiles: Tile[] = [
    { key: "sales", label: "فروش خالص ماه", domain: "فروش", value: mCur.data ? net / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: pace === null ? "در حال مقایسه…" : <span className={pace >= 0 ? "up" : "down"}>{pace >= 0 ? "▲" : "▼"} {nf1.format(Math.abs(pace))}٪ سرعت فروش نسبت به {MONTHS[prev.month - 1]}</span>,
      tone: pace === null ? "neutral" : pace >= 0 ? "good" : "watch", go: "sales", locked: !salesOk, error: mCur.error },
    { key: "coll", label: "وصول فاکتورهای ماه", domain: "فروش", value: mCur.data ? Number(t.collected_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: `مانده ${shortToman(t.remaining_rial)} · ${fa(collPct)}٪ از توزیع‌شده`, tone: "neutral", go: "distribution", locked: !salesOk, error: mCur.error },
    { key: "debt", label: "مطالبات مشتریان شعب", domain: "فروش", value: network.data ? Number(sm.open_account_receivable_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: `${fa(sm.active_customer_count)} مشتری فعال · ${fa(sm.active_visitor_count)} ویزیتور`, tone: "watch", go: "customers", locked: !has("sales", "customers"), error: network.error },
    { key: "recv", label: "چک دریافتی سررسید گذشته", domain: "مالی", value: rec.data ? recOverdue / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: rec.data ? `برگشتی باز ${shortToman(rec.data?.returned_open?.amount_rial)} · ۷ روز آینده ${shortToman(rec.data?.kpis?.next_7_days?.definite_rial)}` : "", tone: "follow",
      go: "receivedCheques", locked: !chequesOk, error: rec.error },
    { key: "iss", label: "چک پرداختی ۳۰ روز آینده", domain: "مالی", value: iss.data ? Number(iss.data?.kpis?.horizon?.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: iss.data ? `${fa(iss.data?.kpis?.horizon?.count)} چک · ۷ روز آینده ${shortToman(iss.data?.kpis?.next_7_days?.amount_rial)}` : "", tone: "neutral",
      go: "issuedCheques", locked: !chequesOk, error: iss.error },
    { key: "pay", label: "بدهی به تأمین‌کنندگان", domain: "مالی", value: pay.data ? (Number(pay.data.trade?.credit_balance_rial || 0) + Number(pay.data.nontrade?.credit_balance_rial || 0)) / 10 : null,
      format: (v) => shortToman(v * 10), unit: "تومان",
      hint: pay.data ? `پیش‌پرداخت باز ${shortToman(Number(pay.data.trade?.debit_balance_rial || 0) + Number(pay.data.nontrade?.debit_balance_rial || 0))}` : "", tone: "neutral",
      go: "payables", locked: !has("management", "payables"), error: pay.error },
  ];
  const tiles = allTiles.filter((x) => !x.locked);

  const hour = new Date().getHours();
  const hello = hour < 12 ? "صبح بخیر" : hour < 17 ? "روز بخیر" : "عصر بخیر";
  const firstName = profile.user.full_name.split(" ")[0];
  const dateLabel = `${faDigits(now.day)} ${MONTHS[now.month - 1]} ${faDigits(now.year)}`;
  const monthSeries = [mPrev2, mPrev, mCur].map((m, i) => ({
    label: MONTHS[[prev2, prev, cur][i].month - 1], values: [Number(m.data?.company_sales?.net_rial || 0), Number(m.data?.company_sales?.returns_rial || 0)],
  }));
  const goCan = (v: string) => (can(v) ? () => go(v) : undefined);

  return <PeekContext.Provider value={setPeek}><section className="xo mo">
    {/* ------------------------------------------------ سربرگ زنده */}
    <header className="mo-hero">
      <span className="mo-orb a" /><span className="mo-orb b" /><span className="mo-orb c" />
      <div className="mo-hero-text">
        <small>{dateLabel} · نمای مدیر</small>
        <h2>{hello}، {firstName} <span className="mo-wave">👋</span></h2>
        <p>
          {mCur.data && <>فروش {MONTHS[cur.month - 1]} تا امروز <b>{shortToman(net)} تومان</b>{pace !== null && <> و سرعتش <b className={pace >= 0 ? "up" : "down"}>{pace >= 0 ? "بیشتر" : "کمتر"}</b> از {MONTHS[prev.month - 1]} است</>}. </>}
          {base && <>پوشش نقدینگی ۳۰ روز آینده <b className={coverage! < 100 ? "down" : "up"}>{fa(coverage)}٪</b>{base.financing_need_rial > 0 && <> و نیاز به تأمین <b className="down">{shortToman(base.financing_need_rial)}</b></>}. </>}
          {alarmsLoaded && (openAlarms.length ? <><b>{fa(openAlarms.length)}</b> الارم باز داری{hot.length ? <>؛ <b className="down">{fa(hot.length)}</b> تا مهم</> : ""}.</> : <>الارم بازی نداری 🌿</>)}
        </p>
      </div>
      <div className="mo-rings">
        {salesOk && <Ring value={distPct} label="توزیع‌شده" sub="فاکتور هیبریدهای ماه" color="#2dd4bf" onClick={goCan("distribution")} />}
        {salesOk && <Ring value={collPct} label="وصول" sub="از توزیع‌شده" color="#a78bfa" onClick={goCan("distribution")} />}
        {has("management", "liquidity") && <Ring value={coverage} label="پوشش نقدینگی" sub="۳۰ روز آینده" color={coverage !== null && coverage < 100 ? "#fb923c" : "#4ade80"} onClick={goCan("liquidity")} />}
      </div>
    </header>

    {/* ------------------------------------------------ شاخص‌های شمارنده */}
    <div className="mo-tiles">
      {tiles.map((k, i) => <button key={k.key} type="button" className={`mo-tile ${k.tone || "neutral"}`} style={{ animationDelay: `${i * 70}ms` }}
        onClick={k.go && can(k.go) ? () => go(k.go!) : undefined}>
        <span className="mo-tile-top"><small>{k.label}</small><em className={k.domain === "مالی" ? "fin" : "sales"}>{k.domain}</em></span>
        <b>{k.value === null ? (k.error ? <span className="mo-err">{k.error}</span> : <span className="mo-shimmer" />) : <CountUp value={k.value} format={k.format} />}</b>
        {k.value !== null && k.unit && <span className="mo-unit">{k.unit}</span>}
        {k.value !== null && k.hint && <span className="mo-hint">{k.hint}</span>}
        <i className="mo-tile-glow" aria-hidden />
      </button>)}
    </div>

    {/* ------------------------------------------------ دو ستون مالی و فروش */}
    <div className="mo-lanes">
      {(chequesOk || has("management", "liquidity", "payables")) && <article className="xo-block mo-lane fin">
        <div className="xo-block-title"><h3><i className="mo-dot fin" />مالی و نقدینگی</h3>
          {can("management") && <button type="button" className="mo-link" onClick={() => go("management")}>خلاصه مالی کامل ←</button>}</div>
        <div className="xo-stats">
          {rec.data && <Stat tone="follow" label="برگشتی باز" value={shortToman(rec.data?.returned_open?.amount_rial)}
            hint={`${fa(rec.data?.returned_open?.count)} چک`} go={goCan("receivedCheques")}
            peek={{ value: shortToman(rec.data?.returned_open?.amount_rial), page: "چک‌های دریافتی",
              list: { title: "بزرگ‌ترین مشتریان ۳۰ روز آینده", rows: peekRows([...(rec.data?.customers || [])].sort((a: any, b: any) => b.definite_rial - a.definite_rial),
                (c: any) => c.customer_name, (c: any) => Number(c.definite_rial || 0), (c: any) => `${fa(c.count)} چک`) } }} />}
          {iss.data && <Stat tone="watch" label="پرداختی سررسیدگذشته" value={shortToman(iss.data?.overdue?.amount_rial)}
            hint={`${fa(iss.data?.overdue?.count)} چک · در خروجی امروز`} go={goCan("issuedCheques")}
            peek={{ value: shortToman(iss.data?.overdue?.amount_rial), page: "چک‌های پرداختی",
              list: { title: "بزرگ‌ترین دریافت‌کنندگان", rows: peekRows(iss.data?.top_payees || [], (p: any) => p.payee_name, (p: any) => Number(p.amount_rial || 0), (p: any) => `${fa(p.count)} چک`) } }} />}
          {base && <Stat tone={base.financing_need_rial > 0 ? "follow" : "good"} label={base.financing_need_rial > 0 ? "نیاز به تأمین" : "بدون کسری"}
            value={base.financing_need_rial > 0 ? shortToman(base.financing_need_rial) : "—"}
            hint={base.first_shortage?.date_jalali ? `اولین کسری ${faDigits(base.first_shortage.date_jalali)}` : "در ۳۰ روز آینده"} go={goCan("liquidity")} />}
        </div>
        <div className="mc-grid">
          {base && <ChartCard title="خالص هر هفته (۳۰ روز آینده)" note="بالای خط: ورودی بیشتر؛ پایین: خروجی بیشتر.">
            <NetWeeks pos={PALETTE.teal} neg={PALETTE.amber} weeks={weeks} />
          </ChartCard>}
          {base && <ChartCard title="ورودی در برابر خروجی" legend={[{ label: "چک دریافتی", color: PALETTE.teal }, { label: "نقد و حواله", color: PALETTE.violet }, { label: "چک پرداختی", color: PALETTE.amber }, { label: "حقوق", color: "#2563eb" }]}>
            <FlowCompare rows={[
              { label: "ورودی", parts: [{ label: "چک دریافتی", value: base.totals?.received_cheques_rial || 0, color: PALETTE.teal }, { label: "نقد و حواله", value: base.totals?.estimated_inflow_rial || 0, color: PALETTE.violet }] },
              { label: "خروجی", parts: [{ label: "چک پرداختی", value: base.totals?.issued_cheques_rial || 0, color: PALETTE.amber }, { label: "حقوق", value: base.totals?.payroll_rial || 0, color: "#2563eb" }, { label: "هزینه‌ها", value: base.totals?.estimated_outflow_rial || 0, color: "#db2777" }] },
            ]} />
          </ChartCard>}
          {!base && liq.error && <div className="profile-warning">{liq.error}</div>}
          {!base && !liq.error && !liq.off && <div className="xo-loading">در حال ساخت پیش‌بینی نقدینگی…</div>}
        </div>
      </article>}

      {salesOk && <article className="xo-block mo-lane sales">
        <div className="xo-block-title"><h3><i className="mo-dot sales" />فروش و توزیع</h3>
          {can("sales") && <button type="button" className="mo-link" onClick={() => go("sales")}>خلاصه فروش کامل ←</button>}</div>
        <div className="xo-stats">
          {mCur.data && <Stat label="فروش هیبریدها" value={shortToman(t.sales_rial)} hint={`${fa(branches.length)} هیبرید فعال در ${MONTHS[cur.month - 1]}`} go={goCan("distribution")}
            peek={{ value: shortToman(t.sales_rial), page: "توزیع بار", list: { title: "بیشترین فروش ماه", rows: peekRows(branches, (b: any) => b.branch_name, (b: any) => Number(b.sales_rial || 0), (b: any) => `توزیع ${fa(b.dist)}٪`) } }} />}
          {mCur.data && <Stat tone="follow" label="توزیع نشده" value={shortToman(t.undistributed_rial)} hint={`${fa(t.undistributed_count)} فاکتور بدون حواله خروج`} go={goCan("distribution")}
            peek={{ value: shortToman(t.undistributed_rial), page: "توزیع بار", list: { title: "بیشترین توزیع‌نشده", rows: peekRows([...branches].sort((a, b) => b.undistributed_rial - a.undistributed_rial), (b: any) => b.branch_name, (b: any) => Number(b.undistributed_rial || 0)) } }} />}
          {mCur.data && <Stat tone={pct(cs.returns_rial, cs.invoices_rial) > 8 ? "watch" : "neutral"} label="سهم برگشتی" value={`${fa(pct(cs.returns_rial, cs.invoices_rial))}٪`} unit=""
            hint={`${shortToman(cs.returns_rial)} تومان برگشتی ماه`} go={goCan("distribution")} />}
        </div>
        <div className="mc-grid">
          {mCur.data ? <>
            <ChartCard title="روند سه ماه اخیر" note="فروش خالص و برگشتی؛ ماه جاری تا امروز." legend={[{ label: "فروش خالص", color: PALETTE.teal }, { label: "برگشتی", color: PALETTE.amber }]}>
              <MonthBars items={monthSeries} series={[{ label: "فروش خالص", color: PALETTE.teal }, { label: "برگشتی", color: PALETTE.amber }]} />
            </ChartCard>
            <ChartCard title={`فاکتورهای ${MONTHS[cur.month - 1]}`} legend={[{ label: "توزیع‌شده", color: PALETTE.teal }, { label: "توزیع‌نشده", color: PALETTE.amber }]}>
              <StackBar segments={[{ label: "توزیع‌شده", value: Number(t.distributed_rial || 0), color: PALETTE.teal }, { label: "توزیع‌نشده", value: Number(t.undistributed_rial || 0), color: PALETTE.amber }]} />
              <StackBar segments={[{ label: "وصول‌شده", value: Number(t.collected_rial || 0), color: PALETTE.violet }, { label: "مانده", value: Number(t.remaining_rial || 0), color: PALETTE.slate }]} />
            </ChartCard>
          </> : mCur.error ? <div className="profile-warning">{mCur.error}</div> : <div className="xo-loading">در حال ساخت گزارش فروش ماه…</div>}
        </div>
      </article>}
    </div>

    {/* ------------------------------------------------ تصمیم‌های امروز + رتبه هیبریدها */}
    <div className="mo-bottom">
      <article className="xo-block mo-decide">
        <div className="xo-block-title"><h3>⚡ نیازمند تصمیم امروز</h3><small>الارم‌های باز همه ماژول‌های شما</small></div>
        <ModuleAlarms title="امروز" onGo={go} />
      </article>
      {salesOk && <article className="xo-block mo-rank">
        <div className="xo-block-title"><h3>🏆 رتبه هیبریدها در {MONTHS[cur.month - 1]}</h3><small>فروش، توزیع، وصول و مطالبات</small></div>
        {!mCur.data ? <div className="xo-loading">در حال دریافت…</div> : <ol className="mo-rank-list">
          {branches.slice(0, 10).map((b, i) => <li key={b.branch_name} style={{ animationDelay: `${i * 60}ms` }}>
            <span className={`mo-medal m${i}`}>{i < 3 ? ["🥇", "🥈", "🥉"][i] : fa(i + 1)}</span>
            <div className="mo-rank-body">
              <div className="mo-rank-head"><b>{b.branch_name}</b><span>{shortToman(b.sales_rial)}</span></div>
              <span className="mo-rank-bar"><i style={{ width: `${(100 * Number(b.sales_rial)) / topSales}%` }} /></span>
              <small>توزیع <b className={b.dist < 70 ? "down" : "up"}>{fa(b.dist)}٪</b> · وصول <b>{fa(b.coll)}٪</b>{b.debt_rial ? <> · مطالبات {shortToman(b.debt_rial)}</> : null}</small>
            </div>
          </li>)}
        </ol>}
      </article>}
    </div>
    <PeekPanel peek={peek} onClose={closePeek} />
  </section></PeekContext.Provider>;
}
