"use client";
// «اسناد خرید» — نسخه زنده دو خروجی راهکاران که واحد مالی دستی می‌گرفت:
// ۱) «عملیات گروهی اسناد»: اسناد خرید/برگشت از خرید که ثبت حسابداری نشده‌اند (/finance/purchase-documents)
// ۲) «مرور تدارکات»: ردیف‌های رسید خرید دائم و موقت + تطبیق موقت↔دائم (/finance/purchase-items)
// هر ۵ دقیقه خودکار از راهکاران تازه می‌شود.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import SortTable from "../sort-table";
import { flashChatTarget, useChatLink, type ChatLink } from "../chatbot/chat-link";
import "./purchase-docs.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/finance`;
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 2 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const faDigits = (v: string | null | undefined) => String(v || "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const shortToman = (rial: number | null | undefined) => {
  const t = Number(rial || 0) / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf2.format(Math.round(t / 1e8) / 10)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const REFRESH_MS = 5 * 60 * 1000;
const currentYear = () => Number(new Intl.DateTimeFormat("en-US-u-ca-persian", { year: "numeric" }).formatToParts(new Date()).find((p) => p.type === "year")?.value || 1405);

async function getJson(path: string) {
  const r = await fetch(`${API()}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

/** داده زنده: بارگذاری اول از کش سرور، سپس هر ۵ دقیقه و با دکمه «به‌روزرسانی» مستقیم از راهکاران. */
function useLive(path: string) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [at, setAt] = useState<Date | null>(null);
  const load = useCallback((refresh: boolean) => {
    setLoading(true);
    const sep = path.includes("?") ? "&" : "?";
    getJson(`${path}${refresh ? `${sep}refresh=true` : ""}`)
      .then((j) => { setData(j); setError(""); setAt(new Date()); })
      .catch((e) => setError(e instanceof Error ? e.message : "خطا"))
      .finally(() => setLoading(false));
  }, [path]);
  useEffect(() => {
    setData(null);
    load(false);
    const id = window.setInterval(() => load(true), REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);
  return { data, error, loading, at, reload: () => load(true) };
}

function LiveBar({ at, loading, reload, excel }: { at: Date | null; loading: boolean; reload: () => void; excel: string }) {
  return <div className="pd-live">
    <span className={`pd-dot${loading ? " busy" : ""}`} />
    <small>{loading ? "در حال خواندن از راهکاران…" : at ? `زنده از راهکاران · آخرین به‌روزرسانی ${at.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })} · هر ۵ دقیقه` : "…"}</small>
    <button type="button" onClick={reload} disabled={loading}>↻ به‌روزرسانی</button>
    <a href={`${API()}${excel}`}>⬇ Excel</a>
  </div>;
}

const MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
type Period = { year: number; month: number };  // month = 0 → کل سال
const inPeriod = (dateJalali: string, p: Period) =>
  String(dateJalali || "").startsWith(p.month ? `${p.year}/${String(p.month).padStart(2, "0")}` : `${p.year}/`);
const periodLabel = (p: Period) => `${p.month ? `${MONTHS[p.month - 1]} ` : "سال "}${faDigits(String(p.year))}`;

/** فیلتر تاریخ: سال + ماه‌های همان سال (ماه بدون سند غیرفعال است؛ عدد هر ماه = تعداد ردیف). */
function PeriodFilter({ period, setPeriod, dates, unit }: { period: Period; setPeriod: (p: Period) => void; dates: string[]; unit: string }) {
  const thisYear = currentYear();
  const years = Array.from({ length: thisYear - 1399 }, (_, i) => thisYear - i);
  const counts = useMemo(() => {
    const c = new Array(13).fill(0);
    dates.forEach((d) => { if (String(d).startsWith(`${period.year}/`)) c[Number(String(d).slice(5, 7))] += 1; });
    return c;
  }, [dates, period.year]);
  const yearTotal = counts.reduce((a, b) => a + b, 0);
  return <div className="pd-period">
    <label className="pd-year">سال
      <select value={period.year} onChange={(e) => setPeriod({ year: Number(e.target.value), month: 0 })}>
        {years.map((y) => <option key={y} value={y}>{faDigits(String(y))}</option>)}
      </select>
    </label>
    <div className="pd-months" role="group" aria-label="ماه">
      <button type="button" className={period.month === 0 ? "active" : ""} onClick={() => setPeriod({ ...period, month: 0 })}>
        همه ماه‌ها<small>{fa(yearTotal)}</small>
      </button>
      {MONTHS.map((name, i) => <button type="button" key={name} disabled={!counts[i + 1]} className={period.month === i + 1 ? "active" : ""}
        onClick={() => setPeriod({ ...period, month: period.month === i + 1 ? 0 : i + 1 })} title={`${name} ${faDigits(String(period.year))}: ${fa(counts[i + 1])} ${unit}`}>
        {name}<small>{counts[i + 1] ? fa(counts[i + 1]) : "—"}</small>
      </button>)}
    </div>
  </div>;
}

function Kpi({ label, value, hint, tone = "", active, onClick }: { label: string; value: string; hint?: string; tone?: string; active?: boolean; onClick?: () => void }) {
  return <button type="button" className={`pd-kpi ${tone}${active ? " active" : ""}`} onClick={onClick} disabled={!onClick}>
    <small>{label}</small><b>{value}</b>{hint && <span>{hint}</span>}
  </button>;
}

export default function PurchaseDocsPage() {
  const [tab, setTab] = useState<"documents" | "items">("documents");
  // لینک چت‌بات: تب، سال/ماه و جستجو (هر تب خودش دوره و جستجو را اعمال می‌کند)
  const chatLink = useChatLink("purchaseDocs");
  useEffect(() => { if (chatLink) setTab(chatLink.tab === "items" ? "items" : "documents"); }, [chatLink]);
  return <div className="pd-page">
    <div className="pd-tabs" role="tablist">
      <button role="tab" aria-selected={tab === "documents"} className={tab === "documents" ? "active" : ""} onClick={() => setTab("documents")}>
        عملیات گروهی اسناد<small>اسناد خرید ثبت‌حسابداری‌نشده</small>
      </button>
      <button role="tab" aria-selected={tab === "items"} className={tab === "items" ? "active" : ""} onClick={() => setTab("items")}>
        مرور تدارکات<small>ردیف رسیدهای دائم و موقت</small>
      </button>
    </div>
    {tab === "documents" ? <DocumentsTab link={chatLink} /> : <ItemsTab link={chatLink} />}
  </div>;
}

// ------------------------------------------------------------ عملیات گروهی اسناد
type DocFilter = "all" | "priced" | "unpriced" | "returns" | "old";
/** دوره و جستجوی لینک چت را روی تب اعمال می‌کند و به جدول اسکرول می‌کند. */
function useLinkPeriod(link: ChatLink | null, setPeriod: (p: Period) => void, ready: boolean) {
  const [search, setSearch] = useState<string | undefined>(undefined);
  const ref = useRef<HTMLDivElement>(null);
  const flashed = useRef(0);
  useEffect(() => {
    if (!link) return;
    if (link.year) setPeriod({ year: link.year, month: link.month || 0 });
    setSearch(link.search || "");
  }, [link]); // eslint-disable-line react-hooks/exhaustive-deps
  // جدول بعد از رسیدن داده ساخته می‌شود؛ اسکرول را تا آن موقع نگه دار (هر لینک فقط یک بار).
  useEffect(() => {
    if (!link || !ready || flashed.current === link.at) return;
    flashed.current = link.at;
    flashChatTarget(ref.current, 400);
  }, [link, ready]);
  return { search, ref };
}

function DocumentsTab({ link }: { link: ChatLink | null }) {
  const [accounting, setAccounting] = useState<"unposted" | "all">("unposted");
  const [period, setPeriod] = useState<Period>(() => ({ year: link?.year || currentYear(), month: link?.month || 0 }));
  const { data, error, loading, at, reload } = useLive(`/purchase-documents?accounting=${accounting}&from_year=${period.year}`);
  const linked = useLinkPeriod(link, setPeriod, Boolean(data));
  const [filter, setFilter] = useState<DocFilter>("all");
  const [store, setStore] = useState("");
  const [creator, setCreator] = useState("");
  const allDocs: any[] = data?.documents || [];
  // همه شمارنده‌ها و گروه‌ها از اسناد همان سال/ماه ساخته می‌شوند.
  const docs = useMemo(() => allDocs.filter((d) => inPeriod(d.date_jalali, period)), [allDocs, period]);
  const t = useMemo(() => {
    const priced = docs.filter((d) => d.priced);
    return {
      count: docs.length, priced_count: priced.length, unpriced_count: docs.length - priced.length,
      return_count: docs.filter((d) => d.is_return).length,
      priced_rial: priced.reduce((s2, d) => s2 + Number(d.price_rial || 0), 0),
      over_30_days: docs.filter((d) => (d.days_waiting || 0) > 30).length,
      older_years_unposted: period.year === currentYear() && !period.month ? Number(data?.totals?.older_years_unposted || 0) : 0,
    };
  }, [docs, period, data]);
  const groupBy = (key: string) => {
    const map = new Map<string, any>();
    docs.forEach((d) => {
      const name = d[key] || "—";
      const g = map.get(name) || { name, count: 0, unpriced: 0, oldest_days: 0 };
      g.count += 1; g.unpriced += d.priced ? 0 : 1; g.oldest_days = Math.max(g.oldest_days, d.days_waiting || 0);
      map.set(name, g);
    });
    return [...map.values()].sort((a, b) => b.count - a.count);
  };
  const rows = useMemo(() => docs.filter((d) =>
    (filter === "all" || (filter === "priced" && d.priced) || (filter === "unpriced" && !d.priced) || (filter === "returns" && d.is_return)
      || (filter === "old" && (d.days_waiting || 0) > 30))
    && (!store || d.store_name === store) && (!creator || d.creator === creator)), [docs, filter, store, creator]);
  const extraUsed = [0, 1, 2, 3, 4].filter((i) => docs.some((d) => d.additional?.[i]));
  const pick = (f: DocFilter) => setFilter(filter === f ? "all" : f);
  return <section className="pd-section">
    <div className="pd-head">
      <div>
        <h3>{accounting === "unposted" ? "اسناد خرید ثبت حسابداری نشده" : "همه اسناد خرید"} <small>{periodLabel(period)}</small></h3>
        <p>خرید داخلی، خرید خارجی و برگشت از خرید — همان فهرست «عملیات گروهی اسناد» راهکاران.</p>
      </div>
      <div className="pd-seg">
        <button className={accounting === "unposted" ? "active" : ""} onClick={() => setAccounting("unposted")}>ثبت حسابداری نشده</button>
        <button className={accounting === "all" ? "active" : ""} onClick={() => setAccounting("all")}>همه وضعیت‌ها</button>
      </div>
    </div>
    <PeriodFilter period={period} setPeriod={setPeriod} dates={allDocs.map((d) => d.date_jalali)} unit="سند" />
    <LiveBar at={at} loading={loading} reload={reload} excel={`/purchase-documents.xlsx?year=${period.year}${period.month ? `&month=${period.month}` : ""}`} />
    {error && <div className="profile-warning">{error}</div>}
    {!data && !error && <div className="pd-loading">در حال خواندن اسناد از راهکاران…</div>}
    {data && <>
      <div className="pd-kpis">
        <Kpi label="کل اسناد" value={fa(t.count)} hint={`${fa(t.return_count)} برگشت از خرید`} active={filter === "all"} onClick={() => setFilter("all")} />
        <Kpi tone="good" label="قیمت‌گذاری شده" value={fa(t.priced_count)} hint={`${shortToman(t.priced_rial)} تومان${accounting === "unposted" ? " · آماده ثبت حسابداری" : ""}`} active={filter === "priced"} onClick={() => pick("priced")} />
        <Kpi tone="watch" label="قیمت‌گذاری نشده" value={fa(t.unpriced_count)} hint="اول باید قیمت‌گذاری شود" active={filter === "unpriced"} onClick={() => pick("unpriced")} />
        <Kpi tone="follow" label="بیش از ۳۰ روز" value={fa(t.over_30_days)} hint="از تاریخ سند" active={filter === "old"} onClick={() => pick("old")} />
        {accounting === "unposted" && t.older_years_unposted > 0 && <Kpi tone="follow" label="سال‌های قبل" value={fa(t.older_years_unposted)} hint="سند ثبت‌حسابداری‌نشده قبل از امسال" />}
      </div>
      <div className="pd-groups">
        <GroupList title="به تفکیک انبار" rows={groupBy("store_name")} selected={store} onPick={(n) => setStore(store === n ? "" : n)} />
        <GroupList title="به تفکیک صادرکننده" rows={groupBy("creator")} selected={creator} onPick={(n) => setCreator(creator === n ? "" : n)} />
      </div>
      {(store || creator || filter !== "all") && <div className="pd-chips">
        فیلتر: {filter !== "all" && <button onClick={() => setFilter("all")}>{({ priced: "قیمت‌گذاری شده", unpriced: "قیمت‌گذاری نشده", returns: "برگشت از خرید", old: "بیش از ۳۰ روز" } as any)[filter]} ✕</button>}
        {store && <button onClick={() => setStore("")}>{store} ✕</button>}
        {creator && <button onClick={() => setCreator("")}>{creator} ✕</button>}
      </div>}
      <div ref={linked.ref} />
      <SortTable rows={rows} rowKey={(d: any) => d.voucher_id} initialSort="date" placeholder="شماره سند، طرف مقابل، کد تفصیلی، توضیحات…"
        initialSearch={linked.search}
        toolbar={<label className="distribution-check"><input type="checkbox" checked={filter === "returns"} onChange={(e) => setFilter(e.target.checked ? "returns" : "all")} /> فقط برگشت از خرید</label>}
        columns={[
          { key: "num", label: "شماره سند", value: (d: any) => d.number, render: (d: any) => <b>{faDigits(d.number)}</b> },
          { key: "title", label: "عنوان سند", value: (d: any) => d.title, render: (d: any) => <span className={d.is_return ? "pd-ret" : ""}>{d.title}</span> },
          { key: "store", label: "عنوان انبار", value: (d: any) => d.store_name },
          { key: "date", label: "تاریخ سند", value: (d: any) => d.date_jalali, render: (d: any) => faDigits(d.date_jalali) },
          { key: "days", label: "روز", value: (d: any) => d.days_waiting ?? 0, render: (d: any) => <span className={(d.days_waiting || 0) > 30 ? "pd-old" : ""}>{fa(d.days_waiting)}</span> },
          { key: "cp", label: "طرف مقابل", value: (d: any) => d.counterpart, className: () => "cf-wrap" },
          { key: "dl", label: "کد تفصیلی طرف مقابل", value: (d: any) => d.counterpart_code, render: (d: any) => faDigits(d.counterpart_code) },
          { key: "state", label: "وضعیت", value: (d: any) => d.state },
          { key: "pricing", label: "وضعیت قیمت گذاری", value: (d: any) => d.pricing_state, render: (d: any) => <span className={`pd-badge ${d.priced ? "yes" : "no"}`}>{d.pricing_state}</span> },
          { key: "acc", label: "وضعیت حسابداری", value: (d: any) => d.accounting_state, render: (d: any) => <span className={`pd-badge ${d.posted ? "yes" : "no"}`}>{d.accounting_state}</span> },
          { key: "sl", label: "وضعیت عامل گذاری", value: (d: any) => d.sl_state },
          { key: "price", label: "مبلغ (تومان)", value: (d: any) => d.price_rial || 0, render: (d: any) => d.price_rial ? nf.format(Math.round(d.price_rial / 10)) : "—" },
          { key: "items", label: "ردیف", value: (d: any) => d.item_count, render: (d: any) => fa(d.item_count) },
          { key: "deliv", label: "تحویل گیرنده/دهنده", value: (d: any) => d.deliverer },
          { key: "branch", label: "شعبه", value: (d: any) => d.branch_name },
          { key: "cstore", label: "انبار مقابل", value: (d: any) => d.counterpart_store },
          { key: "desc", label: "توضیحات", value: (d: any) => d.description, className: () => "cf-wrap pd-desc" },
          ...extraUsed.map((i) => ({ key: `x${i}`, label: `فیلد اضافی ${fa(i + 1)}`, value: (d: any) => d.additional?.[i] || "" })),
          { key: "creator", label: "صادر کننده", value: (d: any) => d.creator },
        ]}
        totalRow={(vis: any[]) => <tr className="cf-debt-total-row"><td colSpan={11}><b>جمع {fa(vis.length)} سند</b></td>
          <td><b>{nf.format(Math.round(vis.reduce((s, d) => s + Number(d.price_rial || 0), 0) / 10))}</b></td>
          <td><b>{fa(vis.reduce((s, d) => s + Number(d.item_count || 0), 0))}</b></td><td colSpan={5 + extraUsed.length} /></tr>} />
      <p className="pd-note">{data.rule} «مبلغ» جمع قیمت ردیف‌های سندِ قیمت‌گذاری‌شده است.</p>
    </>}
  </section>;
}

function GroupList({ title, rows, selected, onPick }: { title: string; rows: any[]; selected: string; onPick: (name: string) => void }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return <div className="pd-group">
    <h4>{title}</h4>
    {rows.slice(0, 8).map((r) => <button key={r.name} type="button" className={selected === r.name ? "active" : ""} onClick={() => onPick(r.name)}
      title={`${r.name}: ${fa(r.count)} سند، ${fa(r.unpriced)} قیمت‌گذاری نشده، قدیمی‌ترین ${fa(r.oldest_days)} روز`}>
      <span className="pd-g-label">{r.name}</span>
      <span className="pd-g-track"><i style={{ width: `${(100 * (r.count - r.unpriced)) / max}%` }} /><i className="un" style={{ width: `${(100 * r.unpriced) / max}%` }} /></span>
      <b>{fa(r.count)}</b>
    </button>)}
    <small className="pd-g-legend"><i /> قیمت‌گذاری شده <i className="un" /> قیمت‌گذاری نشده</small>
  </div>;
}

// --------------------------------------------------------------- مرور تدارکات
type ItemFilter = "all" | "دائم" | "موقت" | "pending" | "noTemp";
function ItemsTab({ link }: { link: ChatLink | null }) {
  const [period, setPeriod] = useState<Period>(() => ({ year: link?.year || currentYear(), month: link?.month || 0 }));
  const { data, error, loading, at, reload } = useLive(`/purchase-items?from_year=${period.year}`);
  const linked = useLinkPeriod(link, setPeriod, Boolean(data));
  const [filter, setFilter] = useState<ItemFilter>("all");
  const [pairOf, setPairOf] = useState<any>(null);
  const allItems: any[] = data?.items || [];
  const items = useMemo(() => allItems.filter((x) => inPeriod(x.date_jalali, period)), [allItems, period]);
  const t = useMemo(() => {
    const perm = items.filter((x) => x.kind === "دائم"), temps = items.filter((x) => x.kind === "موقت");
    const pending = temps.filter((x) => x.converted === false);
    return {
      item_count: items.length, voucher_count: new Set(items.map((x) => `${x.kind}-${x.number}`)).size,
      parts: new Set(items.map((x) => x.part_code)).size, suppliers: new Set(items.map((x) => x.counterpart_code || x.counterpart)).size,
      permanent_items: perm.length, temporary_items: temps.length, pending_items: pending.length,
      pending_vouchers: new Set(pending.map((x) => x.number)).size, permanent_without_temp: perm.filter((x) => !x.linked_number).length,
    };
  }, [items]);
  const rows = useMemo(() => items.filter((x) => filter === "all" || x.kind === filter
    || (filter === "pending" && x.converted === false) || (filter === "noTemp" && x.kind === "دائم" && !x.linked_number)), [items, filter]);
  const pick = (f: ItemFilter) => setFilter(filter === f ? "all" : f);
  return <section className="pd-section">
    <div className="pd-head">
      <div>
        <h3>مرور تدارکات <small>{periodLabel(period)}</small></h3>
        <p>هر ردیف کالای رسید خرید دائم یا «رسید موقت خرید»؛ رسید موقت با رسید دائمش تطبیق داده شده است.</p>
      </div>
    </div>
    <PeriodFilter period={period} setPeriod={setPeriod} dates={allItems.map((x) => x.date_jalali)} unit="ردیف" />
    <LiveBar at={at} loading={loading} reload={reload} excel={`/purchase-items.xlsx?year=${period.year}${period.month ? `&month=${period.month}` : ""}`} />
    {error && <div className="profile-warning">{error}</div>}
    {!data && !error && <div className="pd-loading">در حال خواندن ردیف‌ها از راهکاران…</div>}
    {data && <>
      <div className="pd-kpis">
        <Kpi label="کل ردیف‌ها" value={fa(t.item_count)} hint={`${fa(t.voucher_count)} سند · ${fa(t.parts)} کالا · ${fa(t.suppliers)} تأمین‌کننده`} active={filter === "all"} onClick={() => setFilter("all")} />
        <Kpi tone="good" label="رسید دائم" value={fa(t.permanent_items)} hint="خرید داخلی / خارجی" active={filter === "دائم"} onClick={() => pick("دائم")} />
        <Kpi label="رسید موقت" value={fa(t.temporary_items)} hint="رسید موقت خرید" active={filter === "موقت"} onClick={() => pick("موقت")} />
        <Kpi tone="follow" label="موقتِ تبدیل‌نشده" value={fa(t.pending_items)} hint={`${fa(t.pending_vouchers)} رسید موقت هنوز رسید دائم ندارد`} active={filter === "pending"} onClick={() => pick("pending")} />
        <Kpi tone="watch" label="دائم بدون رسید موقت" value={fa(t.permanent_without_temp)} hint="مستقیم رسید دائم خورده" active={filter === "noTemp"} onClick={() => pick("noTemp")} />
      </div>
      <p className="pd-hint">🔗 روی ردیف‌هایی که «سند مرتبط» دارند بزنید تا رسید موقت و دائم کنار هم باز شوند.</p>
      <div ref={linked.ref} />
      <SortTable rows={rows} rowKey={(x: any) => x.item_id} initialSort={filter === "pending" ? "open" : "date"} limit={300}
        initialSearch={linked.search}
        onRowClick={(x: any) => { if (x.linked_number) setPairOf(x); }}
        placeholder="شماره سند، کد یا عنوان قلم، طرف مقابل، انبار…"
        columns={[
          { key: "num", label: "شماره سند انبار", value: (x: any) => x.number, render: (x: any) => <b>{faDigits(x.number)}</b> },
          { key: "date", label: "تاریخ سند انبار", value: (x: any) => x.date_jalali, render: (x: any) => faDigits(x.date_jalali) },
          { key: "code", label: "کد قلم", value: (x: any) => x.part_code, render: (x: any) => faDigits(x.part_code) },
          { key: "name", label: "عنوان قلم", value: (x: any) => x.part_name, className: () => "cf-wrap" },
          { key: "qty", label: "مقدار", value: (x: any) => x.quantity, render: (x: any) => nf2.format(x.quantity) },
          { key: "unit", label: "واحد", value: (x: any) => x.unit },
          { key: "store", label: "نام انبار", value: (x: any) => x.store_name },
          { key: "cp", label: "طرف مقابل", value: (x: any) => x.counterpart, className: () => "cf-wrap" },
          { key: "pattern", label: "نام الگوی سند انبار", value: (x: any) => x.pattern },
          { key: "kind", label: "دائم / موقت", value: (x: any) => x.kind, render: (x: any) => <span className={`pd-badge ${x.kind === "دائم" ? "yes" : "temp"}`}>{x.kind}</span> },
          { key: "link", label: "سند مرتبط", value: (x: any) => x.linked_number, render: (x: any) => x.linked_number
            ? <span className="pd-link" title={x.kind === "موقت" ? "رسید دائم — برای دیدن کلیک کنید" : "رسید موقت مبدأ — برای دیدن کلیک کنید"}>🔗 {faDigits(x.linked_number)} <small>{faDigits(x.linked_date_jalali)}</small></span>
            : x.converted === false ? <span className="pd-badge no">تبدیل نشده</span> : "—" },
          { key: "open", label: "روز باز", value: (x: any) => x.days_open ?? -1, render: (x: any) => x.days_open == null ? "—" : <span className={x.days_open > 14 ? "pd-old" : ""}>{fa(x.days_open)}</span> },
        ]} />
      <p className="pd-note">{data.rule}</p>
    </>}
    <PairDrawer row={pairOf} onClose={() => setPairOf(null)} />
  </section>;
}

// پنل کناری: سند ردیف انتخاب‌شده و سند مرتبطش (موقت ⇄ دائم) زیر هم، با ردیف‌های تطبیق‌یافته برجسته.
function PairDrawer({ row, onClose }: { row: any; onClose: () => void }) {
  const [shown, setShown] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const open = Boolean(row);
  useEffect(() => {
    if (!row) return;
    setShown(row); setData(null); setError("");
    let alive = true;
    getJson(`/purchase-items/${row.item_id}/pair`).then((j) => alive && setData(j)).catch((e) => alive && setError(e instanceof Error ? e.message : "خطا"));
    return () => { alive = false; };
  }, [row]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (typeof document === "undefined") return null;
  const r = row || shown;
  // ردیف‌های مرتبط: ردیف انتخاب‌شده + ردیف طرف مقابل (از ارجاع ReferenceRef)
  const hot = new Set<number>();
  if (data) {
    hot.add(data.selected_item_id);
    if (data.linked_item_id) hot.add(data.linked_item_id);
    data.linked.forEach((d: any) => d.items.forEach((i: any) => { if (i.ref_item_id === data.selected_item_id) hot.add(i.item_id); }));
  }
  const order = (d: any) => (d.kind === "موقت" ? 0 : 1);
  const docs = data ? [data.document, ...data.linked].sort((a: any, b: any) => order(a) - order(b)) : [];
  return createPortal(<>
    <div className={`pd-overlay${open ? " open" : ""}`} onClick={onClose} />
    <div className={`pd-drawer${open ? " open" : ""}`} role="dialog" aria-modal="true" aria-hidden={!open}>
      {r && <>
        <div className="pd-drawer-head">
          <div><small>سند مرتبط · {r.part_name}</small><h3>رسید {r.kind} {faDigits(r.number)} ⇄ {r.kind === "موقت" ? "دائم" : "موقت"} {faDigits(r.linked_number)}</h3></div>
          <button className="pd-close" onClick={onClose} aria-label="بستن">✕</button>
        </div>
        {error && <div className="profile-warning">{error}</div>}
        {!data && !error && <div className="pd-loading">در حال خواندن دو سند از راهکاران…</div>}
        {data && <div className="pd-pair" key={data.selected_item_id}>
          {docs.map((d: any, k: number) => <div key={d.voucher_id} className="pd-pair-step" style={{ animationDelay: `${k * 160}ms` }}>
            {k > 0 && <div className="pd-arrow" aria-hidden="true"><i /><span>تبدیل به رسید دائم</span></div>}
            <article className={`pd-doc ${d.kind === "موقت" ? "temp" : "perm"}${d.voucher_id === data.document.voucher_id ? " selected" : ""}`}>
              <header>
                <span className={`pd-badge ${d.kind === "دائم" ? "yes" : "temp"}`}>{d.kind}</span>
                <b>{d.pattern} {faDigits(d.number)}</b>
                <small>{faDigits(d.date_jalali)}</small>
              </header>
              <dl>
                <div><dt>انبار</dt><dd>{d.store_name}</dd></div>
                <div><dt>طرف مقابل</dt><dd>{d.counterpart || "—"}{d.counterpart_code && <small> · {faDigits(d.counterpart_code)}</small>}</dd></div>
                <div><dt>ثبت</dt><dd>{d.creator || "—"}{d.created_at_jalali && <small> · {faDigits(d.created_at_jalali)}</small>}</dd></div>
                <div><dt>وضعیت</dt><dd>{[d.state, d.pricing_state, d.accounting_state].filter(Boolean).join(" · ")}</dd></div>
              </dl>
              {d.description && <p className="pd-doc-desc">{d.description}</p>}
              <div className="pd-doc-items">
                {d.items.map((i: any) => <div key={i.item_id} className={`pd-doc-item${hot.has(i.item_id) ? " hot" : ""}`}>
                  <span>{faDigits(String(i.row))}</span>
                  <span className="pd-doc-part">{i.part_name}<small>{faDigits(i.part_code)}</small></span>
                  <b>{nf2.format(i.quantity)} <small>{i.unit}</small></b>
                </div>)}
              </div>
            </article>
          </div>)}
        </div>}
      </>}
    </div>
  </>, document.body);
}
