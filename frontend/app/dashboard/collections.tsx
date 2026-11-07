// بخشی از داشبورد مالی که از dashboard-client.tsx جدا شده است (collections).
import { useEffect, useMemo, useState } from "react";
import { RegCell, chequeNo } from "../cheque-reg";
import { Heading, Risk } from "./agents";
import { daysToDue, fa, fullToman, receivedChequeHoldingBucket, request } from "./shared";
import type { AgentResult, Case, TreasuryCheque } from "./types";

export const ALERT_TERM_DAYS = 90;
export const ALERT_TERM_AMOUNT_RIAL = 1_000_000_000; // 100M toman
export const chequeTermDays = (x: TreasuryCheque) => {
  const start = x.registration_date || x.receipt_date || x.document_date;
  if (!start || !x.due_date) return undefined;
  const from = new Date(`${String(start).slice(0, 10)}T00:00:00`), to = new Date(`${String(x.due_date).slice(0, 10)}T00:00:00`);
  return Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) ? undefined : Math.round((to.getTime() - from.getTime()) / 86400000);
};

export type CollectionAlertKey = "returned" | "overdue" | "soon" | "term";
export type CollectionAlertGroup = { title: string; tone: string; priority: "critical" | "high" | "medium"; items: TreasuryCheque[] };

export function collectionAlertGroups(rows: TreasuryCheque[]): Record<CollectionAlertKey, CollectionAlertGroup> {
  const portfolio = rows.filter((x) => receivedChequeHoldingBucket(x) !== "other");
  const isReturned = (x: TreasuryCheque) => receivedChequeHoldingBucket(x).startsWith("returned");
  return {
    returned: { title: "چک برگشتیِ تسویه‌نشده", tone: "danger", priority: "critical", items: portfolio.filter(isReturned) },
    overdue: { title: "سررسیدگذشته، وصول‌نشده", tone: "warn", priority: "high", items: portfolio.filter((x) => !isReturned(x) && (daysToDue(x) ?? 0) < 0) },
    soon: { title: "سررسید ۷ روز آینده", tone: "soon", priority: "medium", items: portfolio.filter((x) => { const d = daysToDue(x); return !isReturned(x) && d !== undefined && d >= 0 && d <= 7; }) },
    term: { title: "مدت چک بیش از ۹۰ روز و بالای ۱۰۰ میلیون", tone: "term", priority: "high", items: portfolio.filter((x) => !isReturned(x) && (chequeTermDays(x) ?? 0) > ALERT_TERM_DAYS && (x.amount || 0) > ALERT_TERM_AMOUNT_RIAL) },
  };
}
export const ALERT_KEYS: CollectionAlertKey[] = ["returned", "overdue", "soon", "term"];
// Customer names are matched loosely (Arabic/Persian letters, spacing) between cases and cheques.
export const customerKey = (name?: string) => String(name || "").replaceAll("ي", "ی").replaceAll("ك", "ک").replace(/[\s‌]+/g, " ").trim();
export const chequeSum = (items: TreasuryCheque[]) => items.reduce((s, x) => s + (x.amount || 0), 0);
export const chequeTiming = (x: TreasuryCheque) => {
  const d = daysToDue(x);
  return d === undefined ? "—" : d < 0 ? `${fa(-d)} روز گذشته` : d === 0 ? "امروز" : `${fa(d)} روز مانده`;
};
export const chequeStatusText = (x: TreasuryCheque) => String(x.state_label || x.cheque_status || "—").replaceAll("نزذ", "نزد");

export function CollectionAlerts({ groups, loading, openCaseKeys, busyKey, onCreateCase }: {
  groups: Record<CollectionAlertKey, CollectionAlertGroup>;
  loading: boolean;
  openCaseKeys: Set<string>;
  busyKey: string;
  onCreateCase: (x: TreasuryCheque, key: CollectionAlertKey) => void;
}) {
  const [active, setActive] = useState<CollectionAlertKey>("returned");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState<"" | "rahkaran" | "karamad">("");
  const [branch, setBranch] = useState("");
  const branchOf = (x: TreasuryCheque) => x.branch_name || x.branch || "";
  const current = groups[active].items;
  const branches = Array.from(new Set(current.map(branchOf).filter(Boolean))).sort((a, b) => a.localeCompare(b, "fa"));
  const q = search.trim().toLocaleLowerCase("fa-IR");
  const visible = current
    .filter((x) => !source || x.source_system === source)
    .filter((x) => !branch || branchOf(x) === branch)
    .filter((x) => !q || [x.counterpart_name, x.serial_number, x.sayad_number].filter(Boolean).some((v) => String(v).toLocaleLowerCase("fa-IR").includes(q)))
    .sort((a, b) => (b.amount || 0) - (a.amount || 0));
  const heading = <Heading h="هشدارهای وصول" p="چک‌های دریافتی که پیگیری لازم دارند؛ روی هر کارت کلیک کنید تا ریز چک‌ها با نام مشتری، شماره چک و مبلغ باز شود. «ساخت پرونده» پرونده وصول را مستقیم در صف پایین می‌سازد." />;
  if (loading) return <article className="fd-panel collection-alerts">{heading}<div className="profile-loading">در حال دریافت چک‌های دریافتی...</div></article>;
  return <article className="fd-panel collection-alerts">
    {heading}
    <section className="collection-alert-cards">
      {ALERT_KEYS.map((k) => <button key={k} className={`${groups[k].tone}${active === k ? " active" : ""}`}
        onClick={() => { setActive(k); setBranch(""); }}>
        <small>{groups[k].title}</small>
        <b>{fa(groups[k].items.length)} فقره</b>
        <span>{fullToman(chequeSum(groups[k].items))} تومان</span>
      </button>)}
    </section>
    <section className="cash-bank-toolbar cheque-list-search customer-search-toolbar collection-alert-filters">
      <div><b>جستجوی مشتری، شماره چک یا صیاد</b><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="نام، شماره چک یا صیاد..." /></div>
      <div><b>منبع</b><select value={source} onChange={(e) => setSource(e.target.value as any)}>
        <option value="">همه</option><option value="rahkaran">راهکاران</option><option value="karamad">کارآمد</option>
      </select></div>
      <div><b>شعبه</b><select value={branch} onChange={(e) => setBranch(e.target.value)}>
        <option value="">همه شعب</option>{branches.map((b) => <option key={b} value={b}>{b}</option>)}
      </select></div>
      <small>{fa(visible.length)} چک • {fullToman(chequeSum(visible))} تومان</small>
    </section>
    {visible.length ? <div className="cf-table collection-alert-table"><table>
      <thead><tr><th>مشتری</th><th>شماره چک</th><th>صیاد</th><th>مبلغ (تومان)</th><th>ثبت در سیستم</th><th>سررسید</th><th>زمان سررسید</th>{active === "term" && <th>مدت چک</th>}<th>وضعیت</th><th>منبع / شعبه</th><th>بانک</th><th>اقدام</th></tr></thead>
      <tbody>{visible.map((x) => {
        const key = customerKey(x.counterpart_name);
        return <tr key={`${x.source_system}-${x.cheque_id}-${x.serial_number}`}>
          <td className="cf-wrap"><b>{x.counterpart_name || "—"}</b></td>
          <td>{chequeNo(x.serial_number)}</td>
          <td>{chequeNo(x.sayad_number)}</td>
          <td className="cf-debt">{fullToman(x.amount || 0)}</td>
          <td><RegCell x={x} /></td>
          <td>{x.due_date_jalali || "—"}</td>
          <td>{chequeTiming(x)}</td>
          {active === "term" && <td>{fa(chequeTermDays(x) || 0)} روز</td>}
          <td>{chequeStatusText(x)}</td>
          <td>{x.source_system === "karamad" ? "کارآمد" : "راهکاران"}{branchOf(x) ? <small>{branchOf(x)}</small> : null}</td>
          <td>{x.bank_name || "—"}</td>
          <td>{!key ? "—" : openCaseKeys.has(key)
            ? <span className="collection-alert-has-case">پرونده باز دارد ✓</span>
            : <button className="collection-alert-action" disabled={busyKey === key} onClick={() => onCreateCase(x, active)}>
              {busyKey === key ? "در حال ساخت..." : "ساخت پرونده"}
            </button>}</td>
        </tr>;
      })}</tbody>
    </table></div> : <div className="invoice-source-pending">چکی در این دسته وجود ندارد.</div>}
  </article>;
}

export const CASE_STATUS_LABELS: Record<string, string> = { open: "باز", in_progress: "در حال پیگیری", resolved: "حل‌شده" };
export const CASE_PRIORITY_LABELS: Record<string, string> = { critical: "بحرانی", high: "زیاد", medium: "متوسط" };
export const CASE_DUE_DAYS: Record<string, number> = { critical: 1, high: 3, medium: 7 };
export const isoDateAfter = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
export const jalaliOf = (value?: string) => {
  if (!value) return "—";
  const d = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleDateString("fa-IR");
};

// Detail of one case: the customer's alerting cheques (live, matched by name), follow-ups and promises.
export function CaseDetail({ c, cheques }: { c: Case; cheques: { x: TreasuryCheque; keys: CollectionAlertKey[] }[] }) {
  const followups = c.followups || [], promises = c.promises || [];
  return <>
    {cheques.length ? <section className="case-cheques">
      <b>چک‌های هشداردار این مشتری: {fa(cheques.length)} فقره • {fullToman(chequeSum(cheques.map((r) => r.x)))} تومان</b>
      <div className="cf-table"><table>
        <thead><tr><th>شماره چک</th><th>مبلغ (تومان)</th><th>ثبت در سیستم</th><th>سررسید</th><th>زمان</th><th>وضعیت</th><th>هشدار</th></tr></thead>
        <tbody>{cheques.map(({ x, keys }) => <tr key={`${x.source_system}-${x.cheque_id}-${x.serial_number}`}>
          <td>{chequeNo(x.serial_number)}<small>{x.sayad_number ? chequeNo(x.sayad_number) : ""}</small></td>
          <td className="cf-debt">{fullToman(x.amount || 0)}</td>
          <td><RegCell x={x} /></td>
          <td>{x.due_date_jalali || "—"}</td>
          <td>{chequeTiming(x)}</td>
          <td>{chequeStatusText(x)}</td>
          <td>{keys.map((k) => <span key={k} className={`case-alert-tag ${k}`}>{collectionAlertShort[k]}</span>)}</td>
        </tr>)}</tbody>
      </table></div>
    </section> : <section className="case-cheques empty">این مشتری در حال حاضر چک هشداردار ندارد.</section>}
    {(followups.length > 0 || promises.length > 0) && <section className="case-history">
      {followups.slice(0, 3).map((f: any) => <small key={f.followup_id}>📞 {jalaliOf(f.created_at)}: {f.note || "تماس ثبت شد"}{f.created_by ? ` — ${f.created_by}` : ""}</small>)}
      {promises.map((p: any) => <small key={p.promise_id}>🤝 قول پرداخت {fullToman(p.amount || 0)} تومان تا {jalaliOf(p.promise_date)} ({p.status === "pending" ? "در انتظار" : p.status})</small>)}
    </section>}
  </>;
}
export const collectionAlertShort: Record<CollectionAlertKey, string> = { returned: "برگشتی", overdue: "سررسیدگذشته", soon: "سررسید نزدیک", term: "مدت بالای ۹۰ روز" };

export function Collections({
  cases,
  agent,
  refresh,
  received,
}: {
  cases: Case[];
  agent?: AgentResult;
  refresh: () => void;
  received: TreasuryCheque[];
}) {
  const [newCase, setNewCase] = useState({
    counterpart_name: "",
    assignee: "",
    due_at: "",
    priority: "high",
  });
  const [busyKey, setBusyKey] = useState("");
  const [message, setMessage] = useState("");
  const [highlight, setHighlight] = useState("");
  const create = async () => {
    if (!newCase.counterpart_name) return;
    await request("/collection-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newCase),
    });
    setNewCase({
      counterpart_name: "",
      assignee: "",
      due_at: "",
      priority: "high",
    });
    refresh();
  };

  const groups = useMemo(() => collectionAlertGroups(received), [received]);
  // Every alerting cheque per customer, each listed once with all the alerts it raises.
  const chequesByCustomer = useMemo(() => {
    const map = new Map<string, Map<TreasuryCheque, CollectionAlertKey[]>>();
    for (const k of ALERT_KEYS) for (const x of groups[k].items) {
      const key = customerKey(x.counterpart_name);
      if (!key) continue;
      const rows = map.get(key) || new Map();
      rows.set(x, [...(rows.get(x) || []), k]);
      map.set(key, rows);
    }
    return map;
  }, [groups]);
  const openCaseKeys = useMemo(() => new Set(cases.filter((c) => c.status !== "resolved").map((c) => customerKey(c.counterpart_name))), [cases]);

  const createFromAlert = async (x: TreasuryCheque, key: CollectionAlertKey) => {
    const name = (x.counterpart_name || "").trim(), nameKey = customerKey(name);
    if (!name || busyKey) return;
    // The case gets the most urgent alert this customer has, not only the one clicked.
    const customerAlerts = Array.from(chequesByCustomer.get(nameKey)?.values() || []).flat();
    const priority = customerAlerts.includes("returned") ? "critical" : customerAlerts.some((k) => k === "overdue" || k === "term") ? "high" : groups[key].priority;
    setBusyKey(nameKey); setMessage("");
    try {
      const result = await request("/collection-cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          counterpart_name: name,
          counterpart_ref: x.source_system === "rahkaran" ? x.counterpart_ref : undefined,
          priority,
          due_at: isoDateAfter(CASE_DUE_DAYS[priority]),
        }),
      });
      setMessage(`پرونده وصول «${name}» با اولویت ${CASE_PRIORITY_LABELS[priority]} و مهلت ${jalaliOf(isoDateAfter(CASE_DUE_DAYS[priority]))} ساخته شد.`);
      setHighlight(result?.case?.case_id || "");
      refresh();
    } catch (e) {
      setMessage(e instanceof Error ? `ساخت پرونده ناموفق بود: ${e.message}` : "ساخت پرونده ناموفق بود.");
    } finally {
      setBusyKey("");
    }
  };
  useEffect(() => {
    if (!highlight) return;
    document.getElementById(`case-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight, cases]);

  return (
    <>
      <CollectionAlerts groups={groups} loading={!received.length} openCaseKeys={openCaseKeys} busyKey={busyKey} onCreateCase={createFromAlert} />
      {message && <div className="collection-case-message">{message}</div>}
      <article className="fd-panel">
        <Heading
          h="ساخت پرونده وصول"
          p="برای هر مشتری مسئول، اولویت و مهلت تعیین کنید."
        />
        <div className="case-form">
          <input
            placeholder="نام مشتری"
            value={newCase.counterpart_name}
            onChange={(e) =>
              setNewCase({ ...newCase, counterpart_name: e.target.value })
            }
          />
          <input
            placeholder="مسئول پیگیری"
            value={newCase.assignee}
            onChange={(e) =>
              setNewCase({ ...newCase, assignee: e.target.value })
            }
          />
          <input
            type="date"
            value={newCase.due_at}
            onChange={(e) => setNewCase({ ...newCase, due_at: e.target.value })}
          />
          <select
            value={newCase.priority}
            onChange={(e) =>
              setNewCase({ ...newCase, priority: e.target.value })
            }
          >
            <option value="critical">بحرانی</option>
            <option value="high">زیاد</option>
            <option value="medium">متوسط</option>
          </select>
          <button onClick={create}>ایجاد پرونده</button>
        </div>
      </article>
      <article className="fd-panel">
        <Heading
          h="صف عملیات وصول"
          p={`${fa(cases.length)} پرونده • ${fa(cases.filter((c) => c.status !== "resolved").length)} پرونده باز؛ چک‌های هر پرونده زنده از سبد چک‌های دریافتی خوانده می‌شود.`}
        />
        <div className="case-grid case-grid-detailed">
          {cases.map((c) => {
            const cheques = Array.from(chequesByCustomer.get(customerKey(c.counterpart_name))?.entries() || [])
              .map(([x, keys]) => ({ x, keys }))
              .sort((a, b) => (b.x.amount || 0) - (a.x.amount || 0));
            return (
              <div key={c.case_id} id={`case-${c.case_id}`} className={highlight === c.case_id ? "case-new" : undefined}>
                <header>
                  <Risk
                    x={
                      c.priority === "critical"
                        ? "critical"
                        : c.priority === "high"
                          ? "danger"
                          : "safe"
                    }
                  />
                  <b>{c.counterpart_name}</b>
                  <span className={`case-status ${c.status}`}>{CASE_STATUS_LABELS[c.status] || c.status}</span>
                </header>
                <p>
                  اولویت: {CASE_PRIORITY_LABELS[c.priority] || c.priority} • مسئول: {c.assignee || "تعیین نشده"} • مهلت: {jalaliOf(c.due_at)}
                </p>
                <small>
                  {fa(c.followups?.length)} پیگیری • {fa(c.promises?.length)} قول
                  پرداخت
                </small>
                {received.length ? <CaseDetail c={c} cheques={cheques} /> : null}
                <CaseActions c={c} refresh={refresh} />
              </div>
            );
          })}
        </div>
      </article>
    </>
  );
}

export function CaseActions({ c, refresh }: { c: Case; refresh: () => void }) {
  const [note, setNote] = useState(""),
    [amount, setAmount] = useState(""),
    [date, setDate] = useState("");
  const post = async (kind: "followups" | "promises") => {
    let body =
      kind === "followups"
        ? { channel: "call", result: "contacted", note, created_by: c.assignee }
        : {
            amount: Number(amount) * 10,
            promise_date: date,
            status: "pending",
          };
    await request(`/collection-cases/${c.case_id}/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setNote("");
    setAmount("");
    setDate("");
    refresh();
  };
  const status = async (x: string) => {
    await request(`/collection-cases/${c.case_id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: x }),
    });
    refresh();
  };
  return (
    <div className="case-actions">
      <div>
        <input
          placeholder="یادداشت تماس"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button onClick={() => post("followups")}>ثبت پیگیری</button>
      </div>
      <div>
        <input
          inputMode="numeric"
          placeholder="مبلغ قول پرداخت (تومان)"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
        <button onClick={() => post("promises")}>ثبت قول</button>
      </div>
      <footer>
        <button onClick={() => status("in_progress")}>در حال پیگیری</button>
        <button onClick={() => status("resolved")}>حل‌شده</button>
      </footer>
    </div>
  );
}
