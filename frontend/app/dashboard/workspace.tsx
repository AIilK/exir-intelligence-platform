// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (workspace).
import { useState } from "react";
import { AgentCard, Heading, K, ManagerPanel, Risk, Status, label } from "./agents";
import { CashChart, CashTable } from "./customer-profile";
import { fa, money, request } from "./shared";
import type { AgentResult, Alert, Rep } from "./types";

export function Representatives({
  reps,
  unmapped,
  agent,
}: {
  reps: Rep[];
  unmapped?: number;
  agent?: AgentResult;
}) {
  return (
    <>
      <div className="fd-kpis">
        <K t="نماینده فعال" v={fa(reps.length)} n="دارای Mapping" c="teal" />
        <K
          t="مشتری بدون نماینده"
          v={fa(unmapped)}
          n="نیازمند تکمیل فایل"
          c="amber"
        />
        <K
          t="نماینده بحرانی"
          v={fa(reps.filter((x) => x.status === "critical").length)}
          n="پرتفوی پرریسک"
          c="red"
        />
      </div>
      <div className="rep-grid">
        {reps.map((r) => (
          <article key={r.representative_id}>
            <Risk
              x={
                r.status === "critical"
                  ? "critical"
                  : r.status === "attention"
                    ? "danger"
                    : "safe"
              }
            />
            <h3>{r.representative_name}</h3>
            <p>
              {fa(r.customer_count)} مشتری • {fa(r.high_risk_customer_count)}{" "}
              پرریسک
            </p>
            <b>{money(r.open_exposure)} تومان مانده باز</b>
            <small>{r.human_analysis}</small>
          </article>
        ))}
      </div>
    </>
  );
}
export function Simulator({
  result,
  setResult,
}: {
  result: any;
  setResult: (x: any) => void;
}) {
  const [rate, setRate] = useState(75),
    [delay, setDelay] = useState(0),
    [opening, setOpening] = useState("");
  const run = async () =>
    setResult(
      await request("/cashflow/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          collection_rate_percent: rate,
          payment_delay_days: delay,
          opening_cash: opening ? Number(opening) * 10 : null,
        }),
      }),
    );
  return (
    <>
      <article className="fd-panel">
        <Heading
          h="اگر چه اتفاقی بیفتد؟"
          p="نرخ وصول، جابه‌جایی پرداخت و موجودی افتتاحیه را تغییر دهید."
        />
        <div className="scenario-controls">
          <label>
            نرخ وصول چک‌ها <b>{fa(rate)}٪</b>
            <input
              type="range"
              min="0"
              max="100"
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
            />
          </label>
          <label>
            تعویق پرداخت‌ها <b>{fa(delay)} روز</b>
            <input
              type="range"
              min="0"
              max="30"
              value={delay}
              onChange={(e) => setDelay(Number(e.target.value))}
            />
          </label>
          <label>
            موجودی افتتاحیه (تومان)
            <input
              inputMode="numeric"
              placeholder="مثلاً ۵۰۰٬۰۰۰٬۰۰۰"
              value={opening}
              onChange={(e) => setOpening(e.target.value)}
            />
          </label>
          <button onClick={run}>محاسبه سناریو</button>
        </div>
      </article>
      {result && (
        <>
          <div className="fd-kpis">
            <K
              t="نرخ وصول سناریو"
              v={`${fa(result.inputs?.collection_rate_percent)}٪`}
              n="ورودی انتخابی"
              c="teal"
            />
            <K
              t="اولین کسری"
              v={result.first_shortage_date || "ندارد"}
              n="با موجودی ثبت‌شده"
              c="red"
            />
            <K
              t="بدترین مانده"
              v={
                result.worst_projected_cash == null
                  ? "نامشخص"
                  : money(result.worst_projected_cash)
              }
              n="تومان"
              c="amber"
            />
          </div>
          <article className="fd-panel">
            <CashChart days={result.timeline || []} />
            <CashTable days={result.timeline || []} />
            <div className="scenario-advice">✦ {result.management_advice}</div>
          </article>
        </>
      )}
    </>
  );
}
export function Alerts({ rows, refresh }: { rows: Alert[]; refresh: () => void }) {
  const update = async (id: string, status: string) => {
    await request(`/customer-alerts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    refresh();
  };
  return (
    <article className="fd-panel">
      <Heading h="مرکز هشدارها" p="تأیید، ارجاع، پیگیری و بستن هشدار" />
      <div className="alert-enterprise">
        {rows.map((a) => (
          <div key={a.alert_id}>
            <i>!</i>
            <section>
              <Risk x={a.level === "critical" ? "critical" : "danger"} />
              <h3>{a.title}</h3>
              <p>{a.payload?.description || a.payload?.reason}</p>
              <b>{a.payload?.recommended_action}</b>
            </section>
            <aside>
              <button onClick={() => update(a.alert_id, "acknowledged")}>
                تأیید
              </button>
              <button onClick={() => update(a.alert_id, "in_progress")}>
                ارجاع به پیگیری
              </button>
              <button onClick={() => update(a.alert_id, "resolved")}>
                حل‌شده
              </button>
            </aside>
          </div>
        ))}
      </div>
    </article>
  );
}
export function History({ rows }: { rows: any[] }) {
  return (
    <article className="fd-panel">
      <Heading
        h="تاریخچه گزارش‌های Agent"
        p="مقایسه روند تصمیم‌ها و ریسک‌ها در اجرای روزانه"
      />
      <div className="timeline-list">
        {rows.map((r, i) => (
          <div key={r.report_id}>
            <i>{fa(rows.length - i)}</i>
            <section>
              <b>
                {r.management_summary?.analysis?.headline ||
                  "گزارش تیم Agentها"}
              </b>
              <small>
                {new Date(r.created_at).toLocaleString("fa-IR")} •{" "}
                {r.trigger_type === "scheduled" ? "اجرای خودکار" : "اجرای دستی"}
              </small>
              <p>{r.management_summary?.analysis?.summary}</p>
            </section>
            <Status
              x={
                r.management_summary?.analysis?.management_status || "attention"
              }
            />
          </div>
        ))}
      </div>
    </article>
  );
}
export function Performance({ data }: { data: any }) {
  const [type, setType] = useState("collection_amount"),
    [predicted, setPredicted] = useState(""),
    [actual, setActual] = useState(""),
    [saved, setSaved] = useState(false),
    isMoney = type !== "cheque_return";
  const save = async () => {
    const factor = isMoney ? 10 : 1;
    await request("/prediction-performance/outcomes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prediction_type: type,
        predicted_value: Number(predicted) * factor,
        actual_value: Number(actual) * factor,
      }),
    });
    setSaved(true);
  };
  const show = (value: number, rowType: string) =>
    rowType === "cheque_return" ? fa(value) : `${money(value)} تومان`;
  return (
    <>
      <div className="fd-kpis">
        <K
          t="پیش‌بینی ارزیابی‌شده"
          v={fa(data?.evaluated_predictions)}
          n="نتیجه واقعی ثبت‌شده"
          c="teal"
        />
        <K
          t="میانگین خطای مطلق"
          v={
            data?.mean_absolute_error == null
              ? "در انتظار داده"
              : fa(data.mean_absolute_error)
          }
          n="براساس واحد هر پیش‌بینی"
          c="amber"
        />
      </div>
      <article className="fd-panel">
        <Heading
          h="ثبت نتیجه واقعی"
          p="تمام مبلغ‌ها را به تومان وارد کنید؛ نتیجه برگشت بدون واحد پولی ثبت می‌شود."
        />
        <div className="outcome-form">
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="collection_amount">مبلغ وصول</option>
            <option value="cheque_return">برگشت چک</option>
            <option value="cash_balance">مانده نقدی</option>
          </select>
          <input
            placeholder={
              isMoney ? "مقدار پیش‌بینی‌شده (تومان)" : "مقدار پیش‌بینی‌شده"
            }
            value={predicted}
            onChange={(e) => setPredicted(e.target.value)}
          />
          <input
            placeholder={isMoney ? "مقدار واقعی (تومان)" : "مقدار واقعی"}
            value={actual}
            onChange={(e) => setActual(e.target.value)}
          />
          <button onClick={save}>ثبت نتیجه</button>
          {saved && (
            <span>ثبت شد؛ با نوسازی صفحه در محاسبه دقت دیده می‌شود.</span>
          )}
        </div>
      </article>
      <article className="fd-panel">
        <Heading
          h="کنترل کیفیت پیش‌بینی"
          p="مقایسه پیش‌بینی با وصول، برگشت و نقدینگی واقعی"
        />
        {data?.items?.length ? (
          <div className="fd-table">
            <table>
              <thead>
                <tr>
                  <th>نوع</th>
                  <th>مقدار پیش‌بینی</th>
                  <th>مقدار واقعی</th>
                  <th>زمان نتیجه</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((x: any) => (
                  <tr key={x.outcome_id}>
                    <td>{x.prediction_type}</td>
                    <td>{show(x.predicted_value, x.prediction_type)}</td>
                    <td>{show(x.actual_value, x.prediction_type)}</td>
                    <td>{x.outcome_at}</td>
                    <td>{x.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="fd-empty">
            {data?.message ||
              "بعد از رسیدن سررسیدها، نتیجه واقعی برای سنجش دقت ثبت می‌شود."}
          </div>
        )}
      </article>
    </>
  );
}
export function Settings({
  values,
  setValues,
}: {
  values: Record<string, any>;
  setValues: (x: any) => void;
}) {
  const save = async () => {
    const j = await request("/policies", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    });
    setValues(j.values);
  };
  return (
    <article className="fd-panel">
      <Heading
        h="قوانین مالی و اتوماسیون"
        p="بدون تغییر کد، آستانه‌ها و زمان اجرای روزانه را تنظیم کنید."
      />
      <div className="settings-grid">
        <Setting
          t="حداکثر مدت چک"
          unit="روز"
          k="allowed_term_days"
          values={values}
          set={setValues}
        />
        <Setting
          t="احتمال برگشت پرریسک"
          unit="درصد"
          k="high_return_probability_percent"
          values={values}
          set={setValues}
        />
        <Setting
          t="نسبت معوق بحرانی"
          unit="درصد"
          k="critical_overdue_ratio_percent"
          values={values}
          set={setValues}
        />
        <Setting
          t="آستانه روزهای فشار نقدی"
          unit="روز"
          k="cash_pressure_days_threshold"
          values={values}
          set={setValues}
        />
        <Setting
          t="ساعت اجرای روزانه"
          unit="ساعت"
          k="daily_run_hour"
          values={values}
          set={setValues}
        />
        <Setting
          t="دقیقه اجرای روزانه"
          unit="دقیقه"
          k="daily_run_minute"
          values={values}
          set={setValues}
        />
      </div>
      <div className="notification-settings">
        <b>کانال‌های هشدار</b>
        {["dashboard", "email", "sms"].map((x) => (
          <label key={x}>
            <input
              type="checkbox"
              checked={(values.notification_channels || []).includes(x)}
              onChange={(e) =>
                setValues({
                  ...values,
                  notification_channels: e.target.checked
                    ? [...(values.notification_channels || []), x]
                    : (values.notification_channels || []).filter(
                        (v: string) => v !== x,
                      ),
                })
              }
            />
            {x === "dashboard" ? "داشبورد" : x === "email" ? "ایمیل" : "پیامک"}
          </label>
        ))}
      </div>
      <button className="save-settings" onClick={save}>
        ذخیره قوانین
      </button>
    </article>
  );
}
export function Setting({
  t,
  unit,
  k,
  values,
  set,
}: {
  t: string;
  unit: string;
  k: string;
  values: Record<string, any>;
  set: (x: any) => void;
}) {
  return (
    <label>
      <span>
        {t}
        <small>{unit}</small>
      </span>
      <input
        type="number"
        value={values[k] ?? ""}
        onChange={(e) => set({ ...values, [k]: Number(e.target.value) })}
      />
    </label>
  );
}
export function Agents({
  agents,
  manager,
  focusKey,
}: {
  agents?: Record<string, AgentResult>;
  manager?: AgentResult;
  focusKey?: string | null;
}) {
  const hub = manager?.data_context?.karamad || {};
  const paid = hub?.paid_transfers || {};
  const agentEntries = Object.entries(agents || {}).sort(([a], [b]) => {
    if (a === focusKey) return -1;
    if (b === focusKey) return 1;
    return 0;
  });
  return (
    <>
      <ManagerPanel a={manager?.analysis} />
      {hub?.record_count !== undefined && (
        <article className="fd-panel agent-data-hub">
          <Heading h="Snapshot داده متصل به Agentها" p="همه Agentهای مالی این نسخه داده را به‌صورت مشترک می‌خوانند؛ با آپلود Snapshot جدید، گزارش Agentها دوباره ساخته می‌شود." />
          <div className="audit-status-grid">
            <article><small>کل رکورد کارآمد</small><b>{fa(hub.record_count || 0)}</b><em>Snapshot فعلی</em></article>
            <article><small>چک دریافتی</small><b>{fa(hub?.received_cheques?.count || 0)}</b><em>{money(hub?.received_cheques?.amount_rial || 0)}</em></article>
            <article><small>چک پرداختی ثبت‌شده</small><b>{fa(hub?.issued_cheques?.count || 0)}</b><em>آینده کامل نیست</em></article>
            <article><small>حواله دریافت</small><b>{fa(hub?.received_transfers?.count || 0)}</b><em>{money(hub?.received_transfers?.amount_rial || 0)}</em></article>
            <article><small>حواله پرداخت</small><b>{fa(paid?.count || 0)}</b><em>{money(paid?.amount_rial || 0)}</em></article>
            <article><small>انتقال بانک‌به‌بانک</small><b>{fa(paid?.bank_to_bank_count || 0)}</b><em>اثر خالص صفر</em></article>
            <article><small>مشتری کارآمد</small><b>{fa(hub?.customer_count || 0)}</b><em>پرونده یکپارچه</em></article>
          </div>
        </article>
      )}
      {focusKey && agents?.[focusKey] && (
        <div className="agent-focus-note">
          <span>Agent انتخاب‌شده برای جزئیات گزارش</span>
          <b>{agents[focusKey]?.metadata?.agent_name || focusKey}</b>
        </div>
      )}
      <div className="agent-grid large">
        {agentEntries.map(([key, a]) => (
          <div key={key} className={key === focusKey ? "agent-focused-wrap" : ""}>
            <AgentCard agent={a} />
          </div>
        ))}
      </div>
      <article className="fd-panel agent-flow">
        <Heading
          h="نحوه همکاری Agentها"
          p="Finance Manager Agent عدد جدید تولید نمی‌کند؛ خروجی تخصصی Agentها را جمع‌بندی می‌کند."
        />
        <div>
          <span>رفتار مشتری</span>
          <span>ریسک چک</span>
          <span>نقدینگی</span>
          <span>وصول</span>
          <span>نمایندگان</span>
          <b>Finance Manager Agent</b>
        </div>
      </article>
    </>
  );
}
