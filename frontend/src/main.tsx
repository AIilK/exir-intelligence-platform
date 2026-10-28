import React from "react";
import { createRoot } from "react-dom/client";
import DashboardClient from "../app/dashboard-client";
import ReconciliationClient from "../app/reconciliation/reconciliation-client";
import AuthGate, { installAuthFetch, useAuth } from "../app/auth/auth";
import "../app/globals.css";
import "../app/agent.css";
import "../app/reconciliation/reconciliation.css";
import "../app/auth/auth.css";

// همه درخواست‌های /api/v1 با کوکی نشست ورود فرستاده شوند (app/auth/auth.tsx).
installAuthFetch();

const root = createRoot(document.getElementById("root")!);

/** پنل مغایرت‌گیری فقط برای کاربرانی که ماژول «مغایرت‌گیری بانک» را دارند. */
function ReconciliationGate() {
  const { hasModule } = useAuth();
  if (!hasModule("reconciliation")) {
    return <div className="auth-splash error"><b>به پنل مغایرت‌گیری دسترسی ندارید</b>
      <span>برای دسترسی با مدیر سیستم هماهنگ کنید.</span><button type="button" onClick={() => window.location.assign("/")}>بازگشت به داشبورد</button></div>;
  }
  return <ReconciliationClient />;
}

function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  // آدرس قدیمی /reconciliation/login هم به خود پنل می‌رود (ورود حالا سراسری است).
  if (path === "/reconciliation/login") {
    window.location.replace("/reconciliation");
    return null;
  }
  if (path === "/reconciliation" || path.startsWith("/reconciliation/")) {
    return <AuthGate><ReconciliationGate /></AuthGate>;
  }

  return <AuthGate><DashboardClient /></AuthGate>;
}

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
