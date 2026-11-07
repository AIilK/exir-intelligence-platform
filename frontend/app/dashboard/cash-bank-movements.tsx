// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (cash-bank-movements).
import { useCallback, useEffect, useRef, useState } from "react";
import { Heading, K, label } from "./agents";
import { API, fa, fullToman, money, request, treasuryMutation, treasuryRequest } from "./shared";
import type { AgentResult } from "./types";

export function CashBankMovements({ agent }: { agent?: AgentResult }) {
  const movementRequestId = useRef(0);
  const [period, setPeriod] = useState("month"),
    [approval, setApproval] = useState("approved"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [offset, setOffset] = useState(0),
    [report, setReport] = useState<any>(null),
    [transfers, setTransfers] = useState<any>(null),
    [pettyCash, setPettyCash] = useState<any>(null),
    [commitments, setCommitments] = useState<any>(null),
    [karamad, setKaramad] = useState<any>(null),
    [karamadFolder, setKaramadFolder] = useState<any>(null),
    [karamadFile, setKaramadFile] = useState<File | null>(null),
    [karamadMonth, setKaramadMonth] = useState(""),
    [karamadSearch, setKaramadSearch] = useState(""),
    [movementSearchInput, setMovementSearchInput] = useState(""),
    [movementSearch, setMovementSearch] = useState(""),
    [karamadBranch, setKaramadBranch] = useState(""),
    [branchFilter, setBranchFilter] = useState(""),
    [sourceFilter, setSourceFilter] = useState("all"),
    [karamadMessage, setKaramadMessage] = useState(""),
    [tab, setTab] = useState<"movements" | "transfers" | "petty" | "commitments" | "karamad">("movements"),
    [busy, setBusy] = useState(false),
    [decisionBusy, setDecisionBusy] = useState<number | null>(null),
    [decisionMessage, setDecisionMessage] = useState(""),
    [error, setError] = useState("");
  const limit = 500;
  const loadMovements = useCallback(async () => {
    const requestId = ++movementRequestId.current;
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const dates =
        period === "custom" ? `&date_from=${from}&date_to=${to}` : "";
      const branchParam = branchFilter ? `&branch=${encodeURIComponent(branchFilter)}` : "";
      const searchParam = movementSearch.trim() ? `&search=${encodeURIComponent(movementSearch.trim())}` : "";
      const [movementResult, transferResult, pettyResult, commitmentResult] = await Promise.all([
        treasuryRequest(
          `/cash-bank/movements?period=${period}&approval_status=all&source=${sourceFilter}&limit=${limit}&offset=${offset}${dates}${branchParam}${searchParam}`,
        ),
        sourceFilter === "karamad" || branchFilter ? Promise.resolve(null) : treasuryRequest(
          `/cash-bank/transfers?period=${period}&limit=${limit}&offset=${offset}${dates}`,
        ),
        sourceFilter === "karamad" || branchFilter ? Promise.resolve(null) : treasuryRequest(
          `/cash-bank/petty-cash?period=${period}&limit=${limit}&offset=${offset}${dates}`,
        ),
        treasuryRequest(`/cash-bank/commitments?horizon_days=365&limit=${limit}&offset=0`),
      ]);
      if (requestId !== movementRequestId.current) return;
      setReport(movementResult);
      setTransfers(transferResult);
      setPettyCash(pettyResult);
      setCommitments(commitmentResult);
    } catch (e) {
      if (requestId !== movementRequestId.current) return;
      setError(
        e instanceof Error ? e.message : "دریافت گردش نقد و حواله ناموفق بود",
      );
    } finally {
      if (requestId === movementRequestId.current) setBusy(false);
    }
  }, [period, approval, from, to, offset, branchFilter, sourceFilter, movementSearch]);
  useEffect(() => {
    if (period !== "custom" || (from && to)) loadMovements();
  }, [loadMovements, period, from, to]);
  const loadKaramad = useCallback(async (nextOffset = offset) => {
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: String(limit), offset: String(nextOffset) });
      if (karamadMonth) params.set("month", karamadMonth);
      if (karamadSearch.trim()) params.set("search", karamadSearch.trim());
      if (karamadBranch) params.set("branch", karamadBranch);
      const [rows, folder] = await Promise.all([
        request(`/karamad-manual/movements?${params.toString()}`),
        request("/karamad-manual/folder/status"),
      ]);
      setKaramad(rows);
      setKaramadFolder(folder);
    } catch (e) {
      setError(e instanceof Error ? e.message : "دریافت حواله‌های کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  }, [karamadMonth, karamadSearch, karamadBranch, limit, offset]);
  useEffect(() => {
    Promise.all([
      request(`/karamad-manual/movements?limit=${limit}&offset=0`),
      request("/karamad-manual/folder/status"),
    ])
      .then(([rows, folder]) => { setKaramad(rows); setKaramadFolder(folder); })
      .catch(() => undefined);
  }, []);
  const uploadKaramad = async () => {
    if (!karamadFile) return;
    setBusy(true);
    setKaramadMessage("");
    setError("");
    try {
      const body = new FormData();
      body.append("file", karamadFile);
      const result = await request("/karamad-manual/upload", { method: "POST", body });
      setKaramadMessage(result.message || "فایل کارآمد ثبت و یکتاسازی شد.");
      setOffset(0);
      await loadKaramad(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ورود فایل کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const scanKaramadFolder = async () => {
    setBusy(true);
    setKaramadMessage("");
    setError("");
    try {
      const result = await request("/karamad-manual/folder/scan", { method: "POST" });
      setKaramadMessage(`${fa(result.imported_count || 0)} فایل وارد شد؛ ${fa(result.skipped_count || 0)} فایل تکراری بود و ${fa(result.error_count || 0)} خطا ثبت شد.`);
      await loadKaramad(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "بررسی پوشه کارآمد ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const decideCommitment = useCallback(
    async (item: any, decision: "pending_review" | "paid" | "cancelled" | "still_due") => {
      const labels: Record<string, string> = {
        pending_review: "نیازمند بررسی",
        paid: "پرداخت‌شده",
        cancelled: "لغوشده",
        still_due: "همچنان بدهکار",
      };
      if (
        decision !== "pending_review" &&
        !window.confirm(`وضعیت این قسط روی «${labels[decision]}» ثبت شود؟`)
      )
        return;
      setDecisionBusy(item.installment_id);
      setDecisionMessage("");
      setError("");
      try {
        await treasuryMutation(
          `/cash-bank/commitments/${item.installment_id}/decision`,
          {
            method: "PUT",
            body: JSON.stringify({
              payment_order_id: item.payment_order_id,
              decision,
            }),
          },
        );
        const refreshed = await treasuryRequest(
          `/cash-bank/commitments?horizon_days=365&limit=${limit}&offset=0`,
        );
        setCommitments(refreshed);
        setDecisionMessage(`وضعیت قسط ${item.installment_id} روی «${labels[decision]}» ثبت شد.`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "ثبت وضعیت تعهد ناموفق بود");
      } finally {
        setDecisionBusy(null);
      }
    },
    [limit],
  );
  const summary = report?.summary || {};
  const approvalCaption =
    approval === "approved"
      ? "اسناد قطعی"
      : approval === "pending"
        ? "اسناد غیرقطعی"
        : "همه وضعیت‌ها";
  const pageInfo =
    tab === "movements" ? report?.pagination : tab === "transfers" ? transfers?.pagination : tab === "petty" ? pettyCash?.pagination : tab === "karamad" ? karamad?.pagination : commitments?.pagination;
  const approvedFuture = commitments?.summary?.approved_future || {};
  const draftFuture = commitments?.summary?.draft_future || {};
  const currentOverdue = commitments?.summary?.current_year_overdue || {};
  const historicalBacklog = commitments?.summary?.historical_backlog || {};
  const commitmentReview = commitments?.manual_review_summary || {};
  const reviewCounts = commitmentReview?.counts || {};
  const reviewAmounts = commitmentReview?.amounts_rial || {};
  const karamadSummary = karamad?.summary || {};
  const movementLabel: Record<string, string> = {
    cash_receipt: "دریافت نقدی",
    bank_receipt: "واریز / حواله ورودی",
    cash_payment: "پرداخت نقدی",
    bank_payment: "برداشت / حواله خروجی",
  };
  // Status normalization is intentionally defensive because Rahkaran and Karamad
  // expose approval state with different field names.
  const normalizedApproval = (x: any): "approved" | "pending" | "rejected" | "unknown" => {
    const raw = x?.approve_state ?? x?.approval_state ?? x?.approval_status ?? x?.status_ref ?? x?.status;
    if (raw === 3 || raw === "3" || raw === true || raw === "approved" || raw === "confirmed" || raw === "قطعی") return "approved";
    if (raw === 4 || raw === "4" || raw === "rejected" || raw === "ردشده") return "rejected";
    if (raw === 2 || raw === "2" || raw === false || raw === "pending" || raw === "unconfirmed" || raw === "غیرقطعی") return "pending";
    // Karamad Excel has no explicit approval column; "وجوه در راه=true"
    // is the authoritative pending/unsettled signal for those imported rows.
    if (x?.in_transit === true || x?.cash_in_transit === true || x?.funds_in_transit === true || x?.وجوه_در_راه === true || x?.["وجوه در راه"] === true) return "pending";
    if (x?.source_system === "karamad" || x?.source_label === "کارآمد") return "approved";
    return "unknown";
  };
  const visibleMovements = (report?.movements || []).filter((x: any) => {
    if (approval === "all") return true;
    const state = normalizedApproval(x);
    return approval === "approved" ? state === "approved" : state === "pending";
  });
  const visibleKaramadMovements = (karamad?.movements || []).filter((x: any) => {
    if (approval === "all") return true;
    const state = normalizedApproval(x);
    return approval === "approved" ? state === "approved" : state === "pending";
  });
  const corporateTransferRows = branchFilter || sourceFilter === "karamad"
    ? [...(report?.company_bank_transfers || [])]
    : [...(transfers?.transfers || []), ...(report?.company_bank_transfers || [])];
  const pettyCashRows = branchFilter || sourceFilter === "karamad"
    ? [...(report?.petty_cash_movements || [])]
    : [...(pettyCash?.transfers || []), ...(report?.petty_cash_movements || [])];
  const cashBranchOptions: string[] = summary.available_branches || [];
  return (
    <div className="cash-bank-page">
      {<section className="cash-bank-toolbar fd-panel">
        <div>
          <b>بازه گزارش</b>
          {[
            ["today", "امروز"],
            ["week", "۷ روز"],
            ["month", "۳۰ روز"],
            ["3m", "۳ ماه"],
            ["6m", "۶ ماه"],
            ["12m", "۱۲ ماه"],
            ["custom", "دلخواه"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={period === id ? "active" : ""}
              onClick={() => {
                setPeriod(id);
                setOffset(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="approval-filter-group">
          <b>وضعیت سند</b>
          {[
            ["approved", "قطعی"],
            ["pending", "غیرقطعی"],
            ["all", "همه"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={approval === id ? "active" : ""}
              onClick={() => {
                setApproval(id);
                setOffset(0);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="cash-branch-filter">
          <b>منبع حواله‌ها</b>
          <select aria-label="منبع حواله‌ها" value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setBranchFilter(""); setOffset(0); }}>
            <option value="all">همه منابع</option>
            <option value="rahkaran">فقط راهکاران</option>
            <option value="karamad">فقط کارآمد</option>
          </select>
        </div>
        <label className="cash-bank-search-filter">
          <b>جستجو در گردش</b>
          <input
            value={movementSearchInput}
            onChange={(e) => setMovementSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setMovementSearch(movementSearchInput.trim());
                setOffset(0);
              }
            }}
            placeholder="شماره سند، طرف حساب، شرح، مبلغ، بانک یا صندوق"
            aria-label="جستجو در گردش نقد و حواله"
          />
          <button
            type="button"
            className="search-apply"
            onClick={() => {
              setMovementSearch(movementSearchInput.trim());
              setOffset(0);
            }}
          >جستجو</button>
          {movementSearch && (
            <button
              type="button"
              className="search-clear"
              onClick={() => { setMovementSearchInput(""); setMovementSearch(""); setOffset(0); }}
            >پاک کردن</button>
          )}
        </label>
        <div>
          <b>شهر / شعبه کارآمد</b>
          <select disabled={sourceFilter === "rahkaran"} value={branchFilter} onChange={(e) => { setBranchFilter(e.target.value); setOffset(0); }}>
            <option value="">{sourceFilter === "all" ? "همه شعب + راهکاران" : sourceFilter === "rahkaran" ? "برای راهکاران کاربرد ندارد" : "همه شعب کارآمد"}</option>
            {cashBranchOptions.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          {branchFilter && <small>آمار و ریز حواله‌ها فقط برای شعبه «{branchFilter}» از کارآمد نمایش داده می‌شود.</small>}
        </div>
        {period === "custom" && (
          <div className="custom-dates">
            <label>
              از
              <input
                type="date"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label>
              تا
              <input
                type="date"
                value={to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
          </div>
        )}
        <button className="refresh" onClick={loadMovements} disabled={busy}>
          {busy ? "در حال خواندن…" : "به‌روزرسانی"}
        </button>
      </section>}
      {error && <div className="fd-errors">{error}</div>}
      {decisionMessage && <div className="commitment-success">{decisionMessage}</div>}
      <section className="fd-kpis cash-bank-kpis">
        <K t="حواله دریافتی" v={summary.bank_receipt_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_receipt_rial))} n={`تومان؛ ورودی بانکی واقعی · ${approvalCaption}`} c="blue" />
        <K t="حواله پرداختی" v={summary.bank_payment_total_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_payment_total_rial))} n={`تومان؛ شامل انتقال بانکی و تنخواه · ${approvalCaption}`} c="amber" />
        <K t="حواله پرداختی بدون انتقال بانکی" v={summary.bank_payment_excluding_transfer_rial == null ? "در انتظار گزارش" : fullToman(Number(summary.bank_payment_excluding_transfer_rial))} n={`تومان؛ کل حواله منهای انتقال بانک‌به‌بانک؛ تنخواه در این عدد باقی است · ${approvalCaption}`} c="red" />
      </section>
      {Number(summary.hybrid_settlement_count || 0) > 0 && <p className="company-payment-note">
        {fa(Number(summary.hybrid_settlement_count))} ردیف تسویه هیبرید با شرکت (دریافتی شرکت {fullToman(Number(summary.hybrid_settlement_inflow_rial || 0))} تومان، پرداخت هیبریدها به شرکت‌های گروه {fullToman(Number(summary.hybrid_settlement_outflow_rial || 0))} تومان) گردش داخلی گروه است و به «انتقال بین بانکی» منتقل شده؛ در ورودی و خروجی عملیاتی حساب نمی‌شود (همان قانون صفحه نقدینگی).
        {" "}<a href={`${API()}/hybrid-settlement-reconciliation.xlsx`}>دانلود Excel تطبیق پرداخت هیبریدها با دریافت راهکاران (بدهی‌های اصلاح‌شده؛ حدود یک دقیقه)</a>
      </p>}
      {Number(summary.karamad_settlement_adjustment_count || 0) > 0 && <p className="company-payment-note">
        {fa(Number(summary.karamad_settlement_adjustment_count))} ردیف تسویه فاکتور کارآمد که فقط «تخفیف فاکتور» ({fullToman(Number(summary.karamad_settlement_discount_rial || 0))} تومان، حساب «تخفیفات حین تسویه») یا «اضافه فاکتور» ({fullToman(Number(summary.karamad_settlement_surplus_rial || 0))} تومان) داشتند در این گزارش نمی‌آیند؛ این‌ها جابه‌جایی پول نیستند و قبلاً با مبلغ صفر نمایش داده می‌شدند.
      </p>}

      <article className="fd-panel commitment-summary">
        <Heading
          h="تعهدات پرداخت و اثر آن‌ها بر نقدینگی"
          p="تعداد دستور پرداخت از تعداد اقساط چکی جداست؛ تضمینی‌ها و موارد اجراشده دوباره شمرده نمی‌شوند"
        />
        <div className="commitment-cards">
          <div className="commitment-card approved">
            <span>تعهد تأییدشده آینده</span>
            <strong>{money(approvedFuture.amount_rial || 0)} تومان</strong>
            <small>{fa(approvedFuture.payment_order_count || 0)} دستور · {fa(approvedFuture.installment_count || 0)} قسط · وارد Cash Flow پایه</small>
          </div>
          <div className="commitment-card draft">
            <span>در انتظار تأیید</span>
            <strong>{money(draftFuture.amount_rial || 0)} تومان</strong>
            <small>{fa(draftFuture.payment_order_count || 0)} دستور · {fa(draftFuture.installment_count || 0)} قسط · فقط سناریوی محتاطانه</small>
          </div>
          <div className="commitment-card overdue">
            <span>سررسیدگذشته سال جاری</span>
            <strong>{money(currentOverdue.amount_rial || 0)} تومان</strong>
            <small>{fa(currentOverdue.payment_order_count || 0)} دستور · {fa(currentOverdue.installment_count || 0)} قسط · نیازمند تعیین‌تکلیف</small>
          </div>
          <div className="commitment-card history">
            <span>مانده تاریخی کنارگذاشته‌شده</span>
            <strong>{money(historicalBacklog.amount_rial || 0)} تومان</strong>
            <small>{fa(historicalBacklog.payment_order_count || 0)} دستور · وارد پیش‌بینی نمی‌شود</small>
          </div>
        </div>
        <div className="commitment-review-strip">
          <span><b>{fa(reviewCounts.pending_review || 0)}</b> قسط منتظر بررسی</span>
          <span><b>{fa(reviewCounts.paid || 0)}</b> پرداخت‌شده</span>
          <span><b>{fa(reviewCounts.cancelled || 0)}</b> لغوشده</span>
          <span className="still-due"><b>{fa(reviewCounts.still_due || 0)}</b> همچنان بدهکار · {money(reviewAmounts.still_due || 0)} تومان وارد Cash Flow امروز</span>
        </div>
      </article>
      <section className="cash-bank-tabs">
        <button
          className={tab === "movements" ? "active" : ""}
          onClick={() => setTab("movements")}
        >
          دریافت و پرداخت
        </button>
        <button
          className={tab === "transfers" ? "active" : ""}
          onClick={() => setTab("transfers")}
        >
          انتقال بانک‌به‌بانک
        </button>
        <button
          className={tab === "petty" ? "active" : ""}
          onClick={() => setTab("petty")}
        >
          تنخواه
        </button>
        <button
          className={tab === "commitments" ? "active" : ""}
          onClick={() => setTab("commitments")}
        >
          تعهدات پرداخت
        </button>
      </section>
      {tab === "movements" ? (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز دریافت و پرداخت نقدی و بانکی"
            p={`${fa(visibleMovements.length)} ردیف در وضعیت انتخاب‌شده؛ ${approvalCaption}؛ مبالغ نمایشی به تومان`}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>نوع</th>
                  <th>شماره سند</th>
                  <th>طرف حساب</th>
                  <th>مبلغ</th>
                  <th>حساب / صندوق</th>
                  <th>شعبه</th>
                  <th>عامل Cash Flow</th>
                  <th>وضعیت</th>
                  <th>شرح</th>
                  <th>منبع</th>
                </tr>
              </thead>
              <tbody>
                {visibleMovements.map((x: any) => (
                  <tr key={`${x.movement_type}-${x.movement_id}`}>
                    <td>
                      <b>
                        {x.document_date_jalali ||
                          x.document_date?.slice(0, 10)}
                      </b>
                    </td>
                    <td>
                      <span className={`movement-kind ${x.direction}`}>
                        {movementLabel[x.movement_type] || x.movement_type}
                      </span>
                    </td>
                    <td>{x.document_number}</td>
                    <td>
                      {x.counterpart_name ||
                        x.counterpart_code ||
                        x.counterpart_ref ||
                        "—"}
                    </td>
                    <td className={x.direction}>
                      {money(x.amount_rial)} تومان
                    </td>
                    <td>
                      {x.bank_account_number ||
                        (x.cash_ref ? `صندوق ${x.cash_ref}` : "—")}
                    </td>
                    <td>{x.branch_name || x.branch || "—"}</td>
                    <td>{x.cash_flow_factor_ref || "—"}</td>
                    <td>
                      <span className={`approve-state s${x.approve_state}`}>
                        {x.approve_state === 3
                          ? "قطعی"
                          : x.approve_state === 4
                            ? "ردشده"
                            : "غیرقطعی"}
                      </span>
                    </td>
                    <td>{x.description || "—"}</td>
                    <td><span className={`source-badge ${x.source_system || "rahkaran"}`}>{x.source_label || (x.source_system === "karamad" ? "کارآمد" : "راهکاران")}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : tab === "transfers" ? (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز انتقال‌های داخلی"
            p="حواله‌های شرکتی بانک‌به‌بانک؛ در سطح کل شرکت اثر صفر و خارج از Cash Flow"
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>تاریخ</th>
                  <th>شماره</th>
                  <th>نوع</th>
                  <th>مبدأ</th>
                  <th>مقصد</th>
                  <th>شعبه</th>
                  <th>مبلغ خروج</th>
                  <th>مبلغ ورود</th>
                  <th>State</th>
                  <th>شرح</th>
                  <th>منبع</th>
                </tr>
              </thead>
              <tbody>
                {corporateTransferRows.map((x: any, index: number) => (
                  <tr key={`${x.transfer_type || x.movement_type}-${x.transfer_id || x.movement_id}-${index}`}>
                    <td>
                      <b>{x.date_jalali || x.document_date_jalali || x.date?.slice(0, 10) || x.document_date?.slice(0, 10)}</b>
                    </td>
                    <td>{x.number || x.document_number}</td>
                    <td>
                      {x.classification === "company_bank_transfer"
                        ? "حواله شرکتی"
                        : x.transfer_type === "bank_transfer"
                        ? "انتقال بانکی"
                        : "انتقال صندوق"}
                    </td>
                    <td>
                      {x.source_bank_account_ref
                        ? `حساب ${x.source_bank_account_ref}`
                        : x.source_cash_ref
                          ? `صندوق ${x.source_cash_ref}`
                          : x.counterpart_name || "—"}
                    </td>
                    <td>
                      {x.destination_bank_account_ref
                        ? `حساب ${x.destination_bank_account_ref}`
                        : x.destination_cash_ref
                          ? `صندوق ${x.destination_cash_ref}`
                          : x.bank_account_number || x.counterpart_name || "—"}
                    </td>
                    <td>{x.branch_name || x.branch || "—"}</td>
                    <td>{money(x.payment_amount_rial ?? (x.direction === "outflow" ? x.amount_rial : 0))} تومان</td>
                    <td>{money(x.receipt_amount_rial ?? (x.direction === "inflow" ? x.amount_rial : 0))} تومان</td>
                    <td>{x.state || x.approve_state || "—"}</td>
                    <td>{x.description || "—"}</td>
                    <td><span className={`source-badge ${x.source_system || "rahkaran"}`}>{x.source_label || (x.source_system === "karamad" ? "کارآمد" : "راهکاران")}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : tab === "petty" ? (
        <article className="fd-panel cash-bank-table">
          <Heading h="تنخواه‌های شرکت" p="تأمین تنخواه یک انتقال داخلی است و در Cash Flow دریافت/پرداخت عملیاتی محاسبه نمی‌شود." />
          <div className="table-scroll"><table><thead><tr><th>تاریخ</th><th>شماره انتقال</th><th>تنخواه مقصد</th><th>مبدأ</th><th>مبلغ</th><th>شرح</th></tr></thead>
            <tbody>{pettyCashRows.map((x: any, index: number) => <tr key={`${x.transfer_type || x.movement_type}-${x.transfer_id || x.movement_id}-${index}`}>
              <td><b>{x.date_jalali || x.document_date_jalali || x.date?.slice(0, 10) || x.document_date?.slice(0, 10)}</b></td><td>{x.number || x.document_number}</td><td>{x.destination_petty_cash_ref ? `تنخواه ${x.destination_petty_cash_ref}` : x.counterpart_name || "تنخواه"}</td>
              <td>{x.source_bank_account_ref ? `حساب ${x.source_bank_account_ref}` : x.source_cash_ref ? `صندوق ${x.source_cash_ref}` : x.bank_account_number || "—"}</td><td>{money(x.payment_amount_rial ?? x.amount_rial)} تومان</td><td>{x.description || "—"}</td>
            </tr>)}</tbody></table></div>
          {!pettyCashRows.length && <div className="fd-empty">در این بازه انتقالی یا پرداختِ دارای برچسب تنخواه ثبت نشده است.</div>}
        </article>
      ) : tab === "karamad" ? (
        <article className="fd-panel cash-bank-table karamad-panel">
          <Heading
            h="چهار ورودی دستی کارآمد"
            p="چک دریافتی، چک پرداختی، حواله دریافت و حواله پرداخت؛ هم‌پوشانی با کلید جهت و شناسه حواله حذف می‌شود."
          />
          <div className="karamad-folder-box">
            <div><span>محل قرار دادن فایل‌ها</span><b dir="ltr">{karamadFolder?.inbox || "KaramadInbox"}</b></div>
            <div><span>بررسی خودکار</span><b>هر {fa(karamadFolder?.scan_minutes || 15)} دقیقه</b></div>
            <div><span>فایل منتظر</span><b>{fa(karamadFolder?.waiting_count || 0)}</b></div>
            <button onClick={scanKaramadFolder} disabled={busy}>{busy ? "در حال بررسی…" : "بررسی همین حالا"}</button>
          </div>
          <div className="karamad-import">
            <div className="karamad-upload">
              <label>
                <span>ورود فوری یکی از چهار Excel</span>
                <input
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(e) => setKaramadFile(e.target.files?.[0] || null)}
                />
              </label>
              <button disabled={!karamadFile || busy} onClick={uploadKaramad}>
                {busy ? "در حال ورود…" : "ورود و یکتاسازی"}
              </button>
              <small>{karamadFile?.name || "فایلی انتخاب نشده است"}</small>
            </div>
            {karamadMessage && <div className="karamad-message">{karamadMessage}</div>}
          </div>
          <div className="karamad-filters">
            <label>
              ماه ثبت
              <select value={karamadMonth} onChange={(e) => setKaramadMonth(e.target.value)}>
                <option value="">همه ماه‌ها</option>
                {(karamadSummary.available_months || []).map((item: any) => (
                  <option key={item.month} value={item.month}>
                    {item.month} · {fa(item.count || 0)} ردیف
                  </option>
                ))}
              </select>
            </label>
            <label>
              شعبه
              <select value={karamadBranch} onChange={(e) => setKaramadBranch(e.target.value)}>
                <option value="">همه شعب</option>
                {(karamadSummary.available_branches || []).map((item: string) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <label>
              جست‌وجو
              <input
                value={karamadSearch}
                onChange={(e) => setKaramadSearch(e.target.value)}
                placeholder="شناسه، شماره، بانک، بابت یا شرح"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setOffset(0);
                    loadKaramad(0);
                  }
                }}
              />
            </label>
            <button onClick={() => { setOffset(0); loadKaramad(0); }} disabled={busy}>
              اعمال فیلتر
            </button>
          </div>
          <div className="karamad-summary">
            <div><span>کل حواله دریافت</span><b>{money(karamadSummary.received_transfer_total_rial || 0)} تومان · {fa(karamadSummary.received_transfer_total_count || 0)} ردیف</b></div>
            <div><span>کل حواله پرداخت</span><b>{money(karamadSummary.paid_transfer_total_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_total_count || 0)} ردیف</b></div>
            <div><span>انتقال بانک‌به‌بانک پرداخت</span><b>{money(karamadSummary.paid_transfer_bank_to_bank_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_bank_to_bank_count || 0)} ردیف</b></div>
            <div><span>سایر حواله‌های پرداخت</span><b>{money(karamadSummary.paid_transfer_other_rial || 0)} تومان · {fa(karamadSummary.paid_transfer_other_count || 0)} ردیف</b></div>
            <div><span>دریافت عملیاتی قطعی</span><b>{money(karamadSummary.operational_inflow_rial || 0)} تومان</b></div>
            <div><span>پرداخت عملیاتی قطعی</span><b>{money(karamadSummary.operational_outflow_rial || 0)} تومان</b></div>
            <div><span>کل انتقال بانک‌به‌بانک حذف‌شده</span><b>{money(karamadSummary.bank_transfer_rial || 0)} تومان</b></div>
            <div><span>بازه ثبت</span><b>{karamadSummary.min_date_jalali || "—"} تا {karamadSummary.max_date_jalali || "—"}</b></div>
          </div>
          <div className="karamad-rule">در حواله پرداخت، انتقال‌های بانک‌به‌بانک داخلی جدا گزارش می‌شوند و در خالص Cash Flow اثر صفر دارند؛ «سایر حواله‌های پرداخت» شامل همه ردیف‌های پرداخت به‌جز انتقال داخلی است.</div>
          <div className="karamad-rule">فایل‌های فعلی ساختار گردش قطعی دارند و تاریخ سررسید چک ندارند؛ بنابراین ۱۰۰٪ در عملکرد واقعی می‌آیند، اما وارد Cash Flow آینده نمی‌شوند. سیاست وصول ۷۵٪ فقط برای چک باز دارای سررسید است.</div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>تاریخ ثبت</th><th>منبع فایل</th><th>جهت</th><th>شناسه حواله</th><th>شماره حواله</th><th>شعبه</th><th>شماره سند</th><th>بانک</th><th>مبلغ</th><th>وضعیت</th><th>طبقه‌بندی</th><th>بابت</th><th>توضیحات</th></tr></thead>
              <tbody>
                {visibleKaramadMovements.map((x: any) => (
                  <tr key={`${x.direction}-${x.transfer_id}`}>
                    <td><b>{x.registration_date_jalali || "—"}</b></td>
                    <td>{x.source_label || "کارآمد"}</td>
                    <td><span className={`movement-kind ${x.direction}`}>{x.direction === "inflow" ? "دریافت" : "پرداخت"}</span></td>
                    <td>{x.transfer_id}</td>
                    <td>{x.transfer_number || "—"}</td>
                    <td>{x.branch || "—"}</td>
                    <td>{x.document_number || "—"}</td>
                    <td>{x.bank || "—"}</td>
                    <td className={x.direction}>{money(x.amount_rial)} تومان</td>
                    <td><span className={`approve-state s${normalizedApproval(x) === "approved" ? 3 : normalizedApproval(x) === "pending" ? 2 : 4}`}>{normalizedApproval(x) === "approved" ? "قطعی" : normalizedApproval(x) === "pending" ? "غیرقطعی" : "ردشده"}</span></td>
                    <td>{x.classification === "operational" ? "عملیاتی" : x.classification === "company_bank_transfer" ? "انتقال داخلی" : "تنخواه"}</td>
                    <td>{x.purpose || "—"}</td>
                    <td>{x.description || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!visibleKaramadMovements.length && <div className="fd-empty">برای وضعیت انتخاب‌شده، داده‌ای وجود ندارد.</div>}
        </article>
      ) : (
        <article className="fd-panel cash-bank-table">
          <Heading
            h="ریز تعهدات و دستورهای پرداخت"
            p="آینده تأییدشده وارد Cash Flow می‌شود؛ سررسیدگذشته تا بررسی خزانه فقط هشدار است"
          />
          <div className="table-scroll">
            <table>
              <thead><tr><th>سررسید</th><th>طبقه</th><th>شماره دستور</th><th>طرف حساب</th><th>مبلغ قسط</th><th>تعداد</th><th>شرح</th><th>تعیین تکلیف خزانه</th></tr></thead>
              <tbody>
                {(commitments?.commitments || []).map((x: any) => (
                  <tr key={x.installment_id}>
                    <td><b>{x.due_date_jalali || x.due_date?.slice(0, 10)}</b></td>
                    <td><span className={`commitment-kind ${x.commitment_class}`}>
                      {x.commitment_class === "approved_future" ? "تأییدشده آینده" : x.commitment_class === "draft_future" ? "در انتظار تأیید" : x.commitment_class === "current_year_overdue" ? "سررسیدگذشته سال جاری" : "مانده تاریخی"}
                    </span></td>
                    <td>{x.payment_order_number}</td>
                    <td>{x.counterpart_name || x.counterpart_code || x.counterpart_ref || "—"}</td>
                    <td>{money(x.amount_rial)} تومان</td>
                    <td>۱ قسط از دستور {x.payment_order_number}</td>
                    <td>{x.description || "—"}</td>
                    <td>
                      {x.commitment_class === "current_year_overdue" ? (
                        <div className="commitment-decisions">
                          <span className={`review-status ${x.review_decision || "pending_review"}`}>
                            {x.review_decision === "paid" ? "پرداخت‌شده" : x.review_decision === "cancelled" ? "لغوشده" : x.review_decision === "still_due" ? "همچنان بدهکار" : "نیازمند بررسی"}
                          </span>
                          <div>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "paid")}>پرداخت‌شده</button>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "cancelled")}>لغوشده</button>
                            <button disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "still_due")}>همچنان بدهکار</button>
                            {x.review_decision && x.review_decision !== "pending_review" && (
                              <button className="reset" disabled={decisionBusy === x.installment_id} onClick={() => decideCommitment(x, "pending_review")}>بازنشانی</button>
                            )}
                          </div>
                        </div>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}
      {tab !== "commitments" && <footer className="cash-bank-pagination">
        <button
          disabled={offset === 0 || busy}
          onClick={() => {
            const nextOffset = Math.max(0, offset - limit);
            setOffset(nextOffset);
            if (tab === "karamad") loadKaramad(nextOffset);
          }}
        >
          صفحه قبل
        </button>
        <span>
          ردیف {fa(pageInfo?.total_count || 0 ? offset + 1 : 0)} تا{" "}
          {fa(Math.min(offset + limit, pageInfo?.total_count || 0))} از{" "}
          {fa(pageInfo?.total_count || 0)}
        </span>
        <button
          disabled={!pageInfo?.has_more || busy}
          onClick={() => {
            const nextOffset = offset + limit;
            setOffset(nextOffset);
            if (tab === "karamad") loadKaramad(nextOffset);
          }}
        >
          صفحه بعد
        </button>
      </footer>}
    </div>
  );
}
