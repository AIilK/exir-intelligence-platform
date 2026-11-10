"use client";
// نمای مدیر — ترکیب «خلاصه مدیریتی مالی» و «خلاصه مدیریتی فروش» در یک صفحه، هم‌شکل همان دو (کارت + پنل جزئیات + نمودار)
// و با انیمیشن: سربرگ زنده، حلقه‌های نبض کسب‌وکار، شاخص‌های شمارنده، دو ستون مالی/فروش، تصمیم‌های امروز (الارم‌ها) و هیبریدها از کم‌رونق‌تر به پررونق‌تر.
// هر بخش فقط وقتی بارگذاری می‌شود که کاربر به ماژول آن دسترسی دارد (همان قواعد API در backend/app/auth/modules.py).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode, RefObject } from "react";
import { useAuth } from "../auth/auth";
import { ModuleAlarms, useAlarms } from "../alarms/alarms";
import { PeekContext, PeekPanel, type Peek } from "./peek-panel";
import { ChartCard, FlowCompare, MonthBars, NetWeeks, PALETTE, StackBar } from "./mini-charts";
import { Stat, peekRows } from "./executive-overview";
import "./executive-overview.css";
import "./manager-overview.css";

const FIN = () => `/api/v1/finance`;
const LIQ = () => `/api/v1/liquidity`;
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
    // خطای موقت (بک‌اند در حال راه‌اندازی، ۵۰۲ Proxy، قطع کوتاه) تا ۳ بار با فاصله دوباره امتحان می‌شود
    let alive = true, timer = 0;
    const get = (left: number) => getJson(url).then((j) => alive && setS({ data: pickRef.current(j), error: "" }))
      .catch((e) => {
        if (!alive) return;
        if (left > 0) timer = window.setTimeout(() => get(left - 1), 4000);
        else setS({ data: null, error: e instanceof Error ? e.message : "خطا" });
      });
    get(3);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [url]);
  return { ...s, off: !url };
}

/** «۵۲٫۷ میلیارد» ← عدد درشت و واحد کوچک کنارش */
const withUnit = (text: string): ReactNode => {
  const i = text.lastIndexOf(" ");
  return i > 0 ? <>{text.slice(0, i)} <small className="mo-u">{text.slice(i + 1)}</small></> : text;
};

/** عدد شمارنده: از صفر تا مقدار در حدود یک ثانیه بالا می‌رود؛ run = false یعنی هنوز نوبتش نرسیده (صفر می‌ماند) */
function CountUp({ value, format, run = true }: { value: number; format: (v: number) => string; run?: boolean }) {
  const [shown, setShown] = useState(reduceMotion() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reduceMotion()) { setShown(value); return; }
    if (!run) return;
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
  }, [value, run]);
  return <>{withUnit(format(shown))}</>;
}

/** یک بار true می‌شود وقتی عنصر به صفحه رسید (برای انیمیشن ورود هر بخش) */
function useInView<T extends HTMLElement>(): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (reduceMotion() || typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.12 });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen];
}

/** بخشی که هنگام رسیدن به آن از پایین بالا می‌آید */
function Reveal({ id, className = "", children, style }: { id?: string; className?: string; children: ReactNode; style?: CSSProperties }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return <div ref={ref} id={id} style={style} className={`mo-reveal ${seen ? "in" : ""} ${className}`}>{children}</div>;
}

/** رفتن نرم به یک بخش و درخشش کوتاه آن */
function scrollToSection(id: string) {
  const el = typeof document !== "undefined" ? document.getElementById(id) : null;
  if (!el) return;
  // اسکرول دستی فریم‌به‌فریم: scrollIntoView نرم با هر scrollIntoView دیگری در صفحه (چت، الارم) قطع می‌شود
  const from = window.scrollY, to = Math.max(0, from + el.getBoundingClientRect().top - 18);
  const dur = reduceMotion() ? 0 : Math.min(1200, 450 + Math.abs(to - from) / 3), t0 = performance.now();
  const step = (t: number) => {
    const k = dur ? Math.min(1, (t - t0) / dur) : 1, e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
    window.scrollTo({ top: from + (to - from) * e, behavior: "instant" as ScrollBehavior });
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  // تب پس‌زمینه requestAnimationFrame را متوقف می‌کند؛ در هر حال به مقصد برسد
  window.setTimeout(() => { if (Math.abs(window.scrollY - to) > 4) window.scrollTo({ top: to, behavior: "instant" as ScrollBehavior }); }, dur + 200);
  el.classList.remove("mo-flash");
  void el.offsetWidth;
  el.classList.add("mo-flash");
  window.setTimeout(() => el.classList.remove("mo-flash"), 2200);
}

/** P&L لایو یک کانال؛ تا ساخته شود هر ۶ ثانیه دوباره می‌پرسد */
function usePnl(channel: string, on: boolean) {
  const [s, setS] = useState<{ data: any; error: string }>({ data: null, error: "" });
  useEffect(() => {
    if (!on) return;
    let alive = true, timer = 0;
    const get = () => getJson(`${FIN()}/pnl/${channel}?source=live`).then((j) => {
      if (!alive) return;
      if (j.status === "ready") setS({ data: j, error: "" });
      else if (j.status === "error") setS({ data: null, error: j.message || "خطا" });
      else timer = window.setTimeout(get, 6000);
    }).catch((e) => alive && setS({ data: null, error: e instanceof Error ? e.message : "خطا" }));
    get();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [channel, on]);
  return s;
}
const pnlP0 = (rep: any, canon: string) => {
  const r = rep?.rows?.find((x: any) => x.canon === canon);
  return r ? Number(r.periods?.[rep.periods?.[0]?.key]?.value ?? 0) : null;
};

const SEV: Record<string, { label: string; cls: string }> = {
  critical: { label: "اولویت اول", cls: "crit" }, high: { label: "قابل پیگیری", cls: "high" }, watch: { label: "زیر نظر", cls: "watch" },
};

/** نمودار ستونی کوچک یک روند (مبلغ به ریال، یا روز) — ستون‌ها وقتی کارت دیده شد رشد می‌کنند */
function TrendBars({ series, unit, run }: { series: { label: string; value: number }[]; unit?: string; run: boolean }) {
  const max = Math.max(1, ...series.map((s) => s.value));
  const fmt = (v: number) => (unit ? `${nf1.format(v)} ${unit}` : shortToman(v));
  return <div className="mo-tbars" role="img" aria-label={series.map((s) => `${s.label}: ${fmt(s.value)}`).join("، ")}>
    {series.map((s, i) => <div key={`${s.label}-${i}`} className="mo-tbar">
      <small>{fmt(s.value)}</small>
      <span><i style={{ height: run ? `${Math.max(3, (100 * s.value) / max)}%` : 0, transitionDelay: `${i * 80}ms` }} /></span>
      <em>{s.label}</em>
    </div>)}
  </div>;
}

function ProcessCard({ p, i, onGo }: { p: any; i: number; onGo?: () => void }) {
  const [ref, seen] = useInView<HTMLElement>();
  const sev = SEV[p.severity] || SEV.watch;
  const facts = [
    p.amount_rial ? `${shortToman(p.amount_rial)} تومان` : null,
    p.oldest_days ? `قدیمی‌ترین ${fa(p.oldest_days)} روز` : null,
  ].filter(Boolean);
  return <article ref={ref} className={`mo-proc ${sev.cls} ${seen ? "in" : ""}`} style={{ transitionDelay: `${(i % 3) * 90}ms` }}>
    <header><span className="mo-sev">{sev.label}</span><em>{p.system} · {p.domain}</em></header>
    <h4>{p.title}</h4>
    <div className="mo-proc-stat">
      <b><CountUp run={seen} value={Number(p.stat?.value || 0)} format={(v) => (Number.isInteger(p.stat?.value) ? fa(Math.round(v)) : nf1.format(v))} />{p.stat?.unit}</b>
      <span>{p.stat?.label}</span>
    </div>
    <p className="mo-proc-head">{faDigits(p.headline)}{facts.length ? <> · {facts.join(" · ")}</> : null}</p>
    {p.series?.length > 0 && <>
      <small className="mo-proc-cap">{p.series_label}</small>
      <TrendBars series={p.series} unit={p.series_unit} run={seen} />
    </>}
    <dl>
      <dt>آنچه داده نشان می‌دهد</dt><dd>{faDigits(p.evidence)}</dd>
      <dt>چرا مهم است</dt><dd>{p.impact}</dd>
      <dt>پیشنهاد</dt><dd>{p.fix}</dd>
    </dl>
    {p.top?.length > 0 && <details className="mo-proc-top">
      <summary>جزئیات بیشتر</summary>
      <ol>{p.top.map((t: any) => <li key={t.name}><b>{t.name}</b><span>{t.value ? shortToman(t.value) : ""}</span><small>{faDigits(t.sub)}</small></li>)}</ol>
    </details>}
    {onGo && <button type="button" className="mo-link" onClick={onGo}>رفتن به صفحه ←</button>}
  </article>;
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

/** یک گره درخت ریز شاخص: مبلغ به ریال؛ children = جزء بعدی؛ go = صفحه مرتبط (view مالی یا مسیر یکپارچه) */
type DNode = { key: string; label: string; value: number | null; note?: string; go?: string; count?: number; children?: DNode[] };

/** پنل ریز شاخص: کل ← اجزا ← جزئیات (هر سطح با انیمیشن باز می‌شود) و در هر سطح رفتن به صفحه مرتبط */
function DrillPanel({ root, path, setPath, go }: { root: DNode; path: string[]; setPath: (p: string[] | null) => void; go: (v: string) => void }) {
  const trail: DNode[] = [root];
  for (const k of path.slice(1)) {
    const next = trail[trail.length - 1].children?.find((c) => c.key === k);
    if (!next) break;
    trail.push(next);
  }
  const node = trail[trail.length - 1];
  const kids = (node.children || []).filter((c) => c.value !== 0);
  const max = Math.max(1, ...kids.map((c) => Math.abs(Number(c.value || 0))));
  const total = kids.reduce((x, c) => x + Math.max(0, Number(c.value || 0)), 0);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setPath(path.length > 1 ? path.slice(0, -1) : null); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [path, setPath]);
  return <section className="mo-drill" aria-label={`ریز ${root.label}`}>
    <header className="mo-drill-head">
      <nav className="mo-drill-crumbs" aria-label="مسیر">
        {trail.map((n, i) => <span key={n.key}>{i > 0 && <i aria-hidden>‹</i>}
          <button type="button" disabled={i === trail.length - 1} onClick={() => setPath(path.slice(0, i + 1))}>{n.label}</button></span>)}
      </nav>
      <button type="button" className="mo-drill-x" onClick={() => setPath(null)} aria-label="بستن">✕</button>
    </header>
    <div className="mo-drill-body" key={path.join("/")}>
      <div className="mo-drill-total">
        <b>{node.value == null ? (node.count != null ? `${fa(node.count)} مورد` : "…") : <CountUp value={node.value / 10} format={(v) => shortToman(v * 10)} />}</b>
        {node.value != null && <small>تومان</small>}
        {node.note && <em>{node.note}</em>}
        {node.go && <button type="button" className="mo-drill-go" onClick={() => go(node.go!)}>رفتن به صفحه ←</button>}
      </div>
      {kids.length === 0 ? <p className="mo-drill-empty">{node.go ? "ریز بیشتری برای این بخش نیست؛ جزئیات کامل در صفحه مربوط است." : "داده‌ای برای نمایش نیست."}</p>
        : <ol className="mo-drill-list">
          {kids.map((c, i) => {
            const deeper = !!c.children?.some((x) => x.value);
            const w = c.value == null ? 0 : (100 * Math.abs(Number(c.value))) / max;
            return <li key={c.key} style={{ "--i": i, "--w": `${w}%` } as CSSProperties}>
              <button type="button" onClick={() => (deeper ? setPath([...path, c.key]) : c.go && go(c.go))} disabled={!deeper && !c.go}>
                <span className="mo-drill-label">{c.label}{c.note && <small>{c.note}</small>}</span>
                <span className="mo-drill-bar"><i /></span>
                <span className="mo-drill-val">{c.value == null ? "…" : withUnit(shortToman(c.value))}
                  {total > 0 && c.value != null && c.value > 0 && <small>{fa(Math.round((100 * c.value) / total))}٪</small>}</span>
                <span className="mo-drill-arrow" aria-hidden>{deeper ? "›" : c.go ? "↗" : ""}</span>
              </button>
            </li>;
          })}
        </ol>}
    </div>
  </section>;
}

type Tile = { key: string; label: string; domain: "مالی" | "فروش" | "روند"; value: number | null; format: (v: number) => string; unit?: string;
  hint?: ReactNode; tone?: "good" | "watch" | "follow" | "neutral"; target: string; locked?: boolean; error?: string };

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
  const mCur = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${cur.year}&month=${cur.month}&view=summary` : null);
  const mPrev = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${prev.year}&month=${prev.month}&view=summary` : null);
  const mPrev2 = useLoad(salesOk ? `${FIN()}/distribution/monthly?year=${prev2.year}&month=${prev2.month}&view=summary` : null);
  const network = useLoad(has("sales", "customers") ? `${FIN()}/sales-network` : null);
  const liq = useLoad(has("management", "liquidity") ? `${LIQ()}/summary?horizon_days=30` : null, (j) => j.data);
  const chequesOk = has("management", "cheques", "collections");
  const rec = useLoad(chequesOk ? `${LIQ()}/received-cheques?horizon_days=30` : null, (j) => j.data);
  const iss = useLoad(chequesOk ? `${LIQ()}/issued-cheques?horizon_days=30` : null, (j) => j.data);
  const pay = useLoad(has("management", "payables") ? `${FIN()}/payables` : null, (j) => j.modules);
  // سهم راهکاران (فروش نمایندگان B2B ماه و مطالبات) و وصول نقد و حواله هر دو سیستم، تا هر شاخص جمع راهکاران و کارآمد باشد
  const comb = useLoad(salesOk ? `${FIN()}/manager-combined?year=${cur.year}&month=${cur.month}` : null);
  const inflAll = useLoad(salesOk ? `${LIQ()}/inflows?base_days=180&channel=all` : null, (j) => j.data);
  const pnlOk = has("pnl");
  const pnlB2b = usePnl("b2b", pnlOk), pnlExp = usePnl("export", pnlOk), pnlHyb = usePnl("hybrid", pnlOk);
  const slowOk = has("management");
  const [slow, setSlow] = useState<{ data: any; error: string }>({ data: null, error: "" });
  useEffect(() => {
    if (!slowOk) return;
    let alive = true, timer = 0;
    const get = () => getJson(`${FIN()}/process-health`).then((j) => {
      if (!alive) return;
      if (j.status === "ready") setSlow({ data: j, error: "" });
      else if (j.status === "error") setSlow({ data: null, error: j.message || "خطا" });
      else timer = window.setTimeout(get, 4000);
    }).catch((e) => alive && setSlow({ data: null, error: e instanceof Error ? e.message : "خطا" }));
    get();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [slowOk]);

  // ---------------------------------------------------------------- محاسبه
  const cs = mCur.data?.company_sales || {}, ps = mPrev.data?.company_sales || {};
  const net = Number(cs.net_rial ?? mCur.data?.totals?.sales_rial ?? 0);
  const prevNet = Number(ps.net_rial ?? mPrev.data?.totals?.sales_rial ?? 0);
  const rkNet = comb.data?.sales?.cur?.net_rial ?? null, rkPrevNet = comb.data?.sales?.prev?.net_rial ?? null;
  const expCur = comb.data?.export?.cur, expNet = expCur?.net_rial ?? null, expPrevNet = comb.data?.export?.prev?.net_rial ?? null;
  // فروش خالص ماه = کارآمد (همه شعب) + نمایندگان B2B راهکاران + صادرات (معادل ریالی با نرخ اسناد)
  const allNet = net + Number(rkNet || 0) + Number(expNet || 0), allPrevNet = prevNet + Number(rkPrevNet || 0) + Number(expPrevNet || 0);
  const pace = mCur.data && mPrev.data && comb.data && allPrevNet > 0 ? ((allNet / Math.max(1, now.day)) / (allPrevNet / monthDays(prev)) - 1) * 100 : null;
  // فروش ناخالص ماه (پیش از تخفیف‌ها) = کارآمد + B2B راهکاران + صادرات (صادرات تخفیف جدا ندارد: همان خالص)؛ درخواست باز = فقط کارآمد
  const kmCur = comb.data?.karamad?.cur || {};
  const kmGross = kmCur.gross_rial ?? null, rkGross = comb.data?.sales?.cur?.gross_rial ?? null;
  const allGross = kmGross == null ? null : Number(kmGross) + Number(rkGross || 0) + Number(expNet || 0);
  const openReq = kmCur.open_req_rial ?? null;
  const curKey = `${cur.year}/${String(cur.month).padStart(2, "0")}`;
  const rkColl = (inflAll.data?.monthly_trend || []).find((m: any) => m.month === curKey)?.values?.b2b ?? null;
  const rkDebt = comb.data?.receivables?.open_receivable_rial ?? null;
  const recBySys = (s2: string) => (rec.data?.overdue?.by_system || []).find((x: any) => x.system === s2)?.definite_rial ?? null;
  const issBySys = (s2: string) => (iss.data?.horizon_by_system || []).find((x: any) => x.system === s2)?.amount_rial ?? null;
  /** «راهکاران X · کارآمد Y» زیر هر شاخص ترکیبی */
  const split = (rk: number | null, km: number | null) => <>راهکاران <b>{rk == null ? "…" : shortToman(rk)}</b> · کارآمد <b>{km == null ? "…" : shortToman(km)}</b></>;
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
  // هیبریدها از کم‌رونق‌تر به پررونق‌تر: سرعت روزانه فروش ماه جاری در برابر میانگین روزانه دو ماه قبل (سه ماه اخیر)
  const hybridTrend: any[] = useMemo(() => {
    if (!mCur.data || !mPrev.data || !mPrev2.data) return [];
    const sales = (m: any) => new Map<string, number>((m?.branches || []).map((b: any) => [String(b.branch_name || "").trim(), Number(b.sales_rial || 0)]));
    const p1 = sales(mPrev.data), p2 = sales(mPrev2.data);
    const cur = new Map<string, any>(branches.map((b) => [String(b.branch_name || "").trim(), b]));
    const names = new Set([...cur.keys(), ...p1.keys(), ...p2.keys()]);
    const baseDays = monthDays(prev) + monthDays(prev2);
    return [...names].map((name) => {
      const b = cur.get(name) || { branch_name: name, sales_rial: 0, dist: 0, coll: 0, debt_rial: 0 };
      const base = ((p1.get(name) || 0) + (p2.get(name) || 0)) / baseDays;
      const rate = Number(b.sales_rial || 0) / Math.max(1, now.day);
      return { ...b, base_rate: base, trend: base > 0 ? (rate / base - 1) * 100 : null };
    }).filter((b) => b.trend !== null && b.base_rate * baseDays > 1e9).sort((a, b) => a.trend - b.trend);
  }, [mCur.data, mPrev.data, mPrev2.data, branches, now.day]);
  const maxTrend = Math.max(1, ...hybridTrend.map((b) => Math.abs(b.trend)));

  const pnlChannels = [{ key: "b2b", label: "B2B (راهکاران)", rep: pnlB2b.data?.report, err: pnlB2b.error },
    { key: "hybrid", label: "هیبرید (کارآمد)", rep: pnlHyb.data?.report, err: pnlHyb.error },
    { key: "export", label: "صادرات", rep: pnlExp.data?.report, err: pnlExp.error }];
  const sumP = (canon: string) => pnlChannels.reduce((x, c) => x + (pnlP0(c.rep, canon) || 0), 0);
  const pnlNet = pnlChannels.every((c) => c.rep) ? sumP("net") : 0;
  const pnlGp = sumP("gp"), pnlGpStd = sumP("gp_std");
  const pnlPeriod = pnlB2b.data?.period?.label || pnlHyb.data?.period?.label || "";
  const slowItems: any[] = slow.data?.items || [];

  // ---------------------------------------------------------------- شاخص‌های شمارنده
  const allTiles: Tile[] = [
    { key: "sales", label: "فروش خالص ماه (همه کانال‌ها)", domain: "فروش", value: mCur.data && comb.data ? allNet / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: <>کارآمد <b>{shortToman(net)}</b> · B2B <b>{rkNet == null ? "…" : shortToman(rkNet)}</b> · صادرات <b>{expNet == null ? "…" : shortToman(expNet)}</b><br />{pace === null ? "در حال مقایسه…" : <span className={pace >= 0 ? "up" : "down"}>{pace >= 0 ? "▲" : "▼"} {nf1.format(Math.abs(pace))}٪ سرعت فروش نسبت به {MONTHS[prev.month - 1]}</span>}</>,
      tone: pace === null ? "neutral" : pace >= 0 ? "good" : "watch", target: "mo-sales", locked: !salesOk, error: mCur.error || comb.error },
    { key: "gross", label: "فروش ناخالص ماه (همه کانال‌ها)", domain: "فروش", value: allGross == null ? null : allGross / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: <>کارآمد <b>{shortToman(kmGross)}</b> · B2B <b>{rkGross == null ? "…" : shortToman(rkGross)}</b> · صادرات <b>{expNet == null ? "…" : shortToman(expNet)}</b><br />{allGross ? <>تخفیف و برگشت تا خالص: <b>{fa(pct(allGross - allNet, allGross))}٪</b></> : "پیش از تخفیف‌ها"}</>,
      tone: "neutral", target: "mo-sales", locked: !salesOk, error: comb.error },
    { key: "openreq", label: "درخواست باز (فاکتورنشده) ماه — کارآمد", domain: "فروش", value: openReq == null ? null : Number(openReq) / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: openReq == null ? "" : <>{fa(kmCur.open_req_docs)} سند باز از {fa(kmCur.req_docs)} درخواست ماه ({shortToman(kmCur.req_rial)})<br />نرخ تبدیل درخواست به فاکتور <b>{fa(Math.round(Number(kmCur.req_conv || 0) * 100))}٪</b></>,
      tone: "watch", target: "mo-sales", locked: !salesOk, error: comb.error },
    { key: "coll", label: "وصول ماه (راهکاران + کارآمد)", domain: "فروش", value: mCur.data && inflAll.data ? (Number(t.collected_rial || 0) + Number(rkColl || 0)) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: <>{split(rkColl, Number(t.collected_rial || 0))}<br />راهکاران: نقد و حواله ماه · کارآمد: وصول فاکتورهای ماه ({fa(collPct)}٪ توزیع‌شده)</>, tone: "neutral", target: "mo-sales", locked: !salesOk, error: mCur.error || inflAll.error },
    { key: "debt", label: "مطالبات مشتریان (راهکاران + کارآمد)", domain: "فروش", value: network.data && comb.data ? (Number(sm.open_account_receivable_rial || 0) + Number(rkDebt || 0)) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: <>{split(rkDebt, Number(sm.open_account_receivable_rial || 0))}<br />{fa(comb.data?.receivables?.debtor_count)} مشتری بدهکار راهکاران · {fa(sm.active_customer_count)} مشتری فعال شعب</>, tone: "watch", target: "mo-sales", locked: !has("sales", "customers"), error: network.error || comb.error },
    { key: "recv", label: "چک دریافتی سررسید گذشته (راهکاران + کارآمد)", domain: "مالی", value: rec.data ? recOverdue / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: rec.data ? <>{split(recBySys("rahkaran"), recBySys("karamad"))}{Number(rec.data?.overdue?.other_state_rial || 0) > 0 && <> · وضعیت نامشخص <b>{shortToman(rec.data?.overdue?.other_state_rial)}</b></>}<br />برگشتی باز {shortToman(rec.data?.returned_open?.amount_rial)} · ۷ روز آینده {shortToman(rec.data?.kpis?.next_7_days?.definite_rial)}</> : "", tone: "follow",
      target: "mo-fin", locked: !chequesOk, error: rec.error },
    { key: "iss", label: "چک پرداختی ۳۰ روز آینده (راهکاران + کارآمد)", domain: "مالی", value: iss.data ? Number(iss.data?.kpis?.horizon?.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      hint: iss.data ? <>{split(issBySys("rahkaran"), issBySys("karamad"))}<br />{fa(iss.data?.kpis?.horizon?.count)} چک · ۷ روز آینده {shortToman(iss.data?.kpis?.next_7_days?.amount_rial)}</> : "", tone: "neutral",
      target: "mo-fin", locked: !chequesOk, error: iss.error },
    { key: "pay", label: "بدهی به تأمین‌کنندگان (راهکاران)", domain: "مالی", value: pay.data ? (Number(pay.data.trade?.credit_balance_rial || 0) + Number(pay.data.nontrade?.credit_balance_rial || 0)) / 10 : null,
      format: (v) => shortToman(v * 10), unit: "تومان",
      hint: pay.data ? `پیش‌پرداخت باز ${shortToman(Number(pay.data.trade?.debit_balance_rial || 0) + Number(pay.data.nontrade?.debit_balance_rial || 0))}` : "", tone: "neutral",
      target: "mo-fin", locked: !has("management", "payables"), error: pay.error },
    { key: "gp", label: "سود ناخالص فصل (سه کانال)", domain: "مالی", target: "mo-pnl", locked: !pnlOk, error: pnlB2b.error,
      value: pnlChannels.every((c) => c.rep) ? pnlChannels.reduce((x, c) => x + (pnlP0(c.rep, "gp") || 0), 0) * 1e5 : null,
      format: (v) => shortToman(v * 10), unit: "تومان",
      hint: pnlNet ? <>{split(((pnlP0(pnlB2b.data?.report, "gp") || 0) + (pnlP0(pnlExp.data?.report, "gp") || 0)) * 1e6, (pnlP0(pnlHyb.data?.report, "gp") || 0) * 1e6)}<br />حاشیه <b>{fa(pct(pnlGp, pnlNet))}٪</b> · با بهای استاندارد <b className="up">{fa(pct(pnlGpStd, pnlNet))}٪</b></> : "", tone: "good" },
    { key: "slow", label: "فرصت‌های بهبود روندها", domain: "روند", target: "mo-slow", locked: !slowOk, error: slow.error,
      value: slow.data ? slowItems.filter((x: any) => x.severity === "critical").length : null, format: (v) => fa(Math.round(v)), unit: "مورد با اولویت اول",
      hint: slow.data ? `${fa(slowItems.length)} روند در سه ماه اخیر، از داده SQL` : "", tone: "follow" },
  ];
  const tiles = allTiles.filter((x) => !x.locked);

  // ---------------------------------------------------------------- ریز هر شاخص: کل ← اجزا (ماژول‌ها) ← جزئیات ← صفحه مربوط
  const isHyb = (n: unknown) => String(n || "").includes("هیبرید");
  const rows = (list: any[], label: (x: any) => string, value: (x: any) => number, go?: string, note?: (x: any) => string): DNode[] =>
    (list || []).map((x, i) => ({ key: `${i}:${label(x)}`, label: label(x) || "—", value: Number(value(x) || 0), go, note: note?.(x) }))
      .filter((x) => x.value).sort((a, b) => b.value - a.value).slice(0, 12);
  const byBranch: any[] = cs.by_branch || [];
  const hybBranches = byBranch.filter((b) => isHyb(b.branch_name)), otherBranches = byBranch.filter((b) => !isHyb(b.branch_name));
  const sumOf = (l: any[], f: string) => l.reduce((x, b) => x + Number(b[f] || 0), 0);
  const pnlBrands = (rep: any, go: string): DNode[] => {
    const r = rep?.rows?.find((x: any) => x.canon === "gp");
    return r ? rows(Object.entries(r.values || {}), ([b]: any) => b, ([, v]: any) => Number(v || 0) * 1e6, go) : [];
  };
  const drills: Record<string, DNode> = {
    sales: { key: "sales", label: `فروش خالص ${MONTHS[cur.month - 1]}`, value: allNet, go: "/sales", children: [
      { key: "hyb", label: "فروش هیبریدها (کارآمد)", value: sumOf(hybBranches, "net_rial"), go: "/hybrid", note: `${fa(hybBranches.length)} هیبرید`,
        children: rows(hybBranches, (b) => b.branch_name, (b) => b.net_rial, "/hybrid") },
      { key: "kother", label: "سایر شعب کارآمد", value: sumOf(otherBranches, "net_rial"), go: "/sales",
        children: rows(otherBranches, (b) => b.branch_name, (b) => b.net_rial, "/sales") },
      { key: "b2b", label: "نمایندگان B2B (راهکاران)", value: rkNet, go: "/rahkaran", note: `${fa(comb.data?.sales?.cur?.customers)} مشتری خریدار`,
        children: [
          { key: "prov", label: "به تفکیک استان", value: rkNet, go: "/rahkaran", children: rows(comb.data?.sales?.cur?.provinces, (x) => x.key, (x) => x.net_rial, "/rahkaran") },
          { key: "brand", label: "به تفکیک برند", value: rkNet, go: "/rahkaran/customer-brand", children: rows(comb.data?.sales?.cur?.brands, (x) => x.key, (x) => x.net_rial, "/rahkaran/customer-brand") },
        ] },
      { key: "exp", label: "صادرات (راهکاران)", value: expNet, go: "/rahkaran/export", note: expCur ? `${nf.format(Math.round(expCur.net_usd || 0))} دلار` : undefined,
        children: [
          { key: "country", label: "به تفکیک کشور", value: expNet, go: "/rahkaran/export", children: rows(expCur?.countries, (x) => x.key, (x) => x.net_rial, "/rahkaran/export", (x) => `${nf.format(Math.round(x.net_usd))} دلار`) },
          { key: "ecust", label: "به تفکیک مشتری", value: expNet, go: "/rahkaran/export", children: rows(expCur?.customers, (x) => x.key, (x) => x.net_rial, "/rahkaran/export", (x) => `${nf.format(Math.round(x.net_usd))} دلار`) },
        ] },
    ] },
    gross: { key: "gross", label: `فروش ناخالص ${MONTHS[cur.month - 1]}`, value: allGross, go: "/sales", children: [
      { key: "k", label: "شعب کارآمد", value: kmGross, go: "/hybrid", children: rows(kmCur.branches, (b) => b.key, (b) => b.gross_rial, "/hybrid", (b) => `خالص ${shortToman(b.net_rial)}`) },
      { key: "b2b", label: "نمایندگان B2B (راهکاران)", value: rkGross, go: "/rahkaran", note: rkGross && rkNet != null ? `خالص ${shortToman(rkNet)}` : undefined },
      { key: "exp", label: "صادرات (راهکاران)", value: expNet, go: "/rahkaran/export", note: "بدون تخفیف جدا: همان خالص" },
    ] },
    openreq: { key: "openreq", label: `درخواست باز ${MONTHS[cur.month - 1]} (کارآمد)`, value: openReq, go: "/sales", children:
      rows(kmCur.branches, (b) => b.key, (b) => b.open_req_rial, "/hybrid", (b) => `از درخواست ${shortToman(b.req_rial)} · ${fa(b.req_docs)} سند`) },
    coll: { key: "coll", label: `وصول ${MONTHS[cur.month - 1]}`, value: Number(t.collected_rial || 0) + Number(rkColl || 0), go: "cashBank", children: [
      { key: "k", label: "وصول فاکتورهای ماه هیبریدها (کارآمد)", value: Number(t.collected_rial || 0), go: "distribution", note: `${fa(collPct)}٪ از توزیع‌شده`,
        children: rows(mCur.data?.branches, (b) => b.branch_name, (b) => b.collected_rial, "distribution", (b) => `مانده ${shortToman(b.remaining_rial)}`) },
      { key: "r", label: "نقد و حواله مشتریان (راهکاران)", value: rkColl, go: "b2bRemittances" },
    ] },
    debt: { key: "debt", label: "مطالبات مشتریان", value: Number(sm.open_account_receivable_rial || 0) + Number(rkDebt || 0), go: "customers", children: [
      { key: "k", label: "مشتریان شعب (کارآمد)", value: Number(sm.open_account_receivable_rial || 0), go: "/files/hybrids",
        children: rows(network.data?.branches, (b) => b.branch_name, (b) => b.debt?.open_account_receivable_rial, "/files/hybrids") },
      { key: "r", label: "مشتریان راهکاران", value: rkDebt, go: "/files/rahkaran", note: `${fa(comb.data?.receivables?.debtor_count)} مشتری بدهکار`,
        children: rows(comb.data?.receivables?.top, (x) => x.key, (x) => x.amount_rial, "customers") },
    ] },
    recv: { key: "recv", label: "چک دریافتی سررسیدگذشته", value: recOverdue, go: "receivedCheques", children: [
      { key: "r", label: "راهکاران", value: recBySys("rahkaran"), go: "receivedCheques" },
      { key: "k", label: "کارآمد", value: recBySys("karamad"), go: "receivedCheques" },
      { key: "o", label: "وضعیت نامشخص", value: Number(rec.data?.overdue?.other_state_rial || 0), go: "receivedCheques" },
      { key: "age", label: "به تفکیک مدت تأخیر", value: Number(rec.data?.overdue?.definite_rial || 0), go: "receivedCheques",
        children: rows(rec.data?.overdue?.age_buckets, (x) => x.label, (x) => x.definite_rial, "receivedCheques", (x) => `${fa(x.count)} چک`) },
    ] },
    iss: { key: "iss", label: "چک پرداختی ۳۰ روز آینده", value: Number(iss.data?.kpis?.horizon?.amount_rial || 0), go: "issuedCheques", children: [
      { key: "r", label: "راهکاران", value: issBySys("rahkaran"), go: "issuedCheques" },
      { key: "k", label: "کارآمد", value: issBySys("karamad"), go: "issuedCheques" },
      { key: "payee", label: "بزرگ‌ترین دریافت‌کنندگان", value: Number(iss.data?.kpis?.horizon?.amount_rial || 0), go: "issuedCheques",
        children: rows(iss.data?.top_payees, (x) => x.payee_name, (x) => x.amount_rial, "issuedCheques", (x) => `${fa(x.count)} چک`) },
    ] },
    pay: { key: "pay", label: "بدهی به تأمین‌کنندگان", value: Number(pay.data?.trade?.credit_balance_rial || 0) + Number(pay.data?.nontrade?.credit_balance_rial || 0), go: "payables", children: [
      { key: "t", label: "تجاری", value: Number(pay.data?.trade?.credit_balance_rial || 0), go: "payables" },
      { key: "n", label: "غیرتجاری", value: Number(pay.data?.nontrade?.credit_balance_rial || 0), go: "payables" },
    ] },
    gp: { key: "gp", label: `سود ناخالص ${pnlPeriod}`, value: pnlGp * 1e6, go: "pnl", children: pnlChannels.map((c) => ({
      key: c.key, label: c.label, value: (pnlP0(c.rep, "gp") || 0) * 1e6, go: "pnl",
      note: pnlP0(c.rep, "net") ? `حاشیه ${fa(pct(pnlP0(c.rep, "gp"), pnlP0(c.rep, "net")))}٪` : undefined,
      children: pnlBrands(c.rep, "pnl") })) },
    slow: { key: "slow", label: "فرصت‌های بهبود روندها", value: null, count: slowItems.length, children: slowItems.map((x: any, i: number) => ({
      key: `${i}`, label: x.title, value: x.amount_rial ?? null, go: x.go,
      note: x.severity === "critical" ? "اولویت اول" : x.severity === "high" ? "مهم" : "قابل توجه" })) },
  };
  const [drill, setDrill] = useState<string[] | null>(null);
  const drillRef = useRef<HTMLDivElement>(null);
  const openDrill = (key: string) => {
    setDrill((d) => (d && d[0] === key && d.length === 1 ? null : [key]));
    window.setTimeout(() => drillRef.current?.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "nearest" }), 60);
  };

  // ---------------------------------------------------------------- مرور انیمیشنی اعداد ← رفتن به بخش مربوط
  // هر شاخص به نوبت روشن می‌شود و می‌شمارد؛ در پایان صفحه نرم به «فرصت‌های بهبود روندها» می‌رود (اگر کاربر خودش اسکرول نکرده باشد).
  const [stage, setStage] = useState(-1);
  const userMoved = useRef(false);
  const anyReady = tiles.some((x) => x.value !== null);
  useEffect(() => {
    if (stage !== -1) return;
    let played = false;
    try { played = sessionStorage.getItem("mo-intro") === "1"; } catch { /* حالت خصوصی */ }
    if (reduceMotion() || played) { setStage(tiles.length); return; }
    const t = window.setTimeout(() => setStage(0), anyReady ? 500 : 2500);
    return () => window.clearTimeout(t);
  }, [anyReady, stage, tiles.length]);
  useEffect(() => {
    const mark = () => { userMoved.current = true; };
    window.addEventListener("wheel", mark, { passive: true });
    window.addEventListener("touchmove", mark, { passive: true });
    window.addEventListener("keydown", mark);
    return () => { window.removeEventListener("wheel", mark); window.removeEventListener("touchmove", mark); window.removeEventListener("keydown", mark); };
  }, []);
  const playing = stage >= 0 && stage < tiles.length;
  useEffect(() => {
    if (!playing) return;
    const t = window.setTimeout(() => {
      const next = stage + 1;
      setStage(next);
      if (next >= tiles.length) {
        try { sessionStorage.setItem("mo-intro", "1"); } catch { /* حالت خصوصی */ }
        const end = tiles[tiles.length - 1];
        if (!userMoved.current && end) window.setTimeout(() => scrollToSection(end.target), 450);
      }
    }, 1350);
    return () => window.clearTimeout(t);
  }, [playing, stage, tiles]);
  const replay = () => { userMoved.current = false; window.scrollTo({ top: 0, behavior: "smooth" }); setStage(0); };
  const skip = () => { setStage(tiles.length); try { sessionStorage.setItem("mo-intro", "1"); } catch { /* حالت خصوصی */ } };

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
          {mCur.data && comb.data && <>فروش {MONTHS[cur.month - 1]} تا امروز (راهکاران و کارآمد) <b>{shortToman(allNet)} تومان</b>{pace !== null && <> و سرعتش <b className={pace >= 0 ? "up" : "down"}>{pace >= 0 ? "بیشتر" : "کمتر"}</b> از {MONTHS[prev.month - 1]} است</>}. </>}
          {base && <>پوشش نقدینگی ۳۰ روز آینده <b className={coverage! < 100 ? "down" : "up"}>{fa(coverage)}٪</b>{base.financing_need_rial > 0 && <> و نیاز به تأمین <b className="down">{shortToman(base.financing_need_rial)}</b></>}. </>}
          {alarmsLoaded && !profile.alarms_hidden && (openAlarms.length ? <><b>{fa(openAlarms.length)}</b> الارم باز داری{hot.length ? <>؛ <b className="down">{fa(hot.length)}</b> تا مهم</> : ""}.</> : <>الارم بازی نداری 🌿</>)}
        </p>
      </div>
      <div className="mo-rings">
        {salesOk && <Ring value={distPct} label="توزیع‌شده" sub="فاکتور هیبریدهای ماه" color="#2dd4bf" onClick={goCan("distribution")} />}
        {salesOk && <Ring value={collPct} label="وصول" sub="از توزیع‌شده" color="#a78bfa" onClick={goCan("distribution")} />}
        {has("management", "liquidity") && <Ring value={coverage} label="پوشش نقدینگی" sub="۳۰ روز آینده" color={coverage !== null && coverage < 100 ? "#fb923c" : "#4ade80"} onClick={goCan("liquidity")} />}
      </div>
    </header>

    {/* ------------------------------------------------ شاخص‌های شمارنده — مرور به نوبت، کلیک ← بخش مربوط */}
    <div className={`mo-intro ${playing ? "playing" : ""}`}>
      <div className="mo-intro-head">
        <span>{playing ? <>مرور اعداد امروز · <b>{fa(stage + 1)}</b> از {fa(tiles.length)}</> : stage < 0 ? "آماده‌سازی اعداد…" : "روی هر عدد بزنید تا ریزش را ببینید؛ هر جزء با کلیک جزئی‌تر می‌شود و در آخر به صفحه‌اش می‌روید"}</span>
        {playing ? <button type="button" onClick={skip}>رد شدن ⏭</button> : stage >= tiles.length && <button type="button" onClick={replay}>پخش دوباره ▶</button>}
      </div>
      <span className="mo-intro-bar" aria-hidden><i style={{ width: `${tiles.length ? (100 * Math.max(0, Math.min(stage + (playing ? 1 : 0), tiles.length))) / tiles.length : 0}%` }} /></span>
      <div className="mo-tiles">
        {tiles.map((k, i) => {
          const phase = stage < 0 ? "wait" : i < stage ? "done" : i === stage ? "on" : stage >= tiles.length ? "done" : "wait";
          return <button key={k.key} type="button" className={`mo-tile ${k.tone || "neutral"} ${phase}`} style={{ animationDelay: `${i * 70}ms` }}
            onClick={() => openDrill(k.key)} aria-expanded={drill?.[0] === k.key} aria-label={`${k.label} — نمایش ریز`}>
            <span className="mo-tile-top"><small>{k.label}</small><em className={k.domain === "مالی" ? "fin" : k.domain === "روند" ? "ops" : "sales"}>{k.domain}</em></span>
            <b>{k.value === null ? (k.error ? <span className="mo-err">{k.error}</span> : <span className="mo-shimmer" />) : <CountUp value={k.value} format={k.format} run={phase !== "wait"} />}</b>
            {k.value !== null && k.unit && <span className="mo-unit">{k.unit}</span>}
            {k.value !== null && k.hint && <span className="mo-hint">{k.hint}</span>}
            <span className="mo-tile-go" aria-hidden>{drill?.[0] === k.key ? "▴" : "▾"}</span>
            <i className="mo-tile-glow" aria-hidden />
          </button>;
        })}
      </div>
      <div ref={drillRef}>
        {drill && drills[drill[0]] && <DrillPanel root={drills[drill[0]]} path={drill} setPath={setDrill} go={go} />}
      </div>
    </div>

    {/* ------------------------------------------------ دو ستون مالی و فروش */}
    <div className="mo-lanes">
      {(chequesOk || has("management", "liquidity", "payables")) && <Reveal id="mo-fin" className="xo-block mo-lane fin">
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
      </Reveal>}

      {salesOk && <Reveal id="mo-sales" className="xo-block mo-lane sales" style={{ transitionDelay: "120ms" }}>
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
      </Reveal>}
    </div>

    {/* ------------------------------------------------ سود و زیان فصل (نگاه مدیر مالی) */}
    {pnlOk && <Reveal id="mo-pnl" className="xo-block mo-pnl">
      <div className="xo-block-title"><h3><i className="mo-dot fin" />سود و زیان {pnlPeriod ? faDigits(pnlPeriod) : "فصل"} — سه کانال</h3>
        {can("pnl") && <button type="button" className="mo-link" onClick={() => go("pnl")}>P&L کامل ←</button>}</div>
      <div className="mo-pnl-grid">
        {pnlChannels.map((c, i) => {
          const n = pnlP0(c.rep, "net") || 0, gp = pnlP0(c.rep, "gp") || 0, gs = pnlP0(c.rep, "gp_std"), np = pnlP0(c.rep, "np") || 0;
          const m = (x: number | null) => Math.max(0, Math.min(100, n ? (100 * (x || 0)) / n : 0));
          return <div key={c.key} className="mo-pnl-card" style={{ animationDelay: `${i * 110}ms` }}>
            <small>{c.label}</small>
            {!c.rep ? (c.err ? <span className="mo-err">{c.err}</span> : <><span className="mo-shimmer" /><span className="mo-unit">در حال خواندن از SQL…</span></>) : <>
              <b><CountUp value={n * 1e5} format={(v) => shortToman(v * 10)} /></b><span className="mo-unit">فروش خالص (تومان)</span>
              <div className="mo-pnl-bars">
                <span><em>سود ناخالص</em><i className={gp < 0 ? "neg" : ""} style={{ width: `${m(gp)}%` }} /><b className={gp < 0 ? "down" : ""}>{fa(pct(gp, n))}٪</b></span>
                {gs !== null && <span className="std"><em>با بهای استاندارد</em><i style={{ width: `${m(gs)}%` }} /><b>{fa(pct(gs, n))}٪</b></span>}
                <span className="np"><em>سود خالص</em><i className={np < 0 ? "neg" : ""} style={{ width: `${m(np)}%` }} /><b className={np < 0 ? "down" : ""}>{fa(pct(np, n))}٪</b></span>
              </div>
            </>}
          </div>;
        })}
      </div>
      <p className="mo-note">مبالغ به تومان ·بهای استاندارد = روش جذبی IAS 2 (مواد + دستمزد + سربار واقعی تولید) کنار روش فعلی (آخرین خرید × ۱٫۳ × ۱٫۲).</p>
    </Reveal>}

    {/* ------------------------------------------------ فرصت‌های بهبود روندها (سه ماه اخیر) — فقط با شواهد قطعی SQL، با لحن ملایم */}
    {slowOk && <Reveal id="mo-slow" className="xo-block mo-slow">
      <div className="xo-block-title"><h3>🌱 فرصت‌های بهبود روندها — سه ماه اخیر</h3>
        <small>{slow.data ? `${faDigits(slow.data.from_jalali || "")} تا ${faDigits(slow.data.to_jalali || "")} · راهکاران و کارآمد · ${faDigits(String(slow.data.built_at || "").slice(11, 16))}` : "از راهکاران و کارآمد"}</small></div>
      {slow.data ? <div className="mo-proc-grid">
        {slowItems.map((p, i) => <ProcessCard key={p.key} p={p} i={i}
          onGo={p.go && can(p.go.split("/").pop()) ? () => go(p.go.split("/").pop()) : undefined} />)}
      </div> : slow.error ? <div className="profile-warning">{slow.error}</div>
        : <div className="xo-loading">در حال بررسی اسناد، برگشتی‌ها، توزیع و پرداخت‌ها در SQL…</div>}
      {slow.data?.errors?.length > 0 && <div className="profile-warning">{slow.data.errors.join(" · ")}</div>}
    </Reveal>}

    {/* ------------------------------------------------ تصمیم‌های امروز + هیبریدها از کم‌رونق‌تر به پررونق‌تر */}
    <div className="mo-bottom">
      {!profile.alarms_hidden && <Reveal className="xo-block mo-decide">
        <div className="xo-block-title"><h3>⚡ نیازمند تصمیم امروز</h3><small>الارم‌های باز همه ماژول‌های شما</small></div>
        <ModuleAlarms title="امروز" onGo={go} />
      </Reveal>}
      {salesOk && <Reveal className="xo-block mo-rank" style={{ transitionDelay: "120ms" }}>
        <div className="xo-block-title"><h3>📉 هیبریدها — از کم‌رونق‌تر به پررونق‌تر</h3>
          <small>سرعت روزانه فروش {MONTHS[cur.month - 1]} در برابر میانگین {MONTHS[prev2.month - 1]} و {MONTHS[prev.month - 1]}</small></div>
        {!hybridTrend.length ? <div className="xo-loading">{mCur.error || mPrev.error || mPrev2.error || "در حال دریافت سه ماه اخیر…"}</div> : <ol className="mo-rank-list">
          {hybridTrend.map((b, i) => <li key={b.branch_name} className={b.trend < 0 ? "soft" : "good"} style={{ animationDelay: `${i * 60}ms` }}>
            <span className="mo-medal">{fa(i + 1)}</span>
            <div className="mo-rank-body">
              <div className="mo-rank-head"><b>{b.branch_name}</b>
                <span className={b.trend < 0 ? "down" : "up"}>{b.trend < 0 ? "▼" : "▲"} {fa(Math.abs(Math.round(b.trend)))}٪</span></div>
              <span className="mo-trend-bar"><i className={b.trend < 0 ? "neg" : "pos"} style={{ width: `${(50 * Math.abs(b.trend)) / maxTrend}%` }} /></span>
              <small>فروش ماه {shortToman(b.sales_rial)} · توزیع <b>{fa(b.dist)}٪</b> · وصول <b>{fa(b.coll)}٪</b>{b.debt_rial ? <> · مطالبات {shortToman(b.debt_rial)}</> : null}</small>
            </div>
          </li>)}
        </ol>}
      </Reveal>}
    </div>
    <PeekPanel peek={peek} onClose={closePeek} />
  </section></PeekContext.Provider>;
}
