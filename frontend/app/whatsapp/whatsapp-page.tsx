"use client";
// «ارسال واتساپ» — بدهی مشتری، چک‌های پیش‌رو و اکسل ویزیتورها، خودکار در ساعت مشخص (بک‌اند: app/services/whatsapp).
// ارسال از طریق WAHA روی همین سرور. پیام‌ها پیش‌فرض اول در «صف پیام‌ها» منتظر تأیید می‌مانند.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import "./whatsapp.css";

const API = "/api/v1/whatsapp";
const nf = new Intl.NumberFormat("fa-IR", { maximumFractionDigits: 0 });
const fa = (v: number | null | undefined) => nf.format(v || 0);
const faDigits = (v: unknown) => String(v ?? "").replace(/[0-9]/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
const toman = (rial: number | null | undefined) => `${fa(Math.round((rial || 0) / 10))} تومان`;
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("fa-IR", { dateStyle: "short", timeStyle: "short" }) : "—");

async function call(path: string, method = "GET", body?: unknown) {
  const r = await fetch(`${API}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const DAY_LABEL: Record<string, string> = { sat: "شنبه", sun: "یکشنبه", mon: "دوشنبه", tue: "سه‌شنبه", wed: "چهارشنبه", thu: "پنجشنبه", fri: "جمعه" };
const STATUS_LABEL: Record<string, string> = {
  pending: "منتظر تأیید", approved: "در صف ارسال", sending: "در حال ارسال", sent: "ارسال شد",
  failed: "ناموفق", no_whatsapp: "واتساپ ندارد", skipped: "لغو شده",
};
const WAHA_STATUS: Record<string, string> = {
  WORKING: "وصل است", SCAN_QR_CODE: "منتظر اسکن QR", STARTING: "در حال راه‌اندازی", STOPPED: "متوقف",
  FAILED: "خطا — دوباره وصل کنید", NOT_CREATED: "هنوز وصل نشده", UNREACHABLE: "WAHA در دسترس نیست",
};
const PLACEHOLDERS: Record<string, string> = {
  customer_debt: "{name} {code} {debt} {date} {branch}",
  customer_cheques: "{name} {code} {days} {count} {cheques} {total} {date} {branch}",
  visitor_report: "{name} {date} {days} {debtor_count} {debt} {cheque_count} {cheque_total} {branch}",
};

type Rule = {
  id: number; title: string; kind: string; kind_title: string; enabled: boolean; auto_send: boolean;
  days: string[]; hour: number; minute: number; params: Record<string, any>; template: string;
  last_run_at?: string | null; last_result?: Record<string, any> | null;
};
type Item = {
  id: number; rule_id: number; kind: string; recipient_kind: string; recipient_ref: string; recipient_name: string;
  branch?: string; phone?: string; message: string; file_name?: string; amount_rial?: number; status: string;
  created_at: string; sent_at?: string; error?: string; approved_by?: string;
};

type Tab = "connection" | "rules" | "outbox" | "recipients";

export default function WhatsAppPage() {
  const [tab, setTab] = useState<Tab>("connection");
  const [status, setStatus] = useState<any>(null);
  const [error, setError] = useState("");
  const loadStatus = useCallback(() => call("/status").then(setStatus).catch((e) => setError(e.message)), []);
  useEffect(() => {
    void loadStatus();
    const id = window.setInterval(loadStatus, 15000);
    return () => window.clearInterval(id);
  }, [loadStatus]);
  const counts = status?.counts || {};
  const tabs: [Tab, string, string][] = [
    ["connection", "اتصال و وضعیت", WAHA_STATUS[status?.waha?.status] || "…"],
    ["rules", "قاعده‌های ارسال", "چه چیزی، به چه کسی، چه ساعتی"],
    ["outbox", "صف پیام‌ها", `${fa(counts.pending)} منتظر تأیید · ${fa(counts.approved)} در صف`],
    ["recipients", "دفترچه گیرنده‌ها", "شماره جایگزین و لغو ارسال"],
  ];
  return (
    <div className="wa-page">
      <div className="wa-tabs">
        {tabs.map(([k, t, s]) => (
          <button key={k} type="button" className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
            {t}<small>{s}</small>
          </button>
        ))}
      </div>
      {!status?.enabled && status && (
        <div className="wa-banner warn">
          ارسال واتساپ خاموش است. بعد از وصل کردن شماره، در فایل <code>backend/.env</code> مقدار <code>WHATSAPP_ENABLED=true</code> را بگذارید
          و بک‌اند را دوباره اجرا کنید. تا آن موقع می‌توانید قاعده‌ها را بسازید و پیش‌نمایش بگیرید.
        </div>
      )}
      {status?.test_phone && (
        <div className="wa-banner info">حالت آزمایشی: همه پیام‌ها فقط به شماره {faDigits(status.test_phone)} می‌رود، نه به مشتری‌ها (WHATSAPP_TEST_PHONE).</div>
      )}
      {error && <div className="wa-banner bad" onClick={() => setError("")}>{error}</div>}
      {tab === "connection" && <Connection status={status} reload={loadStatus} onError={setError} />}
      {tab === "rules" && <Rules onError={setError} goOutbox={() => { setTab("outbox"); void loadStatus(); }} />}
      {tab === "outbox" && <Outbox onError={setError} reloadStatus={loadStatus} enabled={!!status?.enabled} />}
      {tab === "recipients" && <Recipients onError={setError} />}
    </div>
  );
}

// ------------------------------------------------------------------ اتصال
function Connection({ status, reload, onError }: { status: any; reload: () => void; onError: (m: string) => void }) {
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phone, setPhone] = useState("");
  const [text, setText] = useState("پیام آزمایشی از سامانه اکسیر");
  const [msg, setMsg] = useState("");
  const waha = status?.waha || {};
  const wahaStatus: string = waha.status || "";

  useEffect(() => {
    if (wahaStatus !== "SCAN_QR_CODE") { setQr(null); return; }
    const load = () => call("/session/qr").then((j) => setQr(`data:${j.mimetype || "image/png"};base64,${j.data}`)).catch(() => setQr(null));
    load();
    const id = window.setInterval(() => { load(); reload(); }, 8000);
    return () => window.clearInterval(id);
  }, [wahaStatus, reload]);

  const act = async (fn: () => Promise<any>, ok?: string) => {
    setBusy(true);
    setMsg("");
    try { await fn(); if (ok) setMsg(ok); reload(); } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };
  const w = status?.worker || {};
  return (
    <section className="wa-section">
      <div className="wa-kpis">
        <div className={`wa-kpi ${wahaStatus === "WORKING" ? "good" : "watch"}`}>
          <small>اتصال واتساپ</small><b>{WAHA_STATUS[wahaStatus] || wahaStatus || "…"}</b>
          <span>{waha.me?.id ? `شماره: ${faDigits(String(waha.me.id).split("@")[0])}` : waha.url}</span>
        </div>
        <div className={`wa-kpi ${status?.enabled ? "good" : "watch"}`}>
          <small>ارسال</small><b>{status?.enabled ? "روشن" : "خاموش"}</b>
          <span>ساعت مجاز {faDigits(status?.send_window?.[0])} تا {faDigits(status?.send_window?.[1])}</span>
        </div>
        <div className="wa-kpi">
          <small>ارسال امروز</small><b>{fa(status?.sent_today)} از {fa(status?.daily_limit)}</b>
          <span>فاصله بین پیام‌ها {faDigits(status?.delay_seconds?.[0])} تا {faDigits(status?.delay_seconds?.[1])} ثانیه</span>
        </div>
        <div className={`wa-kpi ${w.running ? "good" : ""}`}>
          <small>ارسال‌کننده صف</small><b>{w.running ? "در حال ارسال" : "بیکار"}</b>
          <span>{w.stopped_reason || (w.last_sent_at ? `آخرین ارسال ${when(w.last_sent_at)}` : "—")}</span>
        </div>
      </div>
      {w.last_error && <div className="wa-banner bad">آخرین خطا: {w.last_error}</div>}

      <div className="wa-grid2">
        <article className="wa-card">
          <h3>اتصال شماره واتساپ</h3>
          {!waha.reachable ? (
            <p className="wa-muted">
              WAHA روی سرور اجرا نیست. فایل <code>START_WAHA.bat</code> را در پوشه اصلی پروژه اجرا کنید (Docker Desktop باید روشن باشد).
              {waha.error && <><br /><small>{waha.error}</small></>}
            </p>
          ) : wahaStatus === "WORKING" ? (
            <>
              <p className="wa-muted">شماره وصل است. برای عوض کردن شماره، اول خارج شوید.</p>
              <button type="button" className="wa-btn ghost" disabled={busy} onClick={() => confirm("شماره از WAHA خارج شود؟") && act(() => call("/session/logout", "POST"))}>خروج شماره</button>
            </>
          ) : (
            <>
              <p className="wa-muted">
                بهتر است یک شماره جدا برای شرکت (واتساپ بیزینس) استفاده کنید. در گوشی: واتساپ ← دستگاه‌های متصل ← اتصال دستگاه، و QR زیر را اسکن کنید.
              </p>
              {qr ? <img className="wa-qr" src={qr} alt="QR واتساپ" /> : (
                <button type="button" className="wa-btn" disabled={busy} onClick={() => act(() => call("/session/start", "POST"))}>
                  {busy ? "…" : "شروع اتصال و نمایش QR"}
                </button>
              )}
            </>
          )}
        </article>
        <article className="wa-card">
          <h3>پیام آزمایشی</h3>
          <label>شماره موبایل<input dir="ltr" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0912..." /></label>
          <label>متن<textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} /></label>
          <button type="button" className="wa-btn" disabled={busy || !phone} onClick={() => act(() => call("/test", "POST", { phone, text }), "پیام ارسال شد.")}>ارسال آزمایشی</button>
          {msg && <p className="wa-ok">{msg}</p>}
        </article>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ قاعده‌ها
function Rules({ onError, goOutbox }: { onError: (m: string) => void; goOutbox: () => void }) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [branches, setBranches] = useState<{ id: number; name: string }[]>([]);
  const [newKind, setNewKind] = useState("customer_debt");
  const load = useCallback(() => call("/rules").then((j) => { setRules(j.rules); setKinds(j.kinds); }).catch((e) => onError(e.message)), [onError]);
  useEffect(() => { void load(); call("/branches").then((j) => setBranches(j.branches || [])).catch(() => setBranches([])); }, [load]);
  return (
    <section className="wa-section">
      <p className="wa-muted">
        هر قاعده در روزها و ساعت انتخابی، پیام‌ها را از داده زنده کارآمد می‌سازد. اگر «ارسال خودکار» خاموش باشد، پیام‌ها در «صف پیام‌ها» منتظر تأیید شما می‌مانند.
        برای شروع، ارسال خودکار را خاموش نگه دارید تا چند دوره پیام‌ها را خودتان ببینید.
      </p>
      {rules.map((r) => <RuleCard key={r.id} rule={r} branches={branches} reload={load} onError={onError} goOutbox={goOutbox} />)}
      <div className="wa-add">
        <select value={newKind} onChange={(e) => setNewKind(e.target.value)}>
          {Object.entries(kinds).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
        </select>
        <button type="button" className="wa-btn ghost" onClick={() => call("/rules", "POST", { kind: newKind }).then(load).catch((e) => onError(e.message))}>+ قاعده جدید</button>
      </div>
    </section>
  );
}

function RuleCard({ rule, branches, reload, onError, goOutbox }: { rule: Rule; branches: { id: number; name: string }[]; reload: () => void; onError: (m: string) => void; goOutbox: () => void }) {
  const [r, setR] = useState<Rule>(rule);
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState<any>(null);
  useEffect(() => setR(rule), [rule]);
  const dirty = JSON.stringify(r) !== JSON.stringify(rule);
  const p = r.params || {};
  const setP = (k: string, v: any) => setR({ ...r, params: { ...p, [k]: v } });
  const save = async () => {
    await call(`/rules/${r.id}`, "PUT", { title: r.title, enabled: r.enabled, auto_send: r.auto_send, days: r.days, hour: r.hour, minute: r.minute, params: r.params, template: r.template });
    reload();
  };
  const run = async (what: "save" | "preview" | "run" | "delete") => {
    setBusy(what);
    try {
      if (what === "save") await save();
      if (what === "preview") { if (dirty) await save(); setPreview(await call(`/rules/${r.id}/preview`, "POST")); }
      if (what === "run") {
        if (dirty) await save();
        const res = await call(`/rules/${r.id}/run`, "POST");
        alert(`${faDigits(res.added)} پیام به صف اضافه شد${res.duplicates ? ` (${faDigits(res.duplicates)} تکراری امروز نادیده گرفته شد)` : ""}.`);
        goOutbox();
      }
      if (what === "delete" && confirm(`قاعده «${r.title}» حذف شود؟`)) { await call(`/rules/${r.id}`, "DELETE"); reload(); }
    } catch (e: any) { onError(e.message); } finally { setBusy(""); }
  };
  const last = r.last_result;
  return (
    <article className={`wa-card wa-rule${r.enabled ? " on" : ""}`}>
      <div className="wa-rule-head">
        <input className="wa-title" value={r.title} onChange={(e) => setR({ ...r, title: e.target.value })} />
        <span className="wa-chip">{r.kind_title}</span>
        <label className="wa-switch"><input type="checkbox" checked={r.enabled} onChange={(e) => setR({ ...r, enabled: e.target.checked })} />فعال</label>
        <label className="wa-switch" title="بدون تأیید دستی، مستقیم ارسال شود"><input type="checkbox" checked={r.auto_send} onChange={(e) => setR({ ...r, auto_send: e.target.checked })} />ارسال خودکار بدون تأیید</label>
      </div>
      <div className="wa-row">
        <div className="wa-days">
          {Object.keys(DAY_LABEL).map((d) => (
            <button key={d} type="button" className={r.days.includes(d) ? "active" : ""}
              onClick={() => setR({ ...r, days: r.days.includes(d) ? r.days.filter((x) => x !== d) : [...r.days, d] })}>{DAY_LABEL[d]}</button>
          ))}
        </div>
        <label className="wa-time">ساعت
          <input type="number" min={0} max={23} value={r.hour} onChange={(e) => setR({ ...r, hour: Number(e.target.value) })} />:
          <input type="number" min={0} max={59} value={r.minute} onChange={(e) => setR({ ...r, minute: Number(e.target.value) })} />
        </label>
      </div>
      <div className="wa-row">
        {r.kind !== "customer_cheques" && (
          <label>حداقل بدهی (تومان)<input type="number" min={0} value={p.min_debt_toman ?? 0} onChange={(e) => setP("min_debt_toman", Number(e.target.value))} /></label>
        )}
        {r.kind !== "customer_debt" && (
          <label>چک‌های چند روز آینده<input type="number" min={0} max={90} value={p.days_ahead ?? 3} onChange={(e) => setP("days_ahead", Number(e.target.value))} /></label>
        )}
        {r.kind === "visitor_report" && (
          <label className="wa-switch"><input type="checkbox" checked={p.attach_excel !== false} onChange={(e) => setP("attach_excel", e.target.checked)} />پیوست فایل اکسل</label>
        )}
        <label>شعبه‌ها
          <select multiple value={(p.branch_ids || []).map(String)} onChange={(e) => setP("branch_ids", Array.from(e.target.selectedOptions).map((o) => Number(o.value)))}>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <small>هیچ‌کدام = همه شعب</small>
        </label>
      </div>
      <label>متن پیام<textarea rows={5} value={r.template} onChange={(e) => setR({ ...r, template: e.target.value })} />
        <small dir="ltr">{PLACEHOLDERS[r.kind]}</small>
      </label>
      <div className="wa-actions">
        <button type="button" className="wa-btn" disabled={!dirty || !!busy} onClick={() => run("save")}>{busy === "save" ? "…" : "ذخیره"}</button>
        <button type="button" className="wa-btn ghost" disabled={!!busy} onClick={() => run("preview")}>{busy === "preview" ? "در حال خواندن از کارآمد…" : "پیش‌نمایش"}</button>
        <button type="button" className="wa-btn ghost" disabled={!!busy} onClick={() => run("run")}>{busy === "run" ? "…" : "ساختن پیام‌ها الان (برای تأیید)"}</button>
        <button type="button" className="wa-btn danger" disabled={!!busy} onClick={() => run("delete")}>حذف</button>
        {last && (
          <small className="wa-muted">
            آخرین اجرا {when(r.last_run_at)}: {last.error ? `خطا: ${last.error}` : `${faDigits(last.added ?? 0)} پیام · ${faDigits(last.no_phone ?? 0)} بدون شماره`}
          </small>
        )}
      </div>
      {preview && <Preview data={preview} close={() => setPreview(null)} />}
    </article>
  );
}

function Preview({ data, close }: { data: any; close: () => void }) {
  const s = data.stats || {};
  return (
    <div className="wa-preview">
      <div className="wa-preview-head">
        <b>پیش‌نمایش: {fa(s.ready)} پیام آماده</b>
        <small>{fa(s.candidates)} گیرنده واجد شرایط · {fa(s.no_phone)} بدون موبایل معتبر · {fa(s.opted_out)} لغو ارسال</small>
        <button type="button" className="wa-btn ghost" onClick={close}>بستن</button>
      </div>
      {s.no_phone_names?.length > 0 && (
        <details><summary>بدون شماره موبایل ({fa(s.no_phone)}) — در «دفترچه گیرنده‌ها» شماره بدهید</summary><p className="wa-muted">{s.no_phone_names.join("، ")}</p></details>
      )}
      <div className="wa-msgs">
        {(data.items || []).map((it: any, i: number) => (
          <div key={i} className="wa-msg">
            <div><b>{it.recipient_name}</b> <small dir="ltr">{it.phone}</small> {it.branch && <small>· {it.branch}</small>}{it.file_name && <small> · 📎 {it.file_name}</small>}</div>
            <pre>{it.message}</pre>
          </div>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ صف پیام‌ها
function Outbox({ onError, reloadStatus, enabled }: { onError: (m: string) => void; reloadStatus: () => void; enabled: boolean }) {
  const [filter, setFilter] = useState("pending");
  const [items, setItems] = useState<Item[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => call(`/outbox?limit=1000${filter ? `&status=${filter}` : ""}`)
    .then((j) => { setItems(j.items); setCounts(j.counts || {}); setSel(new Set()); })
    .catch((e) => onError(e.message)), [filter, onError]);
  useEffect(() => {
    void load();
    const id = window.setInterval(load, 20000);
    return () => window.clearInterval(id);
  }, [load]);
  const act = async (fn: () => Promise<any>) => {
    setBusy(true);
    try { await fn(); await load(); reloadStatus(); } catch (e: any) { onError(e.message); } finally { setBusy(false); }
  };
  const ids = [...sel];
  const total = useMemo(() => items.reduce((s, x) => s + (x.amount_rial || 0), 0), [items]);
  const toggleAll = () => setSel(sel.size === items.length ? new Set() : new Set(items.map((x) => x.id)));
  const optOut = (it: Item) => confirm(`برای «${it.recipient_name}» دیگر هیچ پیامی ارسال نشود؟`) &&
    act(() => call("/recipients", "POST", { kind: it.recipient_kind, ref: it.recipient_ref, name: it.recipient_name, opted_out: true })
      .then(() => call("/outbox/skip", "POST", { ids: [it.id] })));
  return (
    <section className="wa-section">
      <div className="wa-seg">
        {["pending", "approved", "sent", "failed", "no_whatsapp", "skipped", ""].map((s) => (
          <button key={s || "all"} type="button" className={filter === s ? "active" : ""} onClick={() => setFilter(s)}>
            {s ? STATUS_LABEL[s] : "همه"} {s && <small>{fa(counts[s])}</small>}
          </button>
        ))}
      </div>
      <div className="wa-actions">
        <button type="button" className="wa-btn" disabled={busy || !ids.length} onClick={() => act(() => call("/outbox/approve", "POST", { ids }))}>تأیید انتخاب‌شده‌ها ({fa(ids.length)})</button>
        {filter === "pending" && (
          <button type="button" className="wa-btn ghost" disabled={busy || !items.length}
            onClick={() => confirm(`همه ${fa(counts.pending)} پیام منتظر تأیید، ارسال شوند؟`) && act(() => call("/outbox/approve", "POST", { all_pending: true }))}>تأیید همه</button>
        )}
        <button type="button" className="wa-btn danger" disabled={busy || !ids.length} onClick={() => act(() => call("/outbox/skip", "POST", { ids }))}>لغو انتخاب‌شده‌ها</button>
        <button type="button" className="wa-btn ghost" disabled={busy || !enabled || !counts.approved} onClick={() => act(() => call("/outbox/send-now", "POST"))}>شروع ارسال صف</button>
        <small className="wa-muted">{fa(items.length)} پیام · جمع مبالغ {toman(total)}</small>
      </div>
      <div className="wa-table">
        <table>
          <thead><tr>
            <th><input type="checkbox" checked={!!items.length && sel.size === items.length} onChange={toggleAll} /></th>
            <th>گیرنده</th><th>موبایل</th><th>شعبه</th><th>مبلغ</th><th>نوع</th><th>ساخته‌شده</th><th>وضعیت</th><th></th>
          </tr></thead>
          <tbody>
            {items.map((it) => (
              <Fragment key={it.id}>
                <tr className={open === it.id ? "open" : ""} onClick={() => setOpen(open === it.id ? null : it.id)}>
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={sel.has(it.id)} onChange={() => { const n = new Set(sel); if (n.has(it.id)) n.delete(it.id); else n.add(it.id); setSel(n); }} />
                  </td>
                  <td><b>{it.recipient_name}</b><small>{it.recipient_kind === "visitor" ? "ویزیتور" : "مشتری"}</small></td>
                  <td dir="ltr">{it.phone}</td>
                  <td>{it.branch || "—"}</td>
                  <td>{it.amount_rial ? toman(it.amount_rial) : "—"}</td>
                  <td>{{ customer_debt: "بدهی", customer_cheques: "چک پیش‌رو", visitor_report: "گزارش ویزیتور" }[it.kind] || it.kind}{it.file_name && " 📎"}</td>
                  <td>{when(it.created_at)}</td>
                  <td><span className={`wa-st ${it.status}`}>{STATUS_LABEL[it.status] || it.status}</span>{it.sent_at && <small>{when(it.sent_at)}</small>}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <button type="button" className="wa-link" title="دیگر برای این گیرنده ارسال نشود" onClick={() => optOut(it)}>⊘</button>
                  </td>
                </tr>
                {open === it.id && (
                  <tr className="wa-detail"><td colSpan={9}>
                    <pre>{it.message}</pre>
                    {it.file_name && <a href={`${API}/outbox/${it.id}/file`}>⬇ {it.file_name}</a>}
                    {it.error && <p className="wa-bad">{it.error}</p>}
                    {it.approved_by && <small className="wa-muted">تأیید: {it.approved_by}</small>}
                  </td></tr>
                )}
              </Fragment>
            ))}
            {!items.length && <tr><td colSpan={9} className="wa-empty">پیامی نیست.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ دفترچه گیرنده‌ها
function Recipients({ onError }: { onError: (m: string) => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const empty = { kind: "visitor", ref: "", name: "", phone: "", opted_out: false, note: "" };
  const [f, setF] = useState(empty);
  const load = useCallback(() => call("/recipients").then((j) => setRows(j.recipients)).catch((e) => onError(e.message)), [onError]);
  useEffect(() => { void load(); }, [load]);
  const save = () => call("/recipients", "POST", f).then(() => { setF(empty); load(); }).catch((e) => onError(e.message));
  return (
    <section className="wa-section">
      <p className="wa-muted">
        شماره پیش‌فرض هر گیرنده همان موبایل ثبت‌شده در کارآمد است. اینجا می‌توانید برای یک مشتری (کد تفصیلی DL) یا ویزیتور (شناسه ویزیتور کارآمد) شماره دیگری بدهید یا ارسال را برایش قطع کنید.
        شناسه را از ستون گیرنده در «صف پیام‌ها» یا پیش‌نمایش قاعده بردارید.
      </p>
      <article className="wa-card wa-form">
        <label>نوع<select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="visitor">ویزیتور</option><option value="customer">مشتری</option></select></label>
        <label>شناسه<input dir="ltr" value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value })} /></label>
        <label>نام<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label>موبایل<input dir="ltr" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="0912..." /></label>
        <label className="wa-switch"><input type="checkbox" checked={f.opted_out} onChange={(e) => setF({ ...f, opted_out: e.target.checked })} />ارسال نشود</label>
        <label>یادداشت<input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
        <button type="button" className="wa-btn" disabled={!f.ref || (!f.phone && !f.opted_out)} onClick={save}>ثبت</button>
      </article>
      <div className="wa-table">
        <table>
          <thead><tr><th>نوع</th><th>شناسه</th><th>نام</th><th>موبایل</th><th>وضعیت</th><th>یادداشت</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.kind}-${r.ref}`}>
                <td>{r.kind === "visitor" ? "ویزیتور" : "مشتری"}</td><td dir="ltr">{r.ref}</td><td>{r.name}</td><td dir="ltr">{r.phone || "—"}</td>
                <td>{r.opted_out ? <span className="wa-st skipped">ارسال نشود</span> : "شماره جایگزین"}</td><td>{r.note}</td>
                <td><button type="button" className="wa-link" onClick={() => call(`/recipients/${r.kind}/${encodeURIComponent(r.ref)}`, "DELETE").then(load).catch((e) => onError(e.message))}>حذف</button></td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={7} className="wa-empty">هنوز موردی ثبت نشده.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
