// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (sales-network).
import { useEffect, useState } from "react";
import { RegCell, chequeNo } from "../cheque-reg";
import { Heading } from "./agents";
import { ChequeReturnRisk, LastInvoicesTable } from "./customer-profile";
import { API, fa, fullToman, money, request, risk } from "./shared";

export function SalesNetwork({ data, error, onBack }: { data: any; error: string; onBack: () => void }) {
  const [branchId, setBranchId] = useState<number | null>(null);
  const [visitorId, setVisitorId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  if (visitorId != null) return <NetworkFile kind="visitor" id={visitorId} onBack={() => setVisitorId(null)} backLabel={branchId != null ? "→ بازگشت به پرونده هیبرید" : "→ بازگشت به هیبرید من‌ها"} />;
  if (branchId != null) return <NetworkFile kind="branch" id={branchId} onBack={() => setBranchId(null)} onOpenVisitor={setVisitorId} backLabel="→ بازگشت به هیبرید من‌ها" />;

  const cy = data?.current_year_label || "سال جاری", py = data?.previous_year_label || "سال قبل";
  const q = search.trim().toLocaleLowerCase("fa-IR");
  const rows: any[] = (data?.branches || []).filter((b: any) => !q || [b.branch_name, ...(b.hybrids || [])].join(" ").toLocaleLowerCase("fa-IR").includes(q));
  const sm = data?.summary || {};
  return <>
    <button className="cheque-back" onClick={onBack}>→ بازگشت به انتخاب راهکاران یا کارآمد</button>
    <article className="fd-panel unified-customer-directory">
      <Heading h="هیبرید من‌ها و ویزیتورها — کارآمد" p="هر ردیف یک شعبه و هیبرید من‌های آن است؛ برای دیدن ویزیتورها، فروش، مطالبات و چک‌ها روی ردیف کلیک کنید." />
      <div className="unrecorded-payments-bar">
        <div><b>پرداخت‌های ثبت‌نشده احتمالی</b><small>مشتریانی که می‌گویند پرداخت کرده‌اند: واریزهای بی‌صاحب کارآمد، واریزهای ثبت‌شده به نام مشتری دیگر و مشتری پیشنهادی برای هر کدام (ساخت فایل حدود یک دقیقه).</small></div>
        <a className="rc-primary" href={`${API()}/karamad/unrecorded-payments.xlsx`}>دانلود Excel</a>
      </div>
      {error && <div className="profile-warning">{error}</div>}
      {!data && !error ? <div className="profile-loading">در حال دریافت شبکه فروش کارآمد...</div> : <>
        <div className="cf-kpis cf-directory-kpis">
          <article><small>هیبرید من</small><b>{fa(sm.hybrid_count || 0)}</b><span>در {fa(sm.branch_count || 0)} شعبه</span></article>
          <article><small>ویزیتور فعال</small><b>{fa(sm.active_visitor_count || 0)}</b><span>نفر</span></article>
          <article className="cf-active-kpi" title="مشتری با فاکتور فروش در سال جاری یا قبل (هر کد مشتری جدا)"><small>مشتری فعال</small><b>{fa(sm.active_customer_count || 0)} <em>نفر</em></b><span>{fa(sm.active_customer_current_year_count || 0)} نفر خرید {cy}</span></article>
          <article><small>فروش خالص {cy}</small><b>{fullToman(sm.current_year_sales_rial || 0)}</b><span>ناخالص: {fullToman(sm.current_year_gross_sales_rial || 0)} تومان</span></article>
          <article><small>فروش خالص {py}</small><b>{fullToman(sm.previous_year_sales_rial || 0)}</b><span>ناخالص: {fullToman(sm.previous_year_gross_sales_rial || 0)} تومان</span></article>
          <article className="cf-accent-red"><small>مطالبات مشتریان شعب</small><b>{money(sm.open_account_receivable_rial || 0)}</b><span>تومان • مانده دفتر کل</span></article>
        </div>
        <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar">
          <div><b>جستجوی هیبرید من یا شعبه</b><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="مثلاً رییسی یا اصفهان..." /></div>
          <small>{fa(rows.length)} شعبه</small>
        </section>
        <div className="cf-table cf-clickable"><table>
          <thead><tr><th>هیبرید من</th><th>شعبه</th><th>ویزیتور فعال</th><th>مشتری فعال</th><th>فروش {cy} (خالص / ناخالص)</th><th>فروش {py} (خالص / ناخالص)</th><th>مطالبات</th><th>چک باز</th></tr></thead>
          <tbody>{rows.map((b) => <tr key={b.branch_id} onClick={() => setBranchId(b.branch_id)}>
            <td className="cf-wrap"><b>{(b.hybrids || []).join("، ") || "—"}</b></td>
            <td>{b.branch_name}</td>
            <td>{fa(b.active_visitor_count || 0)}<small>{fa(b.active_supervisor_count || 0)} سرپرست</small></td>
            <td><b>{fa(b.active_customer_count || 0)}</b><small>{fa(b.active_customer_current_year_count || 0)} خرید {cy}</small></td>
            <SalesCell net={b.current_year_sales_rial} gross={b.current_year_gross_sales_rial} count={b.current_year_invoice_count} />
            <SalesCell net={b.previous_year_sales_rial} gross={b.previous_year_gross_sales_rial} count={b.previous_year_invoice_count} />
            <td className="cf-debt">{money(b.debt?.open_account_receivable_rial || 0)}<small>{fa(b.debt?.debtor_customer_count || 0)} مشتری بدهکار</small></td>
            <td>{money(b.open_cheque_amount_rial || 0)}<small>{fa(b.open_cheque_count || 0)} فقره</small></td>
          </tr>)}</tbody>
        </table></div>
        <small className="cf-note">{data?.debt_note}</small>
      </>}
    </article>
  </>;
}

// Karamad sales, as in the finance sales report: خالص = قابل پرداخت − برگشتی، ناخالص = جمع قبل تخفیف − برگشتی.
export function SalesCell({ net, gross, count }: { net?: number; gross?: number; count?: number }) {
  return <td><b>خالص {fullToman(net || 0)}</b><small>ناخالص {fullToman(gross || 0)}</small><small>تومان</small><small>{fa(count || 0)} فاکتور</small></td>;
}

// Breakdown of box 1 (مانده بدهی مشتریان), loaded when the box is opened.
export function DebtDetail({ kind, id }: { kind: "branch" | "visitor"; id: number }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    request(`/sales-network/${kind === "branch" ? "branches" : "visitors"}/${id}/debt-detail`)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت جزئیات بدهی ناموفق بود"); });
    return () => { active = false; };
  }, [kind, id]);
  if (error) return <div className="profile-warning">{error}</div>;
  if (!data) return <div className="profile-loading">در حال محاسبه جزئیات بدهی...</div>;

  const total = data.total_debt_rial || 0;
  const share = (v: number) => total ? `${fa(Math.round((v / total) * 100))}٪` : "—";
  const origin = data.origin || {};
  const q = search.trim().toLocaleLowerCase("fa-IR");
  const customers = (data.customers || []).filter((c: any) => !q
    || `${c.customer_name} ${c.customer_code}`.toLocaleLowerCase("fa-IR").includes(q));
  return <div className="cf-debt-detail">
    <div className="cf-debt-detail-grid">
      <div>
        <h4>۱. سن بدهی</h4>
        <p>تاریخ فاکتورهایی که هنوز پرداخت نشده‌اند (FIFO: پرداخت‌ها اول قدیمی‌ترین فاکتورها را تسویه می‌کنند). چک برگشتی جداگانه در بخش ۲ است.</p>
        <div className="cf-table"><table>
          <thead><tr><th>سن</th><th>مبلغ (تومان)</th><th>سهم</th><th>مشتری</th></tr></thead>
          <tbody>{(data.aging || []).map((a: any) => <tr key={a.label}>
            <td>{a.label}</td><td><b>{fullToman(a.amount_rial)}</b></td><td>{share(a.amount_rial)}</td><td>{fa(a.customer_count)}</td>
          </tr>)}</tbody>
        </table></div>
      </div>
      <div>
        <h4>۲. منشأ بدهی</h4>
        <p>بدهی از فاکتور پرداخت‌نشده آمده یا از چکی که برگشت خورده و هنوز تسویه نشده است.</p>
        <div className="cf-table"><table>
          <thead><tr><th>منشأ</th><th>مبلغ (تومان)</th><th>سهم</th></tr></thead>
          <tbody>
            <tr><td>فاکتور پرداخت‌نشده</td><td><b>{fullToman(origin.invoice)}</b></td><td>{share(origin.invoice)}</td></tr>
            <tr><td>بدهی باقی‌مانده بابت چک برگشتی</td><td className="cf-debt"><b>{fullToman(origin.returned_cheque)}</b></td><td>{share(origin.returned_cheque)}</td></tr>
            {origin.unmatched > 0 && <tr><td>مانده قدیمی‌تر از فاکتورهای ثبت‌شده</td><td><b>{fullToman(origin.unmatched)}</b></td><td>{share(origin.unmatched)}</td></tr>}
            <tr><th>جمع</th><th>{fullToman(total)}</th><th>{fa(data.debtor_customer_count || 0)} مشتری</th></tr>
          </tbody>
        </table></div>
        {(() => {
          // مبلغ اسمی چک‌های برگشتی با «بدهی باقی‌مانده بابت برگشتی» فرق دارد: سهم بدهی هیچ‌وقت از مانده دفتر کل مشتری بیشتر نمی‌شود.
          const nominal = Number(data.returned_cheque_nominal_rial || 0) + Number(data.returned_cheque_settled_nominal_rial || 0);
          if (!nominal) return null;
          const paidSeparately = Math.max(nominal - Number(origin.returned_cheque || 0), 0);
          return <div className="cf-returned-note">
            <p>مبلغ اسمی چک‌های برگشتی: <b>{fullToman(nominal)} تومان</b> · بدهی باقی‌مانده بابت برگشتی: <b>{fullToman(origin.returned_cheque)} تومان</b></p>
            {paidSeparately > 0 && <p>
              فرق <b>{fullToman(paidSeparately)} تومان</b> را مشتریان جدا از خود چک پرداخت کرده‌اند (حواله، نقد یا بستانکاری قبلی)، ولی وضعیت چک در کارآمد هنوز «برگشتی» است.
              {Number(data.returned_cheque_settled_customer_count || 0) > 0 && <> {fa(data.returned_cheque_settled_customer_count)} مشتری با {fullToman(data.returned_cheque_settled_nominal_rial)} تومان چک برگشتی اصلاً بدهکار نیستند.</>}
            </p>}
          </div>;
        })()}
      </div>
    </div>

    {kind === "branch" && <div>
      <h4>۳. سهم هر ویزیتور</h4>
      <p>چک برگشتی (فقط سررسید سال جاری و سال قبل) به ویزیتورِ فاکتورِ همان چک و بقیه بدهی با FIFO به ویزیتورِ فاکتورهای پرداخت‌نشده می‌رسد. چک‌های برگشتی قدیمی‌تر نمایش داده نمی‌شوند و مثل بقیه بدهی با FIFO حساب می‌شوند.</p>
      <div className="cf-table"><table>
        <thead><tr><th>ویزیتور</th><th>مبلغ (تومان)</th><th>سهم</th><th>مشتری بدهکار</th></tr></thead>
        <tbody>{(data.visitors || []).map((v: any) => <tr key={v.visitor_name}>
          <td>{v.visitor_name}</td><td><b>{fullToman(v.amount_rial)}</b></td><td>{share(v.amount_rial)}</td><td>{fa(v.customer_count)}</td>
        </tr>)}</tbody>
      </table></div>
    </div>}

    {(data.months || []).length > 0 && <div>
      <h4>۴. بدهی هر مشتری به تفکیک ماه</h4>
      <p>مثل گزارش «مانده حساب‌های هیبرید مشتریان»: پرداخت‌ها اول قدیمی‌ترین بدهکاری‌ها را تسویه می‌کنند و مانده به ماهِ جدیدترین بدهکاری‌ها می‌رسد. مبالغ به تومان.</p>
      <div className="cf-table cf-debt-customers"><table>
        <thead><tr><th>مشتری</th><th>آخرین فاکتور</th>{data.months.map((m: any) => <th key={m.month}>{m.label}</th>)}<th>جمع</th></tr></thead>
        <tbody>
          <tr className="cf-debt-total-row"><td><b>جمع {fa(customers.length)} مشتری</b></td><td>—</td>
            {data.months.map((m: any) => <td key={m.month}><b>{fullToman(customers.reduce((s: number, c: any) => s + Number(c.months?.[m.month] || 0), 0))}</b></td>)}
            <td className="cf-debt"><b>{fullToman(customers.reduce((s: number, c: any) => s + Number(c.debt_rial || 0), 0))}</b></td></tr>
          {customers.map((c: any) => <tr key={c.dl_ref}>
            <td className="cf-wrap"><b>{c.customer_name || "—"}</b><small>کد {c.customer_code || "—"}</small></td>
            <td>{c.last_invoice_date_jalali || "—"}</td>
            {data.months.map((m: any) => <td key={m.month}>{Number(c.months?.[m.month] || 0) ? fullToman(c.months[m.month]) : "—"}</td>)}
            <td className="cf-debt"><b>{fullToman(c.debt_rial)}</b></td>
          </tr>)}
        </tbody>
      </table></div>
    </div>}

    <div>
      <h4>{kind === "branch" ? "۵" : "۳"}. مشتریان بدهکار</h4>
      <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar">
        <div><b>جستجوی نام یا کد مشتری</b><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="نام یا کد..." /></div>
        <small>{fa(customers.length)} مشتری</small>
      </section>
      <div className="cf-table cf-debt-customers"><table>
        <thead><tr><th>مشتری</th><th>بدهی (تومان)</th><th>مبلغ اسمی چک‌های برگشتی</th><th>بدهی باقی‌مانده بابت برگشتی</th><th>قدیمی‌ترین فاکتور پرداخت‌نشده</th><th>آخرین پرداخت {"(سال جاری)"}</th>{kind === "branch" && <th>ویزیتور</th>}</tr></thead>
        <tbody>{customers.map((c: any) => <tr key={c.dl_ref}>
          <td className="cf-wrap"><b>{c.customer_name || "—"}</b><small>کد {c.customer_code || "—"}</small></td>
          <td className="cf-debt">{fullToman(c.debt_rial)}</td>
          <td>{c.returned_cheque_nominal_rial > 0 ? fullToman(c.returned_cheque_nominal_rial) : "—"}</td>
          <td>{c.returned_cheque_rial > 0 ? fullToman(c.returned_cheque_rial) : "—"}
            {c.returned_cheque_nominal_rial - c.returned_cheque_rial > 1 && <small className="cf-returned-gap">مشتری {fullToman(c.returned_cheque_nominal_rial - c.returned_cheque_rial)} جدا پرداخت کرده</small>}
          </td>
          <td>{c.oldest_unpaid_invoice_date_jalali || "—"}</td>
          <td>{c.last_payment_date_jalali || "—"}</td>
          {kind === "branch" && <td className="cf-wrap">{(c.visitors || []).map((v: any) => <small key={v.visitor_name}>{v.visitor_name}: {fullToman(v.amount_rial)}</small>)}</td>}
        </tr>)}</tbody>
      </table></div>
    </div>
  </div>;
}

// Uncollected cheques with a long term (due more than 90 days after receipt) and a large amount need a closer look.
// Cheques over 30 days past due are "unresolved" (not "open") but still uncollected, so both states count.
export const REVIEW_TERM_DAYS = 90;
export const REVIEW_AMOUNT_RIAL = 1_000_000_000; // 100M toman
export const needsChequeReview = (x: any) =>
  (x.return_risk?.state === "open" || x.return_risk?.state === "unresolved")
  && typeof x.receipt_to_due_days === "number" && x.receipt_to_due_days > REVIEW_TERM_DAYS
  && Number(x.amount_rial || 0) > REVIEW_AMOUNT_RIAL;

export function NetworkFile({ kind, id, onBack, onOpenVisitor, backLabel }: { kind: "branch" | "visitor"; id: number; onBack: () => void; onOpenVisitor?: (id: number) => void; backLabel: string }) {
  const [file, setFile] = useState<any>(null);
  const [error, setError] = useState("");
  const [riskFilter, setRiskFilter] = useState<"open" | "high" | "medium" | "low" | "returned" | "review">("open");
  const [showDebt, setShowDebt] = useState(false);
  useEffect(() => {
    let active = true;
    setFile(null); setError(""); setShowDebt(false);
    request(`/sales-network/${kind === "branch" ? "branches" : "visitors"}/${id}`)
      .then((d) => { if (active) setFile(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت پرونده ناموفق بود"); });
    return () => { active = false; };
  }, [kind, id]);

  const back = <button className="cheque-back" onClick={onBack}>{backLabel}</button>;
  if (error) return <>{back}<div className="profile-warning">{error}</div></>;
  if (!file) return <>{back}<div className="profile-loading">در حال دریافت پرونده {kind === "branch" ? "هیبرید" : "ویزیتور"}...</div></>;

  const cy = file.current_year_label || "سال جاری", py = file.previous_year_label || "سال قبل";
  const s = file.sales_stats || {}, d = file.debt || {}, ch = file.cheques || { rows: [], summary: {} };
  const reviewRows = (ch.rows || []).filter(needsChequeReview);
  const reviewAmount = reviewRows.reduce((sum: number, x: any) => sum + Number(x.amount_rial || 0), 0);
  const chequeRows = riskFilter === "review" ? reviewRows : (ch.rows || []).filter((x: any) => {
    const r = x.return_risk || {};
    return riskFilter === "open" ? r.state === "open" : riskFilter === "returned" ? r.state === "returned" : r.level === riskFilter;
  });
  const title = kind === "branch" ? (file.hybrids || []).join("، ") || file.branch_name : file.visitor_name;
  return <>
    {back}
    <article className="customer-profile-expanded customer-profile-page">
      <div className="profile-title">
        <div>
          <span className="fd-badge safe">{kind === "branch" ? "هیبرید من" : file.active ? "ویزیتور فعال" : "ویزیتور غیرفعال"}</span>
          <h2>{title}</h2>
          <p>{kind === "branch"
            ? `شعبه ${file.branch_name} • سرپرست: ${(file.supervisors || []).join("، ") || "—"}`
            : `شعبه ${file.branch_name || "—"} • سرپرست: ${file.supervisor || "—"} • هیبرید من: ${(file.hybrids || []).join("، ") || "—"}`}</p>
        </div>
        <span className="profile-source">کارآمد</span>
      </div>

      <section className="cf-section">
        <div className="cf-title">
          <div><h3>فروش</h3><p>{kind === "branch" ? "همه فاکتورهای فروش این شعبه" : "فاکتورهای فروشی که این ویزیتور زده است"}؛ برگشت از فروش کم شده است. ناخالص = جمع قبل تخفیف، خالص = قابل پرداخت (بعد از تخفیف، با ارزش افزوده).</p></div>
          {s.last_invoice_date_jalali && <small>آخرین فاکتور: {s.last_invoice_date_jalali}</small>}
        </div>
        <div className="cf-kpis">
          <article><small>تعداد کل فاکتور فروش</small><b>{fa(s.invoice_count || 0)}</b><span>از {s.first_invoice_date_jalali || "—"}</span></article>
          <article><small>فروش ناخالص {cy}</small><b>{fullToman(s.current_year_gross_sales_rial || 0)}</b><span>تومان · {fa(s.current_year_invoice_count || 0)} فاکتور</span></article>
          <article><small>فروش خالص {cy}</small><b>{fullToman(s.current_year_sales_rial || 0)}</b><span>تومان</span></article>
          <article><small>فروش ناخالص {py}</small><b>{fullToman(s.previous_year_gross_sales_rial || 0)}</b><span>تومان · {fa(s.previous_year_invoice_count || 0)} فاکتور</span></article>
          <article><small>فروش خالص {py}</small><b>{fullToman(s.previous_year_sales_rial || 0)}</b><span>تومان</span></article>
          <article><small>کل فروش خالص تا امروز</small><b>{fullToman(s.sales_amount_rial || 0)}</b><span>ناخالص: {fullToman(s.gross_sales_amount_rial || 0)} تومان</span></article>
        </div>
      </section>

      {kind === "branch" && <section className="cf-section">
        <div className="cf-title"><div><h3>ویزیتورها</h3><p>ویزیتورهای فعال و ویزیتورهایی که در {cy} یا {py} فروش داشته‌اند؛ برای پرونده ویزیتور کلیک کنید.</p></div></div>
        {(file.visitors || []).length ? <div className="cf-table cf-clickable"><table>
          <thead><tr><th>ویزیتور</th><th>سرپرست</th><th>فروش {cy} (خالص / ناخالص)</th><th>فروش {py} (خالص / ناخالص)</th><th>مطالبات مشتریانش</th><th>آخرین فاکتور</th></tr></thead>
          <tbody>{file.visitors.map((v: any) => <tr key={v.visitor_id} onClick={() => onOpenVisitor?.(v.visitor_id)}>
            <td><b>{v.visitor_name}</b>{!v.active && <small className="cf-muted">غیرفعال</small>}</td>
            <td>{v.supervisor || "—"}</td>
            <SalesCell net={v.current_year_sales_rial} gross={v.current_year_gross_sales_rial} count={v.current_year_invoice_count} />
            <SalesCell net={v.previous_year_sales_rial} gross={v.previous_year_gross_sales_rial} count={v.previous_year_invoice_count} />
            <td className="cf-debt">{money(v.debt?.open_account_receivable_rial || 0)}<small>{fa(v.debt?.debtor_customer_count || 0)} مشتری بدهکار</small></td>
            <td>{v.last_invoice_date_jalali || "—"}</td>
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">ویزیتوری برای این شعبه ثبت نشده است.</div>}
      </section>}

      <section className="cf-section">
        <div className="cf-title"><div><h3>۵ فاکتور آخر {cy}</h3><p>مانده و ریز وصول هر فاکتور از تسویه فاکتور در کارآمد؛ اگر یک چک چند فاکتور را تسویه کرده باشد، سهم همین فاکتور نمایش داده می‌شود.</p></div></div>
        {(file.last_invoices || []).length ? <LastInvoicesTable invoices={file.last_invoices} showVisitor={kind === "branch"} /> : <div className="invoice-source-pending">در {cy} فاکتوری ثبت نشده است.</div>}
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3>مطالبات</h3><p>{kind === "branch" ? "مانده دفتر کل مشتریانی که شعبه اصلی‌شان همین شعبه است." : "مانده دفتر کل مشتریان: چک برگشتیِ تسویه‌نشده (فقط سررسید سال جاری و سال قبل) به ویزیتورِ فاکتورِ همان چک می‌رسد و بقیه به روش FIFO — پرداخت‌ها اول قدیمی‌ترین فاکتورها را تسویه می‌کنند، پس بدهی باقی‌مانده مال جدیدترین فاکتورهاست و به ویزیتوری می‌رسد که همان فاکتورها را زده است. بستانکاری مشتری به ویزیتور آخرین فاکتورش می‌رسد."} مانده شامل اسناد قطعی و اسنادی است که حسابداری هنوز صادر نکرده (مثل گزارش «مانده حساب‌های هیبرید مشتریان»). برای جزئیات، روی «مانده بدهی مشتریان» کلیک کنید.</p></div></div>
        <div className="cf-kpis">
          <article className={`cf-accent-red cf-kpi-clickable${showDebt ? " active" : ""}`} role="button" tabIndex={0}
            onClick={() => setShowDebt((v) => !v)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setShowDebt((v) => !v); } }}>
            <small>مانده بدهی مشتریان</small><b>{money(d.open_account_receivable_rial || 0)}</b><span>{fa(d.debtor_customer_count || 0)} مشتری بدهکار از {fa(d.customer_count || 0)}</span>
            <em>{showDebt ? "بستن جزئیات ▲" : "مشاهده جزئیات ▼"}</em>
          </article>
          <article><small>بستانکاری مشتریان</small><b>{money(d.customer_credit_rial || 0)}</b><span>تومان</span></article>
          <article><small>مانده تسویه‌نشده فاکتورهای {cy}</small><b>{money(d.current_year_unpaid_invoice_rial || 0)}</b><span>{fa(d.current_year_unpaid_invoice_count || 0)} فاکتور</span></article>
          <article><small>چک باز در دست شرکت</small><b>{money(ch.summary?.open?.amount_rial || 0)}</b><span>{fa(ch.summary?.open?.count || 0)} فقره</span></article>
        </div>
        {showDebt && <DebtDetail kind={kind} id={id} />}
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3>چک‌های باز و احتمال برگشت</h3><p>احتمال برگشت هر چک از سابقه چک‌های همان مشتری (وصول و برگشت) به‌علاوه مبلغ، مدت و سررسید چک محاسبه شده است؛ برای دلایل، نشانگر را روی درصد نگه دارید.</p></div></div>
        <section className="customer-cheque-scope-cards">
          {([["open", "همه چک‌های باز"], ["high", "احتمال برگشت بالا"], ["medium", "احتمال برگشت متوسط"], ["low", "احتمال برگشت کم"], ["returned", "برگشتی"]] as const).map(([k, l]) => <button key={k} className={riskFilter === k ? "active" : ""} onClick={() => setRiskFilter(k)}>
            <small>{l}</small><b>{fa(ch.summary?.[k]?.count || 0)} فقره</b><span>{money(ch.summary?.[k]?.amount_rial || 0)} تومان</span>
          </button>)}
          <button className={`cf-review-card${riskFilter === "review" ? " active" : ""}`} onClick={() => setRiskFilter("review")}>
            <small>نیازمند بررسی بیشتر</small><b>{fa(reviewRows.length)} فقره</b><span>{money(reviewAmount)} تومان</span>
          </button>
        </section>
        {reviewRows.length > 0 && <div className="cf-review-alert">
          ⚠ {fa(reviewRows.length)} فقره چک به مبلغ {money(reviewAmount)} تومان سررسیدشان بیش از {fa(REVIEW_TERM_DAYS)} روز بعد از تاریخ دریافت است و مبلغشان بالای {money(REVIEW_AMOUNT_RIAL)} تومان است؛ نیازمند بررسی بیشتر هستند.
        </div>}
        {chequeRows.length ? <div className="cf-table"><table>
          <thead><tr><th>شماره چک</th><th>مشتری</th><th>صیاد</th><th>مبلغ</th><th>ثبت در سیستم</th><th>سررسید</th><th>زمان سررسید</th><th>وضعیت</th><th>احتمال برگشت</th><th>بانک</th>{kind === "branch" && <th>ویزیتور</th>}</tr></thead>
          <tbody>{chequeRows.map((x: any) => <tr key={x.cheque_id} className={needsChequeReview(x) ? "cf-review-row" : undefined}>
            <td><b>{chequeNo(x.cheque_number)}</b>{x.series && x.series !== x.cheque_number && <small>سری {chequeNo(x.series)}</small>}</td>
            <td><b>{x.customer_name || "—"}</b>{x.customer_code && <small>کد {x.customer_code}</small>}</td>
            <td>{chequeNo(x.sayad_number)}</td>
            <td><b>{money(x.amount_rial || 0)}</b><small>تومان</small>{needsChequeReview(x) && <span className="cf-review-badge">⚠ نیازمند بررسی بیشتر</span>}</td>
            <td><RegCell x={x} fallback={x.registration_date_jalali} /></td>
            <td>{x.due_date_jalali || "—"}</td>
            <td>{typeof x.days_until_due !== "number" ? "—" : x.days_until_due < 0 ? `${fa(-x.days_until_due)} روز گذشته` : x.days_until_due === 0 ? "امروز" : `${fa(x.days_until_due)} روز مانده`}</td>
            <td>{x.cheque_status || "—"}</td>
            <td><ChequeReturnRisk risk={x.return_risk} /></td>
            <td>{x.bank || "—"}</td>
            {kind === "branch" && <td>{x.visitor_name || "—"}</td>}
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">چکی در این دسته وجود ندارد.</div>}
      </section>
    </article>
  </>;
}
