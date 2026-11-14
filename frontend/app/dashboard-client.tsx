
"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import "./functional.css";
import "./cheque-totals.css";
import "./enterprise.css";
import "./operations.css";
import "./cheque-remaining.css";
import "./visual-dashboard.css";
import "./agent.css";
import "./readability-fix.css";
import "./customer-reliability.css";
import "./agents-v171.css";
import "./font-size-v36.css";
import "./drilldown.css";
import "./reliance-explanation.css";
import "./command-center-3d.css";
import "./cash-bank-movements.css";
import "./ui-polish-v69.css";
import "./management-v109.css";
import "./theme-stability-v137.css";
import "./customer-file.css";
import LiquidityPage from "./liquidity/liquidity-page";
import InventoryPricingPage from "./inventory-pricing/inventory-pricing-page";
import PurchaseDocsPage from "./purchase-docs/purchase-docs-page";
import PnlPage from "./pnl/pnl-page";
import WhatsAppPage from "./whatsapp/whatsapp-page";
import ChatWidget from "./chatbot/chat-widget";
import { useChatLink } from "./chatbot/chat-link";
import PayablesPage from "./payables/payables-page";
import "./readability-v2.css";
import { useAuth } from "./auth/auth";
import UsersAdmin from "./auth/users-admin";
import ThemePicker from "./theme/theme-picker";
import SalesOverview from "./sales/sales-overview";
import ManagerOverview from "./management/manager-overview";
import { AlarmBell, AlarmCenter, AlarmStrip, AlarmToasts, startAlarms, stopAlarms } from "./alarms/alarms";
import Pet from "./pet/pet";
import "./theme/theme.css";
import { description, label } from "./dashboard/widgets";
import { CashBankMovements } from "./dashboard/cash-bank-movements";
import { ChequeHub, ChequeSourcePage } from "./dashboard/cheques";
import { Collections } from "./dashboard/collections";
import { CustomerProfile } from "./dashboard/customer-profile";
import { Customers } from "./dashboard/customers";
import { DistributionPage } from "./dashboard/distribution";
import { Management } from "./dashboard/management";
import { CompanyPaymentOrders } from "./dashboard/payments";
import { InsightCenter, cname, fa, menu, request, treasuryRequest } from "./dashboard/shared";
import type { Alert, Case, Customer, Pack, TreasuryCheque, View } from "./dashboard/types";
import { Alerts, History, Performance, Representatives, Settings } from "./dashboard/workspace";

export default function Page(props: { view?: View; onViewChange?: (v: View) => void } = {}) {
  const { profile, can, hasModule, logout } = useAuth();
  // صفحه‌های مجاز همین کاربر (سطح دسترسی ماژول‌ها)؛ مدیر سیستم همه را می‌بیند.
  const firstView = (menu.find(([id]) => can(id))?.[0] || "alerts") as View;
  const [innerView, setInnerView] = useState<View>(firstView),
    [pack, setPack] = useState<Pack | null>(null),
    [alerts, setAlerts] = useState<Alert[]>([]),
    [cases, setCases] = useState<Case[]>([]),
    [history, setHistory] = useState<any[]>([]),
    [performance, setPerformance] = useState<any>(null),
    [policies, setPolicies] = useState<Record<string, any>>({}),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<Customer | null>(null),
    [received, setReceived] = useState<TreasuryCheque[]>([]),
    [issued, setIssued] = useState<TreasuryCheque[]>([]),
    [treasuryError, setTreasuryError] = useState("");
  // رفتن به صفحه فقط اگر در ماژول‌های کاربر باشد (لینک چت‌بات، الارم و کارت‌ها هم از همین می‌گذرند).
  const view: View = props.view ?? innerView;
  const { onViewChange } = props;
  const setViewRaw = useCallback((v: View) => { if (onViewChange) onViewChange(v); else setInnerView(v); }, [onViewChange]);
  const setView = useCallback((v: View) => { if (can(v)) setViewRaw(v); }, [can, setViewRaw]);
  const moduleTitles = useMemo(() => Object.fromEntries(profile.catalog.map((m) => [m.key, m.title])), [profile.catalog]);
  const viewModules = useMemo(() => profile.catalog.filter((m) => m.views.includes(view)).map((m) => m.key), [profile.catalog, view]);
  useEffect(() => { startAlarms(profile.user.username); return () => stopAlarms(); }, [profile.user.username]);
  useEffect(() => { if (!can(view)) setViewRaw(firstView); }, [can, view, firstView, setViewRaw]);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const results = await Promise.allSettled([
      request("/agents/latest"),
      request("/customer-alerts?status=open&limit=100"),
      request("/collection-cases"),
      request("/agent-reports/history?limit=30"),
      request("/prediction-performance"),
      request("/policies"),
    ]);
    if (
      results[0].status === "fulfilled" &&
      results[0].value.status !== "empty"
    )
      setPack(results[0].value);
    else if (results[0].status === "rejected")
      setError(results[0].reason.message);
    if (results[1].status === "fulfilled")
      setAlerts(results[1].value.alerts || []);
    if (results[2].status === "fulfilled")
      setCases(results[2].value.cases || []);
    if (results[3].status === "fulfilled")
      setHistory(results[3].value.reports || []);
    if (results[4].status === "fulfilled") setPerformance(results[4].value);
    if (results[5].status === "fulfilled")
      setPolicies(results[5].value.values || {});
    setLoading(false);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const cards = Array.from(
      document.querySelectorAll<HTMLElement>(
        ".fd-kpi,.fd-panel,.manager-panel,.section-agent,.agent-grid>article,.cheque-flow-card,.audit-status-grid>article",
      ),
    );
    const cleanups = cards.map((card) => {
      const move = (event: PointerEvent) => {
        const rect = card.getBoundingClientRect(),
          x = (event.clientX - rect.left) / rect.width,
          y = (event.clientY - rect.top) / rect.height;
        card.style.setProperty("--mx", `${x * 100}%`);
        card.style.setProperty("--my", `${y * 100}%`);
      };
      const leave = () => {
        card.style.setProperty("--mx", "50%");
        card.style.setProperty("--my", "50%");
      };
      card.addEventListener("pointermove", move);
      card.addEventListener("pointerleave", leave);
      return () => {
        card.removeEventListener("pointermove", move);
        card.removeEventListener("pointerleave", leave);
      };
    });
    return () => cleanups.forEach((fn) => fn());
  }, [view, pack, selected]);
  const refreshTreasuryCheques = useCallback(async () => {
    const [r, i] = await Promise.allSettled([
      treasuryRequest("/cheques/received/open?period=all"),
      treasuryRequest("/cheques/issued/open"),
    ]);
    const errors: string[] = [];
    if (r.status === "fulfilled") setReceived(r.value.cheques || []);
    else errors.push(`چک دریافتی: ${r.reason?.message || "خطای نامشخص"}`);
    if (i.status === "fulfilled") setIssued(i.value.cheques || []);
    else errors.push(`چک پرداختی: ${i.reason?.message || "خطای نامشخص"}`);
    setTreasuryError(errors.join(" | "));
  }, []);
  useEffect(() => { void refreshTreasuryCheques(); }, [refreshTreasuryCheques]);
  const refreshAfterKaramadUpdate = useCallback(async () => {
    // V128: the upload endpoint rebuilds the agent report on the backend, but the
    // old UI only refreshed the cheque REST rows. Reload both sources so KPI cards,
    // management summary, customer behavior and cash-flow numbers change immediately.
    await refreshTreasuryCheques();
    await load();
  }, [refreshTreasuryCheques, load]);
  const runAll = async () => {
    setLoading(true);
    setError("");
    try {
      setPack(await request("/agents/run-all", { method: "POST" }));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "اجرای Agentها ناموفق بود");
      setLoading(false);
    }
  };
  const customerChatLink = useChatLink("customers");
  useEffect(() => {
    const l = customerChatLink;
    if (!l || !(l.search || l.ref)) return;
    const list: Customer[] = pack?.data?.customer?.customers || [];
    if (l.source === "karamad") {
      setSelected({ customer_name: l.search, data_source: "karamad", karamad_activity: { customer_name: l.search } } as Customer);
    } else {
      const found = list.find((c) => l.ref && String(c.counterpart_ref) === String(l.ref))
        || list.find((c) => l.search && cname(c).includes(l.search));
      setSelected(found ? { ...found, data_source: "rahkaran" }
        : ({ counterpart_ref: Number(l.ref) || undefined, counterpart_name: l.search, data_source: "rahkaran" } as Customer));
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [customerChatLink]); // eslint-disable-line react-hooks/exhaustive-deps
  const customers = useMemo(
    () =>
      [...(pack?.data?.customer?.customers || [])].sort(
        (a, b) => (b.open_exposure || 0) - (a.open_exposure || 0),
      ),
    [pack],
  );
  const cheques = pack?.data?.cheques?.cheques || [],
    reps = pack?.data?.representatives?.representatives || [],
    manager = pack?.management_summary?.analysis;

  // «/finance/customers?c=کد» (جستجوی سراسری و دکمه «پرونده» نمای مدیر): پرونده همان مشتری مستقیم باز می‌شود
  const urlCustomer = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("c");
  useEffect(() => {
    if (view !== "customers" || !urlCustomer || !customers.length) return;
    const hit = customers.find((x: any) => String(x.counterpart_code || "").trim() === urlCustomer);
    if (hit) setSelected(hit);
  }, [view, urlCustomer, customers]);

  return (
    <main className="fd enterprise">
      <aside>
        <div className="fd-brand">
          <i>ا</i>
          <div>
            <b>اکسیر کادوس</b>
            <small>مرکز فرماندهی مالی و فروش</small>
          </div>
        </div>
        <nav>
          {menu.filter(([id]) => can(id)).map(([id, icon, label]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => setView(id)}
            >
              <i>{icon}</i>
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="fd-health">
          <i className={error ? "warn" : ""} />
          <div>
            <b>{error ? "نیازمند بررسی اتصال" : "الارم‌های ماژول‌ها فعال است"}</b>
            <small>{profile.user.is_admin ? "مدیر سیستم · همه ماژول‌ها" : `${fa(profile.modules.length)} ماژول در دسترس`}</small>
          </div>
        </div>
      </aside>
      <section className="fd-content">
        <header>
          <div>
            <small>مرکز فرماندهی / {label(view)}</small>
            <h1>{label(view)}</h1>
            <p>{description(view)}</p>
          </div>
          <div className="fd-head-tools">
            <AlarmBell onGo={(v) => setView(v as View)} />
            <ThemePicker />
            {profile.user.is_admin && (
              <button className="run" onClick={runAll} disabled={loading} title="اجرای دوباره قواعد همه بخش‌ها و به‌روزرسانی الارم‌ها">
                {loading ? "در حال به‌روزرسانی…" : "↻ به‌روزرسانی الارم‌ها"}
              </button>
            )}
            <span className="user-chip">
              <i>{profile.user.full_name.slice(0, 1)}</i>
              <span>{profile.user.full_name}<small>{profile.user.is_admin ? "مدیر سیستم" : profile.user.username}</small></span>
              <button type="button" onClick={() => void logout()}>خروج</button>
            </span>
          </div>
        </header>
        <AlarmToasts onGo={(v) => setView(v as View)} />
        {!["overview", "management", "sales", "alerts", "users"].includes(view) && viewModules.length > 0 && (
          <AlarmStrip modules={viewModules} title={label(view)} onGo={(v) => setView(v as View)} />
        )}
        {error && (
          <div className="fd-errors">
            <span>{error}</span>
            <small>
              FastAPI باید روی پورت ۸۰۰۰ اجرا و SQL Server در دسترس باشد.
            </small>
          </div>
        )}
        {view === "management" && (
          <Management
            manager={manager}
            customers={customers}
            cheques={cheques}
            alerts={alerts}
            received={received.length ? received : cheques}
            issued={issued}
            openChequePage={(kind) => setView(kind === "received" ? "receivedCheques" : "issuedCheques")}
            openAgent={() => setView("alerts")}
            openView={(v) => setView(v)}
            go={(v) => setView(v as View)}
          />
        )}
        {view === "sales" && <SalesOverview go={(v) => setView(v as View)} />}
        {view === "overview" && <ManagerOverview go={(v) => setView(v as View)} />}
        {view === "users" && profile.user.is_admin && <UsersAdmin />}
        {view === "customers" && (selected ? (
          <CustomerProfile c={selected} close={() => setSelected(null)} refresh={load} embedded />
        ) : (
          <Customers customers={customers} open={setSelected} />
        ))}
        {view === "cheques" && (
          <ChequeHub
            received={received.length ? received : cheques}
            issued={issued}
            error={treasuryError}
            open={setView}
          />
        )}
        {view === "receivedCheques" && (
          <ChequeSourcePage kind="received" rows={received.length ? received : cheques}
            error={treasuryError} back={() => setView("cheques")} onUpdated={refreshAfterKaramadUpdate} />
        )}
        {view === "issuedCheques" && (
          <ChequeSourcePage kind="issued" rows={issued}
            error={treasuryError} back={() => setView("cheques")} onUpdated={refreshAfterKaramadUpdate} />
        )}
        {view === "liquidity" && <LiquidityPage />}
        {view === "inventoryPricing" && <InventoryPricingPage />}
        {view === "purchaseDocs" && <PurchaseDocsPage />}
        {view === "pnl" && <PnlPage />}
        {view === "whatsapp" && <WhatsAppPage />}
        {/* چت‌بات: کدش در app/chatbot. در داشبورد یکپارچه (view کنترل‌شده) خود پوسته یک چت‌بات برای همه صفحه‌ها دارد. */}
        {/* حیوان خانگی (در داشبورد یکپارچه خود پوسته آن را دارد) */}
        {!onViewChange && <Pet onGo={(v) => setView(v as View)} />}
        {!onViewChange && hasModule("chatbot") && <ChatWidget view={view} go={(v) => setView(v as View)} />}
        {view === "payables" && <PayablesPage />}
        {view === "cashBank" && (
          <CashBankMovements />
        )}
        {view === "companyPayments" && <CompanyPaymentOrders />}
        {view === "distribution" && <DistributionPage />}
        {view === "collections" && (
          <Collections
            cases={cases}
            refresh={load}
            received={received.length ? received : cheques}
          />
        )}
        {view === "representatives" && (
          <Representatives
            reps={reps}
            unmapped={pack?.data?.representatives?.unmapped_customer_count}
          />
        )}
        {view === "alerts" && <>
          <AlarmCenter onGo={(v) => setView(v as View)} moduleTitles={moduleTitles} />
          {can("customers") && alerts.length > 0 && <Alerts rows={alerts} refresh={load} />}
        </>}
        {view === "history" && <History rows={history} />}
        {view === "performance" && <Performance data={performance} />}
        {view === "settings" && (
          <Settings values={policies} setValues={setPolicies} />
        )}
      </section>

      <InsightCenter />
    </main>
  );
}
