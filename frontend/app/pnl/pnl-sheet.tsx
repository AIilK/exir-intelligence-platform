"use client";
// نمای «صفحه اول» هر کانال (هیبرید، B2B، صادرات) دقیقاً با شمایل شیت Report اکسل P&L:
// سه کارت TOTAL REVENUE / GROSS PROFIT / OPEX، سربرگ سرمه‌ای «Exir Kadus»، ردیف قرمز برندها،
// ستون جمع دوره + On sales و دوره‌های مقایسه، ردیف‌های اصلی سرمه‌ای و جمع‌ها با خط پررنگ.
// انیمیشن: شمارش اعداد کارت‌ها، ورود پله‌ای ردیف‌ها، نوار داده (data bar) برندها در ردیف‌های اصلی،
// هایلایت سطر و ستون زیر نشانگر، و چشمک سلول‌هایی که با به‌روزرسانی لایو عوض شده‌اند.
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import "./pnl-sheet.css";

type Row = { label: string; kind: "line" | "total" | "ratio" | "share"; canon: string | null; group: string | null; source?: string | null; ratio_base?: string | null;
  values: Record<string, number | null>; periods: Record<string, { value: number | null; ratio: number | null; brands?: Record<string, number | null> | null }> };
type Report = { brands: string[]; periods: { key: string; label: string; has_ratio: boolean; comparable?: boolean }[]; rows: Row[]; unit: string };
/** اولین دوره مقایسه هم‌طول با دوره جاری (فصل با فصل، سال با سال)؛ ستون‌های ریز فصل‌ها برای «رشد» به کار نمی‌روند. */
export const comparablePeriod = (r: { periods: { key: string; label: string; comparable?: boolean }[] }) =>
  r.periods.slice(1).find((p) => p.comparable !== false);
type Unit = "mrial" | "btoman";

const nfEn = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nfEn1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const num = (v: number | null | undefined, unit: Unit) => {
  if (v == null || !isFinite(v)) return "";
  if (unit === "btoman") return nfEn1.format(v / 1e4);
  return nfEn.format(v);
};
const pctCell = (v: number | null | undefined) => (v == null || !isFinite(v) ? "" : `${Math.round(v * 100)}%`);
const unitText = (u: Unit) => (u === "mrial" ? "[MillionRials]" : "[Billion Tomans]");
const reduceMotion = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// ردیف‌های «سرفصل» با برچسب سرمه‌ای، مثل اکسل
const HEAD_CANONS = new Set(["cogs", "gp", "op", "tax", "np", "margin"]);
const TOTAL_CANONS = new Set(["net", "gp", "opex", "op", "np"]);
// ردیف‌هایی که سهم هر برند با نوار داده (مثل Conditional Formatting اکسل) نشان داده می‌شود
const BAR_CANONS: Record<string, string> = { gross: "sales", net: "sales", gp: "profit", op: "profit", np: "profit", cogs: "cost", opex: "cost",
  cogs_std: "std", gp_std: "profit" };

/** شمارش نرم عدد از مقدار قبلی به مقدار جدید (easeOutCubic)؛ با تب پنهان هم به عدد نهایی می‌رسد. */
function useCountUp(value: number | null, ms = 1100) {
  const [shown, setShown] = useState<number | null>(reduceMotion() ? value : value == null ? null : 0);
  const from = useRef(0);
  useEffect(() => {
    if (value == null) { setShown(null); return; }
    if (reduceMotion()) { setShown(value); from.current = value; return; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      setShown(a + (value - a) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const done = window.setTimeout(() => setShown(value), ms + 150);
    from.current = value;
    return () => { cancelAnimationFrame(raf); window.clearTimeout(done); };
  }, [value, ms]);
  return shown;
}

function SheetCard({ title, tone, value, prev, prevLabel, ratio, ratioLabel, unit, delay }: {
  title: string; tone: string; value: number | null; prev: number | null; prevLabel?: string; ratio: number | null; ratioLabel: string; unit: Unit; delay: number;
}) {
  const shown = useCountUp(value);
  const growth = value != null && prev ? (value - prev) / Math.abs(prev) : null;
  // برای OPEX افزایش بد است
  const good = growth == null ? null : tone === "cost" ? growth <= 0 : growth >= 0;
  return <div className={`xl-card ${tone}`} style={{ animationDelay: `${delay}ms` }}>
    <i className="xl-card-shine" aria-hidden />
    <small>{title}</small>
    <b>{num(shown, unit)}</b>
    {ratio != null && <span className="xl-card-ratio">
      <em style={{ "--w": `${Math.max(0, Math.min(100, ratio * 100))}%` } as CSSProperties} />
      {pctCell(ratio)} {ratioLabel}
    </span>}
    {growth != null && <span className={`xl-card-delta ${good ? "up" : "down"}`}>
      {growth >= 0 ? "▲" : "▼"} {Math.abs(Math.round(growth * 100))}% <small>vs {prevLabel}</small>
    </span>}
  </div>;
}

export function SheetCards({ report, unit }: { report: Report; unit: Unit }) {
  const cmp = comparablePeriod(report);
  const p0 = report.periods[0]?.key, p1 = cmp?.key;
  const row = (canon: string) => report.rows.find((r) => r.canon === canon);
  const v = (canon: string, p?: string) => (p ? row(canon)?.periods[p]?.value ?? null : null);
  const net = v("net", p0);
  const cards = [
    { title: "TOTAL REVENUE", tone: "sales", canon: "net", ratio: null as number | null, ratioLabel: "" },
    { title: "GROSS PROFIT", tone: "profit", canon: "gp", ratio: net ? (v("gp", p0) ?? 0) / net : null, ratioLabel: "margin" },
    { title: "OPEX", tone: "cost", canon: "opex", ratio: net ? (v("opex", p0) ?? 0) / net : null, ratioLabel: "of sales" },
  ];
  return <div className="xl-cards">
    {cards.map((c, i) => <SheetCard key={c.title} title={c.title} tone={c.tone} value={v(c.canon, p0)} prev={v(c.canon, p1)}
      prevLabel={cmp?.label} ratio={c.ratio} ratioLabel={c.ratioLabel} unit={unit} delay={i * 110} />)}
  </div>;
}

/** ریز کالاهای هر برند: [کد، نام، گروه کالا، تعداد خالص، بهای تمام شده (م.ر)] */
export type BrandParts = Record<string, [string, string, string, number, number][]>;
type CellT = string | number | null;
type DetailLite = { key: string; table?: { columns: string[]; rows: CellT[][] } };

/** مخرج درصد کوچک کنار سلول برند: همان مبنای «On sales» ولی برای همان برند. فروش خالص = سهم برند از کل. */
function brandBase(report: Report, r: Row, brand: string): { den: number | null; hint: string } {
  if (r.kind === "ratio" || r.kind === "share" || r.canon === "qty") return { den: null, hint: "" };
  if (r.canon === "net") {
    const t = report.brands.reduce((s, b) => s + Number(r.values[b] || 0), 0);
    return { den: t || null, hint: "سهم این برند از کل فروش خالص" };
  }
  const canon = r.ratio_base || "net";
  const base = report.rows.find((x) => x.canon === canon);
  const den = base ? Number(base.values[brand] || 0) : 0;
  const name = canon === "gross" ? "فروش ناخالص" : canon === "cogs" ? "بهای تمام شده" : "فروش خالص";
  return { den: den || null, hint: `نسبت به ${name} همین برند` };
}

/** ریز کالاهای هر دوره (جمع برندها): [کد، نام، گروه کالا، تعداد خالص، بهای تمام شده، برندها] */
export type PeriodParts = Record<string, [string, string, string, number, number, string][]>;
/** مشتریان هر دوره: [کد، مشتری، برند، فروش ناخالص، برگشت، تخفیف، فروش خالص] */
export type PeriodCustomers = Record<string, CellT[][]>;

export function PnlSheet({ report, unit, company = "Exir Kadus", brandParts, details, periodParts, periodCustomers }: {
  report: Report; unit: Unit; company?: string; brandParts?: BrandParts; details?: DetailLite[];
  periodParts?: PeriodParts; periodCustomers?: PeriodCustomers }) {
  const [pick, setPick] = useState<{ row: Row; brand: string } | null>(null);
  const [pickP, setPickP] = useState<{ row: Row; period: string } | null>(null);
  const [openDiscount, setOpenDiscount] = useState(true);
  const [openGroups, setOpenGroups] = useState(true);
  const [hotCol, setHotCol] = useState<string | null>(null);
  const [barsOn, setBarsOn] = useState(false);
  const prevValues = useRef<Map<string, number | null>>(new Map());
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const hasDetail = report.rows.some((r) => r.group === "discount_detail");
  const hasGroups = report.rows.some((r) => r.group === "cogs_group");
  const rows = report.rows.filter((r) => (r.group !== "discount_detail" || openDiscount) && (r.group !== "cogs_group" || openGroups));
  const periods = report.periods;
  // تعداد (Net Sales QqtY) عدد است نه مبلغ؛ با واحد مبلغ تقسیم نمی‌شود
  const cell = (r: Row, v: number | null | undefined) => (r.kind === "ratio" || r.kind === "share" ? pctCell(v)
    : r.canon === "qty" ? (v == null ? "" : nfEn.format(v)) : num(v, unit));

  // نوارهای داده بعد از اولین نقاشی از صفر رشد می‌کنند
  useEffect(() => {
    setBarsOn(false);
    const t = window.setTimeout(() => setBarsOn(true), reduceMotion() ? 0 : 450);
    return () => window.clearTimeout(t);
  }, [report]);

  // سلول‌هایی که با خواندن تازه از SQL عوض شده‌اند یک بار چشمک می‌زنند
  useEffect(() => {
    const next = new Map<string, number | null>(), diff = new Set<string>();
    report.rows.forEach((r) => {
      const k = r.canon || r.label;
      const put = (col: string, v: number | null | undefined) => {
        const id = `${k}|${col}`, val = v ?? null;
        if (prevValues.current.size && prevValues.current.has(id) && prevValues.current.get(id) !== val) diff.add(id);
        next.set(id, val);
      };
      report.brands.forEach((b) => put(b, r.values[b]));
      report.periods.forEach((p) => put(p.key, r.periods[p.key]?.value));
    });
    prevValues.current = next;
    if (!diff.size) return;
    setChanged(diff);
    const t = window.setTimeout(() => setChanged(new Set()), 2200);
    return () => window.clearTimeout(t);
  }, [report]);

  return <article className="xl-wrap" onMouseLeave={() => setHotCol(null)}>
    {hasDetail && <button type="button" className="xl-toggle" onClick={() => setOpenDiscount(!openDiscount)}>
      {openDiscount ? "▾ بستن ریز انواع تخفیف" : "▸ نمایش ریز انواع تخفیف"}</button>}
    {hasGroups && <button type="button" className="xl-toggle" onClick={() => setOpenGroups(!openGroups)}
      title="درصد ستون On sales این ردیف‌ها = سهم هر گروه از کل بهای تمام شده؛ ریز کالاهای هر گروه در «جزئیات» پایین صفحه">
      {openGroups ? "▾ بستن گروه‌های کالا (بهای تمام شده)" : "▸ بهای تمام شده به تفکیک گروه کالا"}</button>}
    <div className="xl-scroll">
      <table className="xl-sheet" dir="ltr">
        <thead>
          <tr className="xl-band">
            <th rowSpan={2} className="xl-title"><b>{company}</b><span>Profit &amp; Loss statement</span><span>{unitText(unit)}</span></th>
            <th colSpan={report.brands.length} className="xl-band-brands"><i className="xl-sweep" aria-hidden /></th>
            {periods.map((p, i) => <th key={p.key} colSpan={p.has_ratio ? 2 : 1} className={`xl-band-period${i === 0 ? " cur" : ""}`} />)}
          </tr>
          <tr className="xl-red">
            {report.brands.map((b, i) => <th key={b} className={hotCol === b ? "hot" : ""} style={{ "--i": i } as CSSProperties}
              onMouseEnter={() => setHotCol(b)}>{b}</th>)}
            {periods.map((p, i) => [<th key={p.key} className={`xl-plabel${i === 0 ? " cur" : ""}${hotCol === p.key ? " hot" : ""}`}
              style={{ "--i": report.brands.length + i } as CSSProperties} onMouseEnter={() => setHotCol(p.key)}>{p.label}</th>,
              p.has_ratio ? <th key={`${p.key}r`} className="xl-onsales">On sales</th> : null])}
          </tr>
        </thead>
        <tbody className={barsOn ? "bars-on" : ""}>
          {rows.map((r, i) => {
            const isHead = !!r.canon && HEAD_CANONS.has(r.canon);
            const isTotal = r.kind === "total" || (!!r.canon && TOTAL_CANONS.has(r.canon));
            const isShare = r.kind === "share";
            const bar = r.canon ? BAR_CANONS[r.canon] : undefined;
            const maxV = bar ? Math.max(0, ...report.brands.map((b) => Math.abs(Number(r.values[b] || 0)))) : 0;
            const key = r.canon || r.label;
            const cls = ["xl-row", isHead ? "head" : "", isTotal ? "total" : "", isShare ? "share" : "", r.kind === "ratio" ? "ratio" : "",
              r.group === "discount_detail" ? "detail" : "", r.group === "cogs_std" ? "detail std-detail" : "",
              r.group === "cogs_group" ? "detail cogs-group" : "",
              r.canon === "cogs_std" || r.canon === "gp_std" ? "std" : "", r.canon ? `c-${r.canon}` : ""].filter(Boolean).join(" ");
            const label = isShare ? "Opex" : r.label;
            return <tr key={`${r.label}-${i}`} className={cls} style={{ "--i": Math.min(i, 40) } as CSSProperties}>
              <th dir="auto" title={r.source || undefined}>{label}</th>
              {report.brands.map((b) => {
                const v = r.values[b];
                const w = bar && maxV && v != null ? Math.abs(v) / maxV : isShare && v != null ? Number(v) : 0;
                const { den, hint } = brandBase(report, r, b);
                const share = den && v ? Number(v) / den : null;
                const clickable = r.kind !== "ratio" && !isShare && v != null && v !== 0;
                return <td key={b} onMouseEnter={() => setHotCol(b)} onClick={clickable ? () => setPick({ row: r, brand: b }) : undefined}
                  title={clickable ? `${hint ? `${pct1(share)} ${hint} · ` : ""}کلیک: جزئیات` : undefined}
                  className={[v != null && v < 0 ? "neg" : "", hotCol === b ? "hot" : "", changed.has(`${key}|${b}`) ? "chg" : "",
                    clickable ? "clk" : ""].filter(Boolean).join(" ")}>
                  {(bar || isShare) && w > 0 && <i className={`xl-bar ${bar || "share"}`} style={{ "--w": `${Math.min(1, w) * 100}%` } as CSSProperties} />}
                  <span>{cell(r, v)}</span>
                  {share != null && isFinite(share) && Math.abs(share) >= 0.0005 && <small className="xl-cpct">{pctSmall(share)}</small>}
                </td>;
              })}
              {periods.map((p, pi) => {
                const pv = r.periods[p.key];
                const v = isShare ? null : pv?.value;
                const pclk = p.key !== "excel" && r.kind !== "ratio" && v != null && v !== 0;
                return [<td key={`${p.key}v`} onMouseEnter={() => setHotCol(p.key)}
                  onClick={pclk ? () => setPickP({ row: r, period: p.key }) : undefined} title={pclk ? "کلیک: جزئیات این دوره" : undefined}
                  className={[`pv${pi === 0 ? " cur" : ""}`, v != null && v < 0 ? "neg" : "", hotCol === p.key ? "hot" : "",
                    changed.has(`${key}|${p.key}`) ? "chg" : "", pclk ? "clk" : ""].filter(Boolean).join(" ")}><span>{cell(r, v)}</span></td>,
                  p.has_ratio ? <td key={`${p.key}r`} className={`pr${hotCol === p.key ? " hot" : ""}`}>
                    {r.kind === "ratio" || isShare || r.canon === "qty" ? "" : pctCell(pv?.ratio)}</td> : null];
              })}
            </tr>;
          })}
        </tbody>
      </table>
    </div>
    {pick && <CellDetail report={report} row={pick.row} brand={pick.brand} unit={unit} brandParts={brandParts} details={details}
      onPick={(row, brand) => setPick({ row, brand })} onClose={() => setPick(null)} />}
    {pickP && <PeriodDetail report={report} row={pickP.row} period={pickP.period} unit={unit} parts={periodParts?.[pickP.period]}
      customers={periodCustomers?.[pickP.period]} onPick={(row, period) => setPickP({ row, period })}
      onBrand={(row, brand) => { setPickP(null); setPick({ row, brand }); }} onClose={() => setPickP(null)} />}
  </article>;
}

const pctSmall = (v: number) => {
  const a = Math.abs(v) * 100;
  return `${v < 0 ? "-" : ""}${a >= 10 ? Math.round(a) : a.toFixed(1).replace(/\.0$/, "")}%`;
};
const pct1 = (v: number | null | undefined) => (v == null || !isFinite(v) ? "—" : pctSmall(v));
const SUMMARY: [string, string][] = [["gross", "فروش ناخالص"], ["discount", "تخفیفات"], ["return", "برگشت"], ["net", "فروش خالص"],
  ["cogs", "بهای تمام شده"], ["gp", "سود ناخالص"], ["opex", "هزینه‌های عملیاتی"], ["op", "سود عملیاتی"], ["np", "سود خالص"]];
type Drill = { title: string; cols: string[]; rows: CellT[][]; pct: number; valCol: number; groups?: boolean };

/** پنجره جزئیات یک سلول برند: درصدها، مقایسه با برندهای دیگر، خلاصه سود و زیان برند، و ریز گروه/کالا/مشتری. */
function CellDetail({ report, row, brand, unit, brandParts, details, onPick, onClose }: {
  report: Report; row: Row; brand: string; unit: Unit; brandParts?: BrandParts; details?: DetailLite[];
  onPick: (row: Row, brand: string) => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const v = Number(row.values[brand] || 0);
  const isQty = row.canon === "qty";
  const fmtV = (x: number | null | undefined) => (isQty ? (x == null ? "—" : nfEn.format(x)) : num(x, unit) || "—");
  const total = report.brands.reduce((s, b) => s + Number(row.values[b] || 0), 0);
  const { den, hint } = brandBase(report, row, brand);
  const totalRatio = row.periods[report.periods[0]?.key]?.ratio ?? null;
  const ranked = [...report.brands].filter((b) => row.values[b]).sort((a, b) => Math.abs(Number(row.values[b])) - Math.abs(Number(row.values[a])));
  const maxAbs = Math.max(1e-9, ...ranked.map((b) => Math.abs(Number(row.values[b]))));
  const val = (canon: string) => { const r = report.rows.find((x) => x.canon === canon); return r ? Number(r.values[brand] || 0) : null; };
  const net = val("net");

  // ریز: گروه‌ها/کالاهای این برند (بهای تمام شده، تعداد) یا مشتریان این برند (فروش B2B/صادرات)
  const parts = brandParts?.[brand] || [];
  const isGroup = row.group === "cogs_group";
  const custT = details?.find((d) => d.key === "customers")?.table;
  let drill: Drill | null = null;
  if (isGroup) {
    const list = parts.filter((p) => p[2] === row.label);
    const tot = list.reduce((s, p) => s + Number(p[4] || 0), 0) || 1;
    drill = { title: `کالاهای گروه «${row.label}» در ${brand}`, cols: ["کد", "نام کالا", "تعداد خالص", "بهای تمام شده", "سهم از گروه"],
      rows: list.map((p) => [p[0], p[1], p[3], p[4], Number(p[4] || 0) / tot]), pct: 4, valCol: 3 };
  } else if ((row.canon === "cogs" || isQty) && parts.length) {
    const vi = isQty ? 3 : 4;
    const tot = parts.reduce((s, p) => s + Number(p[vi] || 0), 0) || 1;
    if (q) {
      drill = { title: `کالاهای ${brand}`, cols: ["کد", "نام کالا", "گروه", "تعداد خالص", "بهای تمام شده", isQty ? "سهم از تعداد" : "سهم"],
        rows: parts.map((p) => [...p, Number(p[vi] || 0) / tot]), pct: 5, valCol: 4 };
    } else {
      const g = new Map<string, [number, number, number]>();
      parts.forEach((p) => { const x = g.get(p[2]) || [0, 0, 0]; x[0] += 1; x[1] += p[3]; x[2] += p[4]; g.set(p[2], x); });
      drill = { title: `گروه‌های کالای ${brand}`, groups: true,
        cols: ["گروه کالا", "تعداد کالا", "تعداد خالص", "بهای تمام شده", isQty ? "سهم از تعداد" : "سهم از بهای تمام شده"],
        rows: [...g.entries()].map(([k, x]) => [k, x[0], x[1], x[2], (isQty ? x[1] : x[2]) / tot] as CellT[])
          .sort((a, b) => Number(b[4]) - Number(a[4])), pct: 4, valCol: 3 };
    }
  } else if (custT && ["gross", "net", "discount", "return"].includes(row.canon || "")) {
    const ci = ({ gross: 3, return: 4, discount: 5, net: 6 } as Record<string, number>)[row.canon as string];
    const list = custT.rows.filter((c) => c[2] === brand && Number(c[ci] || 0) !== 0).sort((a, b) => Number(b[ci]) - Number(a[ci]));
    const tot = list.reduce((s, c) => s + Number(c[ci] || 0), 0) || 1;
    drill = { title: `مشتریان ${brand}`, cols: ["کد", "مشتری", custT.columns[ci], "سهم"],
      rows: list.map((c) => [c[0], c[1], c[ci], Number(c[ci] || 0) / tot]), pct: 3, valCol: 2 };
  }
  const ql = q.toLowerCase();
  const shown = drill ? drill.rows.filter((r) => !q || drill!.groups || r.some((c) => String(c ?? "").toLowerCase().includes(ql))) : [];
  const groupRow = (label: string) => report.rows.find((x) => x.group === "cogs_group" && x.label === label);

  return <div className="xl-modal" role="dialog" aria-modal="true" aria-label={`${row.label} — ${brand}`} onClick={onClose}>
    <div className="xl-modal-box" dir="rtl" onClick={(e) => e.stopPropagation()}>
      <header>
        <div><small>{report.periods[0]?.label}</small><h3><bdi>{row.label}</bdi> · <bdi>{brand}</bdi></h3></div>
        <button type="button" onClick={onClose} aria-label="بستن">✕</button>
      </header>
      <div className="xl-modal-stats">
        <div><small>مبلغ{isQty ? " (تعداد)" : ""}</small><b dir="ltr">{fmtV(v)}</b></div>
        {den != null && <div><small>{hint}</small><b dir="ltr">{pct1(v / den)}</b></div>}
        {row.canon !== "net" && total !== 0 && <div><small>سهم {brand} از کل این ردیف</small><b dir="ltr">{pct1(v / total)}</b></div>}
        {totalRatio != null && !isQty && <div><small>همین نسبت برای همه برندها</small><b dir="ltr">{pct1(totalRatio)}</b></div>}
        {ranked.includes(brand) && <div><small>رتبه بین برندها</small><b>{ranked.indexOf(brand) + 1} از {ranked.length}</b></div>}
      </div>

      <section>
        <h4>مقایسه با برندهای دیگر</h4>
        <div className="xl-mbars">
          {ranked.map((b) => {
            const x = Number(row.values[b]); const d = brandBase(report, row, b).den;
            return <button type="button" key={b} className={b === brand ? "on" : ""} onClick={() => onPick(row, b)}>
              <span>{b}</span><i><em className={x < 0 ? "neg" : ""} style={{ width: `${(Math.abs(x) / maxAbs) * 100}%` }} /></i>
              <b dir="ltr">{fmtV(x)}</b><small dir="ltr">{d ? pct1(x / d) : ""}</small>
            </button>;
          })}
        </div>
      </section>

      {net != null && <section>
        <h4>خلاصه سود و زیان {brand} <small>(درصد = نسبت به فروش خالص)</small></h4>
        <div className="xl-msum">
          {SUMMARY.map(([c, l]) => {
            const x = val(c); const r = report.rows.find((z) => z.canon === c);
            return x == null || !r ? null : <button type="button" key={c} className={row.canon === c ? "on" : ""} onClick={() => { setQ(""); onPick(r, brand); }}>
              <span>{l}</span><b dir="ltr" className={x < 0 ? "neg" : ""}>{num(x, unit)}</b><small dir="ltr">{c === "net" ? "" : net ? pct1(x / net) : ""}</small></button>;
          })}
        </div>
      </section>}

      {drill && <section>
        <h4>{drill.title} <small>({shown.length})</small>
          <input type="search" placeholder={drill.groups || (!isGroup && q) ? "جستجوی کالا…" : "جستجو…"} value={q} onChange={(e) => setQ(e.target.value)} /></h4>
        {drill.groups && <p className="xl-mnote">روی هر گروه کلیک کنید تا کالاهایش باز شود؛ یا نام/کد کالا را جستجو کنید.</p>}
        <div className="xl-mtable"><table>
          <thead><tr>{drill.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{shown.slice(0, 400).map((r, i) => {
            const gr = drill!.groups ? groupRow(String(r[0])) : undefined;
            return <tr key={i} className={gr ? "clk" : ""} onClick={gr ? () => { setQ(""); onPick(gr, brand); } : undefined}>
              {r.map((c, j) => <td key={j} dir={typeof c === "number" ? "ltr" : "auto"}>
                {j === drill!.pct ? <span className="xl-mpct"><em style={{ width: `${Math.min(100, Math.abs(Number(c)) * 100)}%` }} />{pct1(Number(c))}</span>
                  : typeof c === "number" ? (j === drill!.valCol ? num(c, unit) : nfEn.format(c)) : c}</td>)}
            </tr>;
          })}</tbody>
        </table></div>
        {shown.length > 400 && <p className="xl-mnote">۴۰۰ ردیف اول نمایش داده شد؛ برای بقیه جستجو کنید.</p>}
      </section>}
      {!drill && (row.canon === "cogs" || isGroup) && <p className="xl-mnote">ریز کالاها بعد از «خواندن دوباره از SQL» نمایش داده می‌شود.</p>}
      {row.source && <p className="xl-mnote">منبع: {row.source}</p>}
    </div>
  </div>;
}

/** ردیف‌های زیرمجموعه هر ردیف اصلی (برای ریز در پنجره دوره) */
function childRows(report: Report, r: Row): Row[] {
  const g = r.canon === "cogs" ? ["cogs_group"] : r.canon === "discount" ? ["discount_detail"] : r.canon === "cogs_std" ? ["cogs_std"]
    : r.canon === "opex" ? ["opex", "پورسانت"] : [];
  return g.length ? report.rows.filter((x) => x.group && g.includes(x.group) && x.kind === "line") : [];
}
function parentRow(report: Report, r: Row): Row | undefined {
  const c = r.group === "cogs_group" ? "cogs" : r.group === "discount_detail" ? "discount" : r.group === "cogs_std" ? "cogs_std"
    : r.group === "opex" || r.group === "پورسانت" ? "opex" : null;
  return c ? report.rows.find((x) => x.canon === c) : undefined;
}

/** پنجره جزئیات یک سلول دوره (۱۴۰۵، فصل‌ها، ۱۴۰۴): روند دوره‌ها، سهم برندها، ریز ردیف (گروه کالا/نوع تخفیف/هزینه) و ریز کالا یا مشتری. */
function PeriodDetail({ report, row, period, unit, parts, customers, onPick, onBrand, onClose }: {
  report: Report; row: Row; period: string; unit: Unit; parts?: [string, string, string, number, number, string][]; customers?: CellT[][];
  onPick: (row: Row, period: string) => void; onBrand: (row: Row, brand: string) => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  useEffect(() => { setQ(""); }, [row, period]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const isQty = row.canon === "qty";
  const fmtV = (x: number | null | undefined) => (isQty ? (x == null ? "—" : nfEn.format(x)) : num(x, unit) || "—");
  const pmeta = report.periods.find((p) => p.key === period);
  const pv = row.periods[period];
  const v = Number(pv?.value || 0);
  const brandsOf = (r: Row | undefined) => (r ? (period === "p0" ? r.values : r.periods[period]?.brands) || null : null);
  const bv = brandsOf(row);
  const baseRow = row.canon === "net" ? null : report.rows.find((x) => x.canon === (row.ratio_base || "net"));
  const baseB = brandsOf(baseRow || undefined);
  const baseName = (row.ratio_base || "net") === "gross" ? "فروش ناخالص" : row.ratio_base === "cogs" ? "بهای تمام شده" : "فروش خالص";
  const ranked = bv ? report.brands.filter((b) => bv[b]).sort((a, b) => Math.abs(Number(bv[b])) - Math.abs(Number(bv[a]))) : [];
  const maxB = Math.max(1e-9, ...ranked.map((b) => Math.abs(Number(bv![b]))));
  const trend = report.periods.map((p) => ({ p, x: row.periods[p.key]?.value ?? null, r: row.periods[p.key]?.ratio ?? null }));
  const maxT = Math.max(1e-9, ...trend.map((t) => Math.abs(Number(t.x || 0))));
  const kids = childRows(report, row).map((k) => ({ k, x: Number(k.periods[period]?.value || 0) })).filter((k) => k.x)
    .sort((a, b) => Math.abs(b.x) - Math.abs(a.x));
  const parent = parentRow(report, row);
  const pval = parent ? Number(parent.periods[period]?.value || 0) : 0;

  // ریز کالا (بهای تمام شده، تعداد، گروه کالا) یا مشتری (فروش B2B/صادرات)
  const isGroup = row.group === "cogs_group";
  let drill: Drill | null = null;
  if (parts && parts.length && (isGroup || row.canon === "cogs" || isQty)) {
    const vi = isQty ? 3 : 4;
    const list = isGroup ? parts.filter((x) => x[2] === row.label) : parts;
    const tot = list.reduce((s2, x) => s2 + Number(x[vi] || 0), 0) || 1;
    if (isGroup || q) {
      drill = { title: isGroup ? `کالاهای گروه «${row.label}»` : "کالاها", cols: ["کد", "نام کالا", "گروه", "برند", "تعداد خالص", "بهای تمام شده", "سهم"],
        rows: list.map((x) => [x[0], x[1], x[2], x[5], x[3], x[4], Number(x[vi] || 0) / tot]), pct: 6, valCol: 5 };
    } else if (isQty) {
      const g = new Map<string, [number, number, number]>();
      list.forEach((x) => { const t = g.get(x[2]) || [0, 0, 0]; t[0] += 1; t[1] += x[3]; t[2] += x[4]; g.set(x[2], t); });
      drill = { title: "تعداد به تفکیک گروه کالا", groups: true, cols: ["گروه کالا", "تعداد کالا", "تعداد خالص", "بهای تمام شده", "سهم از تعداد"],
        rows: [...g.entries()].map(([k, t]) => [k, t[0], t[1], t[2], t[1] / tot] as CellT[]).sort((a, b) => Number(b[4]) - Number(a[4])), pct: 4, valCol: 3 };
    }
  } else if (customers && ["gross", "net", "discount", "return"].includes(row.canon || "")) {
    const ci = ({ gross: 3, return: 4, discount: 5, net: 6 } as Record<string, number>)[row.canon as string];
    const list = customers.filter((c) => Number(c[ci] || 0) !== 0).sort((a, b) => Number(b[ci]) - Number(a[ci]));
    const tot = list.reduce((s2, c) => s2 + Number(c[ci] || 0), 0) || 1;
    drill = { title: "مشتریان", cols: ["کد", "مشتری", "برند", "مبلغ", "سهم"], rows: list.map((c) => [c[0], c[1], c[2], c[ci], Number(c[ci] || 0) / tot]), pct: 4, valCol: 3 };
  }
  const ql = q.toLowerCase();
  const shown = drill ? drill.rows.filter((r) => !q || drill!.groups || r.some((c) => String(c ?? "").toLowerCase().includes(ql))) : [];
  const groupRow = (label: string) => report.rows.find((x) => x.group === "cogs_group" && x.label === label);
  const kidHead = row.canon === "cogs" ? "گروه‌های کالا" : row.canon === "discount" ? "انواع تخفیف" : row.canon === "opex" ? "ردیف‌های هزینه" : "اجزا";

  return <div className="xl-modal" role="dialog" aria-modal="true" aria-label={`${row.label} — ${pmeta?.label}`} onClick={onClose}>
    <div className="xl-modal-box" dir="rtl" onClick={(e) => e.stopPropagation()}>
      <header>
        <div><small>جزئیات دوره</small><h3><bdi>{row.label}</bdi> · <bdi>{pmeta?.label}</bdi></h3></div>
        <button type="button" onClick={onClose} aria-label="بستن">✕</button>
      </header>
      <div className="xl-modal-stats">
        <div><small>مبلغ{isQty ? " (تعداد)" : ""}</small><b dir="ltr">{fmtV(v)}</b></div>
        {pv?.ratio != null && !isQty && <div><small>On sales (نسبت به {baseName})</small><b dir="ltr">{pct1(pv.ratio)}</b></div>}
        {parent && pval !== 0 && <div><small>سهم از {parent.label}</small><b dir="ltr">{pct1(v / pval)}</b></div>}
        {trend.filter((t) => t.p.key !== period && t.p.key !== "excel" && t.x).slice(0, 2).map((t) =>
          <div key={t.p.key}><small>تغییر نسبت به {t.p.label}</small>
            <b dir="ltr" className={(v - Number(t.x)) * (["cogs", "opex", "discount", "return", "tax"].includes(row.canon || "") || row.group ? -1 : 1) < 0 ? "neg" : ""}>
              {pct1((v - Number(t.x)) / Math.abs(Number(t.x)))}</b></div>)}
      </div>

      <section>
        <h4>همین ردیف در دوره‌های دیگر</h4>
        <div className="xl-mbars">
          {trend.filter((t) => t.x != null).map((t) => <button type="button" key={t.p.key} className={t.p.key === period ? "on" : ""}
            disabled={t.p.key === "excel"} onClick={() => t.p.key !== "excel" && onPick(row, t.p.key)}>
            <span>{t.p.label}</span><i><em className={Number(t.x) < 0 ? "neg" : ""} style={{ width: `${(Math.abs(Number(t.x)) / maxT) * 100}%` }} /></i>
            <b dir="ltr">{fmtV(t.x)}</b><small dir="ltr">{t.r != null && !isQty ? pct1(t.r) : ""}</small></button>)}
        </div>
      </section>

      {kids.length > 0 && <section>
        <h4>{kidHead} <small>(درصد = سهم از {row.label})</small></h4>
        <div className="xl-mbars">
          {kids.map(({ k, x }) => <button type="button" key={k.label} onClick={() => onPick(k, period)}>
            <span title={k.label}>{k.label}</span><i><em style={{ width: `${(Math.abs(x) / Math.abs(kids[0].x)) * 100}%` }} /></i>
            <b dir="ltr">{fmtV(x)}</b><small dir="ltr">{v ? pct1(x / v) : ""}</small></button>)}
        </div>
      </section>}

      {ranked.length > 0 && <section>
        <h4>به تفکیک برند <small>(درصد = {row.canon === "net" ? "سهم از کل" : `نسبت به ${baseName} همان برند`}{period === "p0" ? "؛ کلیک: جزئیات برند" : ""})</small></h4>
        <div className="xl-mbars">
          {ranked.map((b) => {
            const x = Number(bv![b]); const den = row.canon === "net" ? v : Number(baseB?.[b] || 0);
            return <button type="button" key={b} disabled={period !== "p0"} onClick={() => period === "p0" && onBrand(row, b)}>
              <span>{b}</span><i><em className={x < 0 ? "neg" : ""} style={{ width: `${(Math.abs(x) / maxB) * 100}%` }} /></i>
              <b dir="ltr">{fmtV(x)}</b><small dir="ltr">{den && !isQty ? pct1(x / den) : isQty && v ? pct1(x / v) : ""}</small></button>;
          })}
        </div>
      </section>}

      {(drill || (!isGroup && parts?.length && row.canon === "cogs")) && <section>
        <h4>{drill ? drill.title : "کالاها"} <small>({shown.length})</small>
          <input type="search" placeholder="جستجوی کالا یا مشتری…" value={q} onChange={(e) => setQ(e.target.value)} /></h4>
        {drill?.groups && <p className="xl-mnote">روی هر گروه کلیک کنید یا نام/کد کالا را جستجو کنید.</p>}
        {!drill && <p className="xl-mnote">گروه‌های کالا بالاتر آمده‌اند؛ برای دیدن کالاها روی یک گروه کلیک کنید یا نام/کد کالا را جستجو کنید.</p>}
        {drill && <div className="xl-mtable"><table>
          <thead><tr>{drill.cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{shown.slice(0, 400).map((r, i) => {
            const gr = drill!.groups ? groupRow(String(r[0])) : undefined;
            return <tr key={i} className={gr ? "clk" : ""} onClick={gr ? () => onPick(gr, period) : undefined}>
              {r.map((c, j) => <td key={j} dir={typeof c === "number" ? "ltr" : "auto"}>
                {j === drill!.pct ? <span className="xl-mpct"><em style={{ width: `${Math.min(100, Math.abs(Number(c)) * 100)}%` }} />{pct1(Number(c))}</span>
                  : typeof c === "number" ? (j === drill!.valCol ? num(c, unit) : nfEn.format(c)) : c}</td>)}
            </tr>;
          })}</tbody>
        </table></div>}
        {shown.length > 400 && <p className="xl-mnote">۴۰۰ ردیف اول نمایش داده شد؛ برای بقیه جستجو کنید.</p>}
      </section>}
      {parent && <p className="xl-mnote"><button type="button" className="xl-mlink" onClick={() => onPick(parent, period)}>↑ رفتن به {parent.label}</button></p>}
      {row.source && <p className="xl-mnote">منبع: {row.source}</p>}
    </div>
  </div>;
}
