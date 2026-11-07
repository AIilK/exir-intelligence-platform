// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (customer-profile).
import { useEffect, useState } from "react";
import { RegCell, chequeNo } from "../cheque-reg";
import { Heading, K, Risk, description, label } from "./agents";
import { CustomerSqlAudit } from "./cheques";
import { cname, daysToDue, fa, fullToman, money, policy, request, risk, textOf } from "./shared";
import type { CashDay, Customer, CustomerAudit } from "./types";

export function LegacyCustomerProfile({
  c,
  close,
  refresh,
}: {
  c: Customer;
  close: () => void;
  refresh: () => void;
}) {
  const [detail, setDetail] = useState<Customer>(c),
    [loadingDetail, setLoadingDetail] = useState(true),
    [detailError, setDetailError] = useState("");
  useEffect(() => {
    let active = true;
    if (!c.counterpart_ref) {
      setLoadingDetail(false);
      return;
    }
    request(`/customer-intelligence/${c.counterpart_ref}`)
      .then((j) => {
        if (active && j.customer) setDetail({ ...j.customer, karamad_activity: c.karamad_activity });
      })
      .catch((e) => {
        if (active)
          setDetailError(
            e instanceof Error ? e.message : "جزئیات چک‌ها دریافت نشد",
          );
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [c.counterpart_ref]);
  const create = async () => {
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        counterpart_ref: detail.counterpart_ref,
        counterpart_name: cname(detail),
        priority: risk(detail) === "critical" ? "critical" : "high",
      }),
    });
    refresh();
    close();
  };
  const kd: any = detail.karamad_activity?.detail || {};
  const ks: any = kd.summary || {};
  const total = (detail.historical_total_cheque_amount || 0) + (ks.received_cheque_amount_rial || 0),
    collected = detail.collected_cheque_amount || 0,
    open = (detail.open_exposure || 0) + (ks.received_cheque_future_amount_rial || 0) + (ks.received_cheque_overdue_amount_rial || 0) + (ks.received_cheque_today_amount_rial || 0),
    returned = (detail.returned_cheque_amount || 0) + (ks.received_cheque_returned_amount_rial || 0),
    returnedCount = Number(detail.returned_cheque_count || 0) + Number(ks.received_cheque_returned_count || 0),
    futureAmount = Number(detail.future_open_cheque_amount || 0) + Number(ks.received_cheque_future_amount_rial || 0),
    futureCount = Number(detail.future_open_cheque_count || 0) + Number(ks.received_cheque_future_count || 0),
    percent = total ? Math.min(100, (collected / total) * 100) : 0;
  return (
    <div className="fd-backdrop" onClick={close}>
      <article
        className="customer-profile-expanded"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="profile-close" onClick={close}>
          ×
        </button>
        <div className="profile-title">
          <div>
            <Risk x={risk(detail)} />
            <h2>{cname(detail)}</h2>
            <p>ریز سوابق وصول و وضعیت تک‌تک چک‌های دریافتی باز</p>
          </div>
          <span className="profile-source">SQL Server • اطلاعات لحظه‌ای</span>
        </div>
        {detailError && <div className="profile-warning">{detailError}</div>}
        <div className="modal-metrics profile-metrics">
          <K
            t="کل چک‌های دریافت‌شده"
            v={money(total)}
            n={`${fa(detail.historical_cheque_count || 0)} فقره • تومان`}
            c="blue"
          />
          <K
            t="وصول‌شده قطعی"
            v={money(collected)}
            n={`${fa(detail.collected_cheque_count || 0)} فقره • State=3`}
            c="teal"
          />
          <K
            t="چک‌های دریافتی باز"
            v={money(open)}
            n={`${fa(detail.open_cheque_count || 0)} فقره • تومان`}
            c="amber"
          />
          <K
            t="برگشتی/واخواست‌شده"
            v={money(returned)}
            n={`${fa(returnedCount)} فقره • تومان`}
            c="red"
          />
          <K
            t="چک‌های آینده"
            v={money(futureAmount)}
            n={`${fa(futureCount)} فقره • تومان`}
            c="blue"
          />
        </div>
        <section className="collection-progress">
          <header>
            <div>
              <b>نسبت وصول قطعی از کل سوابق</b>
              <small>
                مبلغ وصول‌شده تقسیم بر کل مبلغ چک‌های ثبت‌شده در بازه تحلیل
              </small>
            </div>
            <strong>{fa(percent)}٪</strong>
          </header>
          <div>
            <i style={{ width: `${percent}%` }} />
          </div>
          <footer>
            <span>وصول‌شده: {money(collected)} تومان</span>
            <span>هنوز باز: {money(open)} تومان</span>
          </footer>
        </section>
        <CustomerSqlAudit c={detail as CustomerAudit} />
        <div className="profile-bottom">
          <div>
            <h3>دلایل ارزیابی</h3>
            <ul>
              {[
                ...(detail.late_payment_risk?.reasons || []),
                ...(detail.evidence || []),
              ].map((x, i) => (
                <li key={i}>{textOf(x)}</li>
              ))}
            </ul>
          </div>
          <div className="credit-advice">
            <b>شرایط پیشنهادی چک بعدی</b>
            <span>
              {risk(detail) === "critical"
                ? "تا تأیید مدیر مالی و کاهش چک‌های سررسیدگذشته، چک جدید پذیرفته نشود."
                : risk(detail) === "danger"
                  ? "سررسید حداکثر ۹۰ روز و مبلغ محدود پذیرفته شود."
                  : "شرایط جاری با پایش ماهانه قابل ادامه است."}
            </span>
          </div>
        </div>
        <p className="profile-note">
          «وصول‌شده» براساس وضعیت قطعی چک در راهکاران است؛ این عدد لزوماً معادل
          تسویه کامل تمام فاکتورهای فروش مشتری نیست.
        </p>
        {detail.counterpart_ref ? <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button> : null}
      </article>
    </div>
  );
}
export function CashChart({ days }: { days: CashDay[] }) {
  let shown = days.filter(
      (_, i) => i % Math.max(1, Math.ceil(days.length / 15)) === 0,
    ),
    vals = shown.map((x) => x.projected_cash ?? x.cumulative_net_change ?? 0),
    min = Math.min(...vals, 0),
    max = Math.max(...vals, 1),
    range = max - min || 1,
    pts = vals
      .map(
        (v, i) =>
          `${20 + (i * 560) / Math.max(vals.length - 1, 1)},${175 - ((v - min) / range) * 135}`,
      )
      .join(" ");
  return days.length ? (
    <svg className="cash-chart" viewBox="0 0 600 210">
      <line
        x1="20"
        y1={175 - ((0 - min) / range) * 135}
        x2="580"
        y2={175 - ((0 - min) / range) * 135}
      />
      <polyline points={pts} />
      {vals.map((v, i) => (
        <circle
          key={i}
          cx={20 + (i * 560) / Math.max(vals.length - 1, 1)}
          cy={175 - ((v - min) / range) * 135}
          r="4"
          className={v < 0 ? "neg" : ""}
        />
      ))}
    </svg>
  ) : (
    <div className="fd-empty">داده نقدینگی هنوز دریافت نشده است.</div>
  );
}
export function CashFlowCompositionChart({ summary }: { summary: any }) {
  const rows = [
    { label: "وصول چک", value: Number(summary.reliable_received_cheques_rial || 0), tone: "#19a974" },
    { label: "چک پرداختی", value: Number(summary.issued_cheques_rial || 0), tone: "#f59e0b" },
    { label: "حقوق", value: Number(summary.salary_reserve_rial || 0), tone: "#ef4444" },
  ];
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <section className="cash-composition-chart">
      <b>ترکیب مهم‌ترین ورودی و خروجی‌های بازه</b>
      {rows.map((row) => <div key={row.label}>
        <span>{row.label}</span>
        <i><em style={{ width: `${(row.value / max) * 100}%`, background: row.tone }} /></i>
        <strong>{money(row.value)} تومان</strong>
      </div>)}
    </section>
  );
}
export function CashTable({ days }: { days: CashDay[] }) {
  return (
    <div className="cash-table-wrap">
      <table className="cash-table">
        <thead>
          <tr>
            <th>تاریخ</th>
            <th>چک دریافتی ≥۸۵٪</th>
            <th>چک پرداختی</th>
            <th>حقوق</th>
            <th>خالص روز</th>
            <th>مانده</th>
            <th>وضعیت</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d, i) => {
            let n = d.daily_net_change || 0,
              s = d.cash_shortage ? "critical" : n < 0 ? "pressure" : "good";
            return (
              <tr key={d.date || i} className={s}>
                <td>
                  <b>{d.date_jalali || d.date}</b>
                </td>
                <td className="positive">+ {money(d.reliable_received_cheques || 0)}</td>
                <td className="negative">− {money(d.issued_cheques_due || 0)}</td>
                <td className="negative">− {money(d.salary_reserve || 0)}</td>
                <td className={n < 0 ? "negative" : "positive"}>{money(n)}</td>
                <td>
                  {d.projected_cash == null
                    ? "تعریف نشده"
                    : money(d.projected_cash)}
                </td>
                <td>
                  <span className={`cash-status ${s}`}>
                    {s === "critical"
                      ? "کسری"
                      : s === "pressure"
                        ? "فشار نقدی"
                        : "مناسب"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
export const behaviorFa: Record<string, string> = {
  excellent: "بسیار خوش‌قول",
  good: "خوش‌قول",
  review: "نیازمند بررسی",
  weak: "بدقول",
  high_risk: "پرریسک",
  unknown: "در انتظار سابقه",
};
export const creditPolicyFa: Record<string, string> = {
  accept_normal: "پذیرش عادی",
  accept_with_monitoring: "پذیرش همراه با پایش",
  accept_with_guarantee: "پذیرش فقط با تضمین تکمیلی",
  manual_approval_required: "نیازمند تأیید مدیر مالی",
  review: "نیازمند بررسی",
};

export function ChequeReturnRisk({ risk }: { risk?: any }) {
  if (!risk) return <span className="cf-muted">—</span>;
  if (risk.state !== "open") return <span className={`cf-risk ${risk.state}`}>{risk.label}</span>;
  return <span className={`cf-risk ${risk.level}`} title={(risk.reasons || []).join("\n")}>
    <b>{fa(risk.probability_percent)}٪</b> {risk.label.replace("احتمال برگشت ", "")}
  </span>;
}

export function UnifiedCustomerActivityTables({ c }: { c: Customer }) {
  const kdetail: any = c.karamad_activity?.detail || {};
  const rahkaranChecks: any[] = ((c.all_cheques && c.all_cheques.length ? c.all_cheques : c.open_cheques) || []).map((x: any) => ({
    ...x,
    activity_type: /برگشت|واخواست/.test(String(x.state_label || "")) ? "چک برگشتی" : "چک دریافتی",
    source_system: "rahkaran",
    source_label: "راهکاران",
    cheque_number: x.serial_number || x.document_number || x.receipt_number,
    sayad_number: x.sayad_number,
    amount_rial: x.amount || 0,
    registration_date_jalali: x.receipt_date_jalali || x.receipt_date,
    due_date_jalali: x.due_date_jalali || x.due_date,
    cheque_status: x.state_label || "نامشخص",
    days_until_due: typeof x.days_to_due === "number" ? x.days_to_due : daysToDue(x),
    bank: x.bank_name,
    branch: x.bank_branch_name,
    description: x.description,
  }));
  // V146: all_cheques already contains returned historical rows.  Keep the old
  // returned endpoint only as a compatibility fallback for older API payloads.
  const rahkaranReturned: any[] = (c.all_cheques && c.all_cheques.length ? [] : (c.returned_cheques || [])).map((x: any) => ({
    ...x, activity_type: "چک برگشتی", source_system: "rahkaran", source_label: "راهکاران",
    cheque_number: x.serial_number || x.receipt_number, amount_rial: x.amount || 0, cheque_status: x.state_label || "برگشتی / واخواست‌شده",
  }));
  const karamadReceived: any[] = (kdetail.received_cheques || []).map((x: any) => ({ ...x, activity_type: "چک دریافتی" }));
  const karamadIssued: any[] = (kdetail.issued_cheques || []).map((x: any) => ({ ...x, activity_type: "چک پرداختی" }));
  // Oldest due date first; rows without any date go last.
  const chequeRows = [...rahkaranChecks, ...rahkaranReturned, ...karamadReceived, ...karamadIssued].sort((a, b) => {
    const da = String(a.due_date_jalali || a.registration_date_jalali || ""), db = String(b.due_date_jalali || b.registration_date_jalali || "");
    return !da ? (db ? 1 : 0) : !db ? -1 : da.localeCompare(db, "fa");
  });
  const transferRows = [
    ...(kdetail.received_transfers || []).map((x: any) => ({ ...x, activity_type: "حواله دریافتی" })),
    ...(kdetail.paid_transfers || []).map((x: any) => ({ ...x, activity_type: "حواله پرداختی" })),
  ].sort((a, b) => String(b.registration_date_jalali || b.transfer_date_jalali || "").localeCompare(String(a.registration_date_jalali || a.transfer_date_jalali || ""), "fa"));

  const [chequeScope, setChequeScope] = useState<"all" | "collected" | "returned" | "future" | "overdue" | "risk">("all");
  const [activitySearch, setActivitySearch] = useState("");
  const isReturnedCheque = (x: any) => /برگشت|واخواست|مسترد/.test(String(x.cheque_status || x.state_label || x.activity_type || ""));
  const chequeDay = (x: any) => typeof x.days_until_due === "number" ? x.days_until_due : daysToDue(x);
  const returnedRows = chequeRows.filter(isReturnedCheque);
  // return_risk (backend) knows the real final state; «در جریان وصول» is not collected.
  const collectedRows = chequeRows.filter((x: any) => x.return_risk ? x.return_risk.state === "collected" : /وصول‌?\s?شده/.test(String(x.cheque_status || x.state_label || "")));
  const riskRows = chequeRows.filter((x: any) => x.return_risk?.state === "open" && x.return_risk.level !== "low");
  // V162: a collected cheque is never overdue, whatever its historical due date.
  const isCollectedCheque = (x: any) => collectedRows.includes(x);
  const futureRows = chequeRows.filter((x: any) => { const d = chequeDay(x); return !isReturnedCheque(x) && !isCollectedCheque(x) && d !== undefined && d >= 0; });
  const overdueRows = chequeRows.filter((x: any) => { const d = chequeDay(x); return !isReturnedCheque(x) && !isCollectedCheque(x) && d !== undefined && d < 0; });
  // Rahkaran collected cheques (3 «وصول شده», 30 «نقد شده توسط مأمور وصول») are hidden from «کل چک‌ها»; they stay reachable via the «وصول‌شده» card.
  const isRahkaranCollected = (x: any) => x.source_system === "rahkaran" && (x.master_state === 3 || x.master_state === 30 || /^وصول[‌\s]?شده$/.test(String(x.cheque_status || "").trim()));
  const visibleChequeRows = chequeRows.filter((x: any) => !isRahkaranCollected(x));
  const scopeRows = chequeScope === "collected" ? collectedRows : chequeScope === "returned" ? returnedRows : chequeScope === "future" ? futureRows : chequeScope === "overdue" ? overdueRows : chequeScope === "risk" ? riskRows : visibleChequeRows;
  const q = activitySearch.trim().toLocaleLowerCase("fa-IR");
  const filteredChequeRows = !q ? scopeRows : scopeRows.filter((x: any) => [x.cheque_number, x.sayad_number, x.cheque_status, x.state_label, x.bank, x.bank_name, x.branch, x.description, x.return_reason, x.amount_rial].filter(Boolean).some((v) => String(v).toLocaleLowerCase("fa-IR").includes(q)));
  const filteredChequeAmount = filteredChequeRows.reduce((sum: number, x: any) => sum + Number(x.amount_rial || x.amount || 0), 0);

  const dueLabel = (x: any) => {
    const d = typeof x.days_until_due === "number" ? x.days_until_due : undefined;
    if (d === undefined) return "نامشخص";
    if (d < 0) return `${fa(Math.abs(d))} روز گذشته`;
    if (d === 0) return "امروز";
    return `${fa(d)} روز مانده`;
  };
  const dueClass = (x: any) => {
    const d = typeof x.days_until_due === "number" ? x.days_until_due : undefined;
    return d === undefined ? "unknown" : d < 0 ? "late" : d <= 7 ? "soon" : "normal";
  };

  return (
    <section className="unified-customer-activity">
      <div className="profile-section-title">
        <div>
          <h3>چک و سررسید این مشتری</h3>
          <p>همان الگوی صفحه چک و سررسید: جمع، فیلتر وضعیت/زمان، جستجو و سپس ریز کامل چک.</p>
        </div>
        <b>{fa(filteredChequeRows.length)} فقره · {fullToman(filteredChequeAmount)} تومان</b>
      </div>
      <section className="customer-cheque-scope-cards">
        {[
          ["all", "کل چک‌ها", visibleChequeRows],
          ["collected", "وصول‌شده", collectedRows],
          ["returned", "برگشتی / واخواست", returnedRows],
          ["future", "آینده", futureRows],
          ["overdue", "سررسیدگذشته", overdueRows],
          ["risk", "احتمال برگشت دارد", riskRows],
        ].map(([id, title, items]: any) => <button key={id} className={chequeScope === id ? "active" : ""} onClick={() => setChequeScope(id)}>
          <small>{title}</small><b>{fa(items.length)} فقره</b><span>{fullToman(items.reduce((sum: number, x: any) => sum + Number(x.amount_rial || x.amount || 0), 0))} تومان</span>
        </button>)}
      </section>
      <section className="cash-bank-toolbar cheque-list-search customer-activity-search">
        <div><b>جستجو در چک‌های مشتری</b><input value={activitySearch} onChange={(e) => setActivitySearch(e.target.value)} placeholder="شماره چک، صیاد، بانک، وضعیت، مبلغ یا توضیحات..." /></div>
        <small>{fa(filteredChequeRows.length)} نتیجه</small>
      </section>
      {filteredChequeRows.length ? <div className="profile-cheque-table"><table>
        <thead><tr><th>نوع</th><th>شماره چک</th><th>صیاد</th><th>مبلغ</th><th>ثبت در سیستم</th><th>سررسید</th><th>زمان سررسید</th><th>وضعیت</th><th>احتمال برگشت</th><th>بانک / شعبه</th><th>توضیحات</th><th>منبع</th></tr></thead>
        <tbody>{filteredChequeRows.map((x: any, i: number) => <tr key={`unified-cheque-${x.cheque_id || x.transfer_id || i}`} className={typeof x.days_until_due === "number" && x.days_until_due < 0 ? "overdue-row" : typeof x.days_until_due === "number" && x.days_until_due <= 7 ? "due-soon-row" : ""}>
          <td><b>{x.activity_type}</b></td>
          <td><b>{chequeNo(x.cheque_number || x.serial_number || x.transfer_number)}</b></td>
          <td>{chequeNo(x.sayad_number)}</td>
          <td><b>{fullToman(x.amount_rial || x.amount || 0)} تومان</b></td>
          <td><RegCell x={x} fallback={x.registration_date_jalali || x.receipt_date_jalali} /></td>
          <td>{x.due_date_jalali || x.effective_date_jalali || x.due_date || "—"}</td>
          <td><span className={`profile-due ${dueClass(x)}`}>{dueLabel(x)}</span></td>
          <td><span className={`cheque-business-status ${x.source_system === "rahkaran" ? "rahkaran" : "karamad"}`}>{x.cheque_status || x.state_label || "ثبت‌شده"}</span>{x.cheque_location ? <small className="customer-row-sub">{x.cheque_location}</small> : null}</td>
          <td><ChequeReturnRisk risk={x.return_risk} /></td>
          <td>{[x.bank || x.bank_name, x.branch || x.bank_branch_name || x.bank_and_branch].filter(Boolean).join(" / ") || "—"}</td>
          <td>{[x.purpose, x.description, x.return_reason].filter(Boolean).join(" — ") || "—"}</td>
          <td><span className={`source-badge ${x.source_system || "karamad"}`}>{x.source_label || (x.source_system === "rahkaran" ? "راهکاران" : "کارآمد")}</span></td>
        </tr>)}</tbody>
      </table></div> : <div className="profile-loading">ریز چک قابل نمایش برای این مشتری وجود ندارد.</div>}

      <div className="profile-section-title unified-transfer-title">
        <div>
          <h3>ریز حواله‌های مشتری</h3>
          <p>حواله‌های دریافتی و پرداختی ثبت‌شده در یک جدول جدا.</p>
        </div>
        <b>{fa(transferRows.length)} ردیف</b>
      </div>
      {transferRows.length ? <div className="profile-cheque-table"><table>
        <thead><tr><th>نوع</th><th>شماره حواله</th><th>تاریخ ثبت</th><th>تاریخ حواله</th><th>مبلغ</th><th>بانک</th><th>شعبه</th><th>بابت / توضیحات</th><th>منبع</th></tr></thead>
        <tbody>{transferRows.map((x: any, i: number) => <tr key={`unified-transfer-${x.transfer_id || i}`}>
          <td><b>{x.activity_type}</b></td>
          <td><b>{fa(x.transfer_number || x.document_number || x.transfer_id || "—")}</b></td>
          <td>{x.registration_date_jalali || "—"}</td>
          <td>{x.transfer_date_jalali || x.effective_date_jalali || "—"}</td>
          <td><b>{fullToman(x.amount_rial || 0)} تومان</b></td>
          <td>{x.bank || "—"}</td>
          <td>{x.branch || "—"}</td>
          <td>{[x.purpose, x.description].filter(Boolean).join(" — ") || "—"}</td>
          <td><span className="source-badge karamad">کارآمد</span></td>
        </tr>)}</tbody>
      </table></div> : <div className="profile-loading">ریز حواله ثبت‌شده برای این مشتری وجود ندارد.</div>}
    </section>
  );
}

export function CustomerReliability({ c }: { c: Customer }) {
  const behavior: any = c.customer_behavior || {},
    decision: any = c.credit_decision || {};
  const score = Math.max(
    0,
    Math.min(100, Number(behavior.reliability_score ?? 50)),
  );
  const collection = Math.max(
    0,
    Math.min(100, Number(behavior.historical_collection_rate_percent ?? 0)),
  );
  const returned = Math.max(
    0,
    Math.min(100, Number(behavior.historical_return_rate_percent ?? 0)),
  );
  const reliance = Math.max(
    0,
    Math.min(100, Number(decision.recommended_reliance_percent ?? 0)),
  );
  const tone = score >= 70 ? "#18a98b" : score >= 50 ? "#eea63b" : "#df6269";
  const confidence = behavior.history_confidence || "low";
  const policy = decision.policy || "review";
  const reasons = (decision.reasons || c.evidence || []).slice(0, 4);
  const breakdown = behavior.score_breakdown || [],
    improvements = decision.improvement_actions || [],
    calc = decision.reliance_calculation || {};
  return (
    <section className="reliability-panel">
      <div className="reliability-head">
        <div>
          <h3>سابقه خوش‌قولی و پیشنهاد اعتبار</h3>
          <p>تحلیل سابقه وصول، برگشت، چک‌های عقب‌افتاده و مبلغ تاریخی مشتری</p>
        </div>
        <span className={`history-confidence ${confidence}`}>
          اطمینان سابقه:{" "}
          {confidence === "high"
            ? "زیاد"
            : confidence === "medium"
              ? "متوسط"
              : "کم"}
        </span>
      </div>
      {c.data_source === "karamad" && c.karamad_activity && (
        <div className="karamad-summary">
          <div><span>شعبه‌های کارآمد</span><b>{(c.karamad_activity.branches || []).join("، ") || "—"}</b></div>
          <div><span>گردش کارآمد</span><b>{fa(c.karamad_activity.movement_count || 0)} ردیف</b></div>
          <div><span>چک دریافتی کارآمد</span><b>{fa(c.karamad_activity.received_cheque_count || 0)} فقره · {fullToman(c.karamad_activity.received_cheque_amount_rial || 0)} تومان</b></div>
          <div><span>حواله دریافتی کارآمد</span><b>{fa(c.karamad_activity.received_transfer_count || 0)} فقره · {fullToman(c.karamad_activity.received_transfer_amount_rial || 0)} تومان</b></div>
        </div>
      )}
      <div className="reliability-main">
        <div
          className="reliability-ring"
          style={{
            background: `conic-gradient(${tone} 0 ${score}%,#e6edef ${score}% 100%)`,
          }}
        >
          <span>
            <b>{fa(score)}</b>
            <small>امتیاز از ۱۰۰</small>
            <em style={{ color: tone }}>
              {behaviorFa[behavior.behavior_level || "unknown"] ||
                "نیازمند بررسی"}
            </em>
          </span>
        </div>
        <div className="reliability-bars">
          <div className="reliability-bar collection">
            <header>
              <span>نرخ وصول تاریخی</span>
              <b>{fa(collection)}٪</b>
            </header>
            <div>
              <i style={{ width: `${collection}%` }} />
            </div>
          </div>
          <div className="reliability-bar return">
            <header>
              <span>نرخ برگشت تاریخی</span>
              <b>{fa(returned)}٪</b>
            </header>
            <div>
              <i style={{ width: `${returned}%` }} />
            </div>
          </div>
          <div className="reliability-bar reliance">
            <header>
              <span>درصد پیشنهادی اتکا به چک</span>
              <b>{fa(reliance)}٪</b>
            </header>
            <div>
              <i style={{ width: `${reliance}%` }} />
            </div>
          </div>
        </div>
      </div>
      <div className="credit-decision-grid">
        <div
          className={`policy ${policy === "manual_approval_required" ? "block" : policy === "accept_with_guarantee" ? "review" : ""}`}
        >
          <small>سیاست پیشنهادی پذیرش چک</small>
          <b>{creditPolicyFa[policy] || "نیازمند بررسی"}</b>
        </div>
        <div>
          <small>سقف پیشنهادی چک جدید</small>
          <b>
            {decision.recommended_max_new_cheque_amount_rial == null
              ? "پس از تکمیل سابقه تعیین می‌شود"
              : `${fullToman(decision.recommended_max_new_cheque_amount_rial)} تومان`}
          </b>
        </div>
        <div>
          <small>سوابق قطعی بررسی‌شده</small>
          <b>{fa(behavior.resolved_cheque_count || 0)} فقره</b>
        </div>
      </div>
      {reasons.length > 0 && (
        <div className="reliability-reasons">
          <b>چرا این پیشنهاد ساخته شده است؟</b>
          <ul>
            {reasons.map((x, i) => (
              <li key={i}>{textOf(x)}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="reliance-explanation">
        <section>
          <b>این درصد دقیقاً چگونه ساخته شد؟</b>
          <p>{behavior.score_explanation}</p>
          <div className="score-components">
            {breakdown.map((x: any, i: number) => (
              <div key={i}>
                <span>{x.title}</span>
                <b>{fa(x.observed_percent)}٪</b>
                <small>
                  وزن {fa(x.weight_percent)}٪ • سهم امتیاز{" "}
                  {fa(x.score_contribution)}
                </small>
              </div>
            ))}
          </div>
          <div className="reliance-formula">
            <span>
              {calc.formula_fa || "نرخ وصول مورد انتظار × ضریب اطمینان سابقه"}
            </span>
            <b>
              {fa(calc.expected_collection_rate_percent || 0)}٪ ×{" "}
              {fa(calc.history_confidence_factor_percent || 0)}٪ ={" "}
              {fa(calc.final_reliance_percent ?? reliance)}٪
            </b>
          </div>
        </section>
        <section className="improvement-list">
          <b>برای بهترشدن امتیاز چه کار کنیم؟</b>
          {improvements.map((x: any, i: number) => (
            <article key={i}>
              <i>{fa(i + 1)}</i>
              <div>
                <strong>{x.action}</strong>
                <p>{x.why}</p>
                <small>اثر مورد انتظار: {x.expected_improvement}</small>
              </div>
            </article>
          ))}
        </section>
      </div>
      <div className="reliability-note">
        این امتیاز تصمیم‌یار است و جایگزین تأیید مدیر مالی نیست. سابقه کم، سطح
        اطمینان و درصد اتکا را کاهش می‌دهد.
      </div>
    </section>
  );
}

export function customerFilePath(c: Customer): string | null {
  if (c.data_source === "rahkaran" && c.counterpart_ref) return `/customer-file/rahkaran/${c.counterpart_ref}`;
  const dlRefs = c.karamad_activity?.dl_refs || c.karamad_activity?.detail?.account_position?.dl_refs || [];
  if (c.data_source === "karamad" && dlRefs.length) return `/customer-file/karamad?dl_refs=${dlRefs.join(",")}`;
  return null;
}

export function LastInvoicesTable({ invoices, showVisitor = false }: { invoices: any[]; showVisitor?: boolean }) {
  return <div className="cf-table"><table>
    <thead><tr><th>شماره فاکتور</th><th>تاریخ</th>{showVisitor && <th>ویزیتور</th>}<th>مبلغ فروش</th><th>مانده بدهی</th><th>جریان وصول</th></tr></thead>
    <tbody>{invoices.map((inv) => {
      const pct = Math.max(0, Math.min(100, Number(inv.collected_percent ?? 0)));
      return <tr key={inv.invoice_id}>
        <td><b>{/^\d+$/.test(inv.number || "") ? Number(inv.number).toLocaleString("fa-IR", { useGrouping: false }) : inv.number || "—"}</b></td>
        <td>{inv.date_jalali || "—"}</td>
        {showVisitor && <td>{inv.visitor_name || "—"}</td>}
        <td><b>{fullToman(inv.amount_rial || 0)}</b><small>تومان</small></td>
        <td className={Number(inv.remaining_rial || 0) > 0 ? "cf-debt" : "cf-settled"}>{inv.remaining_rial == null ? "نامشخص" : Number(inv.remaining_rial) > 0 ? `${fullToman(inv.remaining_rial)} تومان` : "تسویه شده"}</td>
        <td className="cf-flow">
          {inv.collected_percent == null ? "—" : <>
            <div className="cf-bar"><i style={{ width: `${pct}%` }} /></div>
            <small>{fa(pct)}٪ وصول شده · {fullToman(inv.collected_rial || 0)} تومان</small>
            {(inv.collection_breakdown || []).length > 0 && <div className="cf-chips">{inv.collection_breakdown.map((b: any) => <span key={b.method}>{b.method}: {fullToman(b.amount_rial)}</span>)}</div>}
          </>}
        </td>
      </tr>;
    })}</tbody>
  </table></div>;
}

// Rahkaran: invoices still (partly) unpaid long after issue. Remaining per invoice is the FIFO share
// of the customer's balance (Rahkaran has no per-invoice settlement).
export function OldOpenInvoices({ invoices }: { invoices: any[] }) {
  const [days, setDays] = useState(60);
  const [open, setOpen] = useState(false);
  const old = invoices.filter((x) => Number(x.age_days || 0) > days).sort((a, b) => Number(b.age_days) - Number(a.age_days));
  const remaining = old.reduce((s, x) => s + Number(x.remaining_rial || 0), 0);
  return <section className="cf-section">
    <div className="cf-title">
      <div><h3>فاکتورهای باز قدیمی</h3><p>فاکتورهایی که بیش از {fa(days)} روز از صدورشان گذشته و هنوز بخشی از مبلغشان باز است (مانده حساب مشتری به ترتیب به جدیدترین فاکتورها تخصیص داده شده).</p></div>
      <div className="distribution-controls"><label>قدیمی‌تر از: <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
        {[30, 60, 90, 180].map((d) => <option key={d} value={d}>{fa(d)} روز</option>)}
      </select></label></div>
    </div>
    <div className="cf-kpis">
      <article className={`cf-accent-red${old.length ? " cf-kpi-clickable" : ""}${open ? " active" : ""}`} role="button" tabIndex={0}
        onClick={() => old.length && setOpen((v) => !v)} onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && old.length) { e.preventDefault(); setOpen((v) => !v); } }}>
        <small>فاکتور باز بیش از {fa(days)} روز</small><b>{fa(old.length)} فاکتور</b>
        <span>{fullToman(remaining)} تومان مانده</span>
        {old.length > 0 && <em>{open ? "بستن ▲" : "مشاهده فاکتورها ▼"}</em>}
      </article>
      <article><small>قدیمی‌ترین فاکتور باز</small><b>{old.length ? old[0].date_jalali : "—"}</b><span>{old.length ? `${fa(old[0].age_days)} روز پیش` : "فاکتور باز قدیمی ندارد"}</span></article>
    </div>
    {open && old.length > 0 && <div className="cf-table distribution-scroll"><table>
      <thead><tr><th>شماره فاکتور</th><th>تاریخ</th><th>گذشته</th><th>مبلغ فاکتور (تومان)</th><th>مانده (تومان)</th><th>درصد باز</th></tr></thead>
      <tbody>{old.map((x) => <tr key={x.invoice_id}>
        <td><b>{x.number || "—"}</b></td><td>{x.date_jalali || "—"}</td>
        <td className="cf-debt">{fa(x.age_days)} روز</td>
        <td>{fullToman(x.amount_rial)}</td>
        <td className="cf-debt"><b>{fullToman(x.remaining_rial)}</b></td>
        <td>{x.amount_rial ? `${fa(Math.round((x.remaining_rial / x.amount_rial) * 100))}٪` : "—"}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

export function CustomerFileOverview({ c }: { c: Customer }) {
  const path = customerFilePath(c);
  const [file, setFile] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!path) return;
    let active = true;
    setFile(null); setError("");
    request(path)
      .then((d) => { if (active) setFile(d); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "دریافت فاکتورهای مشتری ناموفق بود"); });
    return () => { active = false; };
  }, [path]);

  if (!path) return <div className="profile-warning">شناسه این مشتری برای خواندن فاکتورها پیدا نشد.</div>;
  if (error) return <div className="profile-warning">{error}</div>;
  if (!file) return <div className="profile-loading">در حال دریافت فاکتورهای خرید مشتری...</div>;

  const s = file.purchase_stats || {};
  const cy = file.current_year_label || "سال جاری";
  const py = file.previous_year_label || "سال قبل";
  const network = file.sales_network || {};
  const invoices: any[] = file.last_invoices || [];
  return (
    <>
      <section className="cf-section">
        <div className="cf-title">
          <div><h3>خرید مشتری</h3><p>{file.source === "karamad" ? "فاکتورهای فروش کارآمد (tblFactorF)" : "فاکتورهای فروش قطعی راهکاران (SLS3.Invoice)"}</p></div>
          {s.last_invoice_date_jalali && <small>آخرین فاکتور: {s.last_invoice_date_jalali}</small>}
        </div>
        <div className="cf-kpis">
          <article><small>تعداد کل فاکتور خرید</small><b>{fa(s.invoice_count || 0)}</b><span>از {s.first_invoice_date_jalali || "—"}</span></article>
          <article><small>کل مبلغ خرید تا امروز</small><b>{fullToman(s.purchase_amount_rial || 0)}</b><span>تومان</span></article>
          <article><small>تعداد فاکتور خرید {cy}</small><b>{fa(s.current_year_invoice_count || 0)}</b><span>{fullToman(s.current_year_amount_rial || 0)} تومان</span></article>
          <article><small>تعداد فاکتور خرید {py}</small><b>{fa(s.previous_year_invoice_count || 0)}</b><span>{fullToman(s.previous_year_amount_rial || 0)} تومان</span></article>
        </div>
        {Number(s.draft_invoice_count || 0) > 0 && <small className="cf-note">{fa(s.draft_invoice_count)} فاکتور پیش‌نویس/غیرقطعی راهکاران در این آمار شمرده نشده است.</small>}
      </section>

      <OldOpenInvoices invoices={file.open_invoices || []} />

      {/* Rahkaran customers buy directly from the company; only Karamad sales go through visitors. */}
      {file.source === "karamad" && <section className="cf-section">
        <div className="cf-title">
          <div><h3>فروش ویزیتور</h3><p>هیبرید ← سرپرست ← ویزیتوری که به این مشتری فروخته است</p></div>
        </div>
        {network.visitors?.length ? <div className="cf-table"><table>
          <thead><tr><th>ویزیتور</th><th>شعبه</th><th>سرپرست</th><th>هیبرید من</th><th>فروش ویزیتور {cy}</th><th>فروش ویزیتور {py}</th><th>خرید این مشتری از او {cy}</th><th>خرید این مشتری از او {py}</th><th>آخرین فاکتور</th></tr></thead>
          <tbody>{network.visitors.map((v: any) => <tr key={v.visitor_id}>
            <td><b>{v.visitor_name || "—"}</b>{!v.active && <small className="cf-muted">غیرفعال</small>}</td>
            <td>{v.branch || "—"}</td>
            <td>{v.supervisor || "—"}</td>
            <td className="cf-wrap">{(v.hybrids || []).join("، ") || "—"}</td>
            <td><b>{fullToman(v.visitor_sales_current_year_rial || 0)}</b><small>{fa(v.visitor_invoice_count_current_year || 0)} فاکتور</small></td>
            <td><b>{fullToman(v.visitor_sales_previous_year_rial || 0)}</b><small>{fa(v.visitor_invoice_count_previous_year || 0)} فاکتور</small></td>
            <td>{fullToman(v.customer_sales_current_year_rial || 0)}</td>
            <td>{fullToman(v.customer_sales_previous_year_rial || 0)}</td>
            <td>{v.last_invoice_date_jalali || "—"}</td>
          </tr>)}</tbody>
        </table></div> : <div className="invoice-source-pending">{network.note || "برای این مشتری ویزیتوری ثبت نشده است."}</div>}
      </section>}

      <section className="cf-section">
        <div className="cf-title">
          <div><h3>۵ فاکتور آخر {cy}</h3><p>{file.remaining_note}</p></div>
        </div>
        {invoices.length ? <LastInvoicesTable invoices={invoices} /> : <div className="invoice-source-pending">این مشتری در {cy} فاکتور خرید ندارد.</div>}
      </section>
    </>
  );
}

export function CustomerReceivables({ detail }: { detail: Customer }) {
  const isKaramad = detail.data_source === "karamad";
  const kd: any = detail.karamad_activity?.detail || {};
  const ap: any = (isKaramad ? kd.account_position : detail.account_position) || {};
  const cp: any = (isKaramad ? kd.collection_position : detail.collection_position) || {};
  if (!ap.found && !cp.total_collection_exposure_rial) return null;
  const breakdown: any[] = ap.account_breakdown || [];
  const monthly: any[] = isKaramad ? kd.monthly_summary || [] : [];
  const ledger: any[] = isKaramad ? kd.ledger_entries || [] : [];
  return (
    <section className="cf-section">
      <div className="cf-title">
        <div><h3>مطالبات مشتری</h3><p>{isKaramad ? "مانده از دفتر کل کارآمد (tblVoucherLines) سال مالی جاری روی تفصیلی مشتری" : "مانده از گردش سند سال مالی روی حساب‌های دریافتنی تجاری، برگشتی و اشخاص"}</p></div>
        <span className={`collection-account-state ${ap.balance_status || "unknown"}`}>{ap.balance_status === "debtor" ? "بدهکار" : ap.balance_status === "creditor" ? "بستانکار" : ap.balance_status === "settled" ? "تسویه" : "فاقد حساب"}</span>
      </div>
      <div className="cf-kpis">
        <article className="cf-accent-red"><small>مانده بدهی فعلی</small><b>{fullToman(cp.open_account_receivable_rial || 0)}</b><span>تومان • بدون چک</span></article>
        <article><small>چک باز در دست شرکت</small><b>{fullToman(cp.open_cheque_amount_rial || 0)}</b><span>تومان</span></article>
        <article><small>کل مطالبات درگیر وصول</small><b>{fullToman(cp.total_collection_exposure_rial || 0)}</b><span>مانده + چک باز</span></article>
        <article><small>پوشش با چک</small><b>{fa(cp.cheque_coverage_percent || 0)}٪</b><span>{fa(cp.uncovered_percent || 0)}٪ بدون چک</span></article>
        {Number(cp.customer_credit_rial || 0) > 0 && <article><small>بستانکاری مشتری</small><b>{fullToman(cp.customer_credit_rial)}</b><span>تومان</span></article>}
      </div>
      {breakdown.length > 0 && <div className="cf-table"><table>
        <thead><tr><th>حساب</th><th>بدهکار</th><th>بستانکار</th><th>مانده</th></tr></thead>
        <tbody>{breakdown.map((a: any, i: number) => <tr key={`${a.account_id}-${i}`}><td>{a.account_name || a.sl_title || a.account_id}</td><td>{fullToman(a.debit_balance_rial || 0)}</td><td>{fullToman(a.credit_balance_rial || 0)}</td><td><b>{fullToman(a.balance_rial || 0)}</b></td></tr>)}</tbody>
      </table></div>}
      {monthly.length > 0 && <details className="cf-details"><summary>خلاصه ماهانه حساب ({fa(monthly.length)} ماه)</summary><div className="cf-table"><table>
        <thead><tr><th>ماه</th><th>بدهکار</th><th>بستانکار</th><th>مانده پایان ماه</th><th>تعداد تراکنش</th></tr></thead>
        <tbody>{monthly.map((m: any) => <tr key={m.jalali_month}><td>{m.jalali_month}</td><td>{fullToman(m.debit_rial || 0)}</td><td>{fullToman(m.credit_rial || 0)}</td><td>{fullToman(m.closing_balance_rial || 0)}</td><td>{fa(m.transaction_count || 0)}</td></tr>)}</tbody>
      </table></div></details>}
      {ledger.length > 0 && <details className="cf-details"><summary>ریز گردش حساب ({fa(ledger.length)} ردیف)</summary><div className="cf-table"><table>
        <thead><tr><th>تاریخ</th><th>شعبه</th><th>معین</th><th>بدهکار</th><th>بستانکار</th><th>مانده تجمعی</th><th>شرح</th></tr></thead>
        <tbody>{ledger.map((e: any, i: number) => <tr key={e.voucher_ref || i}><td>{e.date_jalali || e.date || "—"}</td><td>{e.branch_name || "—"}</td><td>{e.sl_name || "—"}</td><td>{fullToman(e.debit_rial || 0)}</td><td>{fullToman(e.credit_rial || 0)}</td><td>{fullToman(e.running_balance_rial || 0)}</td><td className="cf-wrap">{e.description || "—"}</td></tr>)}</tbody>
      </table></div></details>}
    </section>
  );
}

export function CustomerProfile({
  c,
  close,
  refresh,
  embedded = false,
}: {
  c: Customer;
  close: () => void;
  refresh: () => void;
  embedded?: boolean;
}) {
  const [detail, setDetail] = useState<Customer>(c);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState("");
  const [predictionWarning, setPredictionWarning] = useState("");
  useEffect(() => {
    let active = true;
    setLoadingDetail(true);
    const jobs: Promise<any>[] = [];
    const kinds: string[] = [];
    if (c.data_source === "rahkaran" && c.counterpart_ref) {
      jobs.push(request(`/customer-intelligence/${c.counterpart_ref}`)); kinds.push("detail");
      jobs.push(request(`/predictions/customers/${c.counterpart_ref}`)); kinds.push("prediction");
    }
    const customerName = cname(c);
    if (c.data_source === "karamad" && customerName) {
      const params = new URLSearchParams({ customer_name: customerName });
      const selectedBranch = c.karamad_activity?.selected_branch;
      if (selectedBranch) params.set("branch", selectedBranch);
      jobs.push(request(`/karamad-manual/customer-detail?${params.toString()}`)); kinds.push("karamad");
    }
    Promise.allSettled(jobs)
      .then((results) => {
        if (!active) return;
        let detailResult: any = undefined;
        let predictionResult: any = undefined;
        let karamadDetail: any = undefined;
        results.forEach((result, index) => {
          const kind = kinds[index];
          if (result.status === "fulfilled") {
            if (kind === "detail") detailResult = result.value?.customer;
            if (kind === "prediction") predictionResult = result.value?.customers?.[0] || result.value?.customer;
            if (kind === "karamad") karamadDetail = result.value;
          } else if (kind === "detail") {
            setDetailError(result.reason instanceof Error ? result.reason.message : "جزئیات چک‌های راهکاران دریافت نشد");
          } else if (kind === "prediction") {
            setPredictionWarning("تحلیل خوش‌قولی راهکاران دریافت نشد.");
          }
        });
        setDetail((previous) => ({
          ...previous,
          ...detailResult,
          ...predictionResult,
          open_cheques: detailResult?.open_cheques || previous.open_cheques,
          karamad_activity: { ...(previous.karamad_activity || {}), detail: karamadDetail },
        }));
      })
      .finally(() => { if (active) setLoadingDetail(false); });
    return () => { active = false; };
  }, [c.counterpart_ref, c.customer_name, c.counterpart_name, c.data_source, c.karamad_activity?.selected_branch]);
  const create = async () => {
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        counterpart_ref: detail.counterpart_ref,
        counterpart_name: cname(detail),
        priority: risk(detail) === "critical" ? "critical" : "high",
      }),
    });
    refresh();
    close();
  };
  const kd: any = detail.karamad_activity?.detail || {};
  const ks: any = kd.summary || {};
  const total = (detail.historical_total_cheque_amount || 0) + (ks.received_cheque_amount_rial || 0),
    collected = detail.collected_cheque_amount || 0,
    open = (detail.open_exposure || 0) + (ks.received_cheque_future_amount_rial || 0) + (ks.received_cheque_overdue_amount_rial || 0) + (ks.received_cheque_today_amount_rial || 0),
    returned = (detail.returned_cheque_amount || 0) + (ks.received_cheque_returned_amount_rial || 0),
    returnedCount = Number(detail.returned_cheque_count || 0) + Number(ks.received_cheque_returned_count || 0),
    futureAmount = Number(detail.future_open_cheque_amount || 0) + Number(ks.received_cheque_future_amount_rial || 0),
    futureCount = Number(detail.future_open_cheque_count || 0) + Number(ks.received_cheque_future_count || 0),
    percent = total ? Math.min(100, (collected / total) * 100) : 0;
  const content = (
      <article className={`customer-profile-expanded ${embedded ? "customer-profile-page" : ""}`} onClick={(e) => e.stopPropagation()}>
        {embedded ? <button className="cheque-back customer-profile-back" onClick={close}>→ بازگشت به فهرست مشتریان</button> : <button className="profile-close" onClick={close}>×</button>}
        <div className="profile-title">
          <div>
            {detail.counterpart_ref ? <Risk x={risk(detail)} /> : <span className="fd-badge safe">دارای سابقه</span>}
            <h2>{cname(detail)}</h2>
            <p>خرید، ویزیتور، ۵ فاکتور آخر، مطالبات، چک‌ها و احتمال برگشت — از منبع انتخاب‌شده</p>
          </div>
          <span className="profile-source">{detail.data_source === "karamad" ? "کارآمد" : "راهکاران"}</span>
        </div>
        {detailError && <div className="profile-warning">{detailError}</div>}
        {predictionWarning && (
          <div className="profile-prediction-warning">{predictionWarning}</div>
        )}
        <CustomerFileOverview c={detail} />
        <CustomerReceivables detail={detail} />
        <div className="cf-title cf-cheques-title">
          <div><h3>چک‌های مشتری</h3><p>کل سوابق چک، وصول، برگشتی و احتمال برگشت چک‌های باز</p></div>
          {loadingDetail && <small>در حال دریافت ریز چک‌ها...</small>}
        </div>
        <div className="modal-metrics profile-metrics">
          <K
            t="کل چک‌های دریافت‌شده"
            v={fullToman(total)}
            n={`${fa(detail.historical_cheque_count || 0)} فقره • تومان`}
            c="blue"
          />
          <K
            t="وصول‌شده قطعی"
            v={fullToman(collected)}
            n={`${fa(detail.collected_cheque_count || 0)} فقره`}
            c="teal"
          />
          <K
            t="چک‌های دریافتی باز"
            v={fullToman(open)}
            n={`${fa(detail.open_cheque_count || 0)} فقره • تومان`}
            c="amber"
          />
          <K
            t="برگشتی/واخواست‌شده"
            v={fullToman(returned)}
            n={`${fa(returnedCount)} فقره • تومان`}
            c="red"
          />
          <K
            t="چک‌های آینده"
            v={fullToman(futureAmount)}
            n={`${fa(futureCount)} فقره • تومان`}
            c="blue"
          />
        </div>
        <section className="collection-progress">
          <header>
            <div>
              <b>نسبت وصول قطعی از کل سوابق</b>
              <small>مبلغ وصول‌شده تقسیم بر کل مبلغ چک‌های ثبت‌شده</small>
            </div>
            <strong>{fa(percent)}٪</strong>
          </header>
          <div>
            <i style={{ width: `${percent}%` }} />
          </div>
          <footer>
            <span>وصول‌شده: {fullToman(collected)} تومان</span>
            <span>هنوز باز: {fullToman(open)} تومان</span>
          </footer>
        </section>
        <UnifiedCustomerActivityTables c={detail} />
        {detail.counterpart_ref ? <CustomerReliability c={detail} /> : null}
        {detail.data_source === "rahkaran" && detail.b2b_remittances ? <section className="customer-b2b-detail">
          <Heading h="حواله‌ها و واریزهای B2B این مشتری" p="این داده‌ها علاوه بر نمایش، در ارزیابی رفتار مالی مشتری نیز لحاظ شده‌اند." />
          <div className="modal-metrics b2b-kpis">
            <K t="کل حواله B2B" v={fa(detail.b2b_remittances.count || 0)} n={fullToman(detail.b2b_remittances.amount_rial || 0) + " تومان"} c="blue" />
            <K t="واریز مستقیم" v={fa(detail.b2b_remittances.direct_count || 0)} n={fullToman(detail.b2b_remittances.direct_amount_rial || 0) + " تومان"} c="teal" />
            <K t="تسویه برگشتی" v={fa(detail.b2b_remittances.returned_cheque_settlement_count || 0)} n={`${fa(detail.b2b_remittances.returned_settlement_ratio_percent || 0)}٪ از مبلغ`} c="amber" />
            <K t="میانگین حواله" v={fullToman(detail.b2b_remittances.average_amount_rial || 0)} n="تومان" c="blue" />
          </div>
          <div className="b2b-table-wrap"><table><thead><tr><th>تاریخ</th><th>رسید</th><th>حواله</th><th>مبلغ (تومان)</th><th>بانک/شعبه</th><th>نوع</th><th>شرح</th></tr></thead><tbody>
          {(detail.b2b_remittances.rows || []).map((x:any)=><tr key={x.receipt_deposit_id}><td>{x.deposit_date_jalali || String(x.deposit_date||"").slice(0,10)}</td><td>{x.receipt_number || "—"}</td><td>{x.deposit_number || "—"}</td><td>{fullToman(Number(x.amount_rial||0))}</td><td>{x.bank_branch_name || `حساب ${x.bank_account_ref || "—"}`}</td><td><span className="b2b-category">{x.category}</span></td><td className="b2b-desc">{x.description || "—"}</td></tr>)}
          </tbody></table></div>
        </section> : null}
        {detail.counterpart_ref ? <CustomerSqlAudit c={detail as CustomerAudit} /> : null}
        <div className="profile-bottom">
          <div>
            <h3>دلایل ارزیابی</h3>
            <ul>
              {[
                ...(detail.late_payment_risk?.reasons || []),
                ...(detail.evidence || []),
              ].map((x, i) => (
                <li key={i}>{textOf(x)}</li>
              ))}
            </ul>
          </div>
          <div className="credit-advice">
            <b>شرایط پیشنهادی چک بعدی</b>
            <span>
              {creditPolicyFa[detail.credit_decision?.policy || ""] ||
                "برای این مشتری هنوز پیشنهاد اعتباری کامل ثبت نشده است."}
            </span>
          </div>
        </div>
        <p className="profile-note">
          این پرونده فقط از منبع انتخاب‌شده نمایش داده می‌شود تا تعداد، مبلغ و ریز چک‌های برگشتی و آینده با منبع دیگر مخلوط نشود.
        </p>
        {detail.counterpart_ref ? <button className="create-case" onClick={create}>
          ایجاد پرونده وصول برای این مشتری
        </button> : null}
      </article>
  );
  return embedded ? content : <div className="fd-backdrop" onClick={close}>{content}</div>;
}
