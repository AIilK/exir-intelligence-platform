"use client";

// V171 — Agent گزارشی هر صفحه: هشدار، پیش‌بینی، اقدام و حافظه (روند اجراهای قبلی).
import { useCallback, useEffect, useMemo, useState } from "react";

type Level = "critical" | "high" | "medium" | "info";
type AgentAlert = {
  alert_key: string; type: string; level: Level; title: string; why?: string[]; action?: string;
  evidence?: { label: string; value: string }[]; consecutive_runs?: number; first_seen?: string; status?: string;
};
type Prediction = { metric: string; label: string; horizon: string; display: string; confidence: string; basis: string };
type Action = { action?: string; why?: string; owner?: string; priority?: string; deadline?: string; expected_effect?: string };
type Delta = { metric: string; label: string; current: number | null;
  vs_previous?: { change: number; percent: number | null; at: string } | null;
  vs_week_ago?: { change: number; percent: number | null; at: string } | null };
type AgentRun = {
  agent_key: string; page: string; name: string; role: string; status: "success" | "error"; error?: string;
  generated_at: string; mode?: string; fallback_reason?: string | null; primary_metric?: string; primary_unit?: string;
  analysis?: { headline?: unknown; summary?: unknown; human_summary?: unknown; management_status?: string;
    good_signals?: unknown[]; risks?: unknown[]; recommended_actions?: Action[]; next_best_action?: unknown };
  alerts?: AgentAlert[]; predictions?: Prediction[];
  memory?: { run_count: number; previous_at?: string | null; week_ago_at?: string | null; deltas: Delta[] };
};
type SeriesPoint = { at: string; value: number | null };
type AgentDetail = { latest: AgentRun | null; series: Record<string, SeriesPoint[]>; history: unknown[]; name: string; page: string };
type CatalogEntry = { agent_key: string; page: string; name: string; role: string; view?: string | null; latest?: AgentRun | null };

const API = () => `http://${typeof window !== "undefined" ? window.location.hostname : "127.0.0.1"}:8000/api/v1/finance`;
async function api(path: string, options?: RequestInit) {
  const r = await fetch(`${API()}${path}`, options);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || `خطای ${r.status}`);
  return j;
}

const faNum = (v: number, digits = 0) => new Intl.NumberFormat("fa-IR", { maximumFractionDigits: digits }).format(v);
const toman = (rial: number) => {
  const t = rial / 10, a = Math.abs(t);
  if (a >= 1e12) return `${faNum(t / 1e12, 1)} همت`;
  if (a >= 1e9) return `${faNum(t / 1e9, 1)} میلیارد تومان`;
  if (a >= 1e6) return `${faNum(t / 1e6, 1)} میلیون تومان`;
  return `${faNum(t)} تومان`;
};
const isRialMetric = (key: string) => !/(count|percent|hours|rows|alerts|_days|accounts)/.test(key);
const metricText = (key: string, value: number) => isRialMetric(key) ? toman(value) : faNum(value, 1);
const text = (v: unknown): string => v === null || v === undefined ? "" : typeof v === "string" ? v : typeof v === "number" ? faNum(v) :
  typeof v === "object" ? Object.values(v as Record<string, unknown>).map(text).filter(Boolean).join(" · ") : String(v);
const when = (iso?: string | null) => {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("fa-IR-u-ca-persian", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  } catch { return iso.slice(0, 16); }
};
const LEVEL_FA: Record<string, string> = { critical: "بحرانی", high: "بالا", medium: "متوسط", info: "اطلاع" };
const STATUS_FA: Record<string, string> = { critical: "بحرانی", attention: "نیازمند توجه", healthy: "سالم" };
const CONF_FA: Record<string, string> = { high: "اطمینان زیاد", medium: "اطمینان متوسط", low: "اطمینان کم" };
const PRIORITY_FA: Record<string, string> = { critical: "فوری", high: "بالا", medium: "متوسط", low: "پایین" };

function readCollapsed(key: string) {
  try { return localStorage.getItem(`page-agent-collapsed:${key}`) === "1"; } catch { return false; }
}
function writeCollapsed(key: string, value: boolean) {
  try { localStorage.setItem(`page-agent-collapsed:${key}`, value ? "1" : "0"); } catch { /* storage unavailable */ }
}

function Sparkline({ points }: { points: SeriesPoint[] }) {
  const values = points.map((p) => p.value).filter((v): v is number => typeof v === "number");
  if (!values.length) return <div className="pa-spark empty">حافظه از اجرای بعد ساخته می‌شود</div>;
  const w = 168, h = 44, pad = 4;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const xs = values.map((_, i) => values.length === 1 ? w / 2 : pad + (i * (w - pad * 2)) / (values.length - 1));
  const ys = values.map((v) => h - pad - ((v - min) / span) * (h - pad * 2));
  const path = xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  const area = `${path} L${xs[xs.length - 1].toFixed(1)},${h} L${xs[0].toFixed(1)},${h} Z`;
  return <svg className="pa-spark" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="روند اجراهای اخیر">
    <path d={area} className="pa-spark-area" />
    <path d={path} className="pa-spark-line" />
    <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="3.2" className="pa-spark-dot" />
  </svg>;
}

function DeltaChip({ delta, refKey }: { delta: Delta; refKey: "vs_previous" | "vs_week_ago" }) {
  const info = delta[refKey];
  if (!info) return null;
  const up = info.change > 0, flat = !info.change;
  return <span className={`pa-delta ${flat ? "flat" : up ? "up" : "down"}`}
    title={`${refKey === "vs_previous" ? "نسبت به اجرای قبل" : "نسبت به حدود ۷ روز قبل"} (${when(info.at)})`}>
    {flat ? "بدون تغییر" : <>{up ? "▲" : "▼"} {metricText(delta.metric, Math.abs(info.change))}{info.percent !== null && info.percent !== undefined ? ` (${faNum(Math.abs(info.percent), 1)}٪)` : ""}</>}
    <small>{refKey === "vs_previous" ? "از اجرای قبل" : "از هفته قبل"}</small>
  </span>;
}

function AlertItem({ a, onStatus }: { a: AgentAlert; onStatus?: (key: string, status: string) => void }) {
  const streak = a.consecutive_runs || 1;
  return <article className={`pa-alert ${a.level}${a.status === "acknowledged" ? " acked" : ""}`}>
    <header>
      <span className={`pa-level ${a.level}`}>{LEVEL_FA[a.level] || a.level}</span>
      <b>{a.title}</b>
    </header>
    {(a.why || []).length > 0 && <ul>{(a.why || []).slice(0, 2).map((w, i) => <li key={i}>{w}</li>)}</ul>}
    {(a.evidence || []).length > 0 && <div className="pa-evidence">{(a.evidence || []).slice(0, 3).map((e, i) => <span key={i}>{e.label}: <b>{e.value}</b></span>)}</div>}
    {a.action && <p className="pa-alert-action">اقدام: {a.action}</p>}
    <footer>
      {streak > 1 ? <span className="pa-streak">↻ {faNum(streak)} اجرای متوالی · از {when(a.first_seen)}</span> : <span className="pa-new">هشدار تازه</span>}
      {onStatus && a.status !== "acknowledged" && <button type="button" onClick={() => onStatus(a.alert_key, "acknowledged")}>دیده شد</button>}
      {onStatus && <button type="button" onClick={() => onStatus(a.alert_key, "dismissed")}>نادیده بگیر</button>}
    </footer>
  </article>;
}

/** کارت Agent بالای هر صفحه. */
export function PageAgentCard({ agentKey, defaultCollapsed = false }: { agentKey: string; defaultCollapsed?: boolean }) {
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [showAllAlerts, setShowAllAlerts] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => { setCollapsed(readCollapsed(agentKey) || defaultCollapsed); }, [agentKey, defaultCollapsed]);
  const load = useCallback(() => {
    api(`/page-agents/${agentKey}`).then(setDetail).catch((e) => setError(e instanceof Error ? e.message : "خطا"))
      .finally(() => setLoaded(true));
  }, [agentKey]);
  useEffect(() => { load(); }, [load]);

  const run = async () => {
    setRunning(true); setError("");
    try { await api(`/page-agents/${agentKey}/run`, { method: "POST" }); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "اجرای Agent ناموفق بود"); }
    finally { setRunning(false); }
  };
  const setAlertStatus = async (key: string, status: string) => {
    await api(`/agent-alerts/${encodeURIComponent(key)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
    }).catch(() => undefined);
    load();
  };
  const toggle = () => { setCollapsed((v) => { writeCollapsed(agentKey, !v); return !v; }); };

  const r = detail?.latest;
  const a = r?.analysis || {};
  const status = r?.status === "error" ? "error" : a.management_status || "healthy";
  const alerts = (r?.alerts || []).filter((x) => x.status !== "dismissed");
  const visibleAlerts = showAllAlerts ? alerts : alerts.slice(0, 2);
  const primaryDelta = r?.memory?.deltas?.find((d) => d.metric === r?.primary_metric) || r?.memory?.deltas?.[0];
  const series = (r?.primary_metric && detail?.series?.[r.primary_metric]) || [];
  const counts = useMemo(() => alerts.reduce((acc: Record<string, number>, x) => ({ ...acc, [x.level]: (acc[x.level] || 0) + 1 }), {}), [alerts]);

  return <article className={`pa-card status-${status}${collapsed ? " collapsed" : ""}`}>
    <header className="pa-head">
      <div className="pa-avatar" aria-hidden="true">✦</div>
      <div className="pa-title">
        <small>Agent این صفحه · {detail?.name || r?.name || agentKey}</small>
        <h3>{!loaded ? "در حال دریافت آخرین تحلیل…" : r?.status === "error" ? "Agent در آخرین اجرا به داده دسترسی نداشت" : text(a.headline) || "هنوز تحلیلی برای این صفحه ساخته نشده است"}</h3>
      </div>
      <div className="pa-meta">
        {r && <span className={`pa-status ${status}`}>{status === "error" ? "خطا" : STATUS_FA[status] || status}</span>}
        {collapsed && (counts.critical || counts.high) ? <span className="pa-count critical">{faNum((counts.critical || 0) + (counts.high || 0))} هشدار مهم</span> : null}
        <span className="pa-time">{r ? <>آخرین تحلیل {when(r.generated_at)} · {r.mode === "llm" ? "روایت هوش مصنوعی" : "موتور قواعد"}</> : "اجرا نشده"}</span>
        <button type="button" className="pa-run" onClick={run} disabled={running}>{running ? "در حال تحلیل…" : "به‌روزرسانی تحلیل"}</button>
        <button type="button" className="pa-toggle" onClick={toggle} aria-expanded={!collapsed} aria-label={collapsed ? "باز کردن" : "بستن"}>{collapsed ? "▾" : "▴"}</button>
      </div>
    </header>
    {error && <div className="pa-error">{error}</div>}
    {!collapsed && r?.status === "error" && <div className="pa-error">{r.error}</div>}
    {!collapsed && r?.status === "success" && <>
      <p className="pa-summary">{text(a.summary) || text(a.human_summary)}</p>
      <section className="pa-memory">
        <div className="pa-memory-chart">
          <small>حافظه · {primaryDelta?.label || "شاخص اصلی"} در {faNum(series.length)} اجرای اخیر</small>
          <Sparkline points={series} />
        </div>
        <div className="pa-memory-deltas">
          {(r.memory?.deltas || []).slice(0, 4).map((d) => <div key={d.metric} className="pa-delta-row">
            <span>{d.label}</span>
            <b>{d.current === null ? "—" : metricText(d.metric, d.current)}</b>
            <DeltaChip delta={d} refKey="vs_previous" />
            <DeltaChip delta={d} refKey="vs_week_ago" />
          </div>)}
          {!r.memory?.previous_at && <p className="pa-memory-note">این اولین اجرای ثبت‌شده است؛ از اجرای بعد، تغییر نسبت به قبل و تکرار هشدارها نمایش داده می‌شود.</p>}
        </div>
      </section>
      <div className="pa-grid">
        <section className="pa-col">
          <h4>هشدارها <span>{faNum(alerts.length)}</span></h4>
          {alerts.length ? visibleAlerts.map((x) => <AlertItem key={x.alert_key} a={x} onStatus={setAlertStatus} />)
            : <div className="pa-empty ok">هشدار فعالی وجود ندارد.</div>}
          {alerts.length > 2 && <button type="button" className="pa-more" onClick={() => setShowAllAlerts((v) => !v)}>
            {showAllAlerts ? "نمایش کمتر" : `${faNum(alerts.length - 2)} هشدار دیگر`}</button>}
        </section>
        <section className="pa-col">
          <h4>پیش‌بینی‌ها</h4>
          {(r.predictions || []).length ? (r.predictions || []).slice(0, 3).map((p, i) => <article key={i} className="pa-prediction">
            <small>{p.label}</small>
            <b>{p.display}</b>
            <div><span className={`pa-conf ${p.confidence}`}>{CONF_FA[p.confidence] || p.confidence}</span><span>افق: {p.horizon}</span></div>
            <p>{p.basis}</p>
          </article>) : <div className="pa-empty">برای این صفحه پیش‌بینی عددی تعریف نشده است.</div>}
        </section>
        <section className="pa-col">
          <h4>اقدام پیشنهادی</h4>
          {text(a.next_best_action) && <div className="pa-next">{text(a.next_best_action)}</div>}
          {(a.recommended_actions || []).slice(0, 2).map((x, i) => <article key={i} className="pa-action">
            <header><b>{text(x.action)}</b>{x.priority && <em className={x.priority}>{PRIORITY_FA[x.priority] || x.priority}</em>}</header>
            {x.why && <p>{text(x.why)}</p>}
            <footer>{[text(x.owner), text(x.deadline)].filter(Boolean).join(" · ")}</footer>
          </article>)}
        </section>
      </div>
    </>}
    {!collapsed && loaded && !r && !error && <div className="pa-empty big">برای ساخت اولین تحلیل، «به‌روزرسانی تحلیل» را بزنید. Agentها هر روز صبح نیز خودکار اجرا می‌شوند.</div>}
  </article>;
}

/** صفحه «تیم Agentها». */
export function AgentTeam({ onOpenView }: { onOpenView?: (view: string) => void }) {
  const [agents, setAgents] = useState<CatalogEntry[] | null>(null);
  const [error, setError] = useState("");
  const [runningAll, setRunningAll] = useState(false);
  const [runningKey, setRunningKey] = useState<string | null>(null);
  const load = useCallback(() => {
    api("/page-agents").then((d) => setAgents(d.agents || [])).catch((e) => setError(e instanceof Error ? e.message : "خطا"));
  }, []);
  useEffect(() => { load(); }, [load]);
  const runAll = async () => {
    setRunningAll(true); setError("");
    try { await api("/page-agents/run-all", { method: "POST" }); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "اجرای تیم ناموفق بود"); }
    finally { setRunningAll(false); }
  };
  const runOne = async (key: string) => {
    setRunningKey(key);
    try { await api(`/page-agents/${key}/run`, { method: "POST" }); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "اجرای Agent ناموفق بود"); }
    finally { setRunningKey(null); }
  };
  const all = agents || [];
  const totals = all.reduce((acc, x) => {
    for (const a of (x.latest?.alerts || []).filter((y) => y.status !== "dismissed")) acc[a.level] = (acc[a.level] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const lastRun = all.map((x) => x.latest?.generated_at).filter(Boolean).sort().pop();

  return <section className="pa-team">
    <header className="pa-team-head">
      <div>
        <small>تیم Agentهای گزارشی</small>
        <h2>هر صفحه، یک Agent با حافظه</h2>
        <p>هر Agent روی داده زنده راهکاران و کارآمد اجرا می‌شود، هشدار و پیش‌بینی می‌سازد و اعداد هر اجرا را به خاطر می‌سپارد تا روند و تکرار مشکل‌ها را ببیند. اجرای خودکار: هر روز ساعت ۷ صبح.</p>
      </div>
      <div className="pa-team-actions">
        <div className="pa-team-kpis">
          <span className="critical"><b>{faNum(totals.critical || 0)}</b>بحرانی</span>
          <span className="high"><b>{faNum(totals.high || 0)}</b>بالا</span>
          <span className="medium"><b>{faNum(totals.medium || 0)}</b>متوسط</span>
        </div>
        <button type="button" className="pa-run big" onClick={runAll} disabled={runningAll}>{runningAll ? "در حال اجرای همه Agentها… (چند دقیقه)" : "اجرای همه Agentها"}</button>
        <small>آخرین اجرا: {when(lastRun)}</small>
      </div>
    </header>
    {error && <div className="pa-error">{error}</div>}
    {!agents ? <div className="pa-empty big">در حال دریافت وضعیت Agentها…</div> : <div className="pa-team-grid">
      {all.map((x) => {
        const r = x.latest, a = r?.analysis || {};
        const status = r?.status === "error" ? "error" : a.management_status || (r ? "healthy" : "none");
        const active = (r?.alerts || []).filter((y) => y.status !== "dismissed");
        return <article key={x.agent_key} className={`pa-team-card status-${status}`}>
          <header>
            <div><b>{x.page}</b><small>{x.name}</small></div>
            <span className={`pa-status ${status}`}>{status === "none" ? "اجرا نشده" : status === "error" ? "خطا" : STATUS_FA[status] || status}</span>
          </header>
          <p className="pa-team-role">{x.role}</p>
          <p className="pa-team-headline">{r?.status === "error" ? r.error : text(a.headline) || "هنوز اجرا نشده است."}</p>
          <div className="pa-team-alerts">
            {(["critical", "high", "medium"] as const).map((lv) => {
              const n = active.filter((y) => y.level === lv).length;
              return n ? <span key={lv} className={`pa-level ${lv}`}>{faNum(n)} {LEVEL_FA[lv]}</span> : null;
            })}
            {r && !active.length && <span className="pa-level ok">بدون هشدار</span>}
          </div>
          <footer>
            <small>{r ? `${when(r.generated_at)} · ${r.mode === "llm" ? "هوش مصنوعی" : "قواعد"} · حافظه ${faNum(r.memory?.run_count || 0)} اجرا` : "—"}</small>
            <div>
              {x.view && onOpenView && <button type="button" onClick={() => onOpenView(x.view as string)}>صفحه ←</button>}
              <button type="button" onClick={() => runOne(x.agent_key)} disabled={runningKey === x.agent_key || runningAll}>
                {runningKey === x.agent_key ? "…" : "اجرا"}</button>
            </div>
          </footer>
        </article>;
      })}
    </div>}
  </section>;
}

/** مرکز هشدارهای Agentها (کنار هشدارهای مشتری). */
export function AgentAlertsCenter({ onOpenView }: { onOpenView?: (view: string) => void }) {
  const [rows, setRows] = useState<(AgentAlert & { agent_key: string; page: string; view?: string; last_seen: string; payload: AgentAlert })[] | null>(null);
  const [level, setLevel] = useState("");
  const [page, setPage] = useState("");
  const [status, setStatus] = useState("active");
  const load = useCallback(() => {
    const q = new URLSearchParams({ status, ...(level ? { level } : {}), ...(page ? { page } : {}) });
    api(`/agent-alerts?${q}`).then((d) => setRows(d.alerts || [])).catch(() => setRows([]));
  }, [level, page, status]);
  useEffect(() => { load(); }, [load]);
  const update = async (key: string, next: string) => {
    await api(`/agent-alerts/${encodeURIComponent(key)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: next }),
    }).catch(() => undefined);
    load();
  };
  const pages = Array.from(new Set((rows || []).map((x) => x.page).filter(Boolean)));
  return <section className="pa-alert-center">
    <header className="pa-team-head compact">
      <div><small>مرکز هشدار Agentها</small><h2>هشدارهای همه صفحات</h2>
        <p>هر هشدار تا وقتی در اجراهای پشت‌سرهم دیده شود باز می‌ماند و شمارنده تکرار آن بالا می‌رود؛ اگر دیگر دیده نشود خودکار «رفع‌شده» می‌شود.</p></div>
      <div className="pa-filters">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="وضعیت">
          <option value="active">فعال</option><option value="acknowledged">دیده‌شده</option>
          <option value="dismissed">نادیده‌گرفته</option><option value="resolved">رفع‌شده</option>
        </select>
        <select value={page} onChange={(e) => setPage(e.target.value)} aria-label="صفحه">
          <option value="">همه صفحات</option>{pages.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <div className="pa-level-filter">
          {["", "critical", "high", "medium"].map((lv) => <button key={lv || "all"} type="button" className={level === lv ? "active" : ""} onClick={() => setLevel(lv)}>{lv ? LEVEL_FA[lv] : "همه سطوح"}</button>)}
        </div>
      </div>
    </header>
    {!rows ? <div className="pa-empty big">در حال دریافت هشدارها…</div> : rows.length ? <div className="pa-alert-list">
      {rows.map((x) => <div key={x.alert_key} className="pa-alert-wrap">
        <div className="pa-alert-page">
          <span>{x.page}</span>
          {x.view && onOpenView && <button type="button" onClick={() => onOpenView(x.view as string)}>رفتن به صفحه ←</button>}
        </div>
        <AlertItem a={{ ...x.payload, alert_key: x.alert_key, consecutive_runs: x.consecutive_runs, first_seen: x.first_seen, status: x.status, level: x.level }}
          onStatus={status === "active" || status === "acknowledged" ? update : undefined} />
      </div>)}
    </div> : <div className="pa-empty big ok">هشداری با این فیلترها وجود ندارد.</div>}
  </section>;
}

/** پیش‌بینی‌های فعلی همه Agentها (صفحه «دقت پیش‌بینی»). */
export function AgentPredictions({ onOpenView }: { onOpenView?: (view: string) => void }) {
  const [agents, setAgents] = useState<CatalogEntry[] | null>(null);
  useEffect(() => { api("/page-agents").then((d) => setAgents(d.agents || [])).catch(() => setAgents([])); }, []);
  const rows = (agents || []).filter((x) => x.agent_key !== "management" && (x.latest?.predictions || []).length);
  return <section className="pa-alert-center">
    <header className="pa-team-head compact">
      <div><small>پیش‌بینی‌های Agentها</small><h2>آنچه هر صفحه برای روزهای آینده پیش‌بینی می‌کند</h2>
        <p>هر پیش‌بینی مبنا و سطح اطمینان خودش را دارد؛ با هر اجرا عدد آن در حافظه Agent ثبت می‌شود تا روندش قابل مقایسه باشد.</p></div>
    </header>
    {!agents ? <div className="pa-empty big">در حال دریافت پیش‌بینی‌ها…</div> : rows.length ? <div className="pa-team-grid">
      {rows.map((x) => <article key={x.agent_key} className="pa-team-card">
        <header><div><b>{x.page}</b><small>{when(x.latest?.generated_at)}</small></div>
          {x.view && onOpenView && <button type="button" className="pa-more" onClick={() => onOpenView(x.view as string)}>صفحه ←</button>}</header>
        {(x.latest?.predictions || []).map((p, i) => <article key={i} className="pa-prediction">
          <small>{p.label}</small><b>{p.display}</b>
          <div><span className={`pa-conf ${p.confidence}`}>{CONF_FA[p.confidence] || p.confidence}</span><span>افق: {p.horizon}</span></div>
          <p>{p.basis}</p>
        </article>)}
      </article>)}
    </div> : <div className="pa-empty big">هنوز پیش‌بینی‌ای ثبت نشده؛ Agentها را اجرا کنید.</div>}
  </section>;
}
