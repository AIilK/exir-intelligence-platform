"use client";
// «قیمت‌گذاری انبار»: اسناد انبار راهکاران که «قیمت گذاری نشده»اند — همان ستون «وضعیت قیمت گذاری»
// فهرست اسناد انبار راهکاران. همه اعداد از /api/v1/finance/inventory-pricing می‌آید.
import { useEffect, useMemo, useRef, useState } from "react";
import { flashChatTarget, useChatLink } from "../chatbot/chat-link";
import "./inventory-pricing.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/finance`;
const fa = (v: number | null | undefined = 0) => new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 }).format(v || 0);

type Store = {
  store_id: number; store_code: string; store_name: string; plant_name: string; is_factory: boolean;
  document_count: number; unpriced_count: number; unpriced_receipt_count: number; unpriced_issue_count: number;
  priced_count: number; oldest_unpriced_date_jalali: string; oldest_unpriced_days: number | null;
};
type Totals = { document_count: number; unpriced_count: number; unpriced_receipt_count: number; unpriced_issue_count: number };
type Summary = {
  from_date_jalali: string; generated_at_jalali: string; total: Totals; factory_total: Totals; stores: Store[];
  monthly: { label: string; document_count: number; unpriced_count: number; priced_percent: number }[];
  types: { title: string; direction: "receipt" | "issue"; unpriced_count: number }[]; note: string;
};
type Doc = {
  voucher_id: number; number: string; title: string; direction: "receipt" | "issue"; store_name: string; plant_name: string;
  date_jalali: string; days_waiting: number | null; counterpart: string; counterpart_code: string; counterpart_store: string;
  state: string; description: string; creator: string; item_count: number; priced: boolean;
};
type Scope = "factory" | "all";
type Direction = "all" | "receipt" | "issue";
type Pricing = "unpriced" | "priced" | "all";

async function get(path: string) {
  const r = await fetch(`${API()}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const faDigits = (v: string) => v.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const severity = (days: number | null) => (days == null ? "" : days > 90 ? "critical" : days > 30 ? "warn" : "ok");

export default function InventoryPricingPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [scope, setScope] = useState<Scope>("factory");
  const [store, setStore] = useState<Store | null>(null);
  const [direction, setDirection] = useState<Direction>("receipt");
  const [pricing, setPricing] = useState<Pricing>("unpriced");
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [docsError, setDocsError] = useState("");
  const [search, setSearch] = useState("");
  // لینک چت‌بات: انبار یا جستجو (شماره سند، طرف مقابل، …)؛ اگر اسم انبار بود همان انبار انتخاب می‌شود.
  const chatLink = useChatLink("inventoryPricing");
  const docsRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!chatLink || !summary) return;
    const q = (chatLink.search || "").trim();
    const st = q ? summary.stores.find((s) => s.store_name.includes(q) || q.includes(s.store_name)) : undefined;
    setScope("all"); setPricing("unpriced"); setDirection("all");
    setStore(st || null); setSearch(st ? "" : q);
    flashChatTarget(docsRef.current, 500);
  }, [chatLink, summary]);
  const [title, setTitle] = useState("");

  useEffect(() => {
    get("/inventory-pricing").then(setSummary).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);

  useEffect(() => {
    let active = true;
    setDocs(null);
    setDocsError("");
    const params = new URLSearchParams();
    if (store) params.set("store_id", String(store.store_id));
    else if (scope === "factory") params.set("factory_only", "true");
    if (direction !== "all") params.set("direction", direction);
    params.set("pricing", pricing);
    get(`/inventory-pricing/documents?${params}`)
      .then((j) => active && setDocs(j.documents || []))
      .catch((e) => active && setDocsError(e instanceof Error ? e.message : "خطا"));
    return () => { active = false; };
  }, [store, scope, direction, pricing]);

  const stores = useMemo(() => (summary?.stores || []).filter((s) => (scope === "factory" ? s.is_factory : true) && s.document_count > 0), [summary, scope]);
  const plants = useMemo(() => {
    const map = new Map<string, Store[]>();
    stores.forEach((s) => map.set(s.plant_name || "—", [...(map.get(s.plant_name || "—") || []), s]));
    return Array.from(map.entries());
  }, [stores]);
  const titles = useMemo(() => Array.from(new Set((docs || []).map((d) => d.title))).sort((a, b) => a.localeCompare(b, "fa")), [docs]);
  const shown = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("fa-IR");
    return (docs || []).filter((d) => (!title || d.title === title) && (!q || [d.number, d.title, d.store_name, d.counterpart, d.counterpart_code,
      d.counterpart_store, d.description, d.creator, d.date_jalali].some((v) => String(v || "").toLocaleLowerCase("fa-IR").includes(q))));
  }, [docs, search, title]);

  if (error) return <div className="profile-warning">دریافت وضعیت قیمت‌گذاری انبار ناموفق بود: {error}</div>;
  if (!summary) return <div className="ip-loading">در حال دریافت وضعیت قیمت‌گذاری اسناد انبار از راهکاران…</div>;

  const t = scope === "factory" ? summary.factory_total : summary.total;
  const latest = summary.monthly[summary.monthly.length - 1];

  return (
    <div className="ip-page">
      <section className="ip-alarm">
        <div>
          <small>هشدار قیمت‌گذاری انبار · از {summary.from_date_jalali} تا {summary.generated_at_jalali}</small>
          <h2>{fa(t.unpriced_count)} سند انبار {scope === "factory" ? "در انبارهای کارخانه" : ""} قیمت‌گذاری نشده است</h2>
          <p>
            کالا وارد یا خارج شده و تعدادش ثبت شده، ولی سند در راهکاران «قیمت گذاری نشده» است و ارزش ریالی ندارد.
            {latest && <> قیمت‌گذاری {faDigits(latest.label)}: فقط <b>{fa(latest.priced_percent)}٪</b> اسناد.</>}
          </p>
        </div>
        <div className="ip-actions">
          <div className="ip-seg">
            <button className={scope === "factory" ? "active" : ""} onClick={() => { setScope("factory"); setStore(null); }}>انبارهای کارخانه</button>
            <button className={scope === "all" ? "active" : ""} onClick={() => { setScope("all"); setStore(null); }}>همه انبارها</button>
          </div>
          <a className="ip-download" href={`${API()}/inventory-pricing.xlsx`}>دانلود Excel</a>
        </div>
      </section>

      <section className="ip-kpis">
        <article><small>کل اسناد</small><b>{fa(t.document_count)}</b></article>
        <article className="good"><small>قیمت‌گذاری شده</small><b>{fa(t.document_count - t.unpriced_count)}</b><span>{fa(t.document_count ? (100 * (t.document_count - t.unpriced_count)) / t.document_count : 0)}٪</span></article>
        <article className="bad"><small>قیمت‌گذاری نشده</small><b>{fa(t.unpriced_count)}</b><span>{fa(t.document_count ? (100 * t.unpriced_count) / t.document_count : 0)}٪</span></article>
        <article className="bad"><small>رسید (کالای ورودی) بی‌قیمت</small><b>{fa(t.unpriced_receipt_count)}</b></article>
        <article><small>حواله (کالای خروجی) بی‌قیمت</small><b>{fa(t.unpriced_issue_count)}</b></article>
      </section>

      <section className="ip-months">
        <h3>درصد قیمت‌گذاری اسناد در هر ماه</h3>
        <div className="ip-month-bars">
          {summary.monthly.map((m) => (
            <div key={m.label} title={`${faDigits(m.label)}: ${fa(m.unpriced_count)} از ${fa(m.document_count)} سند قیمت‌گذاری نشده`}>
              <i style={{ height: `${Math.max(m.priced_percent, 2)}%` }} className={m.priced_percent < 50 ? "low" : ""} />
              <b>{fa(m.priced_percent)}٪</b>
              <small>{faDigits(m.label)}</small>
            </div>
          ))}
        </div>
      </section>

      {plants.map(([plant, list]) => (
        <section className="ip-plant" key={plant}>
          <h3>{plant}</h3>
          <div className="ip-store-grid">
            {list.map((s) => (
              <button key={s.store_id} type="button"
                className={`ip-store ${severity(s.oldest_unpriced_days)} ${store?.store_id === s.store_id ? "selected" : ""} ${s.unpriced_count ? "" : "clean"}`}
                onClick={() => setStore(store?.store_id === s.store_id ? null : s)}>
                <span>{s.store_name} <small>کد {s.store_code}</small></span>
                <strong>{fa(s.unpriced_count)}</strong>
                <small>قیمت‌گذاری نشده از {fa(s.document_count)} سند</small>
                <em className="ip-priced">قیمت‌گذاری شده: {fa(s.priced_count)}</em>
                <em>رسید {fa(s.unpriced_receipt_count)} · حواله {fa(s.unpriced_issue_count)}</em>
                {s.oldest_unpriced_date_jalali && <em>قدیمی‌ترین: {s.oldest_unpriced_date_jalali} ({fa(s.oldest_unpriced_days)} روز)</em>}
              </button>
            ))}
          </div>
        </section>
      ))}

      <section className="ip-docs" ref={docsRef}>
        <div className="ip-docs-head">
          <h3>ریز اسناد {pricing === "unpriced" ? "قیمت‌گذاری‌نشده" : pricing === "priced" ? "قیمت‌گذاری‌شده" : "انبار"} {store ? `— ${store.store_name}` : scope === "factory" ? "— همه انبارهای کارخانه" : "— همه انبارها"}</h3>
          {store && <button className="ip-link" onClick={() => setStore(null)}>نمایش همه انبارها</button>}
        </div>
        <div className="ip-filters">
          <div className="ip-seg">
            {([["unpriced", "قیمت‌گذاری نشده"], ["priced", "قیمت‌گذاری شده"], ["all", "همه"]] as [Pricing, string][]).map(([id, label]) => (
              <button key={id} className={pricing === id ? "active" : ""} onClick={() => setPricing(id)}>{label}</button>
            ))}
          </div>
          <div className="ip-seg">
            {([["receipt", "رسید (ورودی)"], ["issue", "حواله (خروجی)"], ["all", "همه"]] as [Direction, string][]).map(([id, label]) => (
              <button key={id} className={direction === id ? "active" : ""} onClick={() => setDirection(id)}>{label}</button>
            ))}
          </div>
          <select value={title} onChange={(e) => setTitle(e.target.value)}>
            <option value="">همه عنوان‌های سند</option>
            {titles.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره سند، طرف مقابل، صادرکننده، توضیحات…" />
          <small>{docs ? `${fa(shown.length)} سند` : ""}</small>
        </div>
        {docsError && <div className="profile-warning">{docsError}</div>}
        {!docs && !docsError && <div className="ip-loading">در حال دریافت اسناد…</div>}
        {docs && (
          <div className="ip-table-wrap">
            <table className="ip-table">
              <thead><tr>
                <th>شماره سند</th><th>عنوان سند</th><th>انبار</th><th>تاریخ سند</th><th>انتظار</th><th>طرف مقابل</th>
                <th>انبار مقابل</th><th>ردیف</th><th>وضعیت قیمت‌گذاری</th><th>وضعیت</th><th>صادر کننده</th><th>توضیحات</th>
              </tr></thead>
              <tbody>
                {shown.slice(0, 500).map((d) => (
                  <tr key={d.voucher_id} className={d.priced ? "" : severity(d.days_waiting)}>
                    <td className="num">{d.number}</td>
                    <td>{d.title}<small>{d.direction === "receipt" ? "رسید" : "حواله"}</small></td>
                    <td>{d.store_name}</td>
                    <td className="num">{d.date_jalali}</td>
                    <td className="num">{d.priced || d.days_waiting == null ? "—" : d.days_waiting < 0 ? "تاریخ آینده" : `${fa(d.days_waiting)} روز`}</td>
                    <td>{d.counterpart || "—"}{d.counterpart_code && <small>{d.counterpart_code}</small>}</td>
                    <td>{d.counterpart_store || "—"}</td>
                    <td className="num">{fa(d.item_count)}</td>
                    <td><span className={`ip-pricing ${d.priced ? "yes" : "no"}`}>{d.priced ? "قیمت‌گذاری شده" : "قیمت‌گذاری نشده"}</span></td>
                    <td>{d.state}</td>
                    <td>{d.creator || "—"}</td>
                    <td className="desc">{d.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {shown.length > 500 && <p className="ip-more">۵۰۰ سند اول نمایش داده شد؛ برای فهرست کامل فیلتر کنید یا Excel را دانلود کنید.</p>}
          </div>
        )}
      </section>
      <p className="ip-note">{summary.note} انبارهای کارخانه: سایت‌های کادوس، اکسیر کادوس و فراز بهداشت.</p>
    </div>
  );
}
