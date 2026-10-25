"use client";
// پنل کشویی (انیمیشنی) ریز کارت‌های «برگشتی» و «تعیین تکلیف نشده» خلاصه مدیریتی — مثل پنل پرداخت تجاری.
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import "./cheque-status-drawer.css";
import { RegCell, chequeNo } from "../cheque-reg";

export type ChequeStatusKind = "returned" | "undetermined";
type Group = { label: string; amount_rial: number; count: number };
type Row = {
  system: "rahkaran" | "karamad"; system_label: string; customer_name: string; customer_code: string | null; serial_number: string | null;
  sayad_number: string | null; amount_rial: number; due_date_jalali: string; days_overdue: number | null; status_label: string;
  branch_name: string | null; visitor_name: string | null;
};
type Detail = {
  title: string; rule: string; as_of_jalali: string; amount_rial: number; count: number; customer_count: number;
  by_system: Group[]; by_status: Group[]; by_age: Group[]; top_customers: Group[]; cheques: Row[];
};
type SortKey = "amount" | "days" | "customer" | "due";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 1 });
const fa = (v: number | null | undefined) => nf.format(v || 0);
const fullToman = (rial: number) => nf.format(Math.round(rial / 10));
const shortToman = (rial: number) => {
  const t = rial / 10, a = Math.abs(t);
  if (a >= 1e9) return `${nf1.format(t / 1e9)} میلیارد`;
  if (a >= 1e6) return `${nf.format(t / 1e6)} میلیون`;
  return nf.format(t);
};
const faDigits = (v: string | null | undefined) => String(v || "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const SYSTEM_COLOR: Record<string, string> = { "راهکاران": "#0d9488", "کارآمد": "#d97706" };

/** initial: حالت شروع پنل (چت‌بات با آن فهرست را فیلترشده و مرتب‌شده باز می‌کند). */
export type ChequeStatusInitial = { tab?: "summary" | "list"; search?: string; system?: "all" | "rahkaran" | "karamad"; sort?: SortKey };

export default function ChequeStatusDrawer({ kind, onClose, onOpenPage, initial }: {
  kind: ChequeStatusKind | null; onClose: () => void; onOpenPage: () => void; initial?: ChequeStatusInitial;
}) {
  const [data, setData] = useState<Record<string, Detail>>({});
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"summary" | "list">("summary");
  const [search, setSearch] = useState("");
  const [system, setSystem] = useState<"all" | "rahkaran" | "karamad">("all");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "amount", desc: true });

  useEffect(() => {
    if (!kind) return;
    setTab(initial?.tab || "summary"); setSearch(initial?.search || ""); setSystem(initial?.system || "all"); setError("");
    setSort({ key: initial?.sort || "amount", desc: initial?.sort !== "customer" });
    if (data[kind]) return;
    let active = true;
    fetch(`http://${apiHost()}:8000/api/v1/liquidity/received-cheques/status/${kind}`)
      .then(async (r) => { const j = await r.json().catch(() => ({})); if (!r.ok) throw Error(j.detail || `خطای ${r.status}`); return j; })
      .then((j) => setData((d) => ({ ...d, [kind]: j })))
      .catch((e) => active && setError(e instanceof Error ? e.message : "خطا"));
    return () => { active = false; };
  }, [kind, initial]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const d = kind ? data[kind] : undefined;
  const rows = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("fa-IR");
    const list = (d?.cheques || []).filter((x) => (system === "all" || x.system === system)
      && (!q || [x.customer_name, x.customer_code, x.serial_number, x.sayad_number, x.branch_name, x.visitor_name, x.status_label]
        .some((v) => String(v || "").toLocaleLowerCase("fa-IR").includes(q))));
    const value = (x: Row): number | string => sort.key === "amount" ? x.amount_rial : sort.key === "days" ? (x.days_overdue ?? 0)
      : sort.key === "customer" ? x.customer_name : x.due_date_jalali;
    return [...list].sort((a, b) => {
      const p = value(a), q2 = value(b);
      const cmp = typeof p === "number" && typeof q2 === "number" ? p - q2 : String(p).localeCompare(String(q2), "fa");
      return sort.desc ? -cmp : cmp;
    });
  }, [d, search, system, sort]);
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }));
  const arrow = (key: SortKey) => (sort.key === key ? (sort.desc ? " ▼" : " ▲") : " ⇅");
  const maxAge = Math.max(1, ...(d?.by_age || []).map((g) => g.amount_rial));
  const maxTop = Math.max(1, ...(d?.top_customers || []).map((g) => g.amount_rial));
  const open = Boolean(kind);
  const tone = kind === "returned" ? "returned" : "undetermined";
  // پنل مستقیم در body رندر می‌شود؛ انیمیشن/transform کارت‌های والد position:fixed را به خود قفل می‌کند.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(<>
    <div className={`csd-overlay ${open ? "open" : ""}`} onClick={onClose} />
    <div className={`csd-drawer ${open ? "open" : ""} ${tone}`} role="dialog" aria-modal="true" aria-hidden={!open}>
      {kind && <>
        <div className="csd-head">
          <div>
            <small>چک‌های دریافتی · تا {faDigits(d?.as_of_jalali)}</small>
            <h3>{kind === "returned" ? "چک‌های برگشتی" : "چک‌های تعیین تکلیف نشده"}</h3>
          </div>
          <button className="csd-close" onClick={onClose} aria-label="بستن">✕</button>
        </div>
        {error && <div className="profile-warning">{error}</div>}
        {!d && !error && <div className="csd-loading">در حال دریافت ریز چک‌ها…</div>}
        {d && <>
          <div className="csd-kpis">
            <div className="main"><small>جمع</small><b>{shortToman(d.amount_rial)}</b><span>تومان · {fa(d.count)} چک · {fa(d.customer_count)} مشتری</span></div>
            {d.by_system.map((g) => <div key={g.label}><small><i style={{ background: SYSTEM_COLOR[g.label] || "#8b5cf6" }} />{g.label}</small>
              <b>{shortToman(g.amount_rial)}</b><span>{fa(g.count)} چک</span></div>)}
          </div>
          <p className="csd-rule">{faDigits(d.rule)}</p>
          <div className="csd-tabs" data-tab={tab} role="tablist">
            <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>خلاصه</button>
            <button className={tab === "list" ? "active" : ""} onClick={() => setTab("list")}>فهرست چک‌ها ({fa(d.count)})</button>
            <i />
          </div>

          {tab === "summary" && <div className="csd-body" key="summary">
            <section>
              <h4>{kind === "returned" ? "وضعیت در سیستم" : "الان کجاست؟"}</h4>
              <div className="csd-chips static">{d.by_status.map((g) => <span key={g.label}>{g.label} <b>{fa(g.count)}</b> · {shortToman(g.amount_rial)}</span>)}</div>
            </section>
            <section>
              <h4>چند روز از سررسید گذشته</h4>
              {d.by_age.map((g) => <div key={g.label} className="csd-bar">
                <span>{g.label}</span>
                <span className="csd-track"><i style={{ width: `${(100 * g.amount_rial) / maxAge}%` }} /></span>
                <span className="csd-val">{shortToman(g.amount_rial)}<small>{fa(g.count)} چک</small></span>
              </div>)}
            </section>
            <section>
              <h4>بیشترین مبلغ به تفکیک مشتری</h4>
              {d.top_customers.map((g) => <button key={g.label} className="csd-bar link" onClick={() => { setSearch(g.label); setTab("list"); }}>
                <span className="csd-name">{g.label}</span>
                <span className="csd-track"><i className="alt" style={{ width: `${(100 * g.amount_rial) / maxTop}%` }} /></span>
                <span className="csd-val">{shortToman(g.amount_rial)}<small>{fa(g.count)} چک</small></span>
              </button>)}
            </section>
            <button className="csd-page" onClick={onOpenPage}>صفحه چک‌های دریافتی ←</button>
          </div>}

          {tab === "list" && <div className="csd-body" key="list">
            <div className="csd-filters">
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="مشتری، کد، شماره چک یا صیادی…" />
              <div className="csd-chips">
                {([["all", "همه"], ["rahkaran", "راهکاران"], ["karamad", "کارآمد"]] as ["all" | "rahkaran" | "karamad", string][]).map(([id, label]) =>
                  <button key={id} className={system === id ? "active" : ""} onClick={() => setSystem(id)}>{label}</button>)}
              </div>
              <small>{fa(rows.length)} چک · {shortToman(rows.reduce((s, x) => s + x.amount_rial, 0))} تومان</small>
            </div>
            <div className="csd-table-wrap">
              <table className="csd-table">
                <thead><tr>
                  <th onClick={() => sortBy("customer")}>مشتری{arrow("customer")}</th>
                  <th onClick={() => sortBy("amount")}>مبلغ (تومان){arrow("amount")}</th>
                  <th onClick={() => sortBy("due")}>سررسید{arrow("due")}</th>
                  <th onClick={() => sortBy("days")}>گذشته{arrow("days")}</th>
                  <th>وضعیت</th><th>شماره چک</th><th>ثبت در سیستم</th>
                </tr></thead>
                <tbody>{rows.slice(0, 400).map((x, i) => <tr key={`${x.system}-${x.serial_number}-${i}`} style={{ animationDelay: `${Math.min(i, 15) * 15}ms` }}>
                  <td><b>{x.customer_name}</b><small>{x.system_label}{x.customer_code ? ` · کد ${x.customer_code}` : ""}{x.branch_name ? ` · ${x.branch_name}` : ""}</small></td>
                  <td className="num">{fullToman(x.amount_rial)}</td>
                  <td className="num">{faDigits(x.due_date_jalali)}</td>
                  <td className="num">{x.days_overdue == null ? "—" : `${fa(x.days_overdue)} روز`}</td>
                  <td>{x.status_label}</td>
                  <td className="num">{chequeNo(x.serial_number)}{x.sayad_number && <small>صیادی {chequeNo(x.sayad_number)}</small>}</td>
                  <td><RegCell x={x} /></td>
                </tr>)}</tbody>
              </table>
              {!rows.length && <p className="csd-empty">چکی با این فیلتر نیست.</p>}
              {rows.length > 400 && <p className="csd-empty">۴۰۰ چک اول نمایش داده شد؛ برای بقیه جستجو کنید.</p>}
            </div>
          </div>}
        </>}
      </>}
    </div>
  </>, document.body);
}
