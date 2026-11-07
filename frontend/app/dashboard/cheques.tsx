// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (cheques).
import { useEffect, useMemo, useRef, useState } from "react";
import { RegCell, chequeNo } from "../cheque-reg";
import { useChatLink } from "../chatbot/chat-link";
import { Heading, K } from "./widgets";
import { chequeTermDays } from "./collections";
import { VerticalBars } from "./management";
import { IssuedChequeTotals, JALALI_MONTHS, RahkaranChequeTotals, chequeDueJalali, chequeInsightRows, cname, daysToDue, fa, fullToman, isLongTermLargeCheque, longTermChequeInsight, money, receivedChequeHoldingBucket, receivedChequeHoldingLabel, remainingLabel, request } from "./shared";
import type { ReceivedChequeHolding } from "./shared";
import type { AgentResult, CustomerAudit, TreasuryCheque, View } from "./types";

export function ChequeHub({
  received,
  issued,
  error,
  open,
}: {
  received: TreasuryCheque[];
  issued: TreasuryCheque[];
  error: string;
  open: (v: View) => void;
}) {
  const scopedReceived = received;
  const scopedIssued = issued;
  const card = (kind: "received" | "issued", rows: TreasuryCheque[]) => {
    const incoming = kind === "received",
      total = rows.reduce((s, x) => s + (x.amount || 0), 0),
      overdue = rows.filter((x) => (daysToDue(x) ?? 1) < 0),
      month = rows.filter((x) => {
        const d = daysToDue(x);
        return d !== undefined && d >= 0 && d <= 30;
      }),
      over90 = rows.filter(isLongTermLargeCheque);
    return (
      <button
        className={`cheque-flow-card ${incoming ? "received" : "issued"}`}
        onClick={() => open(incoming ? "receivedCheques" : "issuedCheques")}
      >
        <header>
          <span className="flow-icon">{incoming ? "↓" : "↑"}</span>
          <div>
            <small>{incoming ? "ورودی خزانه" : "خروجی خزانه"}</small>
            <h2>{incoming ? "چک‌های دریافتی" : "چک‌های پرداختی باز"}</h2>
            <p>
              {incoming
                ? "مطالبات، وصول، برگشتی و ریسک مشتری"
                : "فقط چک‌های فعال؛ پرداخت‌شده و تضمینی حذف شده‌اند"}
            </p>
          </div>
          <i>انتخاب راهکاران یا کارآمد ←</i>
        </header>
        <strong>{fullToman(total)} <small>تومان</small></strong>
        <div className="flow-stats">
          <span>
            <b>{fa(rows.length)}</b>
            <small>کل چک‌ها</small>
          </span>
          <span>
            <b>{fa(month.length)}</b>
            <small>تا ۳۰ روز</small>
          </span>
          <span className={overdue.length ? "danger" : ""}>
            <b>{fa(overdue.length)}</b>
            <small>سررسیدگذشته</small>
          </span>
          <span className={over90.length ? "warn" : ""}>
            <b>{fa(over90.length)}</b>
            <small>مدت ۹۰+ روز، بالای ۱۰۰ م</small>
          </span>
        </div>
        <div className="flow-bar">
          <i
            style={{
              width: `${rows.length ? (month.length / rows.length) * 100 : 0}%`,
            }}
          />
          <i
            className="late"
            style={{
              width: `${rows.length ? (overdue.length / rows.length) * 100 : 0}%`,
            }}
          />
        </div>
      </button>
    );
  };
  return (
    <>
      <section className="cheque-hub-intro">
        <div>
          <small>مدیریت چک‌ها از کل به جزء</small>
          <h2>ابتدا نوع جریان چک را انتخاب کنید</h2>
          <p>
            هر بخش خلاصه، سررسیدها، ریز چک‌ها و هشدارهای خودش را نشان می‌دهد.
          </p>
        </div>
        <span>سبد یکپارچه خزانه • راهکاران + کارآمد</span>
      </section>
      {error && <div className="profile-warning">{error}</div>}
      <section className="cheque-flow-grid">
        {card("received", scopedReceived)}
        {card("issued", scopedIssued)}
      </section>
      <article className="fd-panel cheque-flow-guide">
        <Heading h="مسیر بررسی" p="از تصویر کلان تا ریز هر چک" />
        <div>
          <span>انتخاب دریافتی یا پرداختی</span>
          <i>←</i>
          <span>انتخاب راهکاران یا کارآمد</span>
          <i>←</i>
          <span>ریز چک و روز باقی‌مانده</span>
          <i>←</i>
          <span>هشدار و اقدام پیشنهادی</span>
        </div>
      </article>
    </>
  );
}
// Company-wide picture of received cheques across both systems, shown before choosing a source.
// Uses the same open portfolio as the detail pages (V117 holding filter), so totals match «همه وضعیت‌ها».
export function ReceivedChequeOverview({ rows }: { rows: TreasuryCheque[] }) {
  const portfolio = rows.filter((x) => receivedChequeHoldingBucket(x) !== "other");
  const systems = [["rahkaran", "راهکاران"], ["karamad", "کارآمد"]] as const;
  const sum = (items: TreasuryCheque[]) => items.reduce((s, x) => s + (x.amount || 0), 0);
  const bySystem = (items: TreasuryCheque[]) => systems.map(([k]) => items.filter((x) => x.source_system === k));
  const total = sum(portfolio);
  const isReturned = (x: TreasuryCheque) => receivedChequeHoldingBucket(x).startsWith("returned");

  const overdue = portfolio.filter((x) => (daysToDue(x) ?? 0) < 0);
  const today = portfolio.filter((x) => daysToDue(x) === 0);
  const future = portfolio.filter((x) => (daysToDue(x) ?? -1) > 0);
  const returned = portfolio.filter(isReturned);
  const kpis = [
    { label: "کل سبد چک‌های دریافتی", icon: "▣", tone: "total", items: portfolio },
    { label: "سررسید گذشته", icon: "!", tone: "danger", items: overdue },
    { label: "سررسید امروز", icon: "◷", tone: "warn", items: today },
    { label: "سررسید آینده", icon: "→", tone: "ok", items: future },
    { label: "برگشتی (نزد صندوق یا مشتری)", icon: "↺", tone: "danger", items: returned },
  ];

  const dueGroups = [
    { title: "معوقات", items: overdue },
    { title: "امروز", items: today },
    { title: "آینده", items: future },
    ...(portfolio.some((x) => daysToDue(x) === undefined) ? [{ title: "بدون سررسید", items: portfolio.filter((x) => daysToDue(x) === undefined) }] : []),
  ];

  const shareValue = (items: TreasuryCheque[]) => total ? (sum(items) / total) * 100 : 0;
  const share = (items: TreasuryCheque[]) => total ? `${fa(Math.round(shareValue(items) * 10) / 10)}٪` : "—";
  const splitTable = (groups: { title: string; items: TreasuryCheque[] }[], head: string) => <div className="cf-table"><table>
    <thead><tr><th>{head}</th>{systems.map(([, l]) => <th key={l}>{l}</th>)}<th>جمع دو سیستم</th><th>سهم از مبلغ کل</th></tr></thead>
    <tbody>
      {groups.map((g) => <tr key={g.title}>
        <td><b>{g.title}</b></td>
        {bySystem(g.items).map((part, i) => <td key={i}>{fullToman(sum(part))}<small>{fa(part.length)} فقره</small></td>)}
        <td><b>{fullToman(sum(g.items))}</b><small>{fa(g.items.length)} فقره</small></td>
        <td>{share(g.items)}</td>
      </tr>)}
      <tr>
        <td><b>جمع کل</b></td>
        {bySystem(portfolio).map((part, i) => <td key={i}><b>{fullToman(sum(part))}</b><small>{fa(part.length)} فقره</small></td>)}
        <td><b>{fullToman(total)}</b><small>{fa(portfolio.length)} فقره</small></td>
        <td>{total ? "۱۰۰٪" : "—"}</td>
      </tr>
    </tbody>
  </table></div>;

  return <>
    <section className="cf-section">
      <div className="cf-title"><div><h3>گزارش کلی چک‌های دریافتی شرکت</h3><p>جمع دو سیستم راهکاران و کارآمد؛ همان سبد باز صفحات جزئیات. مبالغ به تومان و اسمی، قبل از تعدیل وصول هستند. برای ریز چک‌ها و فیلترها، یکی از دو منبع پایین را انتخاب کنید.</p></div></div>
      <div className="rco-kpis">
        {kpis.map((k) => <article key={k.label} className={`rco-kpi ${k.tone}`} title={`${fullToman(sum(k.items))} تومان`}>
          <header><i aria-hidden="true">{k.icon}</i><small>{k.label}</small></header>
          <b>{money(sum(k.items))} <em>تومان</em></b>
          <p><span>{fa(k.items.length)} فقره</span>{k.tone !== "total" && <span>{share(k.items)} از کل</span>}</p>
          {k.tone !== "total" && <div className="rco-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, shareValue(k.items))}%` }} /></div>}
          <dl>
            {bySystem(k.items).map((part, i) => <div key={systems[i][0]} className={systems[i][0]}>
              <dt>{systems[i][1]}</dt>
              <dd><b>{money(sum(part))}</b><small>{fa(part.length)} فقره</small></dd>
            </div>)}
          </dl>
        </article>)}
      </div>
    </section>
    <section className="cf-section">
      <div className="cf-title"><div><h3>تفکیک سررسید</h3><p>مبلغ کامل (تومان) و تعداد چک معوق، امروز و آینده، جدا برای هر سیستم.</p></div></div>
      {splitTable(dueGroups, "سررسید")}
    </section>
  </>;
}

export function ChequeSourcePage({ kind, rows, error, back, onUpdated }: {
  kind: "received" | "issued";
  rows: TreasuryCheque[];
  error: string;
  back: () => void;
  onUpdated?: () => Promise<void>;
}) {
  const [source, setSource] = useState<"rahkaran" | "karamad" | null>(null);
  const [branch, setBranch] = useState("");
  const label = kind === "received" ? "دریافتی" : "پرداختی";
  // چت‌بات: «ریز چک‌های باز شمس» → همین صفحه با منبع و جستجوی آماده باز می‌شود.
  const chatLink = useChatLink(kind === "received" ? "receivedCheques" : "issuedCheques");
  useEffect(() => {
    if (!chatLink?.source) return;
    setSource(chatLink.source);
    setBranch(chatLink.source === "rahkaran" ? "__rahkaran__" : "");
  }, [chatLink]);
  const scope = (system: "rahkaran" | "karamad") => rows.filter((x) => {
    const days = daysToDue(x);
    return x.source_system === system && (kind === "received" || system === "karamad" || (days !== undefined && days >= -20));
  });
  // سقف «۲۰ روز معوق» پرداختی راهکاران را خود ChequeDetails در حالت «همه» اعمال می‌کند؛
  // ریز کامل را می‌فرستیم تا فیلتر سال/ماه سررسید، معوقات قدیمی‌تر را هم ببیند.
  const detailRows = (system: "rahkaran" | "karamad") => rows.filter((x) => x.source_system === system);
  if (source) return <>
    {error && <div className="profile-warning">{error}</div>}
    <section className="cheque-hub-intro"><div><small>جزئیات منبع انتخاب‌شده</small><h2>چک‌های {label} — {source === "rahkaran" ? "راهکاران" : "کارآمد"}</h2></div></section>
    <ChequeDetails key={`${source}-${chatLink?.at || 0}`} kind={kind} rows={detailRows(source)} source={source}
      initialSearch={chatLink?.source === source ? chatLink.search : undefined}
      branch={branch} setBranch={setBranch} onUpdated={onUpdated} back={() => { setSource(null); setBranch(""); }} />
  </>;
  return <>
    <button className="cheque-back" onClick={back}>→ بازگشت به انتخاب نوع چک</button>
    {error && <div className="profile-warning">{error}</div>}
    {kind === "received" && <ReceivedChequeOverview rows={[...scope("rahkaran"), ...scope("karamad")]} />}
    <section className="cheque-hub-intro"><div><small>چک‌های {label}</small><h2>منبع اطلاعات را انتخاب کنید</h2><p>روی هر جمع کلیک کنید تا فیلترها، آمار سررسید و ریز کامل همان منبع باز شود.</p></div></section>
    <section className="cheque-source-grid">
      {(["rahkaran", "karamad"] as const).map((system) => {
        const items = scope(system);
        const title = system === "rahkaran" ? "راهکاران" : "کارآمد";
        return <button type="button" className={`cheque-source-card ${system}`} key={system}
          onClick={() => { setBranch(system === "rahkaran" ? "__rahkaran__" : ""); setSource(system); }}>
          <span>جمع کل چک‌های {label}</span><h2>{title}</h2>
          <strong>{fullToman(items.reduce((sum, x) => sum + (x.amount || 0), 0))}</strong>
          <small>تومان · {fa(items.length)} فقره</small>
          {kind === "received" && system === "karamad" && items.length > 0 && (
            <div className="karamad-status-mini">
              {Array.from(new Set(items.map((x) => x.state_label || x.cheque_status || "وضعیت نامشخص"))).slice(0, 6).map((status) => (
                <span key={status}>{status}: {fa(items.filter((x) => (x.state_label || x.cheque_status || "وضعیت نامشخص") === status).length)}</span>
              ))}
            </div>
          )}
          <p>{kind === "issued" ? (system === "karamad" ? "چک‌های پرداختی ثبت‌شده تا آخرین فایل؛ داده آینده فعلاً کامل نیست" : "چک‌های باز، شامل معوق حداکثر ۲۰ روز") : "کل سبد به‌روز چک‌های دریافتی موجود در گزارش"}</p>
          {!items.length && <p>در ورودی فعلی چکی برای این منبع موجود نیست.</p>}
          <b>مشاهدهٔ جزئیات {title} ←</b>
        </button>;
      })}
    </section>
  </>;
}

export function ChequeDetails({
  kind,
  source,
  rows,
  initialSearch,
  agent,
  back,
  branch,
  setBranch,
  onUpdated,
}: {
  kind: "received" | "issued";
  source: "rahkaran" | "karamad";
  rows: TreasuryCheque[];
  agent?: AgentResult;
  back: () => void;
  branch: string;
  setBranch: (value: string) => void;
  onUpdated?: () => Promise<void>;
  /** جستجوی آماده (از لینک چت‌بات) */
  initialSearch?: string;
}) {
  const incoming = kind === "received";
  // لینک چت‌بات: مستقیم به جستجو و جدول فیلترشده برو (پایین فیلترهای بالا) و لحظه‌ای برجسته‌اش کن.
  const chatSearchRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!initialSearch) return;
    const t = window.setTimeout(() => {
      const el = chatSearchRef.current;
      if (!el) return;
      window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 90, behavior: "smooth" });
      el.classList.add("chat-linked");
      window.setTimeout(() => el.classList.remove("chat-linked"), 2600);
    }, 250);
    return () => window.clearTimeout(t);
  }, [initialSearch]);
  const [period, setPeriod] = useState("all"),
    [selectedDay, setSelectedDay] = useState(""),
    [dueYear, setDueYear] = useState(0),
    [dueMonth, setDueMonth] = useState(0),
    [overdueOnly, setOverdueOnly] = useState(true),
    [search, setSearch] = useState(initialSearch || ""),
    [portfolioFile, setPortfolioFile] = useState<File | null>(null),
    [portfolioBusy, setPortfolioBusy] = useState(false),
    [portfolioMessage, setPortfolioMessage] = useState(""),
    [holdingStatuses, setHoldingStatuses] = useState<ReceivedChequeHolding[]>([]);
  const toggleHolding = (id: ReceivedChequeHolding) => setHoldingStatuses((current) =>
    id === "all" ? [] : current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  const replaceKaramadChequePortfolio = async () => {
    if (!portfolioFile) return;
    setPortfolioBusy(true);
    setPortfolioMessage("");
    try {
      const body = new FormData();
      body.append("file", portfolioFile);
      const endpoint = incoming ? "/karamad-manual/received-cheques/replace" : "/karamad-manual/issued-cheques/replace";
      const result = await request(endpoint, { method: "POST", body });
      setPortfolioMessage(result.message || (incoming ? "سبد چک‌های دریافتی کارآمد به‌روز شد." : "چک‌های پرداختی ثبت‌شده کارآمد به‌روز شد."));
      setPortfolioFile(null);
      if (onUpdated) await onUpdated();
    } catch (e) {
      setPortfolioMessage(e instanceof Error ? `خطا: ${e.message}` : "به‌روزرسانی فایل ناموفق بود");
    } finally {
      setPortfolioBusy(false);
    }
  };
  const branchOptions = useMemo(() => Array.from(new Set(rows
    .filter((x) => x.source_system === "karamad")
    .map((x) => x.branch_name || x.bank_branch_name || x.branch)
    .filter(Boolean) as string[])).sort((a, b) => a.localeCompare(b, "fa")), [rows]);
  const sourceBranchRows = branch === "__rahkaran__"
    ? rows.filter((x) => x.source_system === "rahkaran")
    : branch
      ? rows.filter((x) => x.source_system === "karamad" && (x.branch_name || x.bank_branch_name || x.branch) === branch)
      : rows;
  // V117: the received open portfolio is strictly limited to the three approved holdings.
  // کارآمد: «برگشتی نزد مشتری» به مشتری پس داده شده و در سبد حساب نمی‌شود.
  // همه «واگذار شده»ها (حتی سررسیدگذشته) طبق درخواست مدیریت نمایش داده می‌شوند.
  const branchScopedRows = incoming
    ? sourceBranchRows.filter((x) => {
      const bucket = receivedChequeHoldingBucket(x);
      if (bucket === "other") return false;
      if (x.source_system === "karamad" && bucket === "returned_customer") return false;
      return true;
    })
    : sourceBranchRows;
  const holdingCounts = incoming ? {
    all: branchScopedRows.length,
    collector: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "collector").length,
    bank: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "bank").length,
    assigned: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "assigned").length,
    pending: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "pending").length,
    cashbox: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "cashbox").length,
    returned_cashbox_plain: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_cashbox_plain").length,
    returned_cashbox_yeh: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_cashbox_yeh").length,
    returned_customer: branchScopedRows.filter((x) => receivedChequeHoldingBucket(x) === "returned_customer").length,
  } : null;
  const holdingScopedRows = incoming && holdingStatuses.length
    ? branchScopedRows.filter((x) => holdingStatuses.includes(receivedChequeHoldingBucket(x) as ReceivedChequeHolding))
    : branchScopedRows;
  const portfolioOverdue = holdingScopedRows.filter((x) => (daysToDue(x) ?? 0) < 0),
    portfolioToday = holdingScopedRows.filter((x) => daysToDue(x) === 0),
    portfolioFuture = holdingScopedRows.filter((x) => (daysToDue(x) ?? -1) > 0),
    portfolioOverdueAmount = portfolioOverdue.reduce((sum, x) => sum + (x.amount || 0), 0),
    portfolioTodayAmount = portfolioToday.reduce((sum, x) => sum + (x.amount || 0), 0),
    portfolioFutureAmount = portfolioFuture.reduce((sum, x) => sum + (x.amount || 0), 0);
  // فیلتر سال/ماه سررسید شمسی: جای فیلتر بازه را می‌گیرد تا معوقات سال‌های قبل (بدون سقف ۲۰ روز) هم دیده شوند.
  const isOverdue = (x: TreasuryCheque) => (daysToDue(x) ?? 0) < 0;
  const yearSummary = useMemo(() => {
    const map = new Map<number, { year: number; count: number; amount: number; overdueCount: number; overdueAmount: number }>();
    holdingScopedRows.forEach((x) => {
      const j = chequeDueJalali(x);
      if (!j) return;
      const item = map.get(j.year) || { year: j.year, count: 0, amount: 0, overdueCount: 0, overdueAmount: 0 };
      item.count += 1;
      item.amount += x.amount || 0;
      if (isOverdue(x)) { item.overdueCount += 1; item.overdueAmount += x.amount || 0; }
      map.set(j.year, item);
    });
    return Array.from(map.values()).sort((a, b) => b.year - a.year);
  }, [holdingScopedRows]);
  const monthSummary = useMemo(() => {
    const months = JALALI_MONTHS.map((name, i) => ({ month: i + 1, name, count: 0, amount: 0 }));
    if (!dueYear) return months;
    holdingScopedRows.forEach((x) => {
      const j = chequeDueJalali(x);
      if (!j || j.year !== dueYear || (overdueOnly && !isOverdue(x))) return;
      months[j.month - 1].count += 1;
      months[j.month - 1].amount += x.amount || 0;
    });
    return months;
  }, [holdingScopedRows, dueYear, overdueOnly]);
  const periodRows = dueYear ? holdingScopedRows.filter((x) => {
    const j = chequeDueJalali(x);
    return Boolean(j) && j!.year === dueYear && (!dueMonth || j!.month === dueMonth) && (!overdueOnly || isOverdue(x));
  }) : holdingScopedRows.filter((x) => {
    const days = daysToDue(x);
    const dueDate = x.due_date ? String(x.due_date).slice(0, 10) : "";
    if (period === "day") return Boolean(selectedDay) && dueDate === selectedDay;
    if (period === "overdue20") return days !== undefined && days < 0 && days >= -20;
    if (period === "future") return days !== undefined && days >= 0;
    if (period === "all") return incoming || source === "karamad" ? true : days !== undefined && days >= -20;
    if (period === "after6m") return days !== undefined && days > 180;
    if (period === "12m") return days !== undefined && days >= 0 && days <= 365;
    const horizon = period === "7d" ? 7 : period === "20d" ? 20 : period === "1m" ? 30 : period === "3m" ? 90 : 180;
    return days !== undefined && days >= 0 && days <= horizon;
  });
  const normalizedSearch = search.trim().toLocaleLowerCase("fa-IR");
  const viewRows = !normalizedSearch ? periodRows : periodRows.filter((x) =>
    [x.counterpart_name, x.counterpart_code, x.document_number, x.serial_number, x.sayad_number, x.account_number, x.bank_name, x.branch_name, x.branch, x.description, x.cheque_status, x.cheque_location, x.last_operation_account, x.last_operation_level4, x.amount]
      .filter((value) => value !== null && value !== undefined)
      .some((value) => String(value).toLocaleLowerCase("fa-IR").includes(normalizedSearch)),
  );
  const sortedRows = [...viewRows].sort(
      (a, b) =>
        (daysToDue(a) ?? Number.POSITIVE_INFINITY) -
        (daysToDue(b) ?? Number.POSITIVE_INFINITY),
    ),
    total = viewRows.reduce((s, x) => s + (x.amount || 0), 0),
    overdue = viewRows.filter((x) => (daysToDue(x) ?? 1) < 0),
    soon = viewRows.filter((x) => {
      const d = daysToDue(x);
      return d !== undefined && d >= 0 && d <= 7;
    }),
    over90 = viewRows.filter(isLongTermLargeCheque),
    futureDueDays = viewRows
      .map((x) => daysToDue(x))
      .filter((d): d is number => d !== undefined && d >= 0),
    averageDueDays = futureDueDays.length
      ? futureDueDays.reduce((sum, d) => sum + d, 0) / futureDueDays.length
      : 0,
    due = [
      {
        label: "سررسیدگذشته",
        value: overdue.length,
        tone: "red",
        records: chequeInsightRows(overdue),
      },
      {
        label: "تا ۷ روز",
        value: soon.length,
        tone: "amber",
        records: chequeInsightRows(soon),
      },
      {
        label: "۸ تا ۳۰ روز",
        value: viewRows.filter((x) => {
          const d = daysToDue(x);
          return d !== undefined && d > 7 && d <= 30;
        }).length,
        tone: "teal",
        records: chequeInsightRows(
          viewRows.filter((x) => {
            const d = daysToDue(x);
            return d !== undefined && d > 7 && d <= 30;
          }),
        ),
      },
      {
        label: "۳۱ تا ۹۰ روز",
        value: viewRows.filter((x) => {
          const d = daysToDue(x);
          return d !== undefined && d > 30 && d <= 90;
        }).length,
        tone: "violet",
        records: chequeInsightRows(
          viewRows.filter((x) => {
            const d = daysToDue(x);
            return d !== undefined && d > 30 && d <= 90;
          }),
        ),
      },
      {
        label: "بیشتر از ۹۰ روز",
        value: viewRows.filter((x) => (daysToDue(x) ?? -1) > 90).length,
        tone: "violet",
        records: chequeInsightRows(
          viewRows.filter((x) => (daysToDue(x) ?? -1) > 90),
        ),
      },
    ];
  return (
    <>
      <button className="cheque-back" onClick={back}>
        → بازگشت به انتخاب راهکاران یا کارآمد
      </button>
      {source === "karamad" && (
        <section className="karamad-cheque-update">
          <div>
            <small>{incoming ? "به‌روزرسانی سبد چک دریافتی کارآمد" : "به‌روزرسانی چک‌های پرداختی ثبت‌شده کارآمد"}</small>
            <h3>فایل جدید را بده؛ نسخه قبلی کامل جایگزین می‌شود</h3>
            <p>{incoming ? "وضعیت واقعی چک مثل «نزد صندوق»، «واگذار شده» و «برگشتی نزد مشتری» مستقیماً از آخرین Excel خوانده می‌شود." : "این فایل فقط چک‌های پرداختی ثبت‌شده تا آخرین آپدیت را پوشش می‌دهد. اطلاعات آینده فعلاً کامل نیست و برگشتی گزارش نشده است."}</p>
          </div>
          <label>
            <span>{portfolioFile ? portfolioFile.name : "انتخاب Excel جدید"}</span>
            <input type="file" accept=".xlsx" onChange={(e) => setPortfolioFile(e.target.files?.[0] || null)} />
          </label>
          <button type="button" disabled={!portfolioFile || portfolioBusy} onClick={replaceKaramadChequePortfolio}>
            {portfolioBusy ? "در حال به‌روزرسانی…" : "جایگزینی و به‌روزرسانی"}
          </button>
          {portfolioMessage && <em>{portfolioMessage}</em>}
        </section>
      )}
      {!incoming && source === "karamad" && (
        <section className="profile-warning">
          <b>وضعیت پوشش داده:</b> چک‌های پرداختی ثبت‌شده نمایش داده می‌شوند؛ داده آینده هنوز کامل در دسترس نیست و در فایل فعلی چک برگشتی نداریم. جمع آینده را تعهد کامل شرکت در نظر نگیرید.
        </section>
      )}
      {source === "karamad" && (
        <section className="cheque-period-filter branch-filter-panel">
          <div>
            <b>آمار شهر / شعبه کارآمد</b>
            <small>با انتخاب شعبه، تمام مبلغ‌ها، تعدادها، معوق‌ها، نمودار و ریز چک فقط برای همان شعبه محاسبه می‌شود.</small>
          </div>
          <label className="cheque-date-filter">
            <span>شعبه</span>
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              <option value="">همه شعب کارآمد</option>
              {branchOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          {branch && <button className="active" onClick={() => setBranch("")}>پاک کردن فیلتر شعبه</button>}
        </section>
      )}
      {incoming && source === "karamad" && (
        <section className="karamad-portfolio-timing">
          <div className="karamad-timing-card overdue">
            <small>سررسید گذشته</small>
            <strong>{fullToman(portfolioOverdueAmount)} تومان</strong>
            <span>{fa(portfolioOverdue.length)} فقره</span>
          </div>
          <div className="karamad-timing-card today">
            <small>سررسید امروز</small>
            <strong>{fullToman(portfolioTodayAmount)} تومان</strong>
            <span>{fa(portfolioToday.length)} فقره</span>
          </div>
          <div className="karamad-timing-card future">
            <small>سررسید آینده</small>
            <strong>{fullToman(portfolioFutureAmount)} تومان</strong>
            <span>{fa(portfolioFuture.length)} فقره</span>
          </div>
          <div className="karamad-timing-card total">
            <small>کل سبد کارآمد</small>
            <strong>{fullToman(holdingScopedRows.reduce((sum, x) => sum + (x.amount || 0), 0))} تومان</strong>
            <span>{fa(holdingScopedRows.length)} فقره</span>
          </div>
        </section>
      )}
      {incoming && holdingCounts && (
        <section className="cheque-period-filter cheque-holding-filter">
          <div>
            <b>فیلتر محل / وضعیت چک دریافتی</b>
            <small>چند وضعیت را می‌توانید با هم انتخاب کنید. در کارآمد «برگشتی نزد مشتری» در سبد حساب نمی‌شود؛ همه «واگذار شده»ها، حتی سررسیدگذشته، نمایش داده می‌شوند.</small>
          </div>
          {[
            ["all", "همه وضعیت‌ها", holdingCounts.all],
            ["assigned", "واگذار شده", holdingCounts.assigned],
            ["pending", "غیرقطعی", holdingCounts.pending],
            ["cashbox", "نزد صندوق", holdingCounts.cashbox],
            ["returned_cashbox_plain", "برگشت نزد صندوق", holdingCounts.returned_cashbox_plain],
            ["returned_cashbox_yeh", "برگشتی نزد صندوق", holdingCounts.returned_cashbox_yeh],
            ...(source === "karamad" ? [] : [["returned_customer", "برگشتی نزد مشتری", holdingCounts.returned_customer]]),
          ].map(([id, title, count]) => (
            <button
              key={String(id)}
              type="button"
              className={(id === "all" ? !holdingStatuses.length : holdingStatuses.includes(id as ReceivedChequeHolding)) ? "active" : ""}
              onClick={() => toggleHolding(id as ReceivedChequeHolding)}
            >
              {title} · {fa(Number(count))}
            </button>
          ))}
        </section>
      )}
      <section className="cheque-period-filter">
        <div>
          <b>{incoming ? "فیلتر سررسید چک‌های دریافتی" : "فیلتر سررسید چک‌های پرداختی"}</b>
          <small>فیلتر روزانه و بازه‌های زمانی برای هر دو نوع چک یکسان است؛ آمار، نمودار و ریز جدول هم‌زمان به‌روزرسانی می‌شوند.</small>
        </div>
        {[["all", incoming ? "همه سررسیدها (بدون سقف تاریخ)" : "همه (تا ۲۰ روز معوق)"], ["future", "کل آینده"], ["day", "روز مشخص"], ["overdue20", "معوق ۲۰ روز اخیر"], ["7d", "۷ روز آینده"], ["20d", "۲۰ روز آینده"], ["1m", "یک ماه آینده"], ["3m", "سه ماه آینده"], ["6m", "شش ماه آینده"], ["after6m", "بعد از ۶ ماه"], ["12m", "تا ۱۲ ماه"]].map(([id, title]) => (
          <button key={id} className={!dueYear && period === id ? "active" : ""} onClick={() => { setPeriod(id); setDueYear(0); setDueMonth(0); }}>{title}</button>
        ))}
        {period === "day" && !dueYear && (
          <label className="cheque-date-filter">
            <span>روز سررسید</span>
            <input type="date" value={selectedDay} onChange={(e) => setSelectedDay(e.target.value)} />
          </label>
        )}
      </section>
      <section className="cheque-period-filter cheque-year-filter">
        <div>
          <b>سررسید بر اساس سال و ماه شمسی</b>
          <small>سال را انتخاب کنید تا جمع مبلغ و ریز چک‌های همان سال (و در صورت انتخاب، همان ماه) نمایش داده شود. با انتخاب سال، فیلتر بازه بالا کنار می‌رود و معوقات قدیمی بدون سقف ۲۰ روز دیده می‌شوند.</small>
        </div>
        {yearSummary.map((y) => (
          <button key={y.year} type="button" className={dueYear === y.year ? "active" : ""}
            onClick={() => { setDueYear(dueYear === y.year ? 0 : y.year); setDueMonth(0); }}>
            <b>{fa(y.year).replace(/٬/g, "")}</b>
            {" · "}{y.overdueCount ? `سررسیدگذشته: ${fa(y.overdueCount)} فقره · ${fullToman(y.overdueAmount)} تومان` : `${fa(y.count)} فقره · بدون معوق`}
          </button>
        ))}
        {dueYear > 0 && (
          <>
            <label className="cheque-date-filter">
              <span>ماه</span>
              <select value={dueMonth} onChange={(e) => setDueMonth(Number(e.target.value))}>
                <option value={0}>همه ماه‌های {fa(dueYear).replace(/٬/g, "")}</option>
                {monthSummary.map((m) => (
                  <option key={m.month} value={m.month} disabled={!m.count}>
                    {m.name} — {fa(m.count)} فقره{m.count ? ` · ${fullToman(m.amount)} تومان` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="cheque-date-filter">
              <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
              <span>فقط سررسیدگذشته</span>
            </label>
            <button type="button" onClick={() => { setDueYear(0); setDueMonth(0); }}>پاک کردن فیلتر سال</button>
          </>
        )}
      </section>
      {dueYear > 0 && (
        <section className="karamad-portfolio-timing">
          <div className="karamad-timing-card overdue">
            <small>{overdueOnly ? "سررسیدگذشته" : "سررسید"} {dueMonth ? `${JALALI_MONTHS[dueMonth - 1]} ` : ""}{fa(dueYear).replace(/٬/g, "")}</small>
            <strong>{fullToman(periodRows.reduce((sum, x) => sum + (x.amount || 0), 0))} تومان</strong>
            <span>{fa(periodRows.length)} فقره — ریز کامل در جدول پایین</span>
          </div>
        </section>
      )}
      {branch === "__rahkaran__" ? <RahkaranChequeTotals rows={viewRows} kind={kind} /> : !incoming && <IssuedChequeTotals rows={viewRows} />}
      {(
      <div className="fd-kpis">
        <K
          t={incoming ? "مبلغ چک‌های دریافتی" : source === "karamad" ? "مبلغ چک‌های پرداختی ثبت‌شده" : "مبلغ چک‌های پرداختی باز"}
          v={fullToman(total)}
          n="تومان"
          c={incoming ? "teal" : "blue"}
          detail={{ title: incoming ? "جزئیات مبلغ چک‌های دریافتی" : "جزئیات مبلغ چک‌های پرداختی", subtitle: "ریز کامل مبنای جمع این شاخص", tone: incoming ? "teal" : "blue", stats: [{ label: "تعداد", value: fa(viewRows.length) }, { label: "مبلغ کل", value: `${fullToman(total)} تومان` }], records: chequeInsightRows(viewRows) }}
        />
        <K t="تعداد چک" v={fa(viewRows.length)} n="فقره" c="blue" detail={{ title: "جزئیات چک‌های این جمع", subtitle: "با انتخاب هر شاخص، ریز موارد نمایش داده می‌شود.", tone: "blue", stats: [{ label: "تعداد", value: fa(viewRows.length) }, { label: "مبلغ", value: `${fullToman(total)} تومان` }], records: chequeInsightRows(viewRows) }} />
        <K
          t="سررسیدگذشته"
          v={fa(overdue.length)}
          n={fullToman(overdue.reduce((s, x) => s + (x.amount || 0), 0)) + " تومان"}
          c="red"
          detail={{
            title: incoming
              ? "چک‌های دریافتی سررسیدگذشته"
              : "چک‌های پرداختی سررسیدگذشته",
            subtitle: "فهرست مواردی که موعد آن‌ها گذشته است",
            tone: "red",
            stats: [
              { label: "تعداد چک", value: fa(overdue.length) },
              {
                label: "مبلغ کل",
                value: `${fullToman(overdue.reduce((s, x) => s + (x.amount || 0), 0))} تومان`,
              },
            ],
            records: chequeInsightRows(overdue),
          }}
        />
        <K
          t="مدت بیش از ۹۰ روز و بالای ۱۰۰ میلیون"
          v={fa(over90.length)}
          n={fullToman(over90.reduce((s, x) => s + (x.amount || 0), 0)) + " تومان"}
          c="amber"
          detail={longTermChequeInsight(over90, incoming)}
        />
      </div>
      )}
      <section className="cheque-detail-grid">
        <article className="fd-panel visual-card cheque-chart-panel">
          <Heading
            h="توزیع سررسید"
            p={
              incoming
                ? "زمان‌بندی وصول چک‌های دریافتی"
                : "زمان‌بندی پرداخت چک‌های صادرشده"
            }
          />
          {incoming && (
            <div className="due-average-summary">
              میانگین سررسید چک‌ها: <strong>{fa(Math.round(averageDueDays))} روز</strong>
            </div>
          )}
          <VerticalBars rows={due} />
        </article>
        <article
          className={`fd-panel cheque-side-note ${incoming ? "received" : "issued"}`}
        >
          <small>{incoming ? "Collection View" : "Payment View"}</small>
          <h3>
            {incoming
              ? "اولویت با وصول چک‌های معوق و نزدیک است."
              : source === "karamad" ? "این بخش فقط چک‌های پرداختی ثبت‌شده در آخرین فایل کارآمد را نشان می‌دهد." : "فقط چک‌های باز و سندنخورده باید در برنامه نقدینگی پوشش داده شوند."}
          </h3>
          <p>
            {incoming
              ? "چک‌های پرریسک و خارج از سیاست ۹۰ روز قبل از پذیرش اعتبار جدید بررسی شوند."
              : source === "karamad" ? "اطلاعات آینده کامل نیست و برگشتی هم فعلاً نداریم؛ بنابراین این سبد برای مشاهده ثبت‌هاست، نه برآورد کامل تعهدات آینده." : "با تغییر وضعیت راهکاران از بلندمدت به روز، چک سندخورده/برداشت‌شده محسوب و از Cash Flow آینده حذف می‌شود."}
          </p>
          <div>
            <span>{fa(soon.length)} فقره تا ۷ روز</span>
            <span>{fa(overdue.length)} فقره معوق</span>
          </div>
        </article>
      </section>
      <article className="fd-panel cheque-table-panel">
          <Heading
          h={incoming ? "ریز چک‌های دریافتی" : source === "karamad" ? "ریز چک‌های پرداختی ثبت‌شده" : "ریز چک‌های پرداختی باز"}
          p={incoming ? "فیلترشده بر اساس تاریخ سررسید؛ مرتب از نزدیک‌ترین موعد به دورترین موعد" : source === "karamad" ? "ثبت‌های موجود در آخرین فایل کارآمد؛ داده آینده ممکن است ناقص باشد" : "مرتب‌شده از سررسیدگذشته و نزدیک‌ترین موعد به دورترین موعد"}
        />
        <section className="cash-bank-toolbar cheque-list-search" ref={chatSearchRef}>
          <div>
            <b>{incoming ? "جست‌وجو در همه چک‌های دریافتی" : "جست‌وجو در همه چک‌های پرداختی"}</b>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="شماره سند، طرف حساب، شماره چک، صیاد، بانک یا مبلغ" />
          </div>
          <small>{fa(viewRows.length)} نتیجه از {fa(periodRows.length)} چکِ نمایش‌داده‌شده</small>
        </section>
        <div className="cheque-detail-table">
          <table>
            <thead>
              <tr>
                <th>طرف حساب</th>
                <th>ثبت در سیستم</th>
                <th>تاریخ حواله / سررسید</th>
                <th>شماره چک / سند</th>
                <th>مبلغ</th>
                <th>مدت چک</th>
                <th>زمان باقی‌مانده ↑</th>
                <th>بانک / شعبه</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((x, i) => {
                const d = daysToDue(x),
                  state =
                    d !== undefined && d < 0
                      ? "critical"
                      : d !== undefined && d <= 7
                        ? "danger"
                        : "safe";
                return (
                  <tr
                    key={x.cheque_id || x.cheque_item_id || i}
                    className={state}
                  >
                    <td>
                      <b>{x.counterpart_name || "طرف حساب نامشخص"}</b>
                    </td>
                    <td><RegCell x={x} fallback={x.registration_date_jalali || x.document_date_jalali} /></td>
                    {/* سررسید چک اول؛ تاریخ حواله فقط برای ردیف حواله (بدون سررسید). سرویس زنده کارآمد در
                        transfer_date_jalali تاریخ ثبت را می‌گذارد و نباید جای سررسید نمایش داده شود. */}
                    <td>{x.due_date_jalali || x.transfer_date_jalali || String(x.due_date || "").slice(0, 10) || "—"}</td>
                    <td><b>{chequeNo(x.serial_number || x.transfer_number)}</b>{x.document_number && String(x.document_number) !== String(x.serial_number)
                      ? <small className="customer-row-sub">سند {chequeNo(x.document_number)}</small> : null}</td>
                    <td>{fullToman(x.amount || 0)} تومان</td>
                    <td>
                      {(() => {
                        const term = x.term_days ?? chequeTermDays(x);
                        if (term == null) return "—";
                        // چک ممکن است بعد از سررسیدش در سیستم ثبت شده باشد (مثلاً چک قدیمی یا برگشتی ثبت دوباره).
                        return term < 0 ? `ثبت ${fa(-term)} روز بعد از سررسید` : `${fa(term)} روز`;
                      })()}
                    </td>
                    <td>
                      <span
                        className={`profile-due ${state === "critical" ? "late" : state === "danger" ? "soon" : "normal"}`}
                      >
                        {remainingLabel(x)}
                      </span>
                    </td>
                    <td>
                      {[x.bank_name, x.branch_name || x.bank_branch_name || x.branch]
                        .filter(Boolean)
                        .join(" / ") || "—"}
                    </td>
                    <td>
                      {incoming ? (
                        <span className={`cheque-business-status ${x.source_system === "rahkaran" ? "rahkaran" : "karamad"}`}>
                          {receivedChequeHoldingLabel(x)}
                          <small>
                            {[
                              x.source_system === "karamad" ? (x.cheque_status || x.state_label) : x.state_label,
                              x.source_system === "karamad" ? (x.last_operation_level4 || x.cheque_location) : undefined,
                            ].filter(Boolean).join(" · ") || (x.source_system === "rahkaran" ? "راهکاران" : "کارآمد")}
                          </small>
                        </span>
                      ) : x.source_system === "rahkaran" ? (
                        <span className={`cheque-business-status ${x.is_posted ? "karamad" : "rahkaran"}`}>
                          {x.state_label || (x.state_code === 28 ? "سند خورده / برداشت‌شده" : "باز / سند نخورده")}
                        </span>
                      ) : (
                        <span className="cheque-business-status karamad">ثبت‌شده در کارآمد<small>برگشتی: ندارد · آینده: ناقص</small></span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!viewRows.length && (
            <div className="profile-loading">چکی در این بخش پیدا نشد.</div>
          )}
        </div>
      </article>
    </>
  );
}
export function CustomerSqlAudit({ c }: { c: CustomerAudit }) {
  const rows = [
    {
      title: "کل چک‌های دریافتی",
      count: c.historical_cheque_count,
      amount: c.historical_total_cheque_amount,
      tone: "blue",
    },
    {
      title: "وصول‌شده قطعی",
      count: c.collected_cheque_count,
      amount: c.collected_cheque_amount,
      tone: "green",
    },
    {
      title: "چک‌های باز",
      count: c.open_cheque_count,
      amount: c.open_exposure,
      tone: "amber",
    },
    {
      title: "بازِ سررسیدگذشته",
      count: c.overdue_open_cheque_count,
      amount: c.overdue_open_amount,
      tone: "red",
    },
    {
      title: "برگشتی / واخواست‌شده",
      count: c.returned_cheque_count,
      amount: c.returned_cheque_amount,
      tone: "red",
    },
    {
      title: "سایر وضعیت‌ها",
      count: c.other_state_cheque_count,
      amount: c.other_state_cheque_amount,
      tone: "violet",
    },
  ];
  return (
    <section className="sql-audit">
      <div className="profile-section-title">
        <div>
          <h3>تطبیق کامل پرونده با SQL</h3>
          <p>تمام ستون‌های گزارش کنترلی؛ تمام مبالغ نمایشی به تومان</p>
        </div>
        <b>CounterPartRef: {fa(c.counterpart_ref)}</b>
      </div>
      <div className="audit-identity">
        <div>
          <small>کد مشتری</small>
          <b>{c.counterpart_code || "—"}</b>
        </div>
        <div>
          <small>نام مشتری</small>
          <b>{cname(c)}</b>
        </div>
        <div>
          <small>تعداد ردیف منبع</small>
          <b>{fa(c.source_row_count)}</b>
        </div>
        <div>
          <small>تعداد چک یکتا</small>
          <b>{fa(c.distinct_cheque_count)}</b>
        </div>
        <div
          className={(c.repeated_source_row_count || 0) > 0 ? "has-repeat" : ""}
        >
          <small>ردیف تکراری</small>
          <b>{fa(c.repeated_source_row_count)}</b>
        </div>
      </div>
      <div className="audit-status-grid">
        {rows.map((x, i) => (
          <article key={i} className={x.tone}>
            <header>
              <span>{x.title}</span>
              <b>{fa(x.count)} فقره</b>
            </header>
            <strong>{money(x.amount || 0)} تومان</strong>
            <small>بدون احتساب چک‌های تضمینی</small>
          </article>
        ))}
      </div>
      <div
        className={`audit-check ${(c.repeated_source_row_count || 0) === 0 ? "ok" : "warn"}`}
      >
        <i>{(c.repeated_source_row_count || 0) === 0 ? "✓" : "!"}</i>
        <span>
          <b>
            {(c.repeated_source_row_count || 0) === 0
              ? "تطبیق تعداد ردیف و چک یکتا برقرار است"
              : "ردیف تکراری در منبع مشاهده شد"}
          </b>
          <small>
            SourceRowCount: {fa(c.source_row_count)} • DistinctChequeCount:{" "}
            {fa(c.distinct_cheque_count)} • RepeatedSourceRowCount:{" "}
            {fa(c.repeated_source_row_count)}
          </small>
        </span>
      </div>
    </section>
  );
}
