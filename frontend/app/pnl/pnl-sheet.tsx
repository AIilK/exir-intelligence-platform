"use client";
// نمای «صفحه اول» هر کانال (هیبرید، B2B، صادرات) دقیقاً با شمایل شیت Report اکسل P&L:
// سه کارت TOTAL REVENUE / GROSS PROFIT / OPEX، سربرگ سرمه‌ای «Exir Kadus»، ردیف قرمز برندها،
// ستون جمع دوره + On sales و دوره‌های مقایسه، ردیف‌های اصلی سرمه‌ای و جمع‌ها با خط پررنگ.
// انیمیشن: شمارش اعداد کارت‌ها، ورود پله‌ای ردیف‌ها، نوار داده (data bar) برندها در ردیف‌های اصلی،
// هایلایت سطر و ستون زیر نشانگر، و چشمک سلول‌هایی که با به‌روزرسانی لایو عوض شده‌اند.
import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import "./pnl-sheet.css";

type Row = { label: string; kind: "line" | "total" | "ratio" | "share"; canon: string | null; group: string | null; source?: string | null;
  values: Record<string, number | null>; periods: Record<string, { value: number | null; ratio: number | null }> };
type Report = { brands: string[]; periods: { key: string; label: string; has_ratio: boolean }[]; rows: Row[]; unit: string };
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
  const p0 = report.periods[0]?.key, p1 = report.periods[1]?.key;
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
      prevLabel={p1 ? report.periods[1].label : undefined} ratio={c.ratio} ratioLabel={c.ratioLabel} unit={unit} delay={i * 110} />)}
  </div>;
}

export function PnlSheet({ report, unit, company = "Exir Kadus" }: { report: Report; unit: Unit; company?: string }) {
  const [openDiscount, setOpenDiscount] = useState(true);
  const [hotCol, setHotCol] = useState<string | null>(null);
  const [barsOn, setBarsOn] = useState(false);
  const prevValues = useRef<Map<string, number | null>>(new Map());
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const hasDetail = report.rows.some((r) => r.group === "discount_detail");
  const rows = report.rows.filter((r) => r.group !== "discount_detail" || openDiscount);
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
              r.canon === "cogs_std" || r.canon === "gp_std" ? "std" : "", r.canon ? `c-${r.canon}` : ""].filter(Boolean).join(" ");
            const label = isShare ? "Opex" : r.label;
            return <tr key={`${r.label}-${i}`} className={cls} style={{ "--i": Math.min(i, 40) } as CSSProperties}>
              <th dir="auto" title={r.source || undefined}>{label}</th>
              {report.brands.map((b) => {
                const v = r.values[b];
                const w = bar && maxV && v != null ? Math.abs(v) / maxV : isShare && v != null ? Number(v) : 0;
                return <td key={b} onMouseEnter={() => setHotCol(b)}
                  className={[v != null && v < 0 ? "neg" : "", hotCol === b ? "hot" : "", changed.has(`${key}|${b}`) ? "chg" : ""].filter(Boolean).join(" ")}>
                  {(bar || isShare) && w > 0 && <i className={`xl-bar ${bar || "share"}`} style={{ "--w": `${Math.min(1, w) * 100}%` } as CSSProperties} />}
                  <span>{cell(r, v)}</span>
                </td>;
              })}
              {periods.map((p, pi) => {
                const pv = r.periods[p.key];
                const v = isShare ? null : pv?.value;
                return [<td key={`${p.key}v`} onMouseEnter={() => setHotCol(p.key)}
                  className={[`pv${pi === 0 ? " cur" : ""}`, v != null && v < 0 ? "neg" : "", hotCol === p.key ? "hot" : "",
                    changed.has(`${key}|${p.key}`) ? "chg" : ""].filter(Boolean).join(" ")}><span>{cell(r, v)}</span></td>,
                  p.has_ratio ? <td key={`${p.key}r`} className={`pr${hotCol === p.key ? " hot" : ""}`}>
                    {r.kind === "ratio" || isShare || r.canon === "qty" ? "" : pctCell(pv?.ratio)}</td> : null];
              })}
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  </article>;
}
