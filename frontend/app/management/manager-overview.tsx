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
import { shortTomanText } from "../money-unit";

const FIN = () => `/api/v1/finance`;
const LIQ = () => `/api/v1/liquidity`;
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const shortToman = (rial: number | null | undefined) => shortTomanText(rial);
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
/** file = پرونده همان شخص/شعبه (مسیر داشبورد یکپارچه)؛ کنار ردیف دکمه «پرونده» می‌گیرد */
type DNode = { key: string; label: string; value: number | null; note?: string; go?: string; file?: string; count?: number; children?: DNode[] };

/** راهنمای هر شاخص: از کجا می‌آید، چه چیزی داخلش هست و چه چیزی نیست */
type Guide = { source: string; includes: string[]; excludes?: string[] };
const GUIDES: Record<string, Guide> = {
  tin: { source: "راهکاران: رسیدهای دریافت تأییدشده امروز (صندوق و بانک). کارآمد: واریزهای حواله و نقد امروز با شعبه و مشتری.",
    includes: ["نقد و حواله مشتریان", "پولی که بابت چک برگشتی واریز شده", "پول خریداران مواد اولیه", "چکی که وصول‌کننده نقد کرده و به حساب ریخته"],
    excludes: ["چک‌هایی که امروز گرفته شده ولی هنوز وصول نشده", "جابه‌جایی پول بین حساب‌های خود شرکت", "پول شرکا و تسویه کالای هیبریدها با شرکت", "رسید راهکاران که هنوز تأیید نشده"] },
  tpay: { source: "چک‌های پرداختی باز راهکاران و کارآمد که سررسیدشان امروز است.",
    includes: ["چک‌های سررسید امروز", "در جزئیات: چک‌هایی که سررسیدشان گذشته و هنوز پاس نشده"], excludes: ["چک‌هایی که پاس شده‌اند"] },
  sales: { source: "کارآمد: فاکتورهای همه شعب. راهکاران: فروش نمایندگان B2B و فروش صادراتی (معادل ریالی با نرخ سند).",
    includes: ["فروش این ماه از روز اول تا امروز", "بعد از کم شدن تخفیف‌ها و برگشتی‌ها"], excludes: ["مالیات بر ارزش افزوده", "سفارش‌هایی که هنوز فاکتور نشده‌اند"] },
  gross: { source: "همان فاکتورهای فروش خالص، به قیمت فاکتور پیش از تخفیف.",
    includes: ["فروش ماه به قیمت پیش از تخفیف", "صادرات به قیمت فاکتور (Price)"], excludes: ["تخفیف‌ها و برگشتی‌ها هنوز کم نشده‌اند"] },
  openreq: { source: "درخواست‌های فروش ثبت‌شده در کارآمد در این ماه.",
    includes: ["درخواست‌هایی که هنوز به فاکتور تبدیل نشده‌اند"], excludes: ["راهکاران", "درخواست‌هایی که فاکتور شده‌اند"] },
  coll: { source: "کارآمد: وصول فاکتورهای همین ماه شعب (گزارش توزیع). راهکاران: رسیدهای نقد و حواله تأییدشده روی حساب‌های دریافتنی مشتریان.",
    includes: ["شعب کارآمد: پولی که بابت فاکتورهای همین ماه گرفته شده", "نمایندگان B2B: کد ۷xxxxx تا ۹xxxxx، شامل پرداخت بابت چک برگشتی (معین ۱)", "صادرات: دریافت دلاری روی معین ارزی ۱۲۳۰۱۰", "سایر: بقیه دریافت‌های حساب‌های مشتری"],
    excludes: ["چک‌ها (تا وصول نشده‌اند در بخش چک‌ها هستند)", "فروش مواد اولیه (باکس «وصولی مواد اولیه»)", "تسویه کالای هیبریدها با شرکت", "پول شرکا"] },
  raw: { source: "رسیدهای نقد و حواله راهکاران روی معین ۱۲۴۰۴۶ «دریافتنی غیر رسمی (مواد اولیه)» و خریداران مواد روی حساب‌های دریافتنی.",
    includes: ["هر دریافت از خریداری که نامش «مواد» دارد و نماینده نیست"], excludes: ["فروش محصول", "چک"] },
  fut: { source: "چک‌های دریافتی باز راهکاران و کارآمد که سررسیدشان در ۱۲ ماه آینده است.",
    includes: ["چک‌های نزد صندوق، بانک و وصول‌کننده", "احتمال وصول هر مشتری از سابقه چک‌هایش"], excludes: ["چک‌هایی که سررسیدشان گذشته (باکس تعیین تکلیف نشده)", "چک‌های برگشتی"] },
  open: { source: "راهکاران: همان عدد صفحه «پرونده مشتری» (مانده حساب و حساب چک برگشتی). کارآمد: مانده دفتر کل مشتریان شعب.",
    includes: ["فاکتورهایی که نه پولشان رسیده نه چکشان", "چک‌های برگشتی تسویه‌نشده نمایندگان", "در کارآمد چک برگشتی داخل همان مانده است"], excludes: ["چک‌های در دست که هنوز سررسید نشده (باکس چک‌های آینده)"] },
  und: { source: "چک‌های دریافتی که سررسیدشان گذشته و هیچ وضعیت نهایی ندارند.",
    includes: ["راهکاران: هر وضعیتی غیر از واخواست", "کارآمد: هر وضعیتی غیر از برگشتی نزد مشتری/صندوق"], excludes: ["چک‌های وصول‌شده", "چک‌های برگشتی (باکس جدا)"] },
  ret: { source: "چک‌های دریافتی با وضعیت برگشتی، از ابتدای ۱۴۰۵.",
    includes: ["راهکاران: چک‌های واخواست‌شده", "کارآمد: برگشتی نزد مشتری و نزد صندوق"], excludes: ["چک‌های برگشتی که بعداً تسویه شده‌اند"] },
  iss: { source: "چک‌های پرداختی باز راهکاران و کارآمد با سررسید ۳۰ روز آینده.",
    includes: ["همه چک‌هایی که باید در این یک ماه پاس شوند"], excludes: ["چک‌های سررسیدگذشته (در «امروز باید پرداخت کنی»)"] },
  pay: { source: "مانده بستانکار تأمین‌کنندگان در راهکاران (معین‌های پرداختنی) و چک‌های پرداختی باز.",
    includes: ["چک‌های داده‌شده که هنوز پاس نشده‌اند (آینده و سررسیدگذشته)", "خریدهایی که هنوز چکی بابتشان داده نشده"], excludes: ["پیش‌پرداخت‌ها (بدهی نیستند)"] },
  paync: { source: "مانده بستانکار تأمین‌کنندگان تجاری و غیرتجاری در راهکاران.",
    includes: ["فاکتور خرید که نه پولش داده شده نه چکش"], excludes: ["چک‌های داده‌شده (باکس بدهی به تأمین‌کنندگان)", "پیش‌پرداخت‌ها"] },
  gp: { source: "صورت سود و زیان زنده هر کانال: فروش منهای بهای تمام‌شده کالای فروخته‌شده.",
    includes: ["سه کانال هیبرید، B2B و صادرات", "حاشیه با بهای واقعی و با بهای استاندارد"], excludes: ["هزینه‌های اداری و فروش"] },
  slow: { source: "تحلیل SQL روی سه ماه اخیر.", includes: ["روندهایی که کند یا بد شده‌اند، به ترتیب اولویت"] },
};
const HOW_TO_READ = [
  "هر ردیف یک تکه از عدد بالاست؛ درصد کنار مبلغ، سهم آن تکه از کل است.",
  "نوار رنگی بالای فهرست همان سهم‌ها را با رنگ هر ردیف نشان می‌دهد.",
  "ردیف با علامت › یک مرحله جزئی‌تر می‌شود؛ ↗ یعنی رفتن به صفحه کامل آن.",
  "برای برگشتن روی نام مرحله‌های بالا بزنید یا Esc را بزنید.",
  "همه مبالغ به تومان‌اند.",
];

/** پنل ریز شاخص: کل ← اجزا ← جزئیات (هر سطح با انیمیشن باز می‌شود) و در هر سطح رفتن به صفحه مرتبط */
function DrillPanel({ root, path, setPath, go, about, guide }: { root: DNode; path: string[]; setPath: (p: string[] | null) => void; go: (v: string) => void; about?: string; guide?: Guide }) {
  const [help, setHelp] = useState<boolean>(() => { try { return localStorage.getItem("mo-guide") === "1"; } catch { return false; } });
  const toggleHelp = () => setHelp((h) => { try { localStorage.setItem("mo-guide", h ? "0" : "1"); } catch { /* حالت خصوصی */ } return !h; });
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
  // درصد فقط وقتی اجزا تکه‌های همان کل‌اند (نه چند تفکیک موازی از یک عدد)
  const additive = node.value == null || total <= Math.abs(Number(node.value)) * 1.02;
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setPath(path.length > 1 ? path.slice(0, -1) : null); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [path, setPath]);
  const share = (v: number | null | undefined) => (v != null && v > 0 ? (100 * v) / Math.max(total, Math.abs(Number(node.value || 0))) : 0);
  return <section className="mo-drill" aria-label={`ریز ${root.label}`} style={{ "--depth": trail.length - 1 } as CSSProperties}>
    <header className="mo-drill-head">
      <nav className="mo-drill-crumbs" aria-label="مسیر">
        {trail.map((n, i) => <span key={n.key}>{i > 0 && <i aria-hidden>‹</i>}
          <button type="button" disabled={i === trail.length - 1} onClick={() => setPath(path.slice(0, i + 1))}>{n.label}</button></span>)}
      </nav>
      <button type="button" className={`mo-drill-help ${help ? "on" : ""}`} onClick={toggleHelp} aria-expanded={help}>؟ راهنما</button>
      <span className="mo-drill-steps" aria-label={`مرحله ${fa(trail.length)}`}>{trail.map((n, i) => <i key={n.key} className={i === trail.length - 1 ? "on" : ""} />)}</span>
      <button type="button" className="mo-drill-x" onClick={() => setPath(null)} aria-label="بستن">✕</button>
    </header>
    {about && trail.length === 1 && !help && <p className="mo-drill-about">{about}</p>}
    {help && <div className="mo-guide">
      {about && <section><h5>این عدد چیست</h5><p>{about}</p></section>}
      {guide && <section><h5>از کجا می‌آید</h5><p>{guide.source}</p></section>}
      {guide && <section className="in"><h5>داخلش هست</h5><ul>{guide.includes.map((x) => <li key={x}>{x}</li>)}</ul></section>}
      {guide?.excludes?.length ? <section className="out"><h5>داخلش نیست</h5><ul>{guide.excludes.map((x) => <li key={x}>{x}</li>)}</ul></section> : null}
      <section className="how"><h5>چطور بخوانید</h5><ul>{HOW_TO_READ.map((x) => <li key={x}>{x}</li>)}</ul></section>
    </div>}
    <div className="mo-drill-body" key={path.join("/")}>
      <div className="mo-drill-total">
        <b>{node.value == null ? (node.count != null ? `${fa(node.count)} مورد` : "…") : <CountUp value={node.value / 10} format={(v) => shortToman(v * 10)} />}</b>
        {node.value != null && <small>تومان</small>}
        {node.note && <em>{node.note}</em>}
        {node.file && <button type="button" className="mo-drill-go file" onClick={() => go(node.file!)}>باز کردن پرونده ←</button>}
        {node.go && <button type="button" className={`mo-drill-go ${node.file ? "ghost" : ""}`} onClick={() => go(node.go!)}>رفتن به صفحه ←</button>}
      </div>
      {kids.length > 1 && <div className="mo-drill-stats">
        <span>{fa(kids.length)} ردیف</span>
        {kids[0]?.value != null && <span>بزرگ‌ترین: <b>{kids.reduce((a, c) => (Number(c.value || 0) > Number(a.value || 0) ? c : a)).label}</b></span>}
        {additive && total > 0 && kids.length > 3 && <span>سه‌تای اول <b>{fa(Math.round([...kids].sort((a, b) => Number(b.value || 0) - Number(a.value || 0)).slice(0, 3).reduce((x, c) => x + share(c.value), 0)))}٪</b> کل</span>}
        {!additive && <span className="alt">این ردیف‌ها چند تفکیک جدا از یک عددند؛ جمعشان با کل برابر نیست</span>}
      </div>}
      {additive && total > 0 && kids.length > 1 && <div className="mo-drill-comp" aria-hidden>
        {kids.map((c, i) => <i key={c.key} title={`${c.label}: ${shortToman(c.value)}`}
          style={{ "--c": partColor(i), "--w": `${share(c.value)}%`, "--i": i } as CSSProperties} />)}
      </div>}
      {kids.length === 0 ? <p className="mo-drill-empty">{node.go ? "ریز بیشتری برای این بخش نیست؛ جزئیات کامل در صفحه مربوط است." : "داده‌ای برای نمایش نیست."}</p>
        : <ol className="mo-drill-list">
          {kids.map((c, i) => {
            const deeper = !!c.children?.some((x) => x.value);
            const w = c.value == null ? 0 : (100 * Math.abs(Number(c.value))) / max;
            return <li key={c.key} style={{ "--i": i, "--w": `${w}%`, "--c": partColor(i) } as CSSProperties}>
              <button type="button" onClick={() => (deeper ? setPath([...path, c.key]) : (c.file || c.go) && go((c.file || c.go)!))} disabled={!deeper && !c.go && !c.file}>
                <span className="mo-drill-label"><span className="mo-drill-name"><em className="mo-drill-rank">{fa(i + 1)}</em><i className="mo-drill-dot" />{c.label}</span>{c.note && <small>{c.note}</small>}</span>
                <span className="mo-drill-bar"><i /></span>
                <span className="mo-drill-val">{c.value == null ? "…" : withUnit(shortToman(c.value))}
                  {additive && total > 0 && c.value != null && c.value > 0 && <small>{fa(Math.round(share(c.value)))}٪</small>}</span>
                <span className="mo-drill-arrow" aria-hidden>{deeper ? "›" : c.file || c.go ? "↗" : ""}</span>
              </button>
              {c.file && deeper && <button type="button" className="mo-drill-file" onClick={() => go(c.file!)} title={`پرونده ${c.label}`}>پرونده ↗</button>}
            </li>;
          })}
        </ol>}
    </div>
  </section>;
}

/** about = این عدد به زبان ساده چیست؛ parts = از چه تکه‌هایی ساخته شده (نوار رنگی)؛ foot = یک نکته کوتاه زیرش */
type Tile = { key: string; label: string; domain: "مالی" | "فروش" | "روند"; value: number | null; format: (v: number) => string; unit?: string;
  about?: string; parts?: Part[]; foot?: ReactNode; tone?: "good" | "watch" | "follow" | "neutral"; target: string; locked?: boolean; error?: string };

type Part = { label: string; value: number | null };
const PART_COLORS = ["#2dd4bf", "#60a5fa", "#a78bfa", "#f472b6", "#fbbf24", "#4ade80"];
const partColor = (i: number) => (i < PART_COLORS.length ? PART_COLORS[i] : "#64748b");

/** نوار تکه‌های یک عدد: هر تکه با رنگ خودش و سهمش از کل؛ وقتی کارت روشن شد از صفر پر می‌شود */
function Parts({ parts, run }: { parts: Part[]; run: boolean }) {
  const pos = parts.map((x) => Math.max(0, Number(x.value || 0)));
  const sum = pos.reduce((a, b) => a + b, 0);
  return <span className="mo-parts">
    <span className="mo-parts-bar" aria-hidden>
      {parts.map((x, i) => <i key={x.label} className={run ? "in" : ""}
        style={{ "--c": partColor(i), "--w": sum ? `${(100 * pos[i]) / sum}%` : "0%", "--d": `${150 + i * 140}ms` } as CSSProperties} />)}
    </span>
    <span className="mo-parts-legend">
      {parts.map((x, i) => <span key={x.label} style={{ "--c": partColor(i), "--d": `${250 + i * 110}ms` } as CSSProperties} className={run ? "in" : ""}>
        <i /><em>{x.label}</em><b>{x.value == null ? "…" : shortToman(x.value)}</b><small>{sum > 0 && x.value != null ? `${fa(Math.round((100 * pos[i]) / sum))}٪` : ""}</small>
      </span>)}
    </span>
  </span>;
}

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
  // چک دریافتی: افق ۱۲ ماه (چک‌های آینده)؛ برگشتی و تعیین تکلیف نشده از همان ریز کارت‌های خلاصه مدیریتی
  const rec = useLoad(chequesOk ? `${LIQ()}/received-cheques?horizon_days=365` : null, (j) => j.data);
  const stRet = useLoad(chequesOk ? `${LIQ()}/received-cheques/status/returned` : null, (j) => j.data ?? j);
  const stUnd = useLoad(chequesOk ? `${LIQ()}/received-cheques/status/undetermined` : null, (j) => j.data ?? j);
  const iss = useLoad(chequesOk ? `${LIQ()}/issued-cheques?horizon_days=30` : null, (j) => j.data);
  const iss365 = useLoad(chequesOk ? `${LIQ()}/issued-cheques?horizon_days=365` : null, (j) => j.data);
  const pay = useLoad(has("management", "payables") ? `${FIN()}/payables` : null, (j) => j.modules);
  // سهم راهکاران (فروش نمایندگان B2B ماه و مطالبات) و وصول نقد و حواله هر دو سیستم، تا هر شاخص جمع راهکاران و کارآمد باشد
  const comb = useLoad(salesOk ? `${FIN()}/manager-combined?year=${cur.year}&month=${cur.month}` : null);
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
  // فروش ناخالص ماه (پیش از تخفیف‌ها) = کارآمد + B2B راهکاران + صادرات (قیمت پیش از تخفیف)؛ درخواست باز = فقط کارآمد
  const kmCur = comb.data?.karamad?.cur || {};
  const kmGross = kmCur.gross_rial ?? null, rkGross = comb.data?.sales?.cur?.gross_rial ?? null;
  const expGross = expCur?.gross_rial ?? expNet;  // ناخالص صادرات = قیمت پیش از تخفیف (InvoiceItem.Price)
  const allGross = kmGross == null ? null : Number(kmGross) + Number(rkGross || 0) + Number(expGross || 0);
  const openReq = kmCur.open_req_rial ?? null;
  // وصول ماه راهکاران در دو بخش: محصول (نمایندگان، صادرات، سایر مشتریان) و مواد اولیه (backend: manager_combined_service.rahkaran_collections)
  const rkC = comb.data?.collections, rkProd = rkC?.product, rkRaw = rkC?.raw_material;
  const rkColl = rkProd?.amount_rial ?? null;
  // امروز: واریزهای واقعی (comb.today_inflows) و چک‌های پرداختی سررسید امروز
  const tIn = comb.data?.today_inflows;
  const tSys = (k: string) => (tIn?.systems || []).find((x: any) => x.key === k);
  const recToday = rec.data ? Number(rec.data?.kpis?.today?.definite_rial || 0) : null;
  const issDueToday = (iss.data?.cheques || []).filter((c: any) => c.days_to_due === 0);
  const issOverdue = (iss.data?.cheques || []).filter((c: any) => c.days_to_due < 0);
  const issOverdueAmt = issOverdue.reduce((x: number, c: any) => x + Number(c.amount_rial || 0), 0);
  const seg = (k: string) => (rkProd?.segments || []).find((g: any) => g.key === k)?.amount_rial ?? (rkProd ? 0 : null);
  // مطالبات باز = مانده حساب و حساب چک برگشتی مشتریان راهکاران (همان عدد «پرونده مشتری») + مانده دفتر کل مشتریان شعب کارآمد
  const rr = comb.data?.receivables_report;
  const kmDebt = Number(network.data?.summary?.open_account_receivable_rial || 0);
  const openRecv = rr && (network.data || network.off) ? Number(rr.balance_rial || 0) + Number(rr.returned_rial || 0) + kmDebt : null;
  // چک‌های آینده: چک دریافتی سررسیدنشده تا ۱۲ ماه آینده
  const futCh = rec.data ? Number(rec.data?.kpis?.horizon?.definite_rial || 0) : null;
  // بدهی تأمین‌کنندگان = مانده بستانکار حساب (خرید بدون چک) + چک‌های پرداختی باز (آینده و سررسیدگذشته)
  const payBal = pay.data ? Number(pay.data.trade?.credit_balance_rial || 0) + Number(pay.data.nontrade?.credit_balance_rial || 0) : null;
  const issOpen = iss365.off ? 0 : iss365.data ? Number(iss365.data?.kpis?.horizon?.amount_rial || 0) + Number(iss365.data?.kpis?.overdue?.amount_rial || 0) : null;
  const issBySys = (s2: string) => (iss.data?.horizon_by_system || []).find((x: any) => x.system === s2)?.amount_rial ?? null;
  const t = mCur.data?.totals || {};
  const distPct = mCur.data ? pct(t.distributed_rial, t.sales_rial) : null;
  const collPct = mCur.data ? pct(t.collected_rial, t.distributed_rial) : null;
  const scen: any[] = liq.data?.scenarios || [];
  const base = scen.find((s) => s.key === (liq.data?.base_scenario || "reliance")) || scen[0];
  const coverage = base ? Math.round(base.coverage_percent || 0) : null;
  const sm = network.data?.summary || {};
  const openAlarms = alarms.filter((a) => a.my_status === "open" || a.my_status === "seen");
  const hot = openAlarms.filter((a) => a.level === "critical" || a.level === "high");
  const chan = (c: string) => (rec.data?.by_channel || []).find((x: any) => x.channel === c)?.definite_rial ?? null;
  const sysAmt = (st: any, label: string) => (st?.by_system || []).find((x: any) => x.label === label)?.amount_rial ?? 0;
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
  const P = (label: string, value: number | null | undefined): Part => ({ label, value: value == null ? null : Number(value) });
  const allTiles: Tile[] = [
    { key: "tin", label: "امروز وصول و واریز شد", domain: "مالی", value: tIn ? Number(tIn.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "پول نقد و حواله‌ای که همین امروز واقعاً به حساب‌ها و صندوق ما نشسته؛ چک‌ها جدا شمرده می‌شوند.",
      parts: tIn ? [P("راهکاران", tSys("rahkaran")?.amount_rial ?? 0), P("کارآمد", tSys("karamad")?.amount_rial ?? 0)] : undefined,
      foot: tIn ? <>{fa(tIn.count)} واریز
        {tSys("rahkaran") && !tSys("rahkaran").amount_rial && tSys("rahkaran").last_day_jalali && <> · راهکاران هنوز رسید تأییدشده امروز ندارد</>}
        {recToday != null && recToday > 0 && <><br />چک سررسید امروز در راه: <b>{shortToman(recToday)}</b></>}</> : null,
      tone: "good", target: "mo-fin", locked: !salesOk, error: comb.error || (comb.data && !tIn ? "داده واریز امروز نرسید" : "") },
    { key: "tpay", label: "امروز باید پرداخت کنی", domain: "مالی", value: iss.data ? Number(iss.data?.kpis?.today?.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "چک‌هایی که خودمان داده‌ایم و سررسیدشان امروز است؛ برای پاس شدنشان باید امروز در حساب پول باشد.",
      foot: iss.data ? <>{fa(iss.data?.kpis?.today?.count)} چک امروز{issOverdueAmt > 0 && <><br />از قبل مانده و پاس‌نشده: <b className="down">{shortToman(issOverdueAmt)}</b> ({fa(issOverdue.length)} چک)</>}</> : null,
      tone: "follow", target: "mo-fin", locked: !chequesOk, error: iss.error },
    { key: "sales", label: "فروش خالص ماه", domain: "فروش", value: mCur.data && comb.data ? allNet / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "همه فروش این ماه تا امروز در سه کانال، بعد از کم شدن تخفیف‌ها و برگشتی‌ها.",
      parts: [P("کارآمد", net), P("نمایندگان B2B", rkNet), P("صادرات", expNet)],
      foot: pace === null ? "در حال مقایسه با ماه قبل…" : <span className={pace >= 0 ? "up" : "down"}>{pace >= 0 ? "▲" : "▼"} {nf1.format(Math.abs(pace))}٪ سرعت فروش نسبت به {MONTHS[prev.month - 1]}</span>,
      tone: pace === null ? "neutral" : pace >= 0 ? "good" : "watch", target: "mo-sales", locked: !salesOk, error: mCur.error || comb.error },
    { key: "gross", label: "فروش ناخالص ماه", domain: "فروش", value: allGross == null ? null : allGross / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "فروش این ماه به قیمت فاکتور، پیش از کم شدن تخفیف‌ها و برگشتی‌ها.",
      parts: [P("کارآمد", kmGross), P("نمایندگان B2B", rkGross), P("صادرات", expGross)],
      foot: allGross ? <>تخفیف و برگشت تا خالص: <b>{fa(pct(allGross - allNet, allGross))}٪</b></> : null,
      tone: "neutral", target: "mo-sales", locked: !salesOk, error: comb.error },
    { key: "openreq", label: "سفارش فاکتورنشده ماه", domain: "فروش", value: openReq == null ? null : Number(openReq) / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "سفارش‌هایی که شعب این ماه ثبت کرده‌اند ولی هنوز فاکتور نشده‌اند (کارآمد).",
      foot: openReq == null ? null : <>{fa(kmCur.open_req_docs)} سند باز از {fa(kmCur.req_docs)} · تبدیل به فاکتور <b>{fa(Math.round(Number(kmCur.req_conv || 0) * 100))}٪</b></>,
      tone: "watch", target: "mo-sales", locked: !salesOk, error: comb.error },
    { key: "coll", label: "وصول ماه — محصولات", domain: "فروش", value: mCur.data && comb.data ? (Number(t.collected_rial || 0) + Number(rkColl || 0)) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "پولی که این ماه بابت فروش محصول، نقد یا حواله، به دستمان رسیده؛ چک و مواد اولیه جدا هستند.",
      parts: [P("شعب کارآمد", Number(t.collected_rial || 0)), P("نمایندگان B2B", seg("rep")), P("صادرات", seg("export")), ...(seg("other") ? [P("سایر", seg("other"))] : [])],
      tone: "neutral", target: "mo-sales", locked: !salesOk, error: mCur.error || comb.error },
    { key: "raw", label: "وصولی مواد اولیه", domain: "فروش", value: rkRaw ? Number(rkRaw.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "پولی که این ماه از فروش مواد اولیه به خریداران مواد گرفته‌ایم.",
      parts: rkRaw ? Object.entries(rkRaw.by_method || {}).map(([m, v]) => P(m === "cash" ? "نقد" : "حواله", Number(v))) : undefined,
      foot: rkRaw ? <>{fa(rkRaw.customer_count)} خریدار در {MONTHS[cur.month - 1]}</> : null,
      tone: "neutral", target: "mo-sales", locked: !salesOk, error: comb.error || (comb.data && !rkC ? "داده وصول راهکاران نرسید" : "") },
    { key: "fut", label: "چک‌های آینده", domain: "مالی", value: futCh == null ? null : futCh / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "چک‌هایی که از مشتری‌ها گرفته‌ایم و سررسیدشان تا یک سال آینده می‌رسد؛ پولی که در راه است.",
      parts: rec.data ? [P("نمایندگان", chan("b2b")), P("شعب", chan("hybrid"))] : undefined,
      foot: rec.data ? <>{fa(rec.data?.kpis?.horizon?.count)} چک · احتمال وصول <b>{fa(Math.round(rec.data?.kpis?.horizon?.reliance_percent || 0))}٪</b></> : null,
      tone: "neutral", target: "mo-fin", locked: !chequesOk, error: rec.error },
    { key: "open", label: "مطالبات باز", domain: "مالی", value: openRecv == null ? null : openRecv / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "طلبی که از مشتری‌ها داریم و هنوز نه پولش رسیده نه چکش در دست ماست، به‌اضافه چک‌های برگشتی تسویه‌نشده.",
      parts: rr ? [P("بدهی نمایندگان", rr.balance_rial), P("برگشتی نمایندگان", rr.returned_rial), P("مشتریان شعب", kmDebt)] : undefined,
      tone: "watch", target: "mo-sales", locked: !salesOk, error: comb.error || network.error || (comb.data && !rr ? "مانده پرونده مشتری نرسید" : "") },
    { key: "und", label: "چک‌های تعیین تکلیف نشده", domain: "مالی", value: stUnd.data ? Number(stUnd.data.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "چک‌های مشتری که سررسیدشان گذشته ولی نه پاس شده‌اند نه برگشت خورده‌اند؛ وضعیتشان باید روشن شود.",
      parts: stUnd.data ? [P("راهکاران", sysAmt(stUnd.data, "راهکاران")), P("کارآمد", sysAmt(stUnd.data, "کارآمد"))] : undefined,
      foot: stUnd.data ? <>{fa(stUnd.data.count)} چک · {fa(stUnd.data.customer_count)} مشتری</> : null,
      tone: "follow", target: "mo-fin", locked: !chequesOk, error: stUnd.error },
    { key: "ret", label: "چک‌های برگشتی", domain: "مالی", value: stRet.data ? Number(stRet.data.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "چک‌های مشتری که برگشت خورده‌اند و هنوز پولشان را نگرفته‌ایم.",
      parts: stRet.data ? [P("راهکاران", sysAmt(stRet.data, "راهکاران")), P("کارآمد", sysAmt(stRet.data, "کارآمد"))] : undefined,
      foot: stRet.data ? <>{fa(stRet.data.count)} چک · {fa(stRet.data.customer_count)} مشتری</> : null,
      tone: "follow", target: "mo-fin", locked: !chequesOk, error: stRet.error },
    { key: "iss", label: "چک پرداختی ۳۰ روز آینده", domain: "مالی", value: iss.data ? Number(iss.data?.kpis?.horizon?.amount_rial || 0) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "چک‌هایی که خودمان داده‌ایم و تا یک ماه آینده باید پاس شوند؛ پولی که باید آماده باشد.",
      parts: iss.data ? [P("راهکاران", issBySys("rahkaran")), P("کارآمد", issBySys("karamad"))] : undefined,
      foot: iss.data ? <>{fa(iss.data?.kpis?.horizon?.count)} چک · هفته آینده <b>{shortToman(iss.data?.kpis?.next_7_days?.amount_rial)}</b></> : null,
      tone: "neutral", target: "mo-fin", locked: !chequesOk, error: iss.error },
    { key: "pay", label: "بدهی به تأمین‌کنندگان", domain: "مالی", value: payBal != null && issOpen != null ? (payBal + issOpen) / 10 : null, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "کل بدهی ما بابت خرید: هم چک‌هایی که به تأمین‌کننده‌ها داده‌ایم و هنوز پاس نشده، هم خریدهایی که هنوز چکی بابتشان نداده‌ایم.",
      parts: [P("چک‌های داده‌شده", issOpen), P("خرید بدون چک", payBal)],
      tone: "neutral", target: "mo-fin", locked: !has("management", "payables"), error: pay.error || iss365.error },
    { key: "paync", label: "بدهی باز بدون چک", domain: "مالی", value: payBal == null ? null : payBal / 10, format: (v) => shortToman(v * 10), unit: "تومان",
      about: "جنس و خدمتی که خریده‌ایم ولی هنوز نه پولش را داده‌ایم نه چکی بابتش.",
      parts: pay.data ? [P("تأمین‌کنندگان تجاری", pay.data.trade?.credit_balance_rial), P("سایر طلبکاران", pay.data.nontrade?.credit_balance_rial)] : undefined,
      foot: pay.data ? <>{fa(Number(pay.data.trade?.creditor_count || 0) + Number(pay.data.nontrade?.creditor_count || 0))} طلبکار · پیش‌پرداخت باز {shortToman(Number(pay.data.trade?.debit_balance_rial || 0) + Number(pay.data.nontrade?.debit_balance_rial || 0))}</> : null,
      tone: "watch", target: "mo-fin", locked: !has("management", "payables"), error: pay.error },
    { key: "gp", label: "سود ناخالص فصل", domain: "مالی", target: "mo-pnl", locked: !pnlOk, error: pnlB2b.error,
      value: pnlChannels.every((c) => c.rep) ? pnlChannels.reduce((x, c) => x + (pnlP0(c.rep, "gp") || 0), 0) * 1e5 : null,
      format: (v) => shortToman(v * 10), unit: "تومان",
      about: "سود این فصل بعد از کم کردن بهای تمام‌شده کالا از فروش، در سه کانال.",
      parts: pnlNet ? [P("هیبرید", (pnlP0(pnlHyb.data?.report, "gp") || 0) * 1e6), P("B2B", (pnlP0(pnlB2b.data?.report, "gp") || 0) * 1e6), P("صادرات", (pnlP0(pnlExp.data?.report, "gp") || 0) * 1e6)] : undefined,
      foot: pnlNet ? <>حاشیه <b>{fa(pct(pnlGp, pnlNet))}٪</b> · با بهای استاندارد <b className="up">{fa(pct(pnlGpStd, pnlNet))}٪</b></> : null, tone: "good" },
    { key: "slow", label: "فرصت‌های بهبود روندها", domain: "روند", target: "mo-slow", locked: !slowOk, error: slow.error,
      value: slow.data ? slowItems.filter((x: any) => x.severity === "critical").length : null, format: (v) => fa(Math.round(v)), unit: "مورد با اولویت اول",
      about: "روندهایی در سه ماه اخیر که کند یا بد شده‌اند و ارزش پیگیری دارند.",
      foot: slow.data ? `${fa(slowItems.length)} روند از داده SQL` : null, tone: "follow" },
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
  // پرونده هر نفر: نماینده B2B (کد ۷xxxxx تا ۹xxxxx) ← پرونده نماینده؛ بقیه مشتریان راهکاران ← پرونده مشتری مالی؛ شعبه ← پرونده هیبرید
  const repFile = (code: unknown) => { const k = String(code || "").trim(); return /^[789]\d{5}$/.test(k) ? `/files/rahkaran/${k}` : k ? `/finance/customers?c=${encodeURIComponent(k)}` : undefined; };
  const hybFile = (name: unknown) => { const n = String(name || "").trim(); return n.includes("هیبرید") ? `/files/hybrids/${encodeURIComponent(n)}` : undefined; };
  const METHOD: Record<string, string> = { cash: "نقد (صندوق)", bank: "حواله / بانکی" };
  const sumV = (l: any[], f = "amount_rial") => l.reduce((x, c) => x + Number(c[f] || 0), 0);
  const groupBy = (l: any[], k: (x: any) => string): [string, any[]][] => {
    const m = new Map<string, any[]>();
    l.forEach((x) => { const g = k(x) || "—"; m.set(g, [...(m.get(g) || []), x]); });
    return [...m.entries()];
  };
  /** وصول یک بخش راهکاران: مشتری ← روش دریافت؛ و تفکیک حساب معین و روش */
  const collTree = (p: any, go: string, who: string): DNode[] => p ? [
    { key: "cust", label: `به تفکیک ${who}`, value: p.amount_rial, go, note: `${fa(p.customer_count)} ${who}`, children: (p.top_customers || []).map((c: any, i: number) => ({
      key: `${i}:${c.code}`, label: c.name, value: c.amount_rial, go, file: repFile(c.code), note: `کد ${faDigits(c.code || "—")} · ${fa(c.count)} سند`,
      children: Object.entries(c.by_method || {}).map(([m, v]) => ({ key: m, label: METHOD[m] || m, value: Number(v), go })) })) },
    { key: "acc", label: "به تفکیک حساب معین", value: p.amount_rial, go, children: rows(p.by_account, (x) => x.key, (x) => x.amount_rial, go) },
    { key: "method", label: "به تفکیک روش دریافت", value: p.amount_rial, go, children: Object.entries(p.by_method || {}).map(([m, v]) => ({ key: m, label: METHOD[m] || m, value: Number(v), go })) },
  ] : [];
  /** چک‌های برگشتی / تعیین تکلیف نشده: سیستم ← مشتری ← هر چک */
  const chequeTree = (st: any): DNode[] => {
    if (!st) return [];
    const go = "receivedCheques", ch: any[] = st.cheques || [];
    const sys: DNode[] = (st.by_system || []).map((s: any) => ({ key: `s:${s.label}`, label: s.label, value: Number(s.amount_rial || 0), go, note: `${fa(s.count)} چک`,
      children: groupBy(ch.filter((c) => c.system_label === s.label), (c) => c.customer_name).map(([name, cs]) => ({
        key: `c:${name}`, label: name, value: sumV(cs), go, file: cs[0].system === "rahkaran" ? repFile(cs[0].customer_code) : hybFile(cs[0].branch_name),
        note: `${fa(cs.length)} چک · ${cs[0].branch_name || cs[0].visitor_name || ""}`,
        children: cs.map((c: any, i: number) => ({ key: `${i}:${c.serial_number}`, label: `چک ${faDigits(c.serial_number || "—")} · سررسید ${faDigits(c.due_date_jalali)}`,
          value: Number(c.amount_rial || 0), go, note: `${fa(c.days_overdue)} روز گذشته · ${c.status_label}` })) }))
        .sort((a, b) => b.value - a.value).slice(0, 25) }));
    return [...sys,
      { key: "age", label: "به تفکیک مدت گذشته از سررسید", value: Number(st.amount_rial || 0), go, children: rows(st.by_age, (x) => x.label, (x) => x.amount_rial, go, (x) => `${fa(x.count)} چک`) },
      { key: "status", label: "به تفکیک وضعیت", value: Number(st.amount_rial || 0), go, children: rows(st.by_status, (x) => x.label, (x) => x.amount_rial, go, (x) => `${fa(x.count)} چک`) }];
  };
  /** چک‌های پرداختی: ذی‌نفع ← هر چک */
  const payeeTree = (d: any): DNode[] => groupBy(d?.cheques || [], (c) => c.payee_name).map(([name, cs]) => ({
    key: `p:${name}`, label: name, value: sumV(cs), go: "issuedCheques", note: `${fa(cs.length)} چک${cs.some((c: any) => c.days_to_due < 0) ? " · سررسیدگذشته دارد" : ""}`,
    children: cs.map((c: any, i: number) => ({ key: `${i}:${c.serial_number}`, label: `چک ${faDigits(c.serial_number || "—")} · سررسید ${faDigits(c.due_date_jalali)}`, value: Number(c.amount_rial || 0), go: "issuedCheques",
      note: `${c.bank_name || ""}${c.days_to_due < 0 ? ` · ${fa(-c.days_to_due)} روز گذشته` : ""}` })) })).sort((a, b) => b.value - a.value).slice(0, 25);
  /** تأمین‌کنندگان طلبکار: تجاری/غیرتجاری ← طرف حساب ← گردش */
  const creditorTree = (): DNode[] => (["trade", "nontrade"] as const).map((k) => {
    const m = pay.data?.[k];
    return { key: k, label: k === "trade" ? "تأمین‌کنندگان تجاری" : "سایر طلبکاران (غیرتجاری)", value: Number(m?.credit_balance_rial || 0), go: "payables", note: m ? `${fa(m.creditor_count)} طلبکار` : undefined,
      children: (m?.counterparties || []).filter((c: any) => Number(c.credit_balance_rial) > 0).sort((a: any, b: any) => b.credit_balance_rial - a.credit_balance_rial).slice(0, 20).map((c: any) => ({
        key: `${c.dl_code}`, label: c.title, value: Number(c.credit_balance_rial), go: "payables",
        note: `کد ${faDigits(c.dl_code)} · آخرین خرید ${faDigits(c.last_invoice_date_jalali || "—")} · آخرین پرداخت ${faDigits(c.last_payment_date_jalali || "—")}`,
        children: [{ key: "cr", label: "جمع بستانکار (خرید)", value: Number(c.credit_rial || 0), go: "payables" },
          { key: "dr", label: "جمع بدهکار (پرداخت و چک)", value: Number(c.debit_rial || 0), go: "payables" }] })) };
  });
  const drills: Record<string, DNode> = {
    sales: { key: "sales", label: `فروش خالص ${MONTHS[cur.month - 1]}`, value: allNet, go: "/sales", children: [
      { key: "hyb", label: "فروش هیبریدها (کارآمد)", value: sumOf(hybBranches, "net_rial"), go: "/hybrid", note: `${fa(hybBranches.length)} هیبرید`,
        children: rows(hybBranches, (b) => b.branch_name, (b) => b.net_rial, "/hybrid").map((x) => ({ ...x, file: hybFile(x.label) })) },
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
      { key: "exp", label: "صادرات (راهکاران)", value: expGross, go: "/rahkaran/export", note: expNet != null ? `خالص ${shortToman(expNet)}` : undefined,
        children: rows(expCur?.countries, (x) => x.key, (x) => x.net_rial, "/rahkaran/export") },
    ] },
    openreq: { key: "openreq", label: `درخواست باز ${MONTHS[cur.month - 1]} (کارآمد)`, value: openReq, go: "/sales", children:
      rows(kmCur.branches, (b) => b.key, (b) => b.open_req_rial, "/hybrid", (b) => `از درخواست ${shortToman(b.req_rial)} · ${fa(b.req_docs)} سند`) },
    coll: { key: "coll", label: `وصول ${MONTHS[cur.month - 1]} — محصولات`, value: Number(t.collected_rial || 0) + Number(rkColl || 0), go: "cashBank",
      note: "نقد و حواله؛ چک و مواد اولیه جدا", children: [
      { key: "k", label: "شعب کارآمد (وصول فاکتورهای ماه)", value: Number(t.collected_rial || 0), go: "distribution", note: `${fa((mCur.data?.branches || []).filter((b: any) => Number(b.collected_rial) > 0).length)} شعبه · ${fa(collPct)}٪ از فاکتورهای توزیع‌شده وصول شده`,
        children: (mCur.data?.branches || []).filter((b: any) => Number(b.collected_rial) > 0).sort((a: any, b: any) => b.collected_rial - a.collected_rial).map((b: any) => ({
          key: b.branch_name, label: b.branch_name, value: Number(b.collected_rial || 0), go: "distribution", file: hybFile(b.branch_name), note: `${fa(pct(b.collected_rial, b.distributed_rial))}٪ از توزیع‌شده · مانده ${shortToman(b.remaining_rial)}`,
          children: [{ key: "s", label: "فروش ماه", value: Number(b.sales_rial || 0), go: "distribution" }, { key: "d", label: "توزیع‌شده", value: Number(b.distributed_rial || 0), go: "distribution" },
            { key: "c", label: "وصول‌شده", value: Number(b.collected_rial || 0), go: "distribution" }, { key: "r", label: "مانده وصول‌نشده", value: Number(b.remaining_rial || 0), go: "distribution" }] })) },
      // راهکاران: نمایندگان B2B / صادرات / سایر ← نام هر نفر ← روش دریافت
      ...(rkProd?.segments || []).filter((g: any) => Number(g.amount_rial) > 0).map((g: any) => {
        const unit = g.key === "rep" ? "نماینده" : "مشتری";
        return { key: `seg:${g.key}`, label: g.key === "rep" ? "نمایندگان B2B (راهکاران)" : g.key === "export" ? "صادرات (راهکاران)" : "سایر دریافت‌های مشتری (راهکاران)",
          value: Number(g.amount_rial || 0), go: g.key === "export" ? "/rahkaran/export" : "/rahkaran",
          note: `${fa(g.customer_count)} ${unit} · ${fa((g.customers || []).reduce((x: number, c: any) => x + Number(c.count || 0), 0))} سند دریافت`,
          children: (g.customers || []).map((c: any, i: number) => ({ key: `${i}:${c.code}`, label: c.name, value: Number(c.amount_rial || 0), go: g.key === "export" ? "/rahkaran/export" : "cashBank",
            file: g.key === "export" ? undefined : repFile(c.code),
            note: `کد ${faDigits(c.code || "—")} · ${fa(c.count)} سند`,
            children: Object.entries(c.by_method || {}).map(([m, v]) => ({ key: m, label: METHOD[m] || m, value: Number(v), go: "cashBank" })) })) };
      }),
    ] },
    raw: { key: "raw", label: `وصولی مواد اولیه ${MONTHS[cur.month - 1]}`, value: rkRaw?.amount_rial ?? null, go: "cashBank",
      note: "نقد و حواله معین ۱۲۴۰۴۶ «دریافتنی غیر رسمی (مواد اولیه)» و خریداران مواد روی حساب‌های دریافتنی", children: collTree(rkRaw, "cashBank", "خریدار") },
    fut: { key: "fut", label: "چک‌های آینده (۱۲ ماه)", value: futCh, go: "receivedCheques", note: "چک دریافتی که سررسیدش نرسیده", children:
      (rec.data?.by_channel || []).map((c: any) => {
        const sys = c.channel === "b2b" ? "rahkaran" : "karamad";
        return { key: c.channel, label: c.channel === "b2b" ? "نمایندگان (راهکاران)" : "شعب (کارآمد)", value: Number(c.definite_rial || 0), go: "receivedCheques",
          note: `${fa(c.count)} چک · اتکاپذیر ${fa(Math.round(c.reliance_percent || 0))}٪`,
          children: (rec.data?.customers || []).filter((x: any) => x.system === sys).sort((a: any, b: any) => b.definite_rial - a.definite_rial).slice(0, 25).map((x: any) => ({
            key: x.customer_key || x.customer_code, label: x.customer_name, value: Number(x.definite_rial || 0), go: "receivedCheques",
            file: x.system === "rahkaran" ? repFile(x.customer_code) : undefined,
            note: `${fa(x.count)} چک · نزدیک‌ترین سررسید ${faDigits(x.nearest_due_date_jalali || "—")}`,
            children: [{ key: "rel", label: "اتکاپذیر (احتمال وصول)", value: Number(x.reliance_rial || 0), go: "receivedCheques" },
              { key: "risk", label: "ریسک وصول", value: Number(x.collection_risk_rial || 0), go: "receivedCheques" }] })) };
      }) },
    open: { key: "open", label: "مطالبات باز", value: openRecv, go: "customers", note: "مانده بدهی + چک برگشتی راهکاران (همان پرونده مشتری) + مانده دفتر کل شعب", children: [
      { key: "rb", label: "مانده بدهی مشتریان راهکاران", value: Number(rr?.balance_rial || 0), go: "/files/rahkaran", note: rr ? `${fa(rr.debtor_count)} مشتری بدهکار` : undefined,
        children: (rr?.top || []).filter((x: any) => x.balance_rial > 0).map((x: any) => ({ key: x.code, label: x.name, value: Number(x.balance_rial), go: "/files/rahkaran", file: repFile(x.code),
          note: `کد ${faDigits(x.code)}${x.open_cheques_rial ? ` · چک باز در دست ${shortToman(x.open_cheques_rial)}` : ""}`,
          children: [{ key: "b", label: "مانده حساب", value: Number(x.balance_rial || 0), go: "/files/rahkaran" }, { key: "r", label: "چک برگشتی", value: Number(x.returned_rial || 0), go: "/files/rahkaran" },
            { key: "o", label: "سررسیدگذشته باز", value: Number(x.overdue_rial || 0), go: "/files/rahkaran" }] })) },
      { key: "rr", label: "حساب چک برگشتی راهکاران", value: Number(rr?.returned_rial || 0), go: "/files/rahkaran",
        children: rows((rr?.top || []).filter((x: any) => x.returned_rial > 0), (x) => x.name, (x) => x.returned_rial, "/files/rahkaran", (x) => `کد ${faDigits(x.code)}`) },
      { key: "k", label: "مانده دفتر کل مشتریان شعب (کارآمد)", value: kmDebt, go: "/files/hybrids", note: `${fa(sm.active_customer_count)} مشتری فعال · چک برگشتی داخل همین مانده است`,
        children: (network.data?.branches || []).filter((b: any) => Number(b.debt?.open_account_receivable_rial) > 0).sort((a: any, b: any) => b.debt.open_account_receivable_rial - a.debt.open_account_receivable_rial).map((b: any) => ({
          key: b.branch_name, label: b.branch_name, value: Number(b.debt.open_account_receivable_rial), go: "/files/hybrids", file: hybFile(b.branch_name), note: `${fa(b.debt.debtor_customer_count)} مشتری بدهکار`,
          children: [{ key: "d", label: "مانده بدهی مشتریان", value: Number(b.debt.open_account_receivable_rial || 0), go: "/files/hybrids" },
            { key: "c", label: "بستانکاری مشتریان (کسر شده)", value: Number(b.debt.customer_credit_rial || 0), go: "/files/hybrids" },
            { key: "q", label: "چک باز در دست", value: Number(b.open_cheque_amount_rial || 0), go: "/files/hybrids" }] })) },
    ] },
    und: { key: "und", label: "چک‌های تعیین تکلیف نشده", value: stUnd.data?.amount_rial ?? null, go: "receivedCheques", note: stUnd.data?.rule, children: chequeTree(stUnd.data) },
    ret: { key: "ret", label: "چک‌های برگشتی", value: stRet.data?.amount_rial ?? null, go: "receivedCheques", note: stRet.data?.rule, children: chequeTree(stRet.data) },
    iss: { key: "iss", label: "چک پرداختی ۳۰ روز آینده", value: Number(iss.data?.kpis?.horizon?.amount_rial || 0), go: "issuedCheques", children: [
      { key: "payee", label: "به تفکیک دریافت‌کننده", value: Number(iss.data?.kpis?.horizon?.amount_rial || 0), go: "issuedCheques",
        children: payeeTree({ cheques: (iss.data?.cheques || []).filter((c: any) => c.days_to_due >= 0) }) },
      { key: "r", label: "راهکاران", value: issBySys("rahkaran"), go: "issuedCheques" },
      { key: "k", label: "کارآمد", value: issBySys("karamad"), go: "issuedCheques" },
    ] },
    pay: { key: "pay", label: "بدهی به تأمین‌کنندگان", value: payBal == null ? null : payBal + Number(issOpen || 0), go: "payables", children: [
      { key: "bal", label: "مانده حساب (خرید بدون چک)", value: payBal, go: "payables", children: creditorTree() },
      { key: "chq", label: "چک‌های پرداختی باز", value: issOpen, go: "issuedCheques",
        note: iss365.data ? `آینده ${shortToman(iss365.data?.kpis?.horizon?.amount_rial)} · سررسیدگذشته ${shortToman(iss365.data?.kpis?.overdue?.amount_rial)}` : undefined,
        children: payeeTree(iss365.data) },
    ] },
    tin: { key: "tin", label: `وصول و واریز امروز ${faDigits(tIn?.date_jalali || "")}`, value: tIn?.amount_rial ?? null, go: "cashBank",
      note: "نقد و حواله‌ای که امروز واقعاً وارد صندوق و بانک شده؛ چک دریافتی جداست", children: [
      ...(tIn?.systems || []).map((sy: any) => ({ key: sy.key, label: sy.label, value: Number(sy.amount_rial || 0), go: "cashBank",
        note: sy.amount_rial ? `${fa(sy.count)} واریز` : sy.last_day_jalali ? `رسید تأییدشده امروز هنوز نیست · آخرین ${faDigits(sy.last_day_jalali)}` : undefined,
        children: (sy.groups || []).map((g: any) => ({ key: g.key, label: g.label, value: Number(g.amount_rial || 0), go: "cashBank", note: `${fa(g.count)} واریز`,
          children: sy.key === "karamad"
            // کارآمد: شعبه ← مشتری ← نقد/حواله
            ? groupBy(g.items, (x) => x.branch).map(([br, xs]) => ({ key: `b:${br}`, label: br, value: sumV(xs), go: "/hybrid", file: hybFile(br), note: `${fa(xs.length)} مشتری`,
                children: xs.map((x: any, i: number) => ({ key: `${i}:${x.code}`, label: x.name, value: Number(x.amount_rial), go: "/hybrid", note: `کد ${faDigits(x.code || "—")}`,
                  children: Object.entries(x.by_method || {}).map(([m, v]) => ({ key: m, label: METHOD[m] || m, value: Number(v), go: "cashBank" })) })) })).sort((a, b) => b.value - a.value)
            // راهکاران: مشتری ← نقد/حواله
            : g.items.map((x: any, i: number) => ({ key: `${i}:${x.code}`, label: x.name, value: Number(x.amount_rial), go: "cashBank", file: repFile(x.code), note: `کد ${faDigits(x.code || "—")} · ${fa(x.count)} سند`,
                children: Object.entries(x.by_method || {}).map(([m, v]) => ({ key: m, label: METHOD[m] || m, value: Number(v), go: "cashBank" })) })) })) })),
      ...(recToday ? [{ key: "rec", label: "چک دریافتی سررسید امروز (هنوز جدا، در انتظار وصول)", value: recToday, go: "receivedCheques", note: `${fa(rec.data?.kpis?.today?.count)} چک` }] : []),
    ] },
    tpay: { key: "tpay", label: "امروز باید پرداخت کنی", value: Number(iss.data?.kpis?.today?.amount_rial || 0), go: "issuedCheques",
      note: "چک‌های صادرشده با سررسید امروز؛ موجودی حساب‌ها را برای پاس شدنشان چک کنید", children: [
      { key: "due", label: "سررسید امروز", value: Number(iss.data?.kpis?.today?.amount_rial || 0), go: "issuedCheques", note: `${fa(issDueToday.length)} چک`, children: payeeTree({ cheques: issDueToday }) },
      { key: "late", label: "سررسیدگذشته و هنوز پاس‌نشده", value: issOverdueAmt, go: "issuedCheques", note: `${fa(issOverdue.length)} چک`, children: payeeTree({ cheques: issOverdue }) },
    ] },
    paync: { key: "paync", label: "بدهی باز بدون چک", value: payBal, go: "payables", note: "جنس و خدمت خریده‌شده که هنوز چکی بابتش داده نشده", children: creditorTree() },
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
          return <button key={k.key} type="button" className={`mo-tile ${k.tone || "neutral"} ${phase} ${drill?.[0] === k.key ? "open" : ""}`} style={{ animationDelay: `${i * 70}ms` }}
            onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); e.currentTarget.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`); e.currentTarget.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`); }}
            onClick={() => openDrill(k.key)} aria-expanded={drill?.[0] === k.key} aria-label={`${k.label} — نمایش ریز`}>
            <span className="mo-tile-top"><small>{k.label}</small><em className={k.domain === "مالی" ? "fin" : k.domain === "روند" ? "ops" : "sales"}>{k.domain}</em></span>
            <b>{k.value === null ? (k.error ? <span className="mo-err">{k.error}</span> : <span className="mo-shimmer" />) : <CountUp value={k.value} format={k.format} run={phase !== "wait"} />}</b>
            {k.value !== null && k.unit && <span className="mo-unit">{k.unit}</span>}
            {k.value !== null && k.about && <span className="mo-about">{k.about}</span>}
            {k.value !== null && k.parts && k.parts.length > 0 && <Parts parts={k.parts} run={phase !== "wait"} />}
            {k.value !== null && k.foot && <span className="mo-hint">{k.foot}</span>}
            <span className="mo-tile-go" aria-hidden>{drill?.[0] === k.key ? "▴" : "▾"}</span>
            <i className="mo-tile-glow" aria-hidden />
          </button>;
        })}
      </div>
      <div ref={drillRef}>
        {drill && drills[drill[0]] && <DrillPanel root={drills[drill[0]]} path={drill} setPath={setDrill} go={go} about={allTiles.find((x) => x.key === drill[0])?.about} guide={GUIDES[drill[0]]} />}
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
              list: { title: "بزرگ‌ترین مشتریان ۱۲ ماه آینده", rows: peekRows([...(rec.data?.customers || [])].sort((a: any, b: any) => b.definite_rial - a.definite_rial),
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
