"use client";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

const fa = (v: number = 0) => new Intl.NumberFormat("fa-IR").format(v);

// جدول عمومی: جستجو در همه ستون‌ها + مرتب‌سازی با کلیک روی عنوان ستون (کلیک دوم برعکس می‌کند).
export type SortCol<T> = {
  key: string; label: string;
  value: (row: T) => string | number | null | undefined;
  render?: (row: T) => ReactNode;
  className?: (row: T) => string | undefined;
};
export default function SortTable<T>({ rows, columns, rowKey, onRowClick, initialSort, initialDesc = true, placeholder, totalRow, empty, toolbar, limit = 400, initialSearch }: {
  rows: T[]; columns: SortCol<T>[]; rowKey: (row: T, index: number) => string | number;
  onRowClick?: (row: T) => void; initialSort?: string; initialDesc?: boolean; placeholder?: string;
  totalRow?: (visible: T[]) => ReactNode; empty?: string; toolbar?: ReactNode; limit?: number;
  /** جستجوی آماده (مثلاً از لینک چت‌بات)؛ با تغییرش جستجو دوباره تنظیم می‌شود. */
  initialSearch?: string;
}) {
  const [sortKey, setSortKey] = useState(initialSort || "");
  const [desc, setDesc] = useState(initialDesc);
  const [search, setSearch] = useState(initialSearch || "");
  const [shown, setShown] = useState(limit);
  useEffect(() => { if (initialSearch !== undefined) setSearch(initialSearch); }, [initialSearch]);
  const q = search.trim().toLocaleLowerCase("fa-IR");
  const visible = useMemo(() => {
    const filtered = !q ? rows : rows.filter((r) => columns.some((c) => String(c.value(r) ?? "").toLocaleLowerCase("fa-IR").includes(q)));
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return filtered;
    return [...filtered].sort((a, b) => {
      const x = col.value(a), y = col.value(b);
      const cmp = typeof x === "number" && typeof y === "number" ? x - y
        : x == null || x === "" ? 1 : y == null || y === "" ? -1 : String(x).localeCompare(String(y), "fa");
      return desc ? -cmp : cmp;
    });
  }, [rows, columns, q, sortKey, desc]);
  const sortBy = (key: string) => { if (key === sortKey) setDesc(!desc); else { setSortKey(key); setDesc(true); } };
  return <>
    <div className="st-toolbar">
      <input value={search} onChange={(e) => { setSearch(e.target.value); setShown(limit); }} placeholder={placeholder || "جستجو در همه ستون‌ها..."} />
      {toolbar}
      <small>{fa(visible.length)} ردیف{visible.length !== rows.length ? ` از ${fa(rows.length)}` : ""}</small>
    </div>
    {visible.length ? <div className={`cf-table distribution-scroll${onRowClick ? " cf-clickable" : ""}`}><table className="st-table">
      <thead><tr>{columns.map((c) => <th key={c.key} onClick={() => sortBy(c.key)} className={sortKey === c.key ? "sorted" : undefined} title="برای مرتب‌سازی کلیک کنید">
        {c.label}<i>{sortKey === c.key ? (desc ? " ▼" : " ▲") : " ⇅"}</i>
      </th>)}</tr></thead>
      <tbody>
        {totalRow && totalRow(visible)}
        {visible.slice(0, shown).map((r, i) => <tr key={rowKey(r, i)} onClick={onRowClick ? () => onRowClick(r) : undefined}>
          {columns.map((c) => <td key={c.key} className={c.className?.(r)}>{c.render ? c.render(r) : (c.value(r) ?? "—")}</td>)}
        </tr>)}
      </tbody>
    </table></div> : <div className="invoice-source-pending">{empty || "ردیفی با این جستجو نیست."}</div>}
    {visible.length > shown && <button className="rc-secondary dt-more" onClick={() => setShown((n) => n + limit)}>
      نمایش {fa(Math.min(limit, visible.length - shown))} ردیف دیگر (از {fa(visible.length - shown)} باقی‌مانده)
    </button>}
  </>;
}
