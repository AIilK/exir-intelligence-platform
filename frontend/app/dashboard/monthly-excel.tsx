// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (monthly-excel).
import { useCallback, useEffect, useState } from "react";
import { Heading, K, Risk, Status, label } from "./agents";
import { API, fa, money, request, textOf } from "./shared";

export function MonthlyExcelAutomation({ chequeQuality }: { chequeQuality?: any }) {
  const [file, setFile] = useState<File | null>(null),
    [analysis, setAnalysis] = useState<any>(null),
    [months, setMonths] = useState<any[]>([]),
    [folder, setFolder] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [viewer, setViewer] = useState<any>(null),
    [activeSheet, setActiveSheet] = useState(0);
  const loadMonths = useCallback(async () => {
    try {
      const j = await request("/cashflow-excel/months");
      setMonths(j.months || []);
      if (!analysis && j.months?.length) {
        const m = j.months[0];
        setAnalysis(
          await request(
            `/cashflow-excel/analysis?jalali_year=${m.jalali_year}&jalali_month=${m.jalali_month}`,
          ),
        );
      }
    } catch {}
  }, [analysis]);
  const loadFolder = useCallback(async () => {
    try {
      setFolder(await request("/cashflow-excel/folder/status"));
    } catch (e) {
      setFolder({
        status: "error",
        last_error: {
          error: e instanceof Error ? e.message : "وضعیت پوشه دریافت نشد",
        },
      });
    }
  }, []);
  useEffect(() => {
    loadMonths();
    loadFolder();
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      loadFolder();
      loadMonths();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const body = new FormData();
      body.append("file", file);
      const j = await request("/cashflow-excel/upload", {
        method: "POST",
        body,
      });
      setAnalysis(j.month_analysis);
      setMessage(
        `فایل ${file.name} ثبت شد؛ ماه ${j.month_analysis?.period_label || ""} از ابتدا بازمحاسبه شد.`,
      );
      await loadMonths();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "پردازش فایل ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const scanFolder = async () => {
    setBusy(true);
    setMessage("");
    try {
      const j = await request("/cashflow-excel/folder/scan", {
        method: "POST",
      });
      setMessage(
        j.imported_count
          ? `${fa(j.imported_count)} فایل جدید پردازش شد.`
          : "فایل جدیدی برای پردازش پیدا نشد.",
      );
      await loadFolder();
      await loadMonths();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "بررسی پوشه ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const choose = async (value: string) => {
    const [y, m] = value.split("-");
    setBusy(true);
    try {
      setAnalysis(
        await request(
          `/cashflow-excel/analysis?jalali_year=${y}&jalali_month=${m}`,
        ),
      );
    } finally {
      setBusy(false);
    }
  };
  const showWorkbook = async (row: any) => {
    setBusy(true);
    setMessage("");
    try {
      const j = await request(
        `/cashflow-excel/files/${row.jalali_year}/${row.jalali_month}/${encodeURIComponent(row.stored_file)}/preview`,
      );
      setViewer({ ...j, snapshot: row });
      setActiveSheet(0);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "نمایش فایل ناموفق بود");
    } finally {
      setBusy(false);
    }
  };
  const downloadWorkbook = (row: any) =>
    window.open(
      `${API()}/cashflow-excel/files/${row.jalali_year}/${row.jalali_month}/${encodeURIComponent(row.stored_file)}/download`,
      "_blank",
    );
  const rows = analysis?.snapshots || [],
    summary = analysis?.summary || {},
    forecast = analysis?.forecast || {},
    agent = analysis?.agent_analysis || {},
    max = Math.max(...rows.map((x: any) => x.pressure_percent || 0), 1);
  return (
    <div className="monthly-excel">
      <section
        className={`folder-automation-card ${folder?.status || "loading"}`}
      >
        <div className="folder-state">
          <i>
            {folder?.status === "ready"
              ? "✓"
              : folder?.status === "disabled"
                ? "∥"
                : "!"}
          </i>
          <span>
            <small>ورودی خودکار Cash Flow</small>
            <h2>
              {folder?.status === "ready"
                ? "پوشه Excel فعال است"
                : folder?.status === "disabled"
                  ? "خواندن پوشه غیرفعال است"
                  : "در حال بررسی وضعیت پوشه"}
            </h2>
            <p>فایل‌ها را در این مسیر قرار بده؛ مدیر نیازی به آپلود ندارد.</p>
          </span>
        </div>
        <code>{folder?.inbox || "در حال دریافت مسیر…"}</code>
        <div className="folder-metrics">
          <span>
            <small>فایل در انتظار</small>
            <b>{fa(folder?.waiting_count || 0)}</b>
          </span>
          <span>
            <small>آخرین فایل موفق</small>
            <b>{folder?.last_successful_file?.filename || "هنوز ثبت نشده"}</b>
          </span>
          <span>
            <small>بررسی خودکار</small>
            <b>هر {fa(folder?.scan_minutes || 15)} دقیقه</b>
          </span>
        </div>
        {folder?.last_error && (
          <div className="folder-error">
            خطای آخر: {folder.last_error.error || folder.last_error}
          </div>
        )}
        <button onClick={scanFolder} disabled={busy}>
          {busy ? "در حال بررسی…" : "بررسی همین حالا"}
        </button>
      </section>
      <details className="manual-upload-fallback">
        <summary>بارگذاری دستی فایل؛ فقط برای حالت پشتیبان</summary>
        <section className="excel-upload-card">
          <div>
            <small>روش جایگزین</small>
            <h2>بارگذاری دستی Cash Flow</h2>
            <p>اگر سرویس پوشه در دسترس نبود، فایل را از این قسمت ثبت کنید.</p>
          </div>
          <label>
            <input
              type="file"
              accept=".xlsx"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <span>{file ? file.name : "انتخاب فایل Excel"}</span>
          </label>
          <button onClick={upload} disabled={!file || busy}>
            {busy ? "در حال پردازش…" : "بارگذاری و تحلیل ماه"}
          </button>
        </section>
      </details>
      {message && (
        <div
          className={`excel-message ${message.includes("ثبت شد") ? "ok" : "error"}`}
        >
          {message}
        </div>
      )}
      <div className="excel-period">
        <div>
          <b>ماه مورد بررسی</b>
          <small>هر روز فقط یک Snapshot معتبر نگهداری می‌شود.</small>
        </div>
        <select
          value={
            analysis ? `${analysis.jalali_year}-${analysis.jalali_month}` : ""
          }
          onChange={(e) => choose(e.target.value)}
        >
          {months.map((m) => (
            <option
              key={`${m.jalali_year}-${m.jalali_month}`}
              value={`${m.jalali_year}-${m.jalali_month}`}
            >
              {m.month_name} {fa(m.jalali_year)} — {fa(m.snapshot_count)} فایل
            </option>
          ))}
        </select>
      </div>
      {!!rows.length && (
        <article className="fd-panel excel-files">
          <Heading
            h="فایل‌های Excel معتبر این ماه"
            p="همان فایل‌هایی که مبنای Snapshot و تحلیل Agent قرار گرفته‌اند"
          />
          <div className="excel-file-list">
            {[...rows].reverse().map((row: any) => (
              <div key={row.stored_file}>
                <i>▥</i>
                <span>
                  <b>{row.filename}</b>
                  <small>
                    {row.jalali_date} • ثبت‌شده در{" "}
                    {row.uploaded_at
                      ? new Date(row.uploaded_at).toLocaleString("fa-IR")
                      : "سیستم"}
                  </small>
                </span>
                <em>پردازش موفق</em>
                <button onClick={() => showWorkbook(row)} disabled={busy}>
                  مشاهده محتوا
                </button>
                <button
                  className="secondary"
                  onClick={() => downloadWorkbook(row)}
                >
                  دانلود اصل فایل
                </button>
              </div>
            ))}
          </div>
        </article>
      )}
      {analysis?.status === "success" ? (
        <>
          <article className={`excel-agent ${forecast.status || "attention"}`}>
            <header>
              <i>✦</i>
              <div>
                <small>Monthly Cash Flow Agent</small>
                <h2>{agent.headline}</h2>
              </div>
              <Status x={forecast.status || "attention"} />
            </header>
            <p>{agent.human_summary}</p>
            <div>
              <section>
                <b>نقاط مثبت</b>
                {(agent.good_signals || []).map((x: string, i: number) => (
                  <span key={i}>✓ {x}</span>
                ))}
              </section>
              <section>
                <b>ریسک‌ها و اقدام</b>
                {(agent.risks || []).map((x: string, i: number) => (
                  <span key={i}>! {x}</span>
                ))}
                {(agent.recommended_actions || []).map((x: any, i: number) => (
                  <span key={"a" + i}>→ {textOf(x)}</span>
                ))}
              </section>
            </div>
          </article>
          <div className="fd-kpis">
            <K
              t="میانگین تعهد ماه"
              v={money(summary.average_obligations_rial || 0)}
              n="تومان"
              c="blue"
            />
            <K
              t="فشار وزنی چک‌ها"
              v={`${fa(summary.weighted_average_pressure_percent)}٪`}
              n="تعهد ÷ موجودی"
              c="amber"
            />
            <K
              t="ظرفیت پرداخت پیش‌بینی‌شده"
              v={`${fa(forecast.estimated_payment_capacity_percent)}٪`}
              n={`اطمینان ${forecast.confidence === "medium" ? "متوسط" : "کم"}`}
              c="teal"
            />
            <K
              t={
                chequeQuality?.issued_actual_payment_rate
                  ? "نرخ واقعی پاس‌شدن پرداختی"
                  : "نرخ واقعی وصول دریافتی"
              }
              v={
                chequeQuality?.issued_actual_payment_rate
                  ? `${fa(chequeQuality.issued_actual_payment_rate.amount_rate_percent)}٪`
                  : chequeQuality?.received_verified
                    ? `${fa(chequeQuality.received_verified.amount_rate_percent)}٪`
                    : "در انتظار SQL"
              }
              n={
                chequeQuality?.issued_actual_payment_rate
                  ? `${fa(chequeQuality.issued_actual_payment_rate.paid_count)} چک پرداخت‌شده`
                  : chequeQuality?.received_verified
                    ? `${fa(chequeQuality.received_verified.collected_count)} چک وصول‌شده`
                    : "وضعیت قطعی چک"
              }
              c="teal"
            />
          </div>
          <section className="excel-grid">
            <article className="fd-panel">
              <Heading
                h={`روند فشار چک‌های ${analysis.period_label}`}
                p="درصد تعهدات چکی نسبت به موجودی کل در هر فایل روزانه"
              />
              <div className="excel-bars">
                {rows.map((x: any) => (
                  <div key={x.jalali_date}>
                    <b>{fa(x.pressure_percent)}٪</b>
                    <span>
                      <i
                        className={
                          x.pressure_percent >= 50
                            ? "critical"
                            : x.pressure_percent >= 30
                              ? "warning"
                              : "normal"
                        }
                        style={{
                          height: `${Math.max(5, (x.pressure_percent / max) * 100)}%`,
                        }}
                      />
                    </span>
                    <small>{String(x.jalali_date).slice(8)}</small>
                  </div>
                ))}
              </div>
            </article>
            <article className="fd-panel excel-forecast">
              <Heading h="پیش‌بینی پایان ماه" p={forecast.method || ""} />
              <strong>
                {fa(forecast.estimated_payment_capacity_percent)}٪
              </strong>
              <span>ظرفیت احتمالی پرداخت</span>
              <dl>
                <div>
                  <dt>روند</dt>
                  <dd>{forecast.trend}</dd>
                </div>
                <div>
                  <dt>فشار پایان ماه</dt>
                  <dd>{fa(forecast.projected_end_month_pressure_percent)}٪</dd>
                </div>
                <div>
                  <dt>آخرین فایل</dt>
                  <dd>{analysis.latest_snapshot?.jalali_date}</dd>
                </div>
                <div>
                  <dt>نرخ واقعی پرداخت</dt>
                  <dd>
                    {chequeQuality?.issued_actual_payment_rate
                      ? `${fa(chequeQuality.issued_actual_payment_rate.amount_rate_percent)}٪`
                      : "در انتظار تأیید State"}
                  </dd>
                </div>
              </dl>
              <p>
                {chequeQuality?.issued_actual_payment_rate
                  ? `نرخ واقعی پرداخت از SQL و Stateهای تأییدشده ${chequeQuality.issued_actual_payment_rate.configured_paid_states.join("، ")} محاسبه شده است.`
                  : chequeQuality?.issued_rate_limitation ||
                    "اتصال وضعیت قطعی SQL برقرار نشده است؛ جزئیات خطا در بخش چک‌ها نمایش داده می‌شود."}
              </p>
            </article>
          </section>
          <article className="fd-panel">
            <Heading
              h="ریز Snapshotهای ماه"
              p="مبالغ به تومان؛ فایل جدید همان روز جایگزین نسخه قبلی می‌شود."
            />
            <div className="excel-table">
              <table>
                <thead>
                  <tr>
                    <th>تاریخ</th>
                    <th>موجودی</th>
                    <th>چک معوق</th>
                    <th>چک پیش‌رو</th>
                    <th>کل تعهد</th>
                    <th>مانده بعد از تعهد</th>
                    <th>فشار</th>
                    <th>وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((x: any) => (
                    <tr key={x.jalali_date}>
                      <td>
                        <b>{x.jalali_date}</b>
                      </td>
                      <td>{money(x.liquidity_rial)}</td>
                      <td>{money(x.overdue_cheques_rial)}</td>
                      <td>{money(x.upcoming_cheques_rial)}</td>
                      <td>{money(x.obligations_rial)}</td>
                      <td>{money(x.remaining_cash_rial)}</td>
                      <td>{fa(x.pressure_percent)}٪</td>
                      <td>
                        <Risk
                          x={
                            x.shortfall_rial > 0
                              ? "critical"
                              : x.pressure_percent >= 30
                                ? "danger"
                                : "safe"
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </>
      ) : (
        <div className="fd-empty">
          اولین فایل Excel را داخل پوشه ورودی قرار بده و «بررسی همین حالا» را
          بزن.
        </div>
      )}
      {viewer && (
        <div
          className="excel-viewer-backdrop"
          onMouseDown={() => setViewer(null)}
        >
          <section
            className="excel-viewer"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <small>نمایش فایل Excel</small>
                <h2>{viewer.snapshot?.filename}</h2>
                <p>{viewer.snapshot?.jalali_date} • Snapshot معتبر</p>
              </div>
              <button onClick={() => setViewer(null)}>×</button>
            </header>
            <nav>
              {viewer.sheets?.map((sheet: any, i: number) => (
                <button
                  key={sheet.name}
                  className={activeSheet === i ? "active" : ""}
                  onClick={() => setActiveSheet(i)}
                >
                  {sheet.name}
                </button>
              ))}
            </nav>
            {viewer.sheets?.[activeSheet] && (
              <>
                <div className="excel-sheet-meta">
                  <span>
                    {fa(viewer.sheets[activeSheet].total_row_count)} ردیف
                  </span>
                  {viewer.sheets[activeSheet].truncated && (
                    <em>
                      برای سرعت نمایش، فقط ۲۵۰ ردیف و ۴۰ ستون اول نشان داده
                      می‌شود.
                    </em>
                  )}
                </div>
                <div className="excel-sheet-table">
                  <table>
                    <tbody>
                      {viewer.sheets[activeSheet].rows.map(
                        (row: any[], ri: number) => (
                          <tr key={ri}>
                            <th>{fa(ri + 1)}</th>
                            {row.map((cell: any, ci: number) => (
                              <td key={ci}>
                                {cell == null
                                  ? ""
                                  : typeof cell === "number"
                                    ? fa(cell)
                                    : String(cell)}
                              </td>
                            ))}
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <footer>
              <button onClick={() => downloadWorkbook(viewer.snapshot)}>
                دانلود اصل فایل
              </button>
              <button className="secondary" onClick={() => setViewer(null)}>
                بستن
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
