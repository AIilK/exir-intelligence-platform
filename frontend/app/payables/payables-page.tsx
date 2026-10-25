"use client";
// «پرداخت تجاری»: حساب‌های پرداختنی تجاری (511002) و غیرتجاری (512001) راهکاران — مثل «مرور حساب» و «ریز گردش».
// دو ماژول ← فهرست طرف حساب‌ها ← با کلیک، ریز گردش همان طرف حساب در یک پنل کشویی (انیمیشنی).
import { useEffect, useMemo, useRef, useState } from "react";
import { flashChatTarget, useChatLink } from "../chatbot/chat-link";
import "./payables.css";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/finance`;
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const fa = (v: number | null | undefined = 0) => nf.format(v || 0);
const toman = (rial: number | null | undefined) => nf.format(Math.round(Number(rial || 0) / 10));

type ModuleKey = "trade" | "nontrade";
type Party = {
  dl_code: string; title: string; debit_rial: number; credit_rial: number; credit_balance_rial: number; debit_balance_rial: number;
  item_count: number; last_date_jalali: string; last_payment_date_jalali: string; last_invoice_date_jalali: string;
};
type Module = {
  key: ModuleKey; sl_code: string; title: string; counterparty_count: number; open_count: number; debit_rial: number; credit_rial: number;
  credit_balance_rial: number; debit_balance_rial: number; creditor_count: number; debtor_count: number; counterparties: Party[];
};
type Overview = { fiscal_year_from_jalali: string; generated_at_jalali: string; modules: Record<ModuleKey, Module>; note: string };
type Line = {
  date_jalali: string; voucher_number: string; reference_number: string; description: string; debit_rial: number; credit_rial: number;
  balance_rial: number; follow_up_number: string; follow_up_date_jalali: string; branch: string; is_opening: boolean;
};
type Ledger = {
  title: string; dl_code: string; sl_code: string; debit_rial: number; credit_rial: number; balance_rial: number;
  opening_balance_rial: number; payments_rial: number; invoices_rial: number; lines: Line[];
};
type Filter = "all" | "owe" | "advance" | "settled";
type SortKey = "title" | "credit_balance" | "debit_balance" | "credit" | "debit" | "last";

async function get(path: string) {
  const r = await fetch(`${API()}${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const MODULE_LABEL: Record<ModuleKey, string> = { trade: "تجاری", nontrade: "غیرتجاری" };
const balanceLabel = (rial: number) => (rial > 0 ? "بدهی شرکت" : rial < 0 ? "پیش‌پرداخت / طلب شرکت" : "تسویه");

export default function PayablesPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [module, setModule] = useState<ModuleKey>("trade");
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "credit_balance", desc: true });
  const [party, setParty] = useState<Party | null>(null);

  useEffect(() => {
    get("/payables").then(setData).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);

  // لینک چت‌بات: ماژول (تجاری/غیرتجاری) + جستجو؛ اگر طرف حساب یکتا پیدا شد ریز گردشش هم باز می‌شود.
  const chatLink = useChatLink("payables");
  const listRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!chatLink || !data) return;
    const key: ModuleKey = chatLink.tab === "nontrade" ? "nontrade" : "trade";
    const q = (chatLink.search || "").trim().toLocaleLowerCase("fa-IR");
    const inModule = (k: ModuleKey) => data.modules[k].counterparties.filter((p) =>
      (chatLink.ref && p.dl_code === chatLink.ref) || (q && `${p.title} ${p.dl_code}`.toLocaleLowerCase("fa-IR").includes(q)));
    const own = inModule(key), other = inModule(key === "trade" ? "nontrade" : "trade");
    const useKey = own.length || !other.length ? key : (key === "trade" ? "nontrade" : "trade");
    const matches = useKey === key ? own : other;
    setModule(useKey); setFilter("all"); setSearch(chatLink.search || chatLink.ref || "");
    setParty(matches.length === 1 ? matches[0] : null);
    flashChatTarget(listRef.current);
  }, [chatLink, data]);

  const active = data?.modules[module];
  const rows = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("fa-IR");
    const list = (active?.counterparties || []).filter((p) =>
      (filter === "all" || (filter === "owe" && p.credit_balance_rial > 0) || (filter === "advance" && p.debit_balance_rial > 0)
        || (filter === "settled" && !p.credit_balance_rial && !p.debit_balance_rial))
      && (!q || `${p.title} ${p.dl_code}`.toLocaleLowerCase("fa-IR").includes(q)));
    const value = (p: Party): string | number => ({
      title: p.title, credit_balance: p.credit_balance_rial, debit_balance: p.debit_balance_rial,
      credit: p.credit_rial, debit: p.debit_rial, last: p.last_date_jalali,
    })[sort.key];
    return [...list].sort((a, b) => {
      const x = value(a), y = value(b);
      const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "fa");
      return sort.desc ? -cmp : cmp;
    });
  }, [active, filter, search, sort]);

  const switchModule = (key: ModuleKey) => { setModule(key); setFilter("all"); setSearch(""); setParty(null); };
  const sortBy = (key: SortKey) => setSort((s) => ({ key, desc: s.key === key ? !s.desc : true }));
  const arrow = (key: SortKey) => (sort.key === key ? (sort.desc ? " ▼" : " ▲") : " ⇅");

  if (error) return <div className="profile-warning">دریافت حساب‌های پرداختنی ناموفق بود: {error}</div>;
  if (!data || !active) return <div className="pay-loading">در حال دریافت حساب‌های پرداختنی از راهکاران…</div>;

  const totalOwe = data.modules.trade.credit_balance_rial + data.modules.nontrade.credit_balance_rial;
  const totalAdvance = data.modules.trade.debit_balance_rial + data.modules.nontrade.debit_balance_rial;

  return (
    <div className="pay-page">
      <section className="pay-hero">
        <div>
          <small>پرداخت تجاری · سال مالی از {data.fiscal_year_from_jalali} تا {data.generated_at_jalali}</small>
          <h2>بدهی شرکت به تأمین‌کنندگان و طرف حساب‌ها</h2>
          <p>{data.note}</p>
        </div>
        <div className="pay-hero-totals">
          <div><small>کل بدهی شرکت</small><b className="owe">{toman(totalOwe)}</b><span>تومان</span></div>
          <div><small>کل پیش‌پرداخت / طلب</small><b className="adv">{toman(totalAdvance)}</b><span>تومان</span></div>
        </div>
      </section>

      <section className="pay-modules" role="tablist">
        {(["trade", "nontrade"] as ModuleKey[]).map((key) => {
          const m = data.modules[key];
          return (
            <button key={key} role="tab" aria-selected={module === key} className={`pay-module ${module === key ? "active" : ""}`} onClick={() => switchModule(key)}>
              <span className="pay-module-head"><b>{MODULE_LABEL[key]}</b><small>معین {m.sl_code} · {m.title}</small></span>
              <span className="pay-module-grid">
                <span><small>بدهی شرکت</small><strong className="owe">{toman(m.credit_balance_rial)}</strong><em>{fa(m.creditor_count)} طرف حساب</em></span>
                <span><small>پیش‌پرداخت / طلب</small><strong className="adv">{toman(m.debit_balance_rial)}</strong><em>{fa(m.debtor_count)} طرف حساب</em></span>
                <span><small>گردش بستانکار (فاکتور)</small><strong>{toman(m.credit_rial)}</strong></span>
                <span><small>گردش بدهکار (پرداخت)</small><strong>{toman(m.debit_rial)}</strong></span>
              </span>
              <span className="pay-module-foot">{fa(m.counterparty_count)} طرف حساب · {fa(m.open_count)} با مانده</span>
            </button>
          );
        })}
      </section>

      <section className="pay-list" key={module} ref={listRef}>
        <div className="pay-list-head">
          <h3>طرف حساب‌های {MODULE_LABEL[module]} <small>(معین {active.sl_code})</small></h3>
          <div className="pay-chips">
            {([["all", "همه", active.counterparty_count], ["owe", "بدهی شرکت", active.creditor_count], ["advance", "پیش‌پرداخت / طلب", active.debtor_count],
              ["settled", "تسویه", active.counterparty_count - active.open_count]] as [Filter, string, number][]).map(([id, label, n]) => (
              <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>{label} · {fa(n)}</button>
            ))}
          </div>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="نام یا کد تفصیلی طرف حساب…" />
        </div>
        <div className="pay-table-wrap">
          <table className="pay-table">
            <thead><tr>
              <th onClick={() => sortBy("title")}>طرف حساب{arrow("title")}</th>
              <th onClick={() => sortBy("credit_balance")}>بدهی شرکت (مانده بستانکار){arrow("credit_balance")}</th>
              <th onClick={() => sortBy("debit_balance")}>پیش‌پرداخت (مانده بدهکار){arrow("debit_balance")}</th>
              <th onClick={() => sortBy("credit")}>گردش بستانکار{arrow("credit")}</th>
              <th onClick={() => sortBy("debit")}>گردش بدهکار{arrow("debit")}</th>
              <th onClick={() => sortBy("last")}>آخرین گردش{arrow("last")}</th>
            </tr></thead>
            <tbody>
              <tr className="pay-total">
                <td>جمع {rows.length !== active.counterparty_count ? "(فیلترشده)" : ""} · {fa(rows.length)} طرف حساب</td>
                <td className="owe">{toman(rows.reduce((s, p) => s + p.credit_balance_rial, 0))}</td>
                <td className="adv">{toman(rows.reduce((s, p) => s + p.debit_balance_rial, 0))}</td>
                <td>{toman(rows.reduce((s, p) => s + p.credit_rial, 0))}</td>
                <td>{toman(rows.reduce((s, p) => s + p.debit_rial, 0))}</td>
                <td />
              </tr>
              {rows.map((p, i) => (
                <tr key={p.dl_code} className={party?.dl_code === p.dl_code ? "selected" : ""} style={{ animationDelay: `${Math.min(i, 20) * 18}ms` }} onClick={() => setParty(p)}>
                  <td><b>{p.title}</b><small>کد {p.dl_code} · {fa(p.item_count)} ردیف</small></td>
                  <td className={p.credit_balance_rial ? "owe" : "zero"}>{p.credit_balance_rial ? toman(p.credit_balance_rial) : "—"}</td>
                  <td className={p.debit_balance_rial ? "adv" : "zero"}>{p.debit_balance_rial ? toman(p.debit_balance_rial) : "—"}</td>
                  <td>{toman(p.credit_rial)}</td>
                  <td>{toman(p.debit_rial)}</td>
                  <td>{p.last_date_jalali || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <p className="pay-empty">طرف حسابی با این فیلتر نیست.</p>}
        </div>
      </section>

      <PartyDrawer module={module} party={party} onClose={() => setParty(null)} />
    </div>
  );
}

function PartyDrawer({ module, party, onClose }: { module: ModuleKey; party: Party | null; onClose: () => void }) {
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"lines" | "summary">("lines");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<"all" | "debit" | "credit">("all");

  useEffect(() => {
    if (!party) return;
    let active = true;
    setLedger(null); setError(""); setTab("lines"); setSearch(""); setKind("all");
    get(`/payables/${module}/${encodeURIComponent(party.dl_code)}`)
      .then((d) => active && setLedger(d))
      .catch((e) => active && setError(e instanceof Error ? e.message : "خطا"));
    return () => { active = false; };
  }, [module, party]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const lines = useMemo(() => {
    const q = search.trim().toLocaleLowerCase("fa-IR");
    return (ledger?.lines || []).filter((l) => (kind === "all" || (kind === "debit" ? l.debit_rial > 0 : l.credit_rial > 0))
      && (!q || [l.description, l.voucher_number, l.reference_number, l.date_jalali, l.follow_up_number].some((v) => String(v || "").toLocaleLowerCase("fa-IR").includes(q))));
  }, [ledger, search, kind]);

  const open = Boolean(party);
  return (
    <>
      <div className={`pay-overlay ${open ? "open" : ""}`} onClick={onClose} />
      {/* نه <aside>: استایل سراسری اپ روی aside (منوی کناری) اعمال می‌شود. */}
      <div className={`pay-drawer ${open ? "open" : ""}`} role="dialog" aria-modal="true" aria-hidden={!open}>
        {party && <>
          <div className="pay-drawer-head">
            <div>
              <small>{MODULE_LABEL[module]} · معین {ledger?.sl_code || ""} · تفصیلی {party.dl_code}</small>
              <h3>{ledger?.title || party.title}</h3>
            </div>
            <button className="pay-close" onClick={onClose} aria-label="بستن">✕</button>
          </div>
          <div className="pay-drawer-kpis">
            <div><small>مانده</small><b className={party.credit_balance_rial ? "owe" : party.debit_balance_rial ? "adv" : ""}>
              {toman(Math.abs(party.credit_balance_rial - party.debit_balance_rial))}</b><span>{balanceLabel(party.credit_balance_rial - party.debit_balance_rial)}</span></div>
            <div><small>مانده افتتاحیه</small><b>{ledger ? toman(Math.abs(ledger.opening_balance_rial)) : "…"}</b><span>{ledger ? balanceLabel(ledger.opening_balance_rial) : ""}</span></div>
            <div><small>فاکتور / بستانکار امسال</small><b>{ledger ? toman(ledger.invoices_rial) : "…"}</b><span>تومان</span></div>
            <div><small>پرداخت / بدهکار امسال</small><b>{ledger ? toman(ledger.payments_rial) : "…"}</b><span>تومان</span></div>
          </div>
          <div className="pay-tabs" data-tab={tab} role="tablist">
            <button className={tab === "lines" ? "active" : ""} onClick={() => setTab("lines")}>ریز گردش</button>
            <button className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>خلاصه ماهانه</button>
            <i />
          </div>
          {error && <div className="profile-warning">{error}</div>}
          {!ledger && !error && <div className="pay-loading">در حال دریافت ریز گردش…</div>}
          {ledger && tab === "lines" && <div className="pay-tab-body" key="lines">
            <div className="pay-drawer-filters">
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شرح، شماره سند یا پیگیری…" />
              <div className="pay-chips">
                {([["all", "همه"], ["credit", "بستانکار (فاکتور)"], ["debit", "بدهکار (پرداخت)"]] as ["all" | "debit" | "credit", string][]).map(([id, label]) => (
                  <button key={id} className={kind === id ? "active" : ""} onClick={() => setKind(id)}>{label}</button>
                ))}
              </div>
            </div>
            <div className="pay-table-wrap drawer">
              <table className="pay-table">
                <thead><tr><th>تاریخ</th><th>سند / عطف</th><th>شرح</th><th>بدهکار</th><th>بستانکار</th><th>مانده</th></tr></thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={`${l.voucher_number}-${i}`} className={l.is_opening ? "opening" : ""}>
                      <td className="num">{l.date_jalali}</td>
                      <td className="num">{l.voucher_number}{l.reference_number && l.reference_number !== l.voucher_number ? <small>عطف {l.reference_number}</small> : null}</td>
                      <td className="desc">{l.description || "—"}{l.follow_up_number && <small>پیگیری {l.follow_up_number} {l.follow_up_date_jalali}</small>}</td>
                      <td className="num adv">{l.debit_rial ? toman(l.debit_rial) : ""}</td>
                      <td className="num owe">{l.credit_rial ? toman(l.credit_rial) : ""}</td>
                      <td className="num">{toman(Math.abs(l.balance_rial))}<small>{l.balance_rial > 0 ? "بس" : l.balance_rial < 0 ? "بد" : ""}</small></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!lines.length && <p className="pay-empty">ردیفی با این فیلتر نیست.</p>}
            </div>
          </div>}
          {ledger && tab === "summary" && <div className="pay-tab-body" key="summary"><MonthlySummary lines={ledger.lines} /></div>}
        </>}
      </div>
    </>
  );
}

const MONTH_NAMES = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
const monthName = (key: string) => {
  const m = key.match(/^(\d{4})\/(\d{2})$/);
  return m ? `${MONTH_NAMES[Number(m[2]) - 1]} ${m[1].replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)])}` : key;
};

function MonthlySummary({ lines }: { lines: Line[] }) {
  const months = useMemo(() => {
    const map = new Map<string, { debit: number; credit: number; count: number }>();
    lines.forEach((l) => {
      const key = l.is_opening ? "افتتاحیه" : l.date_jalali.slice(0, 7);
      const m = map.get(key) || { debit: 0, credit: 0, count: 0 };
      m.debit += l.debit_rial; m.credit += l.credit_rial; m.count += 1;
      map.set(key, m);
    });
    let running = 0;
    return Array.from(map.entries()).map(([key, m]) => { running += m.credit - m.debit; return { key, ...m, running }; });
  }, [lines]);
  const max = Math.max(1, ...months.map((m) => Math.max(m.debit, m.credit)));
  return (
    <div className="pay-months">
      {months.map((m) => (
        <div key={m.key} className="pay-month">
          <span className="pay-month-label">{monthName(m.key)}</span>
          <span className="pay-bars">
            <i className="owe" style={{ width: `${(100 * m.credit) / max}%` }} title={`بستانکار ${toman(m.credit)}`} />
            <i className="adv" style={{ width: `${(100 * m.debit) / max}%` }} title={`بدهکار ${toman(m.debit)}`} />
          </span>
          <span className="pay-month-nums">
            <em className="owe">{toman(m.credit)}</em><em className="adv">{toman(m.debit)}</em>
            <b>مانده {toman(Math.abs(m.running))} {m.running > 0 ? "بس" : m.running < 0 ? "بد" : ""}</b>
          </span>
        </div>
      ))}
      <p className="pay-legend"><i className="owe" /> بستانکار (فاکتور، بدهی شرکت) <i className="adv" /> بدهکار (پرداخت شرکت) · مبالغ به تومان</p>
    </div>
  );
}
