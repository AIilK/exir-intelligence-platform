"use client";
// الارم‌های هر ماژول (جایگزین کارت‌های Agent): هر کاربر فقط الارم ماژول‌های خودش را می‌گیرد.
// Backend: GET/PATCH /api/v1/alarms — همان هشدارهای قاعده‌محور اجرای روزانه، فیلترشده با سطح دسترسی.
// «دیده شد / انجام شد / نادیده» برای هر شخص جداگانه در دیتابیس ذخیره می‌شود (my_status)؛ اگر الارمی رفع و دوباره
// ظاهر شود، دوباره باز می‌شود. localStorage فقط برای اینکه اعلان کشویی یک الارم دو بار نیاید.
// زنگوله سربرگ، اعلان‌های لحظه‌ای (toast) برای الارم تازه، نوار الارم بالای هر صفحه و مرکز الارم‌ها.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./alarms.css";

export type Level = "critical" | "high" | "medium" | "info";
export type Alarm = {
  key: string; agent_key: string; module: string; module_title: string; view?: string | null; level: Level; title: string;
  why: string[]; action?: string | null; evidence: { label: string; value: string }[]; first_seen: string; last_seen: string;
  repeats: number; status: string;
  my_status: MyStatus; my_updated_at?: string | null;
};
export type MyStatus = "open" | "seen" | "done" | "dismissed";
/** الارم‌هایی که هنوز برای همین کاربر باز است (نه انجام‌شده، نه نادیده) */
const pending = (a: Alarm) => a.my_status === "open" || a.my_status === "seen";

const apiHost = () => (typeof window !== "undefined" ? window.location.hostname : "127.0.0.1");
const API = () => `http://${apiHost()}:8000/api/v1/alarms`;
const POLL_MS = 60_000;
export const LEVEL_FA: Record<Level, string> = { critical: "فوری", high: "مهم", medium: "قابل توجه", info: "اطلاع" };
const LEVEL_ICON: Record<Level, string> = { critical: "⚠", high: "◆", medium: "●", info: "ℹ" };
const RANK: Record<Level, number> = { critical: 0, high: 1, medium: 2, info: 3 };
const faNum = (n: number) => n.toLocaleString("fa-IR");
const when = (iso?: string) => {
  if (!iso) return "";
  try { return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)); }
  catch { return iso.slice(0, 16); }
};

// ------------------------------------------------------------------ store مشترک (یک بار دریافت برای همه اجزا)
type Snapshot = { alarms: Alarm[]; loaded: boolean; fresh: Alarm[] };
let snapshot: Snapshot = { alarms: [], loaded: false, fresh: [] };
const listeners = new Set<(s: Snapshot) => void>();
let timer: number | null = null;
let seenKey = "exir-alarms-seen";

function readSeen(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(seenKey) || "[]")); } catch { return new Set(); }
}
function writeSeen(keys: Set<string>) {
  try { localStorage.setItem(seenKey, JSON.stringify([...keys].slice(-800))); } catch { /* storage unavailable */ }
}
function publish(next: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...next };
  listeners.forEach((fn) => fn(snapshot));
}
export async function refreshAlarms() {
  try {
    const r = await fetch(API());
    if (!r.ok) throw Error(String(r.status));
    const j = await r.json();
    const alarms: Alarm[] = (j.alarms || []).sort((a: Alarm, b: Alarm) => RANK[a.level] - RANK[b.level]);
    const seen = readSeen();
    const firstLoad = !snapshot.loaded;
    const fresh = alarms.filter((a) => !seen.has(a.key) && a.my_status === "open");
    publish({ alarms, loaded: true, fresh: firstLoad ? fresh.slice(0, 4) : fresh.filter((a) => !snapshot.alarms.some((x) => x.key === a.key)).slice(0, 4) });
  } catch {
    publish({ loaded: true });
  }
}
export function startAlarms(userKey: string) {
  seenKey = `exir-alarms-seen:${userKey}`;
  snapshot = { alarms: [], loaded: false, fresh: [] };
  void refreshAlarms();
  if (timer) window.clearInterval(timer);
  timer = window.setInterval(() => void refreshAlarms(), POLL_MS);
}
export function stopAlarms() {
  if (timer) window.clearInterval(timer);
  timer = null;
}
function markSeen(keys: string[]) {
  const seen = readSeen();
  keys.forEach((k) => seen.add(k));
  writeSeen(seen);
}
export async function setStatus(key: string, status: MyStatus) {
  markSeen([key]);
  publish({ alarms: snapshot.alarms.map((a) => (a.key === key ? { ...a, my_status: status, my_updated_at: new Date().toISOString() } : a)) });
  await fetch(`${API()}/${encodeURIComponent(key)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }).catch(() => undefined);
}
const MY_FA: Record<MyStatus, string> = { open: "باز", seen: "دیده‌شده", done: "انجام‌شده", dismissed: "نادیده‌گرفته" };
export function useAlarms() {
  const [s, setS] = useState(snapshot);
  useEffect(() => {
    listeners.add(setS);
    setS(snapshot);
    return () => { listeners.delete(setS); };
  }, []);
  return s;
}

// ------------------------------------------------------------------ کارت الارم
function AlarmCard({ a, onGo, index = 0, compact = false }: { a: Alarm; onGo?: (view: string) => void; index?: number; compact?: boolean }) {
  const [open, setOpen] = useState(!compact);
  return <article className={`al-card ${a.level}${a.my_status !== "open" ? " seen" : ""}${a.my_status === "done" ? " done" : ""}`} style={{ animationDelay: `${Math.min(index, 10) * 70}ms` }}>
    <span className="al-glow" aria-hidden />
    <header onClick={() => compact && setOpen(!open)} style={compact ? { cursor: "pointer" } : undefined}>
      <span className={`al-badge ${a.level}`}><i>{LEVEL_ICON[a.level]}</i>{LEVEL_FA[a.level]}</span>
      <b>{a.title}</b>
    </header>
    {open && <>
      {a.why.length > 0 && <ul>{a.why.slice(0, 2).map((w, i) => <li key={i}>{w}</li>)}</ul>}
      {a.evidence.length > 0 && <div className="al-evidence">{a.evidence.map((e, i) => <span key={i}>{e.label}: <b>{e.value}</b></span>)}</div>}
      {a.action && <p className="al-action">➜ {a.action}</p>}
    </>}
    <footer>
      <small>{a.module_title} · {a.repeats > 1 ? `${faNum(a.repeats)} بار پشت‌سرهم · از ${when(a.first_seen)}` : `تازه · ${when(a.last_seen)}`}</small>
      <span>
        {onGo && a.view && <button type="button" onClick={() => onGo(a.view!)}>مشاهده ←</button>}
        {pending(a) ? <>
          <button type="button" className="ok" onClick={() => setStatus(a.key, "done")} title="کارش انجام شد؛ برای شما ذخیره می‌شود">✓ انجام شد</button>
          {a.my_status === "open" && <button type="button" onClick={() => setStatus(a.key, "seen")}>دیده شد</button>}
          <button type="button" className="ghost" onClick={() => setStatus(a.key, "dismissed")} title="نادیده بگیر">✕</button>
        </> : <>
          <em className="al-my">{MY_FA[a.my_status]}{a.my_updated_at ? ` · ${when(a.my_updated_at)}` : ""}</em>
          <button type="button" className="ghost" onClick={() => setStatus(a.key, "open")}>برگرداندن</button>
        </>}
      </span>
    </footer>
  </article>;
}

// ------------------------------------------------------------------ زنگوله سربرگ
export function AlarmBell({ onGo }: { onGo: (view: string) => void }) {
  const { alarms: all, loaded } = useAlarms();
  const alarms = all.filter(pending);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const unseen = alarms.filter((a) => a.my_status === "open").length;
  const urgent = alarms.some((a) => a.my_status === "open" && (a.level === "critical" || a.level === "high"));
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return <div className="al-bell-box" ref={box}>
    <button type="button" className={`al-bell${unseen ? " ring" : ""}${urgent ? " urgent" : ""}`} onClick={() => { setOpen(!open); if (!open) markSeen(alarms.map((a) => a.key)); }}
      aria-label={`الارم‌ها: ${faNum(alarms.length)} باز، ${faNum(unseen)} دیده‌نشده`} aria-expanded={open}>
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden><path d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6V11a7 7 0 0 0-5.5-6.84V3.5a1.5 1.5 0 0 0-3 0v.66A7 7 0 0 0 5 11v5l-2 2v1h18v-1Z" fill="currentColor" /></svg>
      {alarms.length > 0 && <em key={alarms.length} className={unseen ? "" : "quiet"}>{faNum(alarms.length)}</em>}
    </button>
    {open && <div className="al-drop" role="dialog" aria-label="الارم‌های فعال">
      <header><b>الارم‌های باز شما</b><small>{loaded ? `${faNum(alarms.length)} مورد · ${faNum(unseen)} دیده‌نشده` : "در حال دریافت…"}</small></header>
      <div className="al-drop-list">
        {alarms.slice(0, 8).map((a, i) => <AlarmCard key={a.key} a={a} index={i} compact onGo={(v) => { setOpen(false); onGo(v); }} />)}
        {loaded && !alarms.length && <div className="al-empty"><span>✓</span>همه چیز آرام است؛ الارم فعالی ندارید.</div>}
      </div>
      {alarms.length > 0 && <button type="button" className="al-all" onClick={() => { setOpen(false); onGo("alerts"); }}>مرکز الارم‌ها ←</button>}
    </div>}
  </div>;
}

// ------------------------------------------------------------------ اعلان لحظه‌ای الارم تازه
export function AlarmToasts({ onGo }: { onGo: (view: string) => void }) {
  const { fresh } = useAlarms();
  const [items, setItems] = useState<Alarm[]>([]);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  useEffect(() => {
    if (!fresh.length) return;
    setItems((cur) => [...fresh.filter((f) => !cur.some((c) => c.key === f.key)), ...cur].slice(0, 4));
    markSeen(fresh.map((a) => a.key));
  }, [fresh]);
  useEffect(() => {
    if (!items.length) return;
    const t = window.setTimeout(() => setItems((cur) => cur.slice(0, -1)), 8000);
    return () => window.clearTimeout(t);
  }, [items]);
  if (!mounted || !items.length) return null;
  return createPortal(<div className="al-toasts" aria-live="polite">
    {items.map((a) => <div key={a.key} className={`al-toast ${a.level}`}>
      <span className="al-toast-icon">{LEVEL_ICON[a.level]}</span>
      <div><small>{a.module_title} · {LEVEL_FA[a.level]}</small><b>{a.title}</b></div>
      <span className="al-toast-actions">
        {a.view && <button type="button" onClick={() => { setItems((c) => c.filter((x) => x.key !== a.key)); onGo(a.view!); }}>مشاهده</button>}
        <button type="button" className="ghost" onClick={() => setItems((c) => c.filter((x) => x.key !== a.key))} aria-label="بستن">✕</button>
      </span>
      <i className="al-toast-bar" />
    </div>)}
  </div>, document.body);
}

// ------------------------------------------------------------------ نوار الارم بالای صفحه هر ماژول
export function AlarmStrip({ modules, onGo, title }: { modules: string[]; onGo?: (view: string) => void; title?: string }) {
  const { alarms, loaded } = useAlarms();
  const rows = useMemo(() => alarms.filter((a) => pending(a) && modules.includes(a.module)), [alarms, modules]);
  const [open, setOpen] = useState(false);
  if (!loaded || !rows.length) return null;
  const top = rows[0];
  return <section className={`al-strip ${top.level}${open ? " open" : ""}`}>
    <button type="button" className="al-strip-head" onClick={() => setOpen(!open)} aria-expanded={open}>
      <span className="al-pulse" aria-hidden />
      <b>{faNum(rows.length)} الارم {title ? `«${title}»` : "این بخش"}</b>
      <span className="al-strip-top">{top.title}</span>
      <span className="al-strip-counts">{(["critical", "high", "medium", "info"] as Level[]).map((lv) => {
        const n = rows.filter((a) => a.level === lv).length;
        return n ? <i key={lv} className={lv}>{faNum(n)} {LEVEL_FA[lv]}</i> : null;
      })}</span>
      <span className="al-chev">{open ? "▲" : "▼"}</span>
    </button>
    {open && <div className="al-grid">{rows.map((a, i) => <AlarmCard key={a.key} a={a} index={i} onGo={onGo} />)}</div>}
  </section>;
}

// ------------------------------------------------------------------ الارم‌های کنار هر بلوک (خلاصه مدیریتی/فروش)
export function ModuleAlarms({ modules, agents, title, onGo }: { modules?: string[]; agents?: string[]; title: string; onGo?: (view: string) => void }) {
  const { alarms, loaded } = useAlarms();
  const rows = alarms.filter((a) => pending(a) && (modules ? modules.includes(a.module) : true) && (agents ? agents.includes(a.agent_key) : true));
  return <div className="al-side">
    <div className="al-side-head"><span className={`al-dot${rows.some((a) => a.level === "critical" || a.level === "high") ? " hot" : rows.length ? " warm" : ""}`} />
      <b>الارم‌های {title}</b><small>{loaded ? faNum(rows.length) : "…"}</small></div>
    {!loaded ? <div className="al-empty small">در حال دریافت…</div>
      : rows.length ? rows.slice(0, 4).map((a, i) => <AlarmCard key={a.key} a={a} index={i} compact onGo={onGo} />)
        : <div className="al-empty small"><span>✓</span>الارم فعالی نیست.</div>}
    {rows.length > 4 && onGo && <button type="button" className="al-all" onClick={() => onGo("alerts")}>{faNum(rows.length - 4)} الارم دیگر ←</button>}
  </div>;
}

// ------------------------------------------------------------------ مرکز الارم‌ها
export function AlarmCenter({ onGo, moduleTitles }: { onGo: (view: string) => void; moduleTitles: Record<string, string> }) {
  const { alarms, loaded } = useAlarms();
  const [level, setLevel] = useState<Level | "">("");
  const [module, setModule] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"pending" | "done" | "dismissed">("pending");
  const inTab = (a: Alarm) => (tab === "pending" ? pending(a) : a.my_status === tab);
  const modules = Array.from(new Set(alarms.map((a) => a.module)));
  const rows = alarms.filter((a) => inTab(a) && (!level || a.level === level) && (!module || a.module === module));
  const reload = useCallback(async () => { setBusy(true); await refreshAlarms(); setBusy(false); }, []);
  const counts = (["critical", "high", "medium", "info"] as Level[]).map((lv) => ({ lv, n: alarms.filter((a) => inTab(a) && a.level === lv).length }));
  const tabCount = (t: typeof tab) => alarms.filter((a) => (t === "pending" ? pending(a) : a.my_status === t)).length;
  return <section className="al-center">
    <header className="al-center-head">
      <div><h2>مرکز الارم‌ها</h2><p>الارم‌های ماژول‌هایی که به آن‌ها دسترسی دارید. «انجام شد»، «دیده شد» و «نادیده» برای خود شما ذخیره می‌شود؛ اگر الارمی رفع و دوباره تکرار شود، دوباره باز می‌شود.</p></div>
      <button type="button" className="al-refresh" onClick={reload} disabled={busy}>{busy ? "…" : "↻ به‌روزرسانی"}</button>
    </header>
    <div className="al-filter al-tabs">
      {([["pending", "باز"], ["done", "انجام‌شده"], ["dismissed", "نادیده‌گرفته"]] as [typeof tab, string][]).map(([t, label]) =>
        <button key={t} type="button" className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{label} ({faNum(tabCount(t))})</button>)}
    </div>
    <div className="al-kpis">
      {counts.map(({ lv, n }) => <button key={lv} type="button" className={`al-kpi ${lv}${level === lv ? " on" : ""}`} onClick={() => setLevel(level === lv ? "" : lv)}>
        <small>{LEVEL_FA[lv]}</small><b>{faNum(n)}</b></button>)}
    </div>
    {modules.length > 1 && <div className="al-filter">
      <button type="button" className={!module ? "on" : ""} onClick={() => setModule("")}>همه ماژول‌ها</button>
      {modules.map((m) => <button key={m} type="button" className={module === m ? "on" : ""} onClick={() => setModule(m)}>{moduleTitles[m] || m}</button>)}
    </div>}
    {!loaded ? <div className="al-empty">در حال دریافت الارم‌ها…</div>
      : rows.length ? <div className="al-grid">{rows.map((a, i) => <AlarmCard key={a.key} a={a} index={i} onGo={onGo} />)}</div>
        : <div className="al-empty big"><span>✓</span>{tab === "pending" ? "الارم بازی با این فیلترها ندارید." : "موردی در این بخش نیست."}</div>}
  </section>;
}
