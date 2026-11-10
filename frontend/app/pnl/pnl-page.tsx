"use client";
// صورت سود و زیان (P&L) — همان سه اکسل مالی (هیبرید، B2B، صادرات) با همان چیدمان: برندها در ستون، ردیف‌های سود و زیان،
// جمع دوره، «On sales» و دوره‌های قبل؛ به‌علاوه نمودار آبشاری، ساختار هزینه هر برند و جزئیات همه شیت‌ها.
// پیش‌فرض «لایو از SQL» (راهکاران + کارآمد، app/services/pnl_live_service.py) با ستون مقایسه اکسل؛
// «اکسل» همان فایل‌های پوشه مشترک (app/services/pnl_service.py).
// Backend: GET /api/v1/finance/pnl/{hybrid|b2b|export}?source=live|excel&period=1405-Q2
import { useEffect, useMemo, useRef, useState } from "react";
import "./pnl.css";
import { PnlSheet, SheetCards, comparablePeriod } from "./pnl-sheet";
import type { BrandParts, PeriodParts, PeriodCustomers } from "./pnl-sheet";

type Row = { label: string; code: string | null; kind: "line" | "total" | "ratio" | "share"; canon: string | null; group: string | null; source?: string | null;
  values: Record<string, number | null>; periods: Record<string, { value: number | null; ratio: number | null }> };
type Report = { brands: string[]; periods: { key: string; label: string; has_ratio: boolean; comparable?: boolean }[]; rows: Row[];
  settings: { method?: string; return_mode?: string; channel?: string; cost_multiplier?: number }; unit: string };
type PivotT = { title: string; key_labels: string[]; measure_labels: string[]; rows: { keys: string[]; values: number[]; count: number }[];
  total: number[]; total_count: number; row_count: number; truncated: boolean };
type Cell = string | number | null;
type TreeT = { columns: string[]; pct_columns?: number[]; child_columns: string[]; child_pct_columns?: number[];
  rows: { cells: Cell[]; children: Cell[][] }[]; total?: Cell[] };
type Detail = { key: string; title: string; source: string; pivots?: PivotT[]; table?: { columns: string[]; rows: Cell[][] }; tree?: TreeT };
type Channel = { status: "ready" | "building" | "missing" | "error"; key: string; title: string; message?: string; elapsed?: number; stale?: boolean;
  modified?: string; source?: { file: string }; report?: Report; details?: Detail[];
  live?: boolean; refreshing?: boolean; warnings?: string[]; period?: Period; excel?: { label: string; modified?: string } | null;
  brand_parts?: BrandParts; period_parts?: PeriodParts; period_customers?: PeriodCustomers };
type Period = { key: string; label: string; from: string; to: string; complete: boolean; default?: boolean };
type Source = "live" | "excel";
type Unit = "mrial" | "btoman";

const API = () => `/api/v1/finance/pnl`;
const CHANNELS = [["all", "تجمیعی"], ["hybrid", "هیبرید"], ["b2b", "B2B"], ["export", "صادرات"]] as const;
type ChannelKey = (typeof CHANNELS)[number][0];
const nf0 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const pct = (v: number | null | undefined, d = 1) => (v == null || !isFinite(v) ? "—" : `${new Intl.NumberFormat("fa-IR", { maximumFractionDigits: d }).format(v * 100)}٪`);
/** مقادیر گزارش «میلیون ریال» است؛ میلیارد تومان = ÷ ۱۰٬۰۰۰ */
const fmt = (v: number | null | undefined, unit: Unit) => {
  if (v == null || !isFinite(v)) return "—";
  if (unit === "btoman") return nf1.format(v / 1e4);
  return nf0.format(v);
};
const unitLabel = (u: Unit) => (u === "mrial" ? "میلیون ریال" : "میلیارد تومان");
const faDigits = (s: unknown) => String(s ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
/** زمان تغییر فایل (ISO) ← «۱۹ مهر ۱۴۰۵، ۱۸:۳۰» */
const jalaliStamp = (iso: string) => {
  try { return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)); }
  catch { return faDigits(iso); }
};
const reduceMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const WATERFALL: { canon: string; label: string; sign: 1 | -1 | 0 }[] = [
  { canon: "gross", label: "فروش ناخالص", sign: 0 }, { canon: "return", label: "برگشت", sign: -1 }, { canon: "discount", label: "تخفیفات", sign: -1 },
  { canon: "net", label: "فروش خالص", sign: 0 }, { canon: "cogs", label: "بهای تمام شده", sign: -1 }, { canon: "gp", label: "سود ناخالص", sign: 0 },
  { canon: "opex", label: "هزینه‌های عملیاتی", sign: -1 }, { canon: "op", label: "سود عملیاتی", sign: 0 }, { canon: "tax", label: "مالیات", sign: -1 },
  { canon: "np", label: "سود خالص", sign: 0 },
];
const CANON_FA: Record<string, string> = { qty: "فروش خالص (تعداد)", gross: "فروش ناخالص", return: "برگشت از فروش", discount: "تخفیفات", net: "فروش خالص",
  vat: "ارزش افزوده", cogs: "بهای تمام شده", gp: "سود ناخالص", opex: "هزینه‌های عملیاتی", op: "سود عملیاتی", tax: "مالیات", np: "سود خالص" };

async function getJson(url: string) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

function CountUp({ value, render }: { value: number; render: (v: number) => string }) {
  const [shown, setShown] = useState(reduceMotion() ? value : 0);
  useEffect(() => {
    if (reduceMotion()) { setShown(value); return; }
    const start = performance.now(), dur = 900;
    let raf = 0;
    const tick = (t: number) => { const k = Math.min(1, (t - start) / dur); setShown(value * (1 - Math.pow(1 - k, 3))); if (k < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    const done = window.setTimeout(() => setShown(value), dur + 150);
    return () => { cancelAnimationFrame(raf); window.clearTimeout(done); };
  }, [value]);
  return <>{render(shown)}</>;
}

/** هر کانال: یک بار دریافت؛ اگر در حال ساخت است هر ۵ ثانیه دوباره می‌پرسد. لایو: هر ۱۰ دقیقه خودکار تازه می‌شود. */
function useChannels(source: Source, period: string | null) {
  const [data, setData] = useState<Record<string, Channel>>({});
  const [error, setError] = useState("");
  const timer = useRef<number | null>(null);
  const ready = source === "excel" || !!period;
  const load = (rebuild = false) => {
    if (!ready) return;
    const q = new URLSearchParams({ source, ...(source === "live" && period ? { period } : {}), ...(rebuild ? { rebuild: "true" } : {}) });
    (["hybrid", "b2b", "export"] as const).forEach((k) => getJson(`${API()}/${k}?${q}`)
      .then((j) => setData((d) => ({ ...d, [k]: j })))
      .catch((e) => setError(e instanceof Error ? e.message : "خطا")));
  };
  useEffect(() => {
    setData({}); setError(""); load();
    const t = source === "live" ? window.setInterval(() => { if (document.visibilityState === "visible") load(); }, 600_000) : 0;
    return () => { if (timer.current) window.clearTimeout(timer.current); if (t) window.clearInterval(t); };
  }, [source, period]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const building = Object.values(data).some((c) => c.status === "building" || c.refreshing);
    if (!building) return;
    timer.current = window.setTimeout(() => load(), 5000);
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, reload: load };
}

/** دوره‌های گزارش لایو (فصل‌های سال شمسی تا امروز + کل سال)؛ پیش‌فرض آخرین فصل کامل‌شده */
function usePeriods() {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    getJson(API()).then((j) => { setPeriods(j.periods || []); if (j.periods_error) setError(j.periods_error); })
      .catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);
  return { periods, error };
}

/** گزارش تجمیعی سه کانال: ردیف‌های اصلی و گروه‌های کالای بهای تمام شده، برای دوره جاری و همه دوره‌های مقایسه
 *  مشترک سه کانال (مثلاً ریز فصل‌ها و کل سال قبل)؛ ستون مقایسه اکسل نمی‌آید. */
function combine(channels: Channel[]): { report: Report; byChannel: Record<string, Record<string, number | null>> } | null {
  const ready = channels.filter((c) => c.report);
  if (!ready.length) return null;
  const brands = Array.from(new Set(ready.flatMap((c) => c.report!.brands)));
  const canons = ["qty", "gross", "return", "discount", "net", "cogs", "gp", "opex", "op", "tax", "np"];
  // دوره‌ها به ترتیب کانال اول؛ فقط آن‌هایی که هر سه کانال دارند (با برچسب یکسان)
  const plist = ready[0].report!.periods.filter((p) => p.key !== "excel"
    && ready.every((c) => c.report!.periods.some((q) => q.key === p.key && q.label === p.label)));
  const byChannel: Record<string, Record<string, number | null>> = {};
  const sumRow = (label: string, find: (rs: Row[]) => Row | undefined, kind: Row["kind"], canon: string | null, group: string | null): Row => {
    const values: Record<string, number | null> = {};
    const per: Row["periods"] = {};
    plist.forEach((p) => { per[p.key] = { value: 0, ratio: null }; });
    ready.forEach((c) => {
      const r = find(c.report!.rows);
      if (canon) byChannel[canon] = { ...(byChannel[canon] || {}), [c.key]: r ? r.periods.p0?.value ?? null : null };
      brands.forEach((b) => { values[b] = (values[b] || 0) + Number(r?.values[b] || 0); });
      plist.forEach((p) => { per[p.key].value = Number(per[p.key].value || 0) + Number(r?.periods[p.key]?.value || 0); });
    });
    return { label, code: null, kind, canon, group, values, periods: per } as Row;
  };
  const rows: Row[] = canons.map((canon) => sumRow(CANON_FA[canon], (rs) => rs.find((x) => x.canon === canon),
    ["net", "gp", "opex", "op", "np"].includes(canon) ? "total" : "line", canon, null));
  const groups = Array.from(new Set(ready.flatMap((c) => c.report!.rows.filter((r) => r.group === "cogs_group").map((r) => r.label))));
  const groupRows = groups.map((g) => sumRow(g, (rs) => rs.find((x) => x.group === "cogs_group" && x.label === g), "line", null, "cogs_group"))
    .sort((a, b) => Number(b.periods.p0?.value || 0) - Number(a.periods.p0?.value || 0));
  const at = rows.findIndex((r) => r.canon === "cogs") + 1;
  rows.splice(at, 0, ...groupRows);
  const net = rows.find((r) => r.canon === "net")!, np = rows.find((r) => r.canon === "np")!;
  const gross = rows.find((r) => r.canon === "gross")!, cogs = rows.find((r) => r.canon === "cogs")!;
  const margin: Row = { label: "حاشیه سود خالص", code: null, kind: "ratio", canon: "margin", group: null,
    values: Object.fromEntries(brands.map((b) => [b, net.values[b] ? Number(np.values[b] || 0) / Number(net.values[b]) : null])),
    periods: Object.fromEntries(plist.map((p) => [p.key, { value: net.periods[p.key]?.value ? Number(np.periods[p.key].value) / Number(net.periods[p.key].value) : null, ratio: null }])) };
  rows.forEach((r) => plist.forEach((p) => {
    const base = r.group === "cogs_group" ? cogs : r.canon === "discount" ? gross : net;
    const den = Number(base.periods[p.key]?.value);
    if (r.kind !== "ratio" && r.canon !== "qty" && den) r.periods[p.key].ratio = Number(r.periods[p.key].value || 0) / den;
  }));
  const periods = plist.map((p, i) => ({ ...p, label: i === 0 ? `جمع سه کانال · ${p.label}` : p.label, has_ratio: true }));
  return { report: { brands, periods, rows: [...rows, margin], settings: {}, unit: "میلیون ریال" }, byChannel };
}

export default function PnlPage() {
  const [source, setSource] = useState<Source>("live");
  const { periods, error: periodError } = usePeriods();
  const [period, setPeriod] = useState<string | null>(null);
  useEffect(() => { if (!period && periods.length) setPeriod((periods.find((p) => p.default) || periods[0]).key); }, [periods, period]);
  const { data, error, reload } = useChannels(source, period);
  const live = source === "live";
  const [channel, setChannel] = useState<ChannelKey>("all");
  const [unit, setUnit] = useState<Unit>("mrial");
  const ch = channel === "all" ? null : data[channel];
  const combined = useMemo(() => combine(["hybrid", "b2b", "export"].map((k) => data[k]).filter(Boolean)), [data]);
  const report = channel === "all" ? combined?.report : ch?.report;
  const building = Object.values(data).filter((c) => c.status === "building");

  return <section className="pnl">
    <header className="pnl-hero">
      <span className="pnl-orb a" /><span className="pnl-orb b" />
      <div>
        <small>Exir Kadus · Profit &amp; Loss statement</small>
        <h2>صورت سود و زیان (P&amp;L)</h2>
        <p>{live
          ? "همان چیدمان اکسل مالی به تفکیک برند، ولی لایو از SQL: B2B و صادرات از اسناد و فاکتورهای راهکاران، هیبرید از فاکتورهای کارآمد. ستون «اکسل» برای مقایسه کنار هر ردیف است."
          : "همان گزارش‌های اکسل مالی، به تفکیک برند. اعداد مستقیم از فایل‌های P&L پوشه مشترک خوانده می‌شوند و با تغییر فایل خودکار به‌روز می‌شوند."}</p>
      </div>
      <div className="pnl-hero-tools">
        <div className="pnl-seg" role="tablist" aria-label="منبع">
          {([["live", "● لایو از SQL"], ["excel", "اکسل"]] as [Source, string][]).map(([k, label]) =>
            <button key={k} type="button" className={`${source === k ? "on" : ""}${k === "live" ? " live" : ""}`} onClick={() => setSource(k)}>{label}</button>)}
        </div>
        {live && periods.length > 0 && <select className="pnl-period" value={period || ""} onChange={(e) => setPeriod(e.target.value)} aria-label="دوره">
          {periods.map((p) => <option key={p.key} value={p.key}>{faDigits(p.label)}{p.complete ? "" : " (جاری)"}
            {/^\d{4}$/.test(p.key) ? " — ریز فصل‌ها + کل سال قبل" : ""}</option>)}
        </select>}
        <div className="pnl-seg" role="tablist" aria-label="واحد">
          {(["btoman", "mrial"] as Unit[]).map((u) => <button key={u} type="button" className={unit === u ? "on" : ""} onClick={() => setUnit(u)}>{unitLabel(u)}</button>)}
        </div>
        <button type="button" className="pnl-refresh" onClick={() => reload(true)} title={live ? "دوباره خواندن از SQL" : "دوباره خواندن فایل‌ها از پوشه مشترک"}>
          {live ? "↻ خواندن دوباره از SQL" : "↻ خواندن دوباره فایل‌ها"}</button>
      </div>
    </header>

    {/* نه <nav>: استایل سراسری منوی کناری روی nav اعمال می‌شود */}
    <div className="pnl-tabs" role="tablist" aria-label="کانال">
      {CHANNELS.map(([k, label]) => {
        const c = k === "all" ? null : data[k];
        return <button key={k} type="button" role="tab" aria-selected={channel === k} className={channel === k ? "on" : ""} onClick={() => setChannel(k)}>
          {label}
          {c?.status === "building" && <i className="pnl-spin" aria-label="در حال خواندن" />}
          {c?.modified && <small>{c.live ? "SQL" : "فایل"}: {jalaliStamp(c.modified)}</small>}
        </button>;
      })}
    </div>

    {(error || periodError) && <div className="profile-warning">{error || periodError}</div>}
    {building.length > 0 && <div className="pnl-building"><i className="pnl-spin" />در حال خواندن {building.map((b) => b.title || b.key).join("، ")} {live ? "از SQL" : "از اکسل"}… {building.map((b) => b.message).filter(Boolean).join(" · ")}
      <small>{live ? " (چند ثانیه؛ نتیجه ۱۰ دقیقه نگه داشته می‌شود)" : " (فایل هیبرید حدود یک تا دو دقیقه؛ بعد از آن تا تغییر فایل آنی است)"}</small></div>}
    {live && (() => {
      const notes = (channel === "all" ? Object.values(data) : ch ? [ch] : []).flatMap((c) => (c.warnings || []).map((w) => `${c.title}: ${w}`));
      return notes.length > 0 && <details className="pnl-notes"><summary>ⓘ {faDigits(notes.length)} نکته درباره منبع اعداد لایو</summary>
        <ul>{notes.map((n) => <li key={n}>{faDigits(n)}</li>)}</ul></details>;
    })()}
    {ch && (ch.status === "missing" || ch.status === "error") && <div className="profile-warning">{ch.message}</div>}

    {!report ? <div className="pnl-skeleton">{Array.from({ length: 6 }).map((_, i) => <i key={i} style={{ animationDelay: `${i * 90}ms` }} />)}</div> : ch ? <>
      {/* صفحه اول هر کانال: همان شمایل شیت Report اکسل */}
      <SheetCards report={report} unit={unit} />
      <PnlSheet report={report} unit={unit} brandParts={ch.brand_parts} details={ch.details}
        periodParts={ch.period_parts} periodCustomers={ch.period_customers} />
      <div className="pnl-grid">
        <Waterfall report={report} unit={unit} />
        <BrandStructure report={report} />
      </div>
      {ch.details && <Details details={ch.details} />}
    </> : <>
      <Kpis report={report} unit={unit} />
      {channel === "all" && combined && <ChannelSplit byChannel={combined.byChannel} unit={unit} data={data} />}
      <div className="pnl-grid">
        <Waterfall report={report} unit={unit} />
        <BrandStructure report={report} />
      </div>
      <PnlTable report={report} unit={unit} title="صورت سود و زیان تجمیعی (هیبرید + B2B + صادرات)"
        source={live ? `لایو از SQL${period ? ` · ${faDigits(period.replace("-", " "))}` : ""}` : undefined} />
    </>}
  </section>;
}

function canonRow(report: Report, canon: string) { return report.rows.find((r) => r.canon === canon); }
function periodValue(row: Row | undefined, key: string) { return row?.periods[key]?.value ?? null; }

function Kpis({ report, unit }: { report: Report; unit: Unit }) {
  const cmp = comparablePeriod(report);
  const p0 = report.periods[0]?.key, p1 = cmp?.key;
  const items = [
    { canon: "gross", label: "فروش ناخالص", tone: "sales" }, { canon: "net", label: "فروش خالص", tone: "sales" },
    { canon: "gp", label: "سود ناخالص", tone: "good", ratio: "net" }, { canon: "opex", label: "هزینه‌های عملیاتی", tone: "cost", ratio: "net" },
    { canon: "op", label: "سود عملیاتی", tone: "good", ratio: "net" }, { canon: "np", label: "سود خالص", tone: "profit", ratio: "net" },
  ];
  return <div className="pnl-kpis">
    {items.map((k, i) => {
      const row = canonRow(report, k.canon);
      const v = periodValue(row, p0);
      if (v == null) return null;
      const base = k.ratio ? periodValue(canonRow(report, k.ratio), p0) : null;
      const prev = p1 ? periodValue(row, p1) : null;
      const prevBase = p1 && k.ratio ? periodValue(canonRow(report, k.ratio), p1) : null;
      const m = base ? v / base : null, pm = prevBase && prev != null ? prev / prevBase : null;
      return <article key={k.canon} className={`pnl-kpi ${k.tone}`} style={{ animationDelay: `${i * 70}ms` }}>
        <small>{k.label}</small>
        <b><CountUp value={v} render={(x) => fmt(x, unit)} /></b>
        <span>{unitLabel(unit)}{m != null && <> · <em>{pct(m)}</em> از فروش خالص</>}</span>
        {p1 && prev != null && <i className={`pnl-delta ${m != null && pm != null ? (m >= pm ? "up" : "down") : ""}`}>
          {cmp?.label}: {fmt(prev, unit)}{pm != null ? ` (${pct(pm)})` : ""}</i>}
      </article>;
    })}
  </div>;
}

function ChannelSplit({ byChannel, unit, data }: { byChannel: Record<string, Record<string, number | null>>; unit: Unit; data: Record<string, Channel> }) {
  const keys = ["hybrid", "b2b", "export"];
  const order = ["gross", "return", "discount", "net", "cogs", "gp", "opex", "op", "tax", "np"];
  const max = Math.max(1, ...keys.map((k) => Math.abs(Number(byChannel.gross?.[k] || 0))));
  return <article className="pnl-card">
    <header><h3>سهم هر کانال</h3><small>دوره جاری هر فایل · {unitLabel(unit)}</small></header>
    <div className="pnl-split">
      {keys.map((k, i) => {
        const net = Number(byChannel.net?.[k] || 0), np = Number(byChannel.np?.[k] || 0);
        return <div key={k} className={`pnl-split-col c${i}`}>
          <b>{data[k]?.title || k}</b>
          <span className="pnl-split-bar"><i style={{ width: `${(100 * Math.abs(Number(byChannel.gross?.[k] || 0))) / max}%` }} /></span>
          {order.map((c) => <div key={c} className={`pnl-split-row${["net", "gp", "op", "np"].includes(c) ? " strong" : ""}`}><span>{CANON_FA[c]}</span><b>{fmt(byChannel[c]?.[k], unit)}</b></div>)}
          <div className="pnl-split-row margin"><span>حاشیه سود خالص</span><b>{net ? pct(np / net) : "—"}</b></div>
        </div>;
      })}
    </div>
  </article>;
}

function Waterfall({ report, unit }: { report: Report; unit: Unit }) {
  const p0 = report.periods[0]?.key;
  const steps = WATERFALL.map((s) => ({ ...s, v: Number(periodValue(canonRow(report, s.canon), p0) ?? 0) })).filter((s) => s.sign === 0 || s.v !== 0);
  const W = 640, H = 260, pad = 30, top = 16, bottom = 54;
  const max = Math.max(1, ...steps.map((s) => Math.abs(s.v)));
  const bw = (W - pad * 2) / steps.length;
  const y = (v: number) => top + (H - top - bottom) * (1 - v / max);
  let running = 0;
  const bars = steps.map((s) => {
    let from: number, to: number;
    if (s.sign === 0) { from = 0; to = s.v; running = s.v; } else { from = running; to = running - s.v; running = to; }
    return { ...s, from, to };
  });
  const [hover, setHover] = useState<number | null>(null);
  return <article className="pnl-card">
    <header><h3>از فروش تا سود خالص</h3><small>دوره جاری · {unitLabel(unit)}</small></header>
    <div className="pnl-wf-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="pnl-wf" role="img" aria-label="نمودار آبشاری سود و زیان">
        <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} className="pnl-wf-base" />
        {bars.map((b, i) => {
          const x = W - pad - bw * (i + 1) + 6, hi = Math.max(b.from, b.to), lo = Math.min(b.from, b.to);
          const cls = b.sign === 0 ? (b.canon === "np" ? "profit" : "subtotal") : "minus";
          return <g key={b.canon} onMouseEnter={() => setHover(i)}>
            <rect x={x} y={y(hi)} width={bw - 12} height={Math.max(1.5, y(lo) - y(hi))} rx={4} className={`pnl-wf-bar ${cls}`} style={{ animationDelay: `${i * 80}ms` }} />
            {i < bars.length - 1 && <line x1={x} x2={x - 12} y1={y(b.to)} y2={y(b.to)} className="pnl-wf-link" />}
            <text x={x + (bw - 12) / 2} y={H - bottom + 16} className="pnl-wf-label">{b.label}</text>
            <text x={x + (bw - 12) / 2} y={y(hi) - 5} className="pnl-wf-val">{b.sign === -1 ? "−" : ""}{fmt(Math.abs(b.v), unit)}</text>
          </g>;
        })}
      </svg>
      {hover !== null && <div className="pnl-tip">{bars[hover].label}: <b>{fmt(Math.abs(bars[hover].v), unit)}</b> {unitLabel(unit)}
        {(() => { const net = Number(periodValue(canonRow(report, "net"), p0) || 0); return net ? <> · {pct(Math.abs(bars[hover].v) / net)} فروش خالص</> : null; })()}</div>}
    </div>
  </article>;
}

/** «از هر ۱۰۰ تومان فروش ناخالص هر برند»: برگشت، تخفیف، بهای تمام شده، هزینه، مالیات و سود */
function BrandStructure({ report }: { report: Report }) {
  const parts = [["return", "برگشت", "#f59e0b"], ["discount", "تخفیف", "#a78bfa"], ["cogs", "بهای تمام شده", "#64748b"], ["opex", "هزینه", "#fb7185"], ["tax", "مالیات", "#38bdf8"], ["np", "سود خالص", "#22c55e"]] as const;
  const gross = canonRow(report, "gross"), net = canonRow(report, "net"), np = canonRow(report, "np");
  const brands = report.brands.filter((b) => Number(gross?.values[b] || 0) > 0)
    .sort((a, b) => Number(np?.values[b] || 0) / Math.max(1, Number(net?.values[b] || 0)) - Number(np?.values[a] || 0) / Math.max(1, Number(net?.values[a] || 0)));
  return <article className="pnl-card">
    <header><h3>از هر ۱۰۰ تومان فروش ناخالص هر برند</h3><small>مرتب از بیشترین حاشیه سود خالص</small></header>
    <div className="pnl-legend">{parts.map(([, l, c]) => <span key={l}><i style={{ background: c }} />{l}</span>)}</div>
    <div className="pnl-struct">
      {brands.map((b, i) => {
        const g = Number(gross?.values[b] || 0);
        const m = Number(net?.values[b] || 0) ? Number(np?.values[b] || 0) / Number(net?.values[b]) : null;
        return <div key={b} className="pnl-struct-row" style={{ animationDelay: `${i * 50}ms` }}>
          <span className="pnl-struct-name">{b}</span>
          <span className="pnl-struct-bar">{parts.map(([c, l, color]) => {
            const v = Math.max(0, Number(canonRow(report, c)?.values[b] || 0));
            return v > 0 ? <i key={c} style={{ width: `${(100 * v) / g}%`, background: color }} title={`${l}: ${pct(v / g)}`} /> : null;
          })}</span>
          <b className={m != null && m < 0 ? "neg" : ""}>{pct(m)}</b>
        </div>;
      })}
    </div>
  </article>;
}

function PnlTable({ report, unit, title, source }: { report: Report; unit: Unit; title: string; source?: string }) {
  const [openDiscount, setOpenDiscount] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [openGroups, setOpenGroups] = useState(true);
  const hasDetail = report.rows.some((r) => r.group === "discount_detail");
  const hasGroups = report.rows.some((r) => r.group === "cogs_group");
  const cell = (r: Row, v: number | null | undefined) => r.kind === "ratio" || r.kind === "share" ? pct(v, r.kind === "share" ? 1 : 1) : fmt(v, unit);
  const rows = report.rows.filter((r) => (r.group !== "discount_detail" || openDiscount) && (r.group !== "cogs_group" || openGroups));
  const s = report.settings;
  return <article className="pnl-card pnl-table-card">
    <header>
      <h3>{title}</h3>
      <small>{unitLabel(unit)}{source ? ` · ${source}` : ""}</small>
      <div className="pnl-chips">
        {s.method && <span title="روش تخصیص هزینه در اکسل">{s.method}</span>}
        {s.return_mode && <span title="فروش با/بدون برگشتی">{s.return_mode === "WithReturn" ? "با برگشت از فروش" : "بدون برگشت"}</span>}
        {s.cost_multiplier && <span title="ضریب بهای تمام شده در اکسل">ضریب بهای تمام شده {nf1.format(s.cost_multiplier)}</span>}
        {hasDetail && <button type="button" onClick={() => setOpenDiscount(!openDiscount)}>{openDiscount ? "▾ بستن ریز تخفیفات" : "▸ ریز انواع تخفیف"}</button>}
        {hasGroups && <button type="button" onClick={() => setOpenGroups(!openGroups)}
          title="درصد کنار هر گروه = سهمش از کل بهای تمام شده">{openGroups ? "▾ بستن گروه‌های کالا" : "▸ بهای تمام شده به تفکیک گروه کالا"}</button>}
      </div>
    </header>
    <div className="pnl-table-wrap">
      <table className="pnl-table">
        <thead><tr>
          <th className="sticky">شرح</th>
          {report.brands.map((b) => <th key={b} className={focus === b ? "focus" : ""} onClick={() => setFocus(focus === b ? null : b)} title="برجسته کردن ستون">{b}</th>)}
          {report.periods.map((p, i) => <th key={p.key} className={`period${i === 0 ? " current" : ""}`} colSpan={p.has_ratio ? 2 : 1}>{faDigits(p.label)}</th>)}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => <tr key={`${r.label}-${i}`} className={`k-${r.kind}${r.group ? ` g-${r.group}` : ""}${r.canon ? ` c-${r.canon}` : ""}`}>
            <th className="sticky" title={r.source || undefined}>{r.code && <small>{faDigits(r.code)}</small>}{r.label}{r.source && <i className="pnl-src">ⓘ</i>}</th>
            {report.brands.map((b) => {
              const v = r.values[b];
              return <td key={b} className={`${focus === b ? "focus" : ""}${v != null && v < 0 ? " neg" : ""}`}>{cell(r, v)}</td>;
            })}
            {report.periods.map((p, pi) => {
              const pv = r.periods[p.key];
              return [<td key={`${p.key}v`} className={`period${pi === 0 ? " current" : ""}${pv?.value != null && pv.value < 0 ? " neg" : ""}`}>{cell(r, pv?.value)}</td>,
                p.has_ratio ? <td key={`${p.key}r`} className="ratio">{pv?.ratio != null ? pct(pv.ratio) : ""}</td> : null];
            })}
          </tr>)}
        </tbody>
      </table>
    </div>
  </article>;
}

function Details({ details }: { details: Detail[] }) {
  const [tab, setTab] = useState(details[0]?.key);
  const d = details.find((x) => x.key === tab) || details[0];
  if (!d) return null;
  return <article className="pnl-card">
    <header><h3>جزئیات شیت‌های اکسل</h3><small>هر شیت، خلاصه‌شده؛ روی عنوان ستون بزنید تا مرتب شود.</small></header>
    <div className="pnl-subtabs" role="tablist">{details.map((x) => <button key={x.key} type="button" role="tab" aria-selected={x.key === d.key} className={x.key === d.key ? "on" : ""} onClick={() => setTab(x.key)}>{x.title}<small>{x.source}</small></button>)}</div>
    {d.pivots?.map((p) => <PivotView key={`${d.key}-${p.title}`} p={p} />)}
    {d.table && <TableView key={d.key} t={d.table} />}
    {d.tree && <TreeView key={d.key} t={d.tree} />}
  </article>;
}

/** جدول باز شدنی: هر ردیف (مثلاً گروه کالا با سهمش از بهای تمام شده) با کلیک ریز خودش (کالاها) را نشان می‌دهد. */
function TreeView({ t }: { t: TreeT }) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [q, setQ] = useState("");
  const show = (v: Cell, isPct: boolean) => v == null ? "" : isPct ? pct(Number(v)) : typeof v === "number" ? nf0.format(v) : faDigits(v);
  const s = q.trim();
  const rows = t.rows.map((r, i) => ({ r, i, kids: s ? r.children.filter((c) => c.join(" ").includes(s)) : r.children }))
    .filter(({ r, kids }) => !s || String(r.cells[0]).includes(s) || kids.length);
  const toggle = (i: number) => setOpen((o) => { const n = new Set(o); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const pctCol = (cols: number[] | undefined, j: number) => !!cols?.includes(j);
  const maxShare = Math.max(1e-9, ...t.rows.map((r) => Number(r.cells[t.pct_columns?.[0] ?? -1] || 0)));
  return <section className="pnl-pivot pnl-tree">
    <div className="pnl-pivot-head"><b>{faDigits(t.rows.length)} گروه</b><small>روی هر گروه بزنید تا ریز کالاهایش باز شود</small>
      <button type="button" className="pnl-tree-all" onClick={() => setOpen(open.size ? new Set() : new Set(t.rows.map((_, i) => i)))}>
        {open.size ? "بستن همه" : "باز کردن همه"}</button>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجوی گروه یا کالا…" aria-label="جستجو" /></div>
    <div className="pnl-pivot-wrap"><table>
      <thead><tr><th aria-hidden />{t.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map(({ r, i, kids }) => {
        const isOpen = open.has(i) || (!!s && kids.length > 0);
        return [<tr key={`g${i}`} className={`pnl-tree-row${isOpen ? " open" : ""}`} onClick={() => toggle(i)} tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(i); } }} aria-expanded={isOpen}>
          <td className="pnl-tree-caret">{isOpen ? "▾" : "▸"}</td>
          {r.cells.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>
            {pctCol(t.pct_columns, j) && v != null && <i className="pnl-inbar" style={{ width: `${(100 * Number(v)) / maxShare}%` }} />}
            <span>{show(v, pctCol(t.pct_columns, j))}</span></td>)}
        </tr>,
        isOpen ? <tr key={`c${i}`} className="pnl-tree-kids"><td />
          <td colSpan={t.columns.length}><table>
            <thead><tr>{t.child_columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{kids.slice(0, 300).map((c, k) => <tr key={k}>{c.map((v, j) =>
              <td key={j} className={typeof v === "number" ? "num" : ""}>{show(v, pctCol(t.child_pct_columns, j))}</td>)}</tr>)}</tbody>
          </table>{kids.length > 300 && <small className="muted">{faDigits(kids.length - 300)} کالای دیگر؛ با جستجو محدود کنید.</small>}</td>
        </tr> : null];
      })}</tbody>
      {t.total && <tfoot><tr><th />{t.total.map((v, j) => <th key={j} className="num">{j === 0 ? "جمع کل" : show(v, pctCol(t.pct_columns, j))}</th>)}</tr></tfoot>}
    </table></div>
  </section>;
}

function PivotView({ p }: { p: PivotT }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ i: number; dir: 1 | -1 }>({ i: 0, dir: -1 });
  const rows = useMemo(() => {
    const s = q.trim();
    const list = p.rows.filter((r) => !s || r.keys.join(" ").includes(s));
    return [...list].sort((a, b) => sort.dir * ((a.values[sort.i] || 0) - (b.values[sort.i] || 0)));
  }, [p, q, sort]);
  const max = Math.max(1, ...rows.map((r) => Math.abs(r.values[sort.i] || 0)));
  const big = (v: number) => (Math.abs(v) >= 1e9 ? `${nf1.format(v / 1e10)} میلیارد ت` : nf0.format(v));
  return <section className="pnl-pivot">
    <div className="pnl-pivot-head"><b>{p.title}</b><small>{faDigits(p.row_count)} ردیف{p.truncated ? ` (${faDigits(p.rows.length)} بزرگ‌ترین)` : ""}</small>
      {p.rows.length > 8 && <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو…" aria-label={`جستجو در ${p.title}`} />}</div>
    <div className="pnl-pivot-wrap"><table>
      <thead><tr>{p.key_labels.map((k) => <th key={k}>{k}</th>)}
        {p.measure_labels.map((m, i) => <th key={m} className="num sortable" onClick={() => setSort({ i, dir: sort.i === i ? (-sort.dir as 1 | -1) : -1 })}>{m}{sort.i === i ? (sort.dir < 0 ? " ▾" : " ▴") : ""}</th>)}
        <th className="num">تعداد ردیف</th></tr></thead>
      <tbody>{rows.slice(0, 300).map((r, i) => <tr key={i}>
        {r.keys.map((k, j) => <td key={j}>{faDigits(k)}</td>)}
        {r.values.map((v, j) => <td key={j} className={`num${v < 0 ? " neg" : ""}`} title={nf0.format(v)}>
          {j === sort.i && <i className="pnl-inbar" style={{ width: `${(100 * Math.abs(v)) / max}%` }} />}<span>{big(v)}</span></td>)}
        <td className="num muted">{faDigits(r.count)}</td>
      </tr>)}</tbody>
      <tfoot><tr><th colSpan={p.key_labels.length}>جمع کل</th>{p.total.map((v, j) => <th key={j} className="num" title={nf0.format(v)}>{big(v)}</th>)}<th className="num">{faDigits(p.total_count)}</th></tr></tfoot>
    </table></div>
  </section>;
}

function TableView({ t }: { t: { columns: string[]; rows: (string | number | null)[][] } }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => t.rows.filter((r) => !q.trim() || r.join(" ").includes(q.trim())), [t, q]);
  return <section className="pnl-pivot">
    <div className="pnl-pivot-head"><b>{faDigits(t.rows.length)} ردیف</b><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="جستجو…" aria-label="جستجو" /></div>
    <div className="pnl-pivot-wrap"><table>
      <thead><tr>{t.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.slice(0, 400).map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : ""}>
        {typeof v === "number" ? (Math.abs(v) > 1e6 || Number.isInteger(v) ? nf0.format(v) : nf1.format(v)) : faDigits(v ?? "")}</td>)}</tr>)}</tbody>
    </table></div>
    {rows.length > 400 && <small className="muted">{faDigits(rows.length - 400)} ردیف دیگر؛ با جستجو محدود کنید.</small>}
  </section>;
}
