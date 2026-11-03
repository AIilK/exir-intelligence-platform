"use client";
// نمودارهای کوچک گزارش مدیریت: نوار ترکیب ۱۰۰٪، ستون ماهانه، دوطرفه (بدهی/پیش‌پرداخت)، مقایسه ورودی/خروجی، خالص هفتگی.
// قواعد: یک محور، میله‌های باریک با سر گرد ۴px و فاصله ۲px، برچسب مستقیم با رنگ متن (نه رنگ سری)، راهنما برای ≥۲ سری،
// و راهنمای شناور (tooltip) روی هر میله. رنگ‌ها دسته‌ای ثابت و اعتبارسنجی‌شده روی سطح تیره.
import { useState } from "react";
import type { ReactNode } from "react";
import "./mini-charts.css";

const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
export const shortToman = (rial: number | null | undefined) => {
  const t = Number(rial || 0) / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const pct = (part: number, total: number) => (total ? `${nf.format(Math.round((100 * part) / total))}٪` : "۰٪");

export const PALETTE = { teal: "#0d9488", amber: "#d97706", violet: "#8b5cf6", slate: "#64748b" };

/** عنوان + توضیح یک‌خطی + راهنمای سری‌ها */
export function ChartCard({ title, note, legend, children }: { title: string; note?: string; legend?: { label: string; color: string }[]; children: ReactNode }) {
  return <figure className="mc-card">
    <figcaption>
      <b>{title}</b>
      {legend && legend.length > 1 && <span className="mc-legend">{legend.map((l) => <span key={l.label}><i style={{ background: l.color }} />{l.label}</span>)}</span>}
    </figcaption>
    {note && <p className="mc-note">{note}</p>}
    {children}
  </figure>;
}

/** نوار ترکیب ۱۰۰٪ با برچسب درصد و مبلغ زیر هر بخش */
export function StackBar({ segments }: { segments: { label: string; value: number; color: string; hint?: string }[] }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0);
  const [hover, setHover] = useState<number | null>(null);
  return <div className="mc-stack">
    <div className="mc-stack-bar" onMouseLeave={() => setHover(null)}>
      {segments.map((s, i) => s.value > 0 && <span key={s.label} style={{ flexGrow: s.value, background: s.color }} className={hover === i ? "hover" : ""}
        onMouseEnter={() => setHover(i)} title={`${s.label}: ${shortToman(s.value)} تومان (${pct(s.value, total)})`} />)}
    </div>
    <div className="mc-stack-labels">
      {segments.map((s, i) => <div key={s.label} className={hover === i ? "hover" : ""} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
        <small><i style={{ background: s.color }} />{s.label}</small>
        <b>{pct(s.value, total)}</b>
        <span>{shortToman(s.value)}{s.hint ? ` · ${s.hint}` : ""}</span>
      </div>)}
    </div>
  </div>;
}

/** ستون ماهانه (یک یا دو سری روی هم) با برچسب مقدار روی بلندترین ستون و راهنمای شناور */
export function MonthBars({ items, series }: {
  items: { label: string; values: number[]; counts?: number[] }[]; series: { label: string; color: string }[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = items.map((x) => x.values.reduce((s, v) => s + v, 0));
  const max = Math.max(1, ...totals);
  const peak = totals.indexOf(Math.max(...totals));
  return <div className="mc-months" onMouseLeave={() => setHover(null)}>
    {items.map((x, i) => <div key={x.label} className={`mc-month${hover === i ? " hover" : ""}`} onMouseEnter={() => setHover(i)}>
      <span className="mc-month-val">{hover === i || i === peak ? shortToman(totals[i]) : ""}</span>
      <span className="mc-month-col" style={{ height: `${Math.max(totals[i] ? 3 : 0, (100 * totals[i]) / max)}%` }}>
        {x.values.map((v, k) => v > 0 && <i key={k} style={{ flexGrow: v, background: series[k]?.color }} />)}
      </span>
      <small>{x.label}</small>
      {hover === i && <div className="mc-tip">
        <b>{x.label}</b>
        {series.map((s, k) => <span key={s.label}><i style={{ background: s.color }} />{s.label}: {shortToman(x.values[k])}{x.counts ? ` (${nf.format(x.counts[k] || 0)} چک)` : ""}</span>)}
      </div>}
    </div>)}
  </div>;
}

/** میله دوطرفه: چپ و راست از خط وسط (مثلاً بدهی شرکت ↔ پیش‌پرداخت) */
export function DivergingRows({ rows, left, right }: {
  rows: { label: string; left: number; right: number; sub?: string }[]; left: { label: string; color: string }; right: { label: string; color: string };
}) {
  const max = Math.max(1, ...rows.flatMap((r) => [r.left, r.right]));
  return <div className="mc-div">
    <div className="mc-div-head"><span>{right.label}</span><span /><span>{left.label}</span></div>
    {rows.map((r) => <div key={r.label} className="mc-div-row">
      <span className="mc-div-side right"><i style={{ width: `${(100 * r.right) / max}%`, background: right.color }} /><em>{shortToman(r.right)}</em></span>
      <span className="mc-div-label">{r.label}{r.sub && <small>{r.sub}</small>}</span>
      <span className="mc-div-side left"><i style={{ width: `${(100 * r.left) / max}%`, background: left.color }} /><em>{shortToman(r.left)}</em></span>
    </div>)}
  </div>;
}

/** دو نوار روی یک مقیاس: ورودی (بخش‌ها) در برابر خروجی (بخش‌ها) */
export function FlowCompare({ rows }: { rows: { label: string; parts: { label: string; value: number; color: string }[] }[] }) {
  const totals = rows.map((r) => r.parts.reduce((s, p) => s + Math.max(0, p.value), 0));
  const max = Math.max(1, ...totals);
  return <div className="mc-flow">
    {rows.map((r, i) => <div key={r.label} className="mc-flow-row">
      <span className="mc-flow-label">{r.label}<b>{shortToman(totals[i])}</b></span>
      <span className="mc-flow-track">
        <span className="mc-flow-bar" style={{ width: `${(100 * totals[i]) / max}%` }}>
          {r.parts.map((p) => p.value > 0 && <i key={p.label} style={{ flexGrow: p.value, background: p.color }} title={`${p.label}: ${shortToman(p.value)} تومان`} />)}
        </span>
      </span>
      {r.parts.length > 1 && <span className="mc-flow-parts">{r.parts.map((p) => <span key={p.label}><i style={{ background: p.color }} />{p.label} {shortToman(p.value)}</span>)}</span>}
    </div>)}
  </div>;
}

/** خالص هفتگی: مثبت بالا، منفی پایین خط صفر */
export function NetWeeks({ weeks, pos, neg }: { weeks: { label: string; net: number; inflow: number; outflow: number }[]; pos: string; neg: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...weeks.map((w) => Math.abs(w.net)));
  return <div className="mc-net" onMouseLeave={() => setHover(null)}>
    {weeks.map((w, i) => <div key={w.label} className={`mc-net-col${hover === i ? " hover" : ""}`} onMouseEnter={() => setHover(i)}>
      <span className="mc-net-up">{w.net > 0 && <i style={{ height: `${(100 * w.net) / max}%`, background: pos }} />}</span>
      <span className="mc-net-down">{w.net < 0 && <i style={{ height: `${(100 * -w.net) / max}%`, background: neg }} />}</span>
      <em className={w.net < 0 ? "neg" : ""}>{w.net < 0 ? "−" : "+"}{shortToman(Math.abs(w.net))}</em>
      <small>{w.label}</small>
      {hover === i && <div className="mc-tip">
        <b>{w.label}</b><span>ورودی: {shortToman(w.inflow)}</span><span>خروجی: {shortToman(w.outflow)}</span>
        <span>خالص: {w.net < 0 ? "−" : "+"}{shortToman(Math.abs(w.net))}</span>
      </div>}
    </div>)}
  </div>;
}
