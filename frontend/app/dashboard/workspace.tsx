// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (workspace).
import { useState } from "react";
import { Heading, K, Risk, Status } from "./widgets";
import { fa, money, request } from "./shared";
import type { Alert, Rep } from "./types";

export function Representatives({
  reps,
  unmapped,
}: {
  reps: Rep[];
  unmapped?: number;
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