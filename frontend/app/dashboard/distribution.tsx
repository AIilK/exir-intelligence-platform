// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (distribution).
import { useEffect, useMemo, useRef, useState } from "react";
import SortTable from "../sort-table";
import { flashChatTarget, useChatLink } from "../chatbot/chat-link";
import { API, boldToman, fa, fullToman, monthLabel, recentJalaliMonths, request, sumOf } from "./shared";
import type { YearMonth } from "./shared";

export function MonthlyDistributionReport({ ym, branch, onBranch }: { ym: YearMonth; branch: string; onBranch: (name: string) => void }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    request(`/distribution/monthly?year=${ym.year}&month=${ym.month}`)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت گزارش ناموفق بود"); });
    return () => { active = false; };
  }, [ym.year, ym.month]);
  const t = data?.totals || {};
  const b = (data?.branches || []).find((x: any) => x.branch_name === branch);
  const customers = (data?.customers || []).filter((c: any) => c.branch_name === branch);
  const undistributed = (data?.undistributed || []).filter((x: any) => x.branch_name === branch);
  return <section className="cf-section dist-primary">
    <div className="cf-title">
      <div><h3><span className="dist-step">۱</span> توزیع و وصول فاکتورهای {data?.month_label ? faDigits(data.month_label) : monthLabel(ym)}{branch ? ` — ${branch}` : " — همه هیبریدها"}</h3>
        <p>کل فروش = همان عدد داشبورد فروش (با ارزش افزوده){data?.sales_source === "karamad" ? " — داشبورد فروش در دسترس نبود؛ فروش از کارآمد محاسبه شده" : ""}؛ توزیع‌شده = کل فروش منهای توزیع‌نشده؛ توزیع‌نشده = فاکتور بدون «خروجی» (خروجی کمتر از ۱)؛ وصول = نقد + حواله + چکِ تسویه‌شده روی فاکتورهای ماه؛ مانده = کمترینِ «مانده حساب مشتری» و «توزیع‌شده منهای وصول». مبالغ به تومان. {branch ? "" : "روی هر هیبرید کلیک کنید تا کل صفحه مخصوص همان هیبرید شود."}</p></div>
    </div>
    {error ? <div className="profile-warning">{error}</div> : !data ? <div className="profile-loading">در حال ساخت گزارش ماه از کارآمد...</div> : !branch ? <>
      <div className="cf-kpis">
        <article><small>کل فروش ماه</small><b>{fullToman(t.sales_rial)}</b><span>تومان</span></article>
        <article className="cf-accent-red"><small>توزیع نشده (برگشتی‌ها کم شده)</small><b>{fullToman(t.undistributed_rial)}</b><span>{fa(t.undistributed_count || 0)} فاکتور · با برگشتی: {fullToman(t.undistributed_gross_rial)} تومان ({fa(t.undistributed_gross_count || 0)} فاکتور)</span></article>
        <article><small>توزیع شده</small><b>{fullToman(t.distributed_rial)}</b><span>تومان</span></article>
        <article><small>وصولی ماه</small><b>{fullToman(t.collected_rial)}</b><span>تومان</span></article>
        <article className="cf-accent-red"><small>مانده ماه</small><b>{fullToman(t.remaining_rial)}</b><span>تومان</span></article>
      </div>
      <SortTable rows={data.branches || []} rowKey={(r: any) => r.branch_name} onRowClick={(r: any) => onBranch(r.branch_name)}
        initialSort="sales" placeholder="جستجوی هیبرید..."
        columns={[
          { key: "branch", label: "هیبرید", value: (r: any) => r.branch_name, render: (r: any) => <b>{r.branch_name}</b> },
          { key: "sales", label: "کل فروش", value: (r: any) => Number(r.sales_rial || 0), render: (r: any) => fullToman(r.sales_rial) },
          { key: "undist", label: "توزیع نشده", value: (r: any) => Number(r.undistributed_rial || 0), className: (r: any) => r.undistributed_rial > 0 ? "cf-debt" : undefined,
            render: (r: any) => <>{fullToman(r.undistributed_rial)}<small>{fa(r.undistributed_count)} فاکتور</small></> },
          { key: "dist", label: "توزیع شده", value: (r: any) => Number(r.distributed_rial || 0), render: (r: any) => fullToman(r.distributed_rial) },
          { key: "coll", label: "وصولی ماه", value: (r: any) => Number(r.collected_rial || 0), render: (r: any) => fullToman(r.collected_rial) },
          { key: "rem", label: "مانده ماه", value: (r: any) => Number(r.remaining_rial || 0), className: () => "cf-debt", render: (r: any) => boldToman(r.remaining_rial) },
        ]}
        totalRow={(rows: any[]) => <tr className="cf-debt-total-row"><td><b>جمع{rows.length !== (data.branches || []).length ? " (فیلترشده)" : " کل"}</b></td>
          <td>{boldToman(sumOf(rows, "sales_rial"))}</td><td>{boldToman(sumOf(rows, "undistributed_rial"))}</td><td>{boldToman(sumOf(rows, "distributed_rial"))}</td>
          <td>{boldToman(sumOf(rows, "collected_rial"))}</td><td className="cf-debt">{boldToman(sumOf(rows, "remaining_rial"))}</td></tr>} />
    </> : <>
      <div className="cf-kpis">
        <article><small>کل فروش {branch}</small><b>{fullToman(b?.sales_rial)}</b><span>تومان</span></article>
        <article className="cf-accent-red"><small>توزیع نشده (برگشتی‌ها کم شده)</small><b>{fullToman(b?.undistributed_rial)}</b><span>{fa(b?.undistributed_count || 0)} فاکتور · با برگشتی: {fullToman(b?.undistributed_gross_rial)} تومان ({fa(b?.undistributed_gross_count || 0)} فاکتور)</span></article>
        <article><small>توزیع شده</small><b>{fullToman(b?.distributed_rial)}</b><span>تومان</span></article>
        <article><small>وصولی ماه</small><b>{fullToman(b?.collected_rial)}</b><span>تومان</span></article>
        <article className="cf-accent-red"><small>مانده ماه</small><b>{fullToman(b?.remaining_rial)}</b><span>تومان</span></article>
      </div>
      <h4>مشتریان {branch} در این ماه</h4>
      <SortTable rows={customers} rowKey={(r: any) => r.dl_ref} initialSort="rem" placeholder="نام یا کد مشتری..."
        columns={[
          { key: "dl", label: "کد تفضیلی", value: (r: any) => r.dl_code },
          { key: "code", label: "کد مشتری", value: (r: any) => r.customer_code },
          { key: "name", label: "نام مشتری", value: (r: any) => r.customer_name, render: (r: any) => <b>{r.customer_name || "—"}</b>, className: () => "cf-wrap" },
          { key: "bal", label: "مانده سیستم", value: (r: any) => Number(r.system_balance_rial || 0), render: (r: any) => fullToman(r.system_balance_rial) },
          { key: "dist", label: "توزیع شده", value: (r: any) => Number(r.distributed_rial || 0), render: (r: any) => fullToman(r.distributed_rial) },
          { key: "undist", label: "توزیع نشده", value: (r: any) => Number(r.undistributed_rial || 0), className: (r: any) => r.undistributed_rial > 0 ? "cf-debt" : undefined, render: (r: any) => fullToman(r.undistributed_rial) },
          { key: "coll", label: "وصول", value: (r: any) => Number(r.collected_rial || 0), render: (r: any) => fullToman(r.collected_rial) },
          { key: "rem", label: "مانده فاکتورهای ماه", value: (r: any) => Number(r.remaining_rial || 0), className: () => "cf-debt", render: (r: any) => boldToman(r.remaining_rial) },
        ]}
        totalRow={(rows: any[]) => <tr className="cf-debt-total-row"><td colSpan={3}><b>جمع</b></td>
          <td>{boldToman(sumOf(rows, "system_balance_rial"))}</td><td>{boldToman(sumOf(rows, "distributed_rial"))}</td><td>{boldToman(sumOf(rows, "undistributed_rial"))}</td>
          <td>{boldToman(sumOf(rows, "collected_rial"))}</td><td className="cf-debt">{boldToman(sumOf(rows, "remaining_rial"))}</td></tr>} />
      {undistributed.length > 0 && <>
        <h4>فاکتورهای توزیع‌نشده این ماه — {branch}</h4>
        <SortTable rows={undistributed} rowKey={(r: any) => r.invoice_id} initialSort="wait" placeholder="شماره فاکتور، مشتری یا ویزیتور..."
          columns={[
            { key: "num", label: "شماره فاکتور", value: (r: any) => r.number, render: (r: any) => <b>{r.number}</b> },
            { key: "date", label: "تاریخ", value: (r: any) => r.date_jalali },
            { key: "wait", label: "انتظار", value: (r: any) => Number(r.days_waiting || 0), render: (r: any) => `${fa(r.days_waiting || 0)} روز` },
            { key: "cust", label: "مشتری", value: (r: any) => `${r.customer_name || ""} ${r.customer_code || ""}`, className: () => "cf-wrap",
              render: (r: any) => <><b>{r.customer_name || "—"}</b><small>کد {r.customer_code || "—"}</small></> },
            { key: "vis", label: "ویزیتور", value: (r: any) => r.visitor_name },
            { key: "inv", label: "قابل پرداخت", value: (r: any) => Number(r.invoice_rial ?? r.amount_rial ?? 0), render: (r: any) => fullToman(r.invoice_rial ?? r.amount_rial) },
            { key: "ret", label: "برگشتی", value: (r: any) => Number(r.returned_rial || 0), render: (r: any) => r.returned_rial ? fullToman(r.returned_rial) : "—" },
            { key: "amt", label: "توزیع نشده", value: (r: any) => Number(r.amount_rial || 0), render: (r: any) => boldToman(r.amount_rial) },
          ]} />
      </>}
    </>}
    {data && <CollectionControl rows={(data.collection_control || []).filter((r: any) => !branch || r.branch_name === branch)} showBranch={!branch} />}
  </section>;
}

// «کنترل وصول فاکتورها» — هر فاکتور ماه با اجزای مبلغ و تسویه؛ همان ستون‌های گزارش روزانه واحد مالی.
export function CollectionControl({ rows, showBranch }: { rows: any[]; showBranch: boolean }) {
  const [open, setOpen] = useState(false);
  const [onlyOpen, setOnlyOpen] = useState(false);
  const view = onlyOpen ? rows.filter((r) => Number(r.unpaid_rial || 0) > 0) : rows;
  const money = (key: string, label: string, bold = false) => ({
    key, label, value: (r: any) => Number(r[key] || 0),
    render: (r: any) => (Number(r[key] || 0) ? (bold ? boldToman(r[key]) : fullToman(r[key])) : "—"),
  });
  const moneyCols = ["gross_rial", "volume_discount_rial", "cash_discount_rial", "vat_rial", "payable_rial", "cash_rial", "draft_rial",
    "cheque_rial", "collected_rial", "returned_rial", "shared_rial", "barter_rial", "unpaid_rial"];
  return <div className="cc-block">
    <button type="button" className={`dist-toggle${open ? " open" : ""}`} onClick={() => setOpen(!open)}>
      {open ? "بستن کنترل وصول ▲" : `کنترل وصول فاکتورها (${fa(rows.length)} فاکتور) ▼`}
    </button>
    {open && <>
      <p className="cc-note">هر فاکتور ماه با مبلغ ناخالص، تخفیف‌ها، ارزش افزوده، پرداختی (نقد/حواله/چک)، برگشت، تسهیم و مانده — مثل برگه «کنترل وصول» گزارش واحد مالی. مبالغ به تومان.</p>
      <SortTable rows={view} rowKey={(r: any) => r.invoice_id} initialSort="unpaid_rial" placeholder="شماره فاکتور، مشتری، فروشنده، لاین، شهر یا عامل توزیع..."
        toolbar={<label className="distribution-check"><input type="checkbox" checked={onlyOpen} onChange={(e) => setOnlyOpen(e.target.checked)} /> فقط مانده‌دار</label>}
        columns={[
          ...(showBranch ? [{ key: "branch", label: "شعبه", value: (r: any) => r.branch_name }] : []),
          { key: "line", label: "لاین", value: (r: any) => r.line_name },
          { key: "num", label: "شماره فاکتور", value: (r: any) => Number(r.number) || r.number, render: (r: any) => <b>{r.number}</b> },
          { key: "exit", label: "خروجی", value: (r: any) => r.exit_code || "" },
          { key: "date", label: "تاریخ فاکتور", value: (r: any) => r.date_jalali },
          { key: "ddate", label: "تاریخ توزیع", value: (r: any) => r.distribution_date_jalali || "" },
          { key: "days", label: "روز از توزیع", value: (r: any) => r.days_since_distribution ?? -1, render: (r: any) => r.days_since_distribution == null ? "—" : fa(r.days_since_distribution) },
          { key: "pay", label: "نحوه پرداخت", value: (r: any) => r.payment_name },
          { key: "ccode", label: "کد مشتری", value: (r: any) => r.customer_code },
          { key: "cname", label: "نام مشتری", value: (r: any) => r.customer_name, className: () => "cf-wrap" },
          { key: "vis", label: "فروشنده", value: (r: any) => r.visitor_name, className: () => "cf-wrap" },
          { key: "city", label: "شهر", value: (r: any) => r.city_name },
          { key: "deliver", label: "عامل توزیع", value: (r: any) => r.deliver_name },
          money("gross_rial", "مبلغ ناخالص"), money("volume_discount_rial", "تخفیف حجمی"), money("cash_discount_rial", "تخفیف نقدی"),
          money("vat_rial", "ارزش افزوده"), money("payable_rial", "قابل پرداخت", true), money("cash_rial", "نقد"), money("draft_rial", "حواله"),
          money("cheque_rial", "چک"), money("collected_rial", "پرداختی", true), money("returned_rial", "برگشت از فروش"), money("shared_rial", "تسهیم"),
          money("barter_rial", "تهاتر"), money("unpaid_rial", "مانده", true),
        ]}
        totalRow={(vis: any[]) => <tr className="cf-debt-total-row">
          <td colSpan={showBranch ? 13 : 12}><b>جمع {fa(vis.length)} فاکتور</b></td>
          {moneyCols.map((k) => <td key={k}>{boldToman(sumOf(vis, k))}</td>)}
        </tr>} />
    </>}
  </div>;
}

// زمان‌بندی توزیع هر فاکتور: تاریخ فاکتور ← ثبت فاکتور ← ثبت حواله خروج ← خروج بار.
export const TIMELINE_STAGES = [
  ["all", "همه فاکتورها"],
  ["waiting", "در انتظار حواله خروج"],
  ["dispatched", "حواله و خروج ثبت شده"],
  ["scheduled", "خروج برای روزهای آینده"],
] as const;
export type TimelineStage = (typeof TIMELINE_STAGES)[number][0];
export const TIMELINE_PAGE = 60;

export function hoursLabel(hours?: number | null): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return "کمتر از ۱ ساعت";
  if (hours < 24) return `${fa(Math.round(hours))} ساعت`;
  const d = Math.floor(hours / 24), h = Math.round(hours % 24);
  return h ? `${fa(d)} روز و ${fa(h)} ساعت` : `${fa(d)} روز`;
}

export const faDigits = (value: string) => value.replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
export const stampLabel = (stamp: any) => stamp ? `${stamp.date_jalali} • ساعت ${faDigits(stamp.time)}` : "";

export function TimelineStep({ label, stamp, date, sub, state }: {
  label: string; stamp?: any; date?: string | null; sub?: string; state: "done" | "pending" | "late";
}) {
  return <div className={`dt-step ${state}`}>
    <i />
    <small>{label}</small>
    <b>{stamp?.date_jalali || date || "—"}</b>
    {stamp?.time && <span>ساعت {faDigits(stamp.time)}</span>}
    {sub && <em>{sub}</em>}
  </div>;
}

export function TimelineGap({ text, warn }: { text: string; warn?: boolean }) {
  return <div className={`dt-gap${warn ? " warn" : ""}`}><span>{text}</span></div>;
}

// شاخص‌های زمان‌بندی یک گروه فاکتور (کل یا یک هیبرید).
export function timingStats(items: any[]) {
  const exited = items.filter((x) => x.hours_to_exit_registration !== null && x.hours_to_exit_registration !== undefined);
  const hours = exited.map((x) => x.hours_to_exit_registration).sort((a, b) => a - b);
  const sameDay = exited.filter((x) => x.invoice_created?.date_jalali === x.exit_registered?.date_jalali).length;
  const leads = items.filter((x) => typeof x.days_invoice_to_exit === "number");
  const waiting = items.filter((x) => x.stage === "waiting");
  return {
    count: items.length,
    amount: sumOf(items, "amount_rial"),
    exited: exited.length,
    median: hours.length ? hours[Math.floor(hours.length / 2)] : null,
    sameDay,
    sameDayPercent: exited.length ? Math.round(100 * sameDay / exited.length) : null,
    avgLead: leads.length ? leads.reduce((s, x) => s + x.days_invoice_to_exit, 0) / leads.length : null,
    lateRegistered: items.filter((x) => (x.registration_delay_days || 0) > 0).length,
    waiting: waiting.length,
    waitingAmount: sumOf(waiting, "amount_rial"),
    maxWaiting: waiting.reduce((m, x) => Math.max(m, Number(x.days_waiting || 0)), 0),
  };
}

// آخرین بخش صفحه؛ فقط وقتی کاربر بخواهد باز می‌شود. بازه: یک ماه شمسی یا چند روز اخیر.
export function InvoiceDistributionTimeline({ branch, staleDays, onBranch, ym }: { branch: string; staleDays: number; onBranch: (name: string) => void; ym: YearMonth }) {
  const [mode, setMode] = useState<"month" | "days">("month");
  const [days, setDays] = useState(14);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [stage, setStage] = useState<TimelineStage>("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"created" | "slowest">("created");
  const [limit, setLimit] = useState(TIMELINE_PAGE);
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    const path = mode === "month" ? `/distribution/timeline?year=${ym.year}&month=${ym.month}` : `/distribution/timeline?days=${days}`;
    request(path)
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت زمان‌بندی توزیع ناموفق بود"); });
    return () => { active = false; };
  }, [mode, days, ym.year, ym.month]);
  useEffect(() => { setLimit(TIMELINE_PAGE); setOpen(null); }, [branch, stage, search, sort, days, mode, ym.year, ym.month]);

  const everything: any[] = data?.invoices || [];
  const all: any[] = everything.filter((x: any) => !branch || x.branch_name === branch);
  const byStage = (k: TimelineStage) => k === "all" ? all : all.filter((x) => x.stage === k);
  const stats = timingStats(all);
  const perBranch = useMemo(() => {
    const names = Array.from(new Set(everything.map((x: any) => x.branch_name || "—"))) as string[];
    return names.map((name) => ({ name, ...timingStats(everything.filter((x: any) => (x.branch_name || "—") === name)) }));
  }, [everything]);
  const waitingAge = (x: any) => x.stage === "waiting" ? Number(x.days_waiting || 0) * 24 : Number(x.hours_to_exit_registration ?? 0);

  const q = search.trim().toLocaleLowerCase("fa-IR");
  const visible = byStage(stage)
    .filter((x) => !q || [x.number, x.customer_name, x.customer_code, x.visitor_name, x.deliver_name, x.driver_name, x.exit_code]
      .filter(Boolean).some((v) => String(v).toLocaleLowerCase("fa-IR").includes(q)))
    .sort((a, b) => sort === "slowest" ? waitingAge(b) - waitingAge(a) : String(b.invoice_created?.iso || "").localeCompare(String(a.invoice_created?.iso || "")));
  const period = mode === "month" ? monthLabel(ym) : `${fa(days)} روز اخیر`;

  return <section className="cf-section dt-section">
    <div className="cf-title">
      <div><h3>زمان‌بندی توزیع هر فاکتور — {period}{branch ? ` — ${branch}` : ""}</h3>
        <p>برای هر فاکتور: تاریخ فاکتور، ساعت ثبت در کارآمد، ساعت ثبت حواله خروج و تاریخ خروج بار. اول خلاصه هر هیبرید، بعد ریز فاکتورها؛ روی هر فاکتور کلیک کنید تا جزئیات حواله، موزع و راننده را ببینید.</p></div>
      <div className="distribution-controls">
        <label>بازه: <select value={mode === "month" ? "month" : String(days)} onChange={(e) => { if (e.target.value === "month") setMode("month"); else { setMode("days"); setDays(Number(e.target.value)); } }}>
          <option value="month">ماه انتخاب‌شده ({monthLabel(ym)})</option>
          {[7, 14, 30, 60].map((d) => <option key={d} value={d}>{fa(d)} روز اخیر</option>)}
        </select></label>
        <label>مرتب‌سازی فاکتورها: <select value={sort} onChange={(e) => setSort(e.target.value as "created" | "slowest")}>
          <option value="created">جدیدترین ثبت</option><option value="slowest">کندترین توزیع</option>
        </select></label>
      </div>
    </div>
    {error ? <div className="profile-warning">{error}</div> : !data ? <div className="profile-loading">در حال ساخت خط زمان فاکتورها از کارآمد...</div> : <>
      {!branch && <>
        <h4>زمان‌بندی هر هیبرید — {period}</h4>
        <SortTable rows={perBranch} rowKey={(r) => r.name} onRowClick={(r) => onBranch(r.name)} initialSort="amount" placeholder="جستجوی هیبرید..."
          columns={[
            { key: "name", label: "هیبرید", value: (r) => r.name, render: (r) => <b>{r.name}</b> },
            { key: "count", label: "فاکتور", value: (r) => r.count, render: (r) => fa(r.count) },
            { key: "amount", label: "مبلغ (تومان)", value: (r) => r.amount, render: (r) => fullToman(r.amount) },
            { key: "waiting", label: "در انتظار حواله", value: (r) => r.waitingAmount, className: (r) => r.waiting ? "cf-debt" : undefined,
              render: (r) => r.waiting ? <>{fullToman(r.waitingAmount)}<small>{fa(r.waiting)} فاکتور • تا {fa(r.maxWaiting)} روز</small></> : "—" },
            { key: "median", label: "میانه ثبت فاکتور تا حواله", value: (r) => r.median ?? -1, render: (r) => hoursLabel(r.median) },
            { key: "same", label: "حواله همان روز", value: (r) => r.sameDayPercent ?? -1, render: (r) => r.sameDayPercent == null ? "—" : `${fa(r.sameDayPercent)}٪` },
            { key: "lead", label: "میانگین فاکتور تا خروج", value: (r) => r.avgLead ?? -1, className: (r) => (r.avgLead || 0) > 7 ? "cf-debt" : undefined,
              render: (r) => r.avgLead == null ? "—" : `${fa(Math.round(r.avgLead * 10) / 10)} روز` },
            { key: "late", label: "ثبت دیرتر از تاریخ فاکتور", value: (r) => r.lateRegistered, render: (r) => fa(r.lateRegistered) },
          ]} />
      </>}
      <h4>ریز فاکتورها{branch ? ` — ${branch}` : ""}</h4>
      <div className="dt-stage-cards">
        {TIMELINE_STAGES.map(([k, l]) => <button key={k} className={`${stage === k ? "active" : ""} dt-stage-${k}`} onClick={() => setStage(k)}>
          <small>{l}</small><b>{fa(byStage(k).length)} فاکتور</b><span>{fullToman(sumOf(byStage(k), "amount_rial"))} تومان</span>
        </button>)}
      </div>
      <div className="cf-kpis">
        <article><small>میانه ثبت فاکتور تا ثبت حواله</small><b>{hoursLabel(stats.median)}</b><span>{fa(stats.exited)} فاکتور حواله‌شده</span></article>
        <article><small>حواله در همان روز ثبت فاکتور</small><b>{fa(stats.sameDayPercent || 0)}٪</b><span>{fa(stats.sameDay)} فاکتور</span></article>
        <article><small>میانگین تاریخ فاکتور تا خروج بار</small><b>{fa(Math.round((stats.avgLead || 0) * 10) / 10)} روز</b><span>بر اساس تاریخ حواله خروج</span></article>
        <article className={stats.lateRegistered ? "cf-accent-red" : undefined}><small>فاکتورهایی که دیرتر از تاریخشان ثبت شده‌اند</small><b>{fa(stats.lateRegistered)} فاکتور</b><span>ساعت ثبت بعد از روز تاریخ فاکتور</span></article>
      </div>
      <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar collection-alert-filters">
        <div><b>جستجو</b><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره فاکتور، مشتری، ویزیتور، موزع یا کد حواله..." /></div>
        <small>{fa(visible.length)} فاکتور • {fullToman(sumOf(visible, "amount_rial"))} تومان • {data.from_date_jalali} تا {data.to_date_jalali}</small>
      </section>
      {visible.length ? <div className="dt-list">
        {visible.slice(0, limit).map((x) => {
          const waiting = x.stage === "waiting";
          const stale = waiting && Number(x.days_waiting || 0) > staleDays;
          const late = (x.registration_delay_days || 0) > 0;
          const expanded = open === x.invoice_id;
          return <article key={x.invoice_id} className={`dt-row${stale ? " stale" : ""}${expanded ? " open" : ""}`}
            role="button" tabIndex={0} onClick={() => setOpen(expanded ? null : x.invoice_id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(expanded ? null : x.invoice_id); } }}>
            <header>
              <div className="dt-invoice">
                <b>فاکتور {x.number || "—"}</b>
                <span className={`dt-badge ${x.stage}`}>{waiting ? `در انتظار حواله • ${fa(x.days_waiting || 0)} روز` : x.stage === "scheduled" ? "خروج در روزهای آینده" : "خارج شده"}</span>
              </div>
              <div className="dt-customer"><b>{x.customer_name || "—"}</b><small>کد {x.customer_code || "—"} • ویزیتور: {x.visitor_name || "—"}{branch ? "" : ` • ${x.branch_name || "—"}`}</small></div>
              <div className="dt-amount"><b>{fullToman(x.amount_rial)}</b><small>تومان</small></div>
            </header>
            <div className="dt-track">
              <TimelineStep label="تاریخ فاکتور" date={x.invoice_date_jalali} state="done" />
              <TimelineGap text={late ? `${fa(x.registration_delay_days)} روز بعد` : "همان روز"} warn={late} />
              <TimelineStep label="ثبت فاکتور در سیستم" stamp={x.invoice_created} sub={x.invoice_user || undefined} state={late ? "late" : "done"} />
              <TimelineGap text={waiting ? `${fa(x.days_waiting || 0)} روز در انتظار` : hoursLabel(x.hours_to_exit_registration)} warn={stale || (x.hours_to_exit_registration || 0) > staleDays * 24} />
              <TimelineStep label="ثبت حواله خروج" stamp={x.exit_registered} date={waiting ? "ثبت نشده" : undefined}
                sub={waiting ? undefined : `حواله ${x.exit_code || "—"}${x.exit_save_count > 1 ? ` • ${fa(x.exit_save_count - 1)} بار ویرایش` : ""}`}
                state={waiting ? (stale ? "late" : "pending") : "done"} />
              <TimelineGap text={waiting ? "" : x.exit_date_jalali && x.exit_registered?.date_jalali && x.exit_date_jalali !== x.exit_registered.date_jalali ? "تاریخ خروج متفاوت" : "همان روز"} />
              <TimelineStep label="خروج بار / توزیع" date={waiting ? "—" : x.exit_date_jalali}
                sub={waiting ? undefined : [x.deliver_name, x.driver_name && x.driver_name !== x.deliver_name ? `راننده: ${x.driver_name}` : ""].filter(Boolean).join(" • ") || undefined}
                state={waiting ? "pending" : x.stage === "scheduled" ? "pending" : "done"} />
            </div>
            {expanded && <dl className="dt-detail" onClick={(e) => e.stopPropagation()}>
              <div><dt>ثبت‌کننده فاکتور</dt><dd>{x.invoice_user || "—"}</dd></div>
              <div><dt>ساعت ثبت فاکتور</dt><dd>{stampLabel(x.invoice_created) || "—"}</dd></div>
              {!waiting && <>
                <div><dt>کد حواله خروج</dt><dd>{x.exit_code || "—"} <small>({fa(x.exit_invoice_count)} فاکتور در این حواله)</small></dd></div>
                <div><dt>ثبت‌کننده حواله</dt><dd>{x.exit_user || "—"}</dd></div>
                <div><dt>اولین ثبت حواله</dt><dd>{stampLabel(x.exit_registered) || "در لاگ کارآمد پیدا نشد"}</dd></div>
                <div><dt>آخرین ویرایش حواله</dt><dd>{stampLabel(x.exit_last_edit) || "ویرایش نشده"}</dd></div>
                <div><dt>تاریخ حواله خروج</dt><dd>{x.exit_date_jalali || "—"}</dd></div>
                <div><dt>تاریخ توزیع</dt><dd>{x.distribution_date_jalali || "—"}</dd></div>
                <div><dt>موزع</dt><dd>{x.deliver_name || "—"}{x.deliver2_name && x.deliver2_name !== x.deliver_name ? ` • موزع دوم: ${x.deliver2_name}` : ""}</dd></div>
                <div><dt>راننده</dt><dd>{x.driver_name || "—"}</dd></div>
                <div><dt>ثبت فاکتور تا ثبت حواله</dt><dd>{hoursLabel(x.hours_to_exit_registration)}</dd></div>
              </>}
              {waiting && <div><dt>وضعیت</dt><dd className={stale ? "cf-debt" : undefined}>{fa(x.days_waiting || 0)} روز از تاریخ فاکتور گذشته و هنوز حواله خروج ندارد</dd></div>}
            </dl>}
          </article>;
        })}
        {visible.length > limit && <button className="rc-secondary dt-more" onClick={() => setLimit((n) => n + TIMELINE_PAGE)}>
          نمایش {fa(Math.min(TIMELINE_PAGE, visible.length - limit))} فاکتور دیگر (از {fa(visible.length - limit)} باقی‌مانده)
        </button>}
      </div> : <div className="invoice-source-pending">فاکتوری با این فیلترها نیست.</div>}
      <p className="dt-notes">{(data.notes || []).join(" ")}</p>
    </>}
  </section>;
}

// توزیع بار (Karamad) — از کل به جزء:
// ۱. توزیع و وصول فاکتورهای ماه ← ۲. خلاصه توزیع‌نشده ← ۳. به تفکیک هیبرید/ویزیتور ← ۴. سن و سرعت خروج
// ← ۵. ریز فاکتورهای توزیع‌نشده ← ۶. حواله‌های وضعیت ۰ ← ۷. موزعان ← ۸. زمان‌بندی (فقط با درخواست کاربر).
// انتخاب هیبرید کل صفحه را مخصوص همان هیبرید می‌کند؛ هر جدول جستجو و مرتب‌سازی خودش را دارد.
export function DistributionPage() {
  const months = useMemo(() => recentJalaliMonths(), []);
  const [ym, setYm] = useState<YearMonth>(() => months[1] || months[0]);
  // لینک چت‌بات: ماه و هیبرید (search = نام هیبرید/شعبه)
  const distChatLink = useChatLink("distribution");
  const distRef = useRef<HTMLDivElement>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [staleDays, setStaleDays] = useState(14);
  const [selected, setSelected] = useState("");
  const [onlyStale, setOnlyStale] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  useEffect(() => {
    const l = distChatLink;
    if (!l) return;
    if (l.year && l.month) setYm({ year: l.year, month: l.month });
    setSelected(l.search || "");
    flashChatTarget(distRef.current, 600);
  }, [distChatLink]);
  useEffect(() => {
    let active = true;
    request("/distribution")
      .then((d) => { if (active) setData(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت اطلاعات توزیع ناموفق بود"); });
    return () => { active = false; };
  }, []);
  const pick = (name: string) => {
    setSelected(name); setOnlyStale(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const inScope = (x: any) => !selected || x.branch_name === selected;
  const allRows: any[] = data?.undistributed || [];
  const rows = allRows.filter(inScope);
  const lead: any[] = (data?.lead_time || []).filter(inScope);
  const distributors: any[] = (data?.distributors || []).filter(inScope);
  const days = (x: any) => Number(x.days_waiting ?? 0);
  const stale = rows.filter((x) => days(x) > staleDays);
  const aging = [
    { label: "تا ۳ روز (عادی)", items: rows.filter((x) => days(x) <= 3) },
    { label: `۴ تا ${fa(staleDays)} روز`, items: rows.filter((x) => days(x) > 3 && days(x) <= staleDays) },
    { label: `بیش از ${fa(staleDays)} روز (مشکوک)`, items: stale },
  ];
  const leadByBranch = new Map<string, any>((data?.lead_time || []).map((l: any) => [l.branch_name, l]));
  const branchNames = Array.from(new Set([...allRows.map((x) => x.branch_name)].filter(Boolean))) as string[];
  const byBranch = branchNames.map((name) => {
    const items = allRows.filter((x) => x.branch_name === name), old = items.filter((x) => days(x) > staleDays);
    return { name, items, old, amount: sumOf(items, "amount_rial"), oldAmount: sumOf(old, "amount_rial"),
      oldest: items.reduce((m, x) => Math.max(m, days(x)), 0), lead: leadByBranch.get(name) };
  });
  const byVisitor = Array.from(new Set(rows.map((x) => x.visitor_name || "بدون ویزیتور"))).map((name) => {
    const items = rows.filter((x) => (x.visitor_name || "بدون ویزیتور") === name), old = items.filter((x) => days(x) > staleDays);
    return { name, items, old, amount: sumOf(items, "amount_rial"), oldAmount: sumOf(old, "amount_rial"), oldest: items.reduce((m, x) => Math.max(m, days(x)), 0) };
  });
  const invoiceRows = rows.filter((x) => !onlyStale || days(x) > staleDays);
  const leadInvoices = lead.reduce((s, l) => s + l.invoice_count, 0);
  const averageLead = leadInvoices ? lead.reduce((s, l) => s + l.average_days * l.invoice_count, 0) / leadInvoices : 0;
  const scopeLabel = selected || "همه هیبریدها";
  const excelUrl = `${API()}/distribution.xlsx?year=${ym.year}&month=${ym.month}&days=30`;

  return <div className="dist-page" ref={distRef}>
    <section className="cf-section dist-header">
      <div>
        <h2>توزیع بار{selected ? ` — ${selected}` : ""}</h2>
        <p>از کل به جزء: اول توزیع و وصول ماه، بعد توزیع‌نشده‌ها، حواله‌ها، موزعان و در آخر زمان‌بندی هر فاکتور. هر جدول جستجو و مرتب‌سازی (با کلیک روی عنوان ستون) دارد.</p>
      </div>
      <div className="distribution-controls">
        <label>ماه: <select value={`${ym.year}-${ym.month}`} onChange={(e) => { const [y, m] = e.target.value.split("-").map(Number); setYm({ year: y, month: m }); }}>
          {months.map((m) => <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>{monthLabel(m)}</option>)}
        </select></label>
        <label>هیبرید: <select value={selected} onChange={(e) => pick(e.target.value)}>
          <option value="">همه هیبریدها</option>{branchNames.sort((a, b) => a.localeCompare(b, "fa")).map((b) => <option key={b} value={b}>{b}</option>)}
        </select></label>
        <label>آستانه مشکوک: <input type="number" min={1} max={120} value={staleDays} onChange={(e) => setStaleDays(Math.max(1, Number(e.target.value) || 14))} /> روز</label>
        <a className="dist-excel" href={excelUrl}>⬇ دانلود Excel همه بخش‌ها ({monthLabel(ym)})</a>
      </div>
      {selected && <button className="cheque-back" onClick={() => pick("")}>→ بازگشت به همه هیبریدها</button>}
    </section>

    <MonthlyDistributionReport ym={ym} branch={selected} onBranch={pick} />

    {error ? <div className="profile-warning">{error}</div> : !data ? <div className="profile-loading">در حال دریافت خلاصه توزیع بار از کارآمد...</div> : <>
      <section className="cf-section">
        <div className="cf-title"><div><h3><span className="dist-step">۲</span> وضعیت امروز توزیع بار — {scopeLabel} (سال {faDigits(String(data.fiscal_year_label))})</h3><p>{(data.notes || []).join(" ")}</p></div></div>
        <div className="cf-kpis">
          <article className="cf-accent-red"><small>فاکتور توزیع‌نشده</small><b>{fullToman(sumOf(rows, "amount_rial"))}</b><span>تومان • {fa(rows.length)} فاکتور هنوز بار نرفته</span></article>
          <article><small>توزیع‌نشده بیش از {fa(staleDays)} روز</small><b>{fullToman(sumOf(stale, "amount_rial"))}</b><span>تومان • {fa(stale.length)} فاکتور</span></article>
          <article><small>میانگین صدور فاکتور تا خروج بار</small><b>{fa(Math.round(averageLead * 10) / 10)} روز</b><span>{fa(leadInvoices)} فاکتور خارج‌شده امسال</span></article>
        </div>
      </section>

      {!selected ? <section className="cf-section">
        <div className="cf-title"><div><h3><span className="dist-step">۳</span> توزیع‌نشده به تفکیک هیبرید</h3><p>روی هر هیبرید کلیک کنید تا کل صفحه مخصوص همان هیبرید شود.</p></div></div>
        <SortTable rows={byBranch} rowKey={(r) => r.name} onRowClick={(r) => pick(r.name)} initialSort="amount" placeholder="جستجوی هیبرید..."
          columns={[
            { key: "name", label: "هیبرید", value: (r) => r.name, render: (r) => <b>{r.name}</b> },
            { key: "amount", label: "توزیع‌نشده", value: (r) => r.amount, render: (r) => <>{boldToman(r.amount)}<small>{fa(r.items.length)} فاکتور</small></> },
            { key: "old", label: `بیش از ${fa(staleDays)} روز`, value: (r) => r.oldAmount, className: (r) => r.old.length ? "cf-debt" : undefined,
              render: (r) => <>{fullToman(r.oldAmount)}<small>{fa(r.old.length)} فاکتور</small></> },
            { key: "oldest", label: "قدیمی‌ترین", value: (r) => r.oldest, render: (r) => r.items.length ? `${fa(r.oldest)} روز` : "—" },
            { key: "lead", label: "میانگین صدور تا خروج", value: (r) => r.lead?.average_days ?? -1, render: (r) => r.lead ? `${fa(r.lead.average_days)} روز` : "—" },
          ]} />
      </section> : <section className="cf-section">
        <div className="cf-title"><div><h3><span className="dist-step">۳</span> توزیع‌نشده به تفکیک ویزیتور — {selected}</h3><p>فاکتورهای بدون حواله خروج هر ویزیتور این هیبرید.</p></div></div>
        <SortTable rows={byVisitor} rowKey={(r) => r.name} initialSort="amount" placeholder="جستجوی ویزیتور..." empty="این هیبرید فاکتور توزیع‌نشده ندارد."
          columns={[
            { key: "name", label: "ویزیتور", value: (r) => r.name, render: (r) => <b>{r.name}</b> },
            { key: "amount", label: "توزیع‌نشده", value: (r) => r.amount, render: (r) => <>{boldToman(r.amount)}<small>{fa(r.items.length)} فاکتور</small></> },
            { key: "old", label: `بیش از ${fa(staleDays)} روز`, value: (r) => r.oldAmount, className: (r) => r.old.length ? "cf-debt" : undefined,
              render: (r) => <>{fullToman(r.oldAmount)}<small>{fa(r.old.length)} فاکتور</small></> },
            { key: "oldest", label: "قدیمی‌ترین", value: (r) => r.oldest, render: (r) => `${fa(r.oldest)} روز` },
          ]} />
      </section>}

      <section className="cf-section">
        <div className="cf-debt-detail-grid">
          <div>
            <div className="cf-title"><div><h3><span className="dist-step">۴</span> سن فاکتورهای توزیع‌نشده</h3><p>چند روز از صدور فاکتور گذشته و هنوز حواله خروج ندارد — {scopeLabel}.</p></div></div>
            <div className="cf-table"><table>
              <thead><tr><th>سن</th><th>تعداد</th><th>مبلغ (تومان)</th></tr></thead>
              <tbody>{aging.map((a) => <tr key={a.label}><td>{a.label}</td><td>{fa(a.items.length)}</td><td><b>{fullToman(sumOf(a.items, "amount_rial"))}</b></td></tr>)}</tbody>
            </table></div>
          </div>
          <div>
            <div className="cf-title"><div><h3>سرعت خروج بار</h3><p>فاصله صدور فاکتور تا تاریخ حواله خروج، برای فاکتورهای امسال.</p></div></div>
            <SortTable rows={lead} rowKey={(r) => r.branch_name || "—"} initialSort="avg" placeholder="جستجوی هیبرید..."
              columns={[
                { key: "branch", label: "هیبرید", value: (r) => r.branch_name },
                { key: "avg", label: "میانگین", value: (r) => r.average_days, className: (r) => r.average_days > 7 ? "cf-debt" : undefined, render: (r) => <b>{fa(r.average_days)} روز</b> },
                { key: "d1", label: "تا ۱ روز", value: (r) => r.within_1_day_percent, render: (r) => `${fa(r.within_1_day_percent)}٪` },
                { key: "d3", label: "تا ۳ روز", value: (r) => r.within_3_days_percent, render: (r) => `${fa(r.within_3_days_percent)}٪` },
                { key: "d7", label: "بیش از ۷ روز", value: (r) => r.over_7_days, render: (r) => `${fa(r.over_7_days)} از ${fa(r.invoice_count)}` },
              ]} />
          </div>
        </div>
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3><span className="dist-step">۵</span> فاکتورهای توزیع‌نشده — {scopeLabel}</h3><p>همه فاکتورهای بدون «خروجی» (خروجی کمتر از ۱)؛ پیش‌فرض: قدیمی‌ترین بالا.</p></div></div>
        <SortTable rows={invoiceRows} rowKey={(r) => r.invoice_id} initialSort="wait" placeholder="شماره فاکتور، مشتری، ویزیتور یا هیبرید..."
          toolbar={<label className="distribution-check"><input type="checkbox" checked={onlyStale} onChange={(e) => setOnlyStale(e.target.checked)} /> فقط بیش از {fa(staleDays)} روز</label>}
          empty="فاکتوری با این فیلترها نیست."
          columns={[
            { key: "num", label: "شماره فاکتور", value: (r) => r.number, render: (r) => <b>{r.number || "—"}</b> },
            { key: "date", label: "تاریخ", value: (r) => r.date_jalali },
            { key: "wait", label: "انتظار", value: (r) => days(r), className: (r) => days(r) > staleDays ? "cf-debt" : undefined, render: (r) => `${fa(days(r))} روز` },
            { key: "cust", label: "مشتری", value: (r) => `${r.customer_name || ""} ${r.customer_code || ""}`, className: () => "cf-wrap",
              render: (r) => <><b>{r.customer_name || "—"}</b><small>کد {r.customer_code || "—"}</small></> },
            { key: "vis", label: "ویزیتور", value: (r) => r.visitor_name },
            ...(!selected ? [{ key: "branch", label: "هیبرید", value: (r: any) => r.branch_name }] : []),
            { key: "amt", label: "مبلغ (تومان)", value: (r) => Number(r.amount_rial || 0), render: (r) => boldToman(r.amount_rial) },
          ]} />
      </section>

      <section className="cf-section">
        <div className="cf-title"><div><h3><span className="dist-step">۶</span> عملکرد موزعان — {scopeLabel}</h3><p>حواله‌های خروج امسال به تفکیک موزع.</p></div></div>
        <SortTable rows={distributors} rowKey={(r, i) => `${r.deliver_name}-${r.branch_name}-${i}`} initialSort="amt" placeholder="نام موزع یا هیبرید..." empty="حواله خروجی ثبت نشده است."
          columns={[
            { key: "name", label: "موزع", value: (r) => r.deliver_name, render: (r) => <b>{r.deliver_name}</b> },
            ...(!selected ? [{ key: "branch", label: "هیبرید", value: (r: any) => r.branch_name }] : []),
            { key: "exits", label: "حواله", value: (r) => r.exit_count, render: (r) => fa(r.exit_count) },
            { key: "inv", label: "فاکتور", value: (r) => r.invoice_count, render: (r) => fa(r.invoice_count) },
            { key: "amt", label: "مبلغ بار (تومان)", value: (r) => Number(r.amount_rial || 0), render: (r) => boldToman(r.amount_rial) },
            { key: "lead", label: "میانگین صدور تا خروج", value: (r) => r.average_lead_days, className: (r) => r.average_lead_days > 7 ? "cf-debt" : undefined, render: (r) => `${fa(r.average_lead_days)} روز` },
            { key: "last", label: "آخرین خروج", value: (r) => r.last_exit_date_jalali },
          ]} />
      </section>
    </>}

    <section className="cf-section dist-timeline-toggle">
      <div className="cf-title">
        <div><h3><span className="dist-step">۷</span> زمان‌بندی توزیع هر فاکتور</h3>
          <p>ثبت فاکتور تا ثبت حواله و خروج بار، ماهانه و به تفکیک هر هیبرید. هر وقت لازم بود باز کنید.</p></div>
        <button className={`dist-toggle${showTimeline ? " open" : ""}`} onClick={() => setShowTimeline(!showTimeline)}>
          {showTimeline ? "بستن زمان‌بندی ▲" : "نمایش زمان‌بندی ▼"}
        </button>
      </div>
    </section>
    {showTimeline && <InvoiceDistributionTimeline branch={selected} staleDays={staleDays} onBranch={pick} ym={ym} />}
  </div>;
}
