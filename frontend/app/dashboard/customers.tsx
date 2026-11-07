// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (customers).
import { useEffect, useMemo, useState } from "react";
import { Heading, Risk } from "./widgets";
import { SalesNetwork } from "./sales-network";
import { JALALI_MONTH_NAMES, cname, currentJalali, daysToDue, fa, fullToman, money, remainingLabel, request, risk } from "./shared";
import type { Cheque, Customer } from "./types";

export function Customers({
  customers,
  open,
}: {
  customers: Customer[];
  open: (c: Customer) => void;
}) {
  const [branch, setBranch] = useState("");
  const [search, setSearch] = useState("");
  const [customerSource, setCustomerSource] = useState<"rahkaran" | "karamad" | null>(null);
  const [karamad, setKaramad] = useState<any>({ customers: [], available_branches: [], summary: {} });
  const [karamadError, setKaramadError] = useState("");
  const [portfolio, setPortfolio] = useState<any>({ summary: {}, customers: [] });
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [debtFilter, setDebtFilter] = useState<"all" | "active" | "debtor" | "uncovered" | "cheque" | "creditor">("all");
  const [network, setNetwork] = useState<any>(null);
  const [networkError, setNetworkError] = useState("");
  useEffect(() => {
    let active = true;
    request("/sales-network")
      .then((d) => { if (active) setNetwork(d); })
      .catch((e) => { if (active) setNetworkError(e instanceof Error ? e.message : "دریافت شبکه فروش کارآمد ناموفق بود"); });
    return () => { active = false; };
  }, []);
  // فیلتر ماه پرونده مشتری: null = مانده امروز؛ {year, month} = مانده هر مشتری تا پایان همان ماه شمسی
  const [asOf, setAsOf] = useState<{ year: number; month: number } | null>(null);
  useEffect(() => {
    // فهرست کامل مشتریان راهکاران (دارای چک + خریداران فعال سال جاری و قبل) با مانده حساب.
    let active = true;
    setPortfolioLoading(true);
    request(`/customer-collection-portfolio?limit=1000&source=rahkaran${asOf ? `&year=${asOf.year}&month=${asOf.month}` : ""}`)
      .then((d) => { if (active) setPortfolio(d); })
      .catch(() => { if (active) setPortfolio({ summary: {}, customers: [] }); })
      .finally(() => { if (active) setPortfolioLoading(false); });
    return () => { active = false; };
  }, [asOf]);
  const asOfLabel = asOf ? `تا پایان ${JALALI_MONTH_NAMES[asOf.month - 1]} ${fa(asOf.year).replace(/٬/g, "")}` : "تا امروز";
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams();
    if (branch) params.set("branch", branch);
    request(`/karamad-manual/customer-summary${params.toString() ? `?${params}` : ""}`)
      .then((data) => { if (active) { setKaramad(data); setKaramadError(""); } })
      .catch((e) => { if (active) setKaramadError(e instanceof Error ? e.message : "دریافت داده کارآمد ناموفق بود"); });
    return () => { active = false; };
  }, [branch]);

  const normalizeName = (value?: string) => String(value || "")
    .replace(/[يى]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/\u200c/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase("fa-IR");

  const customerPortfolioAmount = (c: Customer) => {
    const k: any = c.karamad_activity || {};
    return Number(c.open_exposure || 0)
      + Number(k.received_cheque_amount_rial || 0)
      + Number(k.issued_cheque_amount_rial || 0)
      + Number(k.received_transfer_amount_rial || 0)
      + Number(k.paid_transfer_amount_rial || 0);
  };

  const customerStatus = (c: Customer) => {
    const k: any = c.karamad_activity || {};
    const overdue = Number(c.overdue_open_amount || 0) + Number(k.received_cheque_overdue_amount_rial || 0);
    const today = Number(k.received_cheque_today_amount_rial || 0);
    const future = Number(k.received_cheque_future_amount_rial || 0);
    if (overdue > 0) return { label: "دارای سررسید گذشته", tone: "danger" };
    if (today > 0) return { label: "سررسید امروز", tone: "critical" };
    if (future > 0) return { label: "دارای سررسید آینده", tone: "safe" };
    const r = c.counterpart_ref ? risk(c) : "safe";
    if (r === "critical") return { label: "پرریسک", tone: "critical" };
    if (r === "danger") return { label: "نیازمند توجه", tone: "danger" };
    return { label: "عادی / بدون معوق", tone: "safe" };
  };

  const merged = useMemo(() => {
    // کلید راهکاران = کد تفصیلی (counterpart_ref)؛ پرتفوی کامل اگر رسیده، وگرنه فهرست مشتریان دارای چک.
    const byRef = new Map<string, Customer>();
    customers.forEach((c) => { if (c.counterpart_ref != null) byRef.set(String(c.counterpart_ref), { ...c, data_source: "rahkaran" }); });
    (portfolio?.customers || []).forEach((p: any) => {
      if (p.counterpart_ref == null) return;
      const key = String(p.counterpart_ref);
      byRef.set(key, { ...(byRef.get(key) || {}), ...p, data_source: "rahkaran" } as Customer);
    });
    // فعالیت کارآمد به همه ردیف‌های راهکاران هم‌نام وصل می‌شود؛ مشتری فقط‌کارآمد جدا می‌ماند.
    const rahkaranByName = new Map<string, Customer[]>();
    byRef.forEach((c) => {
      const n = normalizeName(cname(c));
      if (n) rahkaranByName.set(n, [...(rahkaranByName.get(n) || []), c]);
    });
    const karamadOnly: Customer[] = [];
    (karamad?.customers || []).forEach((k: any) => {
      const n = normalizeName(k.customer_name);
      if (!n) return;
      const same = rahkaranByName.get(n);
      if (same) same.forEach((c) => { c.karamad_activity = k; });
      else karamadOnly.push({ customer_name: k.customer_name, data_source: "karamad", karamad_activity: k } as Customer);
    });
    let rows = [...byRef.values(), ...karamadOnly];
    if (branch) rows = rows.filter((c) => Boolean(c.karamad_activity));
    const q = normalizeName(search);
    if (q) rows = rows.filter((c) => normalizeName(`${cname(c)} ${(c as any).counterpart_code || ""} ${c.counterpart_ref || ""}`).includes(q));
    return rows.sort((a, b) => {
      const diff = customerPortfolioAmount(b) - customerPortfolioAmount(a);
      return diff !== 0 ? diff : cname(a).localeCompare(cname(b), "fa");
    });
  }, [customers, portfolio, karamad, branch, search]);

  const rahkaranCustomers = merged.filter((c) => Boolean(c.counterpart_ref));
  // Karamad is shown as the sales network (هیبرید من / ویزیتور), never as a customer list.
  const sourceRows = customerSource === "rahkaran" ? rahkaranCustomers : [];
  const positions = useMemo(() => {
    const map = new Map<string, any>();
    (portfolio?.customers || []).forEach((p: any) => {
      const key = customerSource === "rahkaran" ? String(p.counterpart_ref) : normalizeName(p.customer_name || cname(p));
      map.set(key, p);
    });
    return map;
  }, [portfolio, customerSource]);
  const positionOf = (c: Customer): any => positions.get(customerSource === "rahkaran" ? String(c.counterpart_ref) : normalizeName(cname(c)))?.collection_position || {};
  const accountStateOf = (c: Customer): string => positions.get(customerSource === "rahkaran" ? String(c.counterpart_ref) : normalizeName(cname(c)))?.account_position?.balance_status || "unknown";
  const visibleRows = sourceRows.filter((c) => {
    const cp = positionOf(c);
    const debt = Number(cp.open_account_receivable_rial || 0), cheque = Number(cp.open_cheque_amount_rial || 0);
    if (debtFilter === "active") return Boolean((c as any).is_active_buyer);
    if (debtFilter === "debtor") return debt > 0;
    if (debtFilter === "uncovered") return debt > 0 && cheque <= 0;
    if (debtFilter === "cheque") return cheque > 0;
    if (debtFilter === "creditor") return Number(cp.customer_credit_rial || 0) > 0;
    return true;
  });
  const debtSummary = portfolio?.summary || {};

  if (!customerSource) return (
    <>
      <section className="cheque-hub-intro customer-source-intro">
        <div>
          <small>پرونده مشتری</small>
          <h2>ابتدا منبع اطلاعات مشتری را انتخاب کنید</h2>
          <p>مثل بخش چک‌ها، ابتدا راهکاران یا کارآمد را باز کنید؛ سپس فهرست مشتریان همان منبع و در مرحله بعد ریز پرونده نمایش داده می‌شود.</p>
        </div>
        <span>راهکاران + کارآمد</span>
      </section>
      {karamadError && <div className="profile-warning">{karamadError}</div>}
      <section className="cheque-source-grid customer-source-grid">
        <button type="button" className="cheque-source-card rahkaran" onClick={() => { setCustomerSource("rahkaran"); setBranch(""); setSearch(""); }}>
          <span>پرونده‌های مشتری</span><h2>راهکاران</h2>
          <strong>{portfolioLoading ? "…" : fa(rahkaranCustomers.length)}</strong><small>مشتری{portfolio?.summary?.active_customer_count != null ? ` · ${fa(portfolio.summary.active_customer_count)} خریدار فعال (سال جاری و قبل)` : ""}</small>
          <p>هر کد تفصیلی یک پرونده است (یک شخص با دو برند دو پرونده دارد)؛ ریز چک، مانده، ریسک و سوابق مالی.</p>
          <b>مشاهده مشتریان راهکاران ←</b>
        </button>
        <button type="button" className="cheque-source-card karamad" onClick={() => { setCustomerSource("karamad"); setBranch(""); setSearch(""); }}>
          <span>شبکه فروش</span><h2>کارآمد</h2>
          <strong>{network ? fa(network.summary?.hybrid_count || 0) : "…"}</strong><small>هیبرید من · {network ? fa(network.summary?.active_visitor_count || 0) : "…"} ویزیتور فعال · {network ? fa(network.summary?.active_customer_count || 0) : "…"} مشتری فعال</small>
          <p>هیبرید من‌ها و ویزیتورهای کارآمد؛ فروش، مطالبات و چک‌های هر شعبه و هر ویزیتور.</p>
          <b>مشاهده هیبرید من‌ها و ویزیتورها ←</b>
        </button>
      </section>
    </>
  );

  if (customerSource === "karamad") return (
    <>
      <SalesNetwork data={network} error={networkError} onBack={() => setCustomerSource(null)} />
    </>
  );

  return (
    <>
      <button className="cheque-back" onClick={() => { setCustomerSource(null); setBranch(""); setSearch(""); setDebtFilter("all"); }}>→ بازگشت به انتخاب راهکاران یا کارآمد</button>
      <article className="fd-panel unified-customer-directory">
        <Heading
          h="پرونده مشتریان — راهکاران"
          p="فهرست مشتریان راهکاران؛ برای ورود به ریز پرونده روی مشتری کلیک کنید."
        />
        <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar">
          <div>
            <b>جستجو با نام یا کد مشتری</b>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="نام، برند یا کد تفصیلی مشتری…"
            />
          </div>
          <small>{fa(visibleRows.length)} مشتری پیدا شد</small>
        </section>
        <CustomerMonthFilter value={asOf} onChange={setAsOf} loading={portfolioLoading} />
        <div className="cf-kpis cf-directory-kpis">
          {/* مشتری فعال = فاکتور فروش قطعی در سال مالی جاری یا قبل؛ کلیک = فیلتر همین مشتریان */}
          <article className={`cf-active-kpi${debtFilter === "active" ? " active" : ""}`} onClick={() => setDebtFilter(debtFilter === "active" ? "all" : "active")} title="نمایش فقط مشتریان فعال">
            <small>مشتری فعال</small>
            <b>{portfolioLoading ? "…" : fa(debtSummary.active_customer_count || 0)} <em>نفر</em></b>
            <span>{portfolioLoading ? "در حال دریافت" : `${fa(debtSummary.active_current_year_count || 0)} نفر خرید امسال · از ${fa(debtSummary.customer_count || 0)} پرونده`}</span>
          </article>
          {/* مثل گزارش واحد مالی «مانده حساب مشتری بر اساس تجاری و برگشتی»: مشتریان برند (بدون هیبرید و انبار پخش)،
              مانده حساب = تجاری + اشخاص هر مشتری اگر مثبت؛ بستانکاران کم نمی‌شوند؛ برگشتی (۱۲۳۰۰۴ + ۱۲۳۰۰۹) جدا */}
          <article className="cf-accent-red"><small>کل مانده بدهی مشتریان · {asOfLabel}</small><b>{portfolioLoading ? "…" : fullToman(debtSummary.report_open_account_receivable_rial || 0)}</b>
            <span>{portfolioLoading ? "تومان" : `تومان · با برگشتی ${fullToman((debtSummary.report_open_account_receivable_rial || 0) + (debtSummary.report_returned_account_rial || 0))} · بستانکاران کم نشده`}</span></article>
          <article><small>حساب برگشتی · {asOfLabel}</small><b>{portfolioLoading ? "…" : fullToman(debtSummary.report_returned_account_rial || 0)}</b><span>تومان · معین ۱۲۳۰۰۴ و ۱۲۳۰۰۹</span></article>
          {/* رسمی = ۱۲۳۰۰۳ دریافتنی تجاری؛ غیررسمی = ۱۲۳۰۱۱ دریافتنی اشخاص + حساب‌های برگشتی */}
          <article><small>غیررسمی منهای رسمی</small><b>{portfolioLoading ? "…" : fullToman(debtSummary.report_unofficial_minus_official_rial || 0)}</b>
            <span>{portfolioLoading ? "تومان" : `تومان · غیررسمی ${fullToman(debtSummary.report_unofficial_balance_rial || 0)} − رسمی ${fullToman(debtSummary.report_official_balance_rial || 0)}`}</span></article>
          <article><small>چک باز در دست شرکت</small><b>{portfolioLoading ? "…" : fullToman(debtSummary.open_cheque_amount_rial || 0)}</b><span>تومان</span></article>
          <article><small>بستانکاری مشتریان</small><b>{portfolioLoading ? "…" : fullToman(debtSummary.report_customer_credit_rial || 0)}</b><span>تومان · جدا؛ از بدهی کم نشده</span></article>
        </div>
        <div className="collection-module-filters cf-debt-filters">
          {([["all", "همه"], ["active", `خریدار فعال${portfolio?.summary?.active_customer_count != null ? ` (${fa(portfolio.summary.active_customer_count)})` : ""}`], ["debtor", "مانده بدهکار"], ["uncovered", "بدهکار بدون چک"], ["cheque", "دارای چک باز"], ["creditor", "بستانکار"]] as const).map(([k, l]) => <button key={k} className={debtFilter === k ? "active" : ""} onClick={() => setDebtFilter(k)}>{l}</button>)}
        </div>
        {karamadError && <div className="profile-warning">{karamadError}</div>}
        <div className="fd-table">
          <table>
            <thead>
              <tr>
                <th>مشتری</th>
                <th>مانده بدهی</th>
                <th>غیررسمی − رسمی</th>
                <th>ارزش پرونده</th>
                <th>مانده باز</th>
                <th>معوق</th>
                <th>چک برگشتی</th>
                <th>چک آینده</th>
                <th>چک‌های ثبت‌شده</th>
                <th>حواله‌های ثبت‌شده</th>
                <th>شعبه / فعالیت</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((c) => {
                const k: any = c.karamad_activity || {};
                const chequeCount = Number(c.historical_cheque_count || 0) + Number(k.received_cheque_count || 0) + Number(k.issued_cheque_count || 0);
                const transferCount = Number(k.received_transfer_count || 0) + Number(k.paid_transfer_count || 0);
                const cc: any = c;
                return <tr key={`rk-${c.counterpart_ref || normalizeName(cname(c))}`} onClick={() => open({ ...c, data_source: "rahkaran", karamad_activity: undefined })}>
                  <td className="cf-wrap"><b>{cname(c)}</b>
                    <small className="customer-row-sub">کد {fa(Number(cc.counterpart_code || c.counterpart_ref || 0)).replace(/٬/g, "")}
                      {cc.invoice_current_year_count ? ` · ${fa(cc.invoice_current_year_count)} فاکتور امسال` : cc.invoice_previous_year_count ? " · خرید سال قبل" : cc.no_cheque_history ? "" : " · بدون خرید ۲ سال اخیر"}</small></td>
                  <td>{portfolioLoading ? "…" : <><b>{fullToman(positionOf(c).open_account_receivable_rial || 0)}</b> <span className={`collection-account-state ${accountStateOf(c)}`}>{({ debtor: "بدهکار", creditor: "بستانکار", settled: "تسویه" } as any)[accountStateOf(c)] || "—"}</span></>}</td>
                  <td>{portfolioLoading ? "…" : <><b>{fullToman(positionOf(c).unofficial_minus_official_rial || 0)}</b>
                    <small className="customer-row-sub">غیررسمی {fullToman(positionOf(c).unofficial_balance_rial || 0)} · رسمی {fullToman(positionOf(c).official_balance_rial || 0)}</small></>}</td>
                  <td><b>{fullToman(customerPortfolioAmount(c))}</b></td>
                  <td>{c.counterpart_ref ? fullToman(c.open_exposure) : "—"}</td>
                  <td>{c.counterpart_ref ? fullToman(c.overdue_open_amount) : fullToman(k.received_cheque_overdue_amount_rial || 0)}</td>
                  <td><b>{fa(c.counterpart_ref ? (c.returned_cheque_count || 0) : (k.received_cheque_returned_count || 0))}</b> فقره · {fullToman(c.counterpart_ref ? (c.returned_cheque_amount || 0) : (k.received_cheque_returned_amount_rial || 0))}</td>
                  <td><b>{fa(c.counterpart_ref ? (c.future_open_cheque_count || 0) : (k.received_cheque_future_count || 0))}</b> فقره · {fullToman(c.counterpart_ref ? (c.future_open_cheque_amount || 0) : (k.received_cheque_future_amount_rial || 0))}</td>
                  <td><b>{fa(chequeCount)}</b> فقره</td>
                  <td><b>{fa(transferCount)}</b> ردیف</td>
                  <td>{k.movement_count ? `${fa(k.movement_count)} گردش · ${(k.branches || []).join("، ") || "بدون شعبه"}` : (c.counterpart_ref ? "اطلاعات راهکاران" : "—")}</td>
                  <td>{(() => { const s = customerStatus(c); return <span className={`fd-badge ${s.tone}`}>{s.label}</span>; })()}</td>
                </tr>;
              })}
            </tbody>
          </table>
          {!visibleRows.length && <div className="profile-loading">مشتری با این نام یا فیلتر پیدا نشد.</div>}
        </div>
      </article>
    </>
  );
}

// فیلتر ماه پرونده مشتری: سال + ماه‌های همان سال؛ «امروز» = مانده لحظه‌ای. ماه‌های آینده غیرفعال‌اند.
export function CustomerMonthFilter({ value, onChange, loading }: {
  value: { year: number; month: number } | null; onChange: (v: { year: number; month: number } | null) => void; loading: boolean;
}) {
  const now = currentJalali();
  const [year, setYear] = useState(value?.year || now.year);
  const years = [now.year, now.year - 1];
  return <section className="cf-month-filter">
    <b>مانده</b>
    <button type="button" className={!value ? "active" : ""} onClick={() => onChange(null)}>امروز</button>
    <select value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="سال">
      {years.map((y) => <option key={y} value={y}>{fa(y).replace(/٬/g, "")}</option>)}
    </select>
    {JALALI_MONTH_NAMES.map((name, i) => {
      const future = year > now.year || (year === now.year && i + 1 > now.month);
      const active = value?.year === year && value?.month === i + 1;
      return <button type="button" key={name} disabled={future} className={active ? "active" : ""}
        onClick={() => onChange(active ? null : { year, month: i + 1 })} title={`مانده هر مشتری تا پایان ${name} ${fa(year).replace(/٬/g, "")}`}>{name}</button>;
    })}
    {loading && <small>در حال محاسبه…</small>}
  </section>;
}

export function Cheques({ rows }: { rows: Cheque[] }) {
  return (
    <>
      <article className="fd-panel">
        <Heading
          h="چک‌های آینده و دلایل ریسک"
          p="قانون شرکت: سررسید حداکثر ۹۰ روز"
        />
        <div className="cheque-enterprise">
          {rows.map((c) => {
            const remaining = daysToDue(c);
            return (
              <div
                key={c.cheque_id}
                className={(c.term_days || 0) > 90 ? "bad" : ""}
              >
                <header>
                  <div>
                    <b>{c.counterpart_name}</b>
                    <small>
                      تاریخ سررسید: {c.due_date_jalali || c.due_date} • مدت کل
                      چک: {fa(c.term_days)} روز
                    </small>
                  </div>
                  <Risk
                    x={
                      c.risk_level === "critical"
                        ? "critical"
                        : c.risk_level === "high" || (c.term_days || 0) > 90
                          ? "danger"
                          : "safe"
                    }
                  />
                </header>
                <div className="cheque-time-row">
                  <span
                    className={`due-count ${remaining === undefined ? "unknown" : remaining < 0 ? "overdue" : remaining <= 7 ? "soon" : "normal"}`}
                  >
                    ◷ {remainingLabel(c)}
                  </span>
                  <span>مدت کل: {fa(c.term_days)} روز</span>
                </div>
                <strong>{money(c.amount)} تومان</strong>
                <em>
                  احتمال برگشت {fa(c.estimated_return_probability_percent)}٪
                </em>
                <section>
                  <b>چرا پرریسک است؟</b>
                  {(c.reasons || ["ریسک از سابقه مشتری محاسبه شده است."]).map(
                    (x, i) => (
                      <p key={i}>! {x}</p>
                    ),
                  )}
                </section>
              </div>
            );
          })}
        </div>
      </article>
    </>
  );
}
