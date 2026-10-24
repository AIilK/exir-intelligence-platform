import React from "react";
import { createRoot } from "react-dom/client";
import DashboardClient from "../app/dashboard-client";
import ReconciliationClient from "../app/reconciliation/reconciliation-client";
import "../app/globals.css";
import "../app/agent.css";
import "../app/reconciliation/reconciliation.css";

const root = createRoot(document.getElementById("root")!);

function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  // پنل مغایرت‌گیری بدون صفحه ورود باز می‌شود؛ آدرس قدیمی /reconciliation/login هم به خود پنل می‌رود.
  if (path === "/reconciliation/login") {
    window.location.replace("/reconciliation");
    return null;
  }
  if (path === "/reconciliation" || path.startsWith("/reconciliation/")) {
    return <ReconciliationClient />;
  }

  return <DashboardClient />;
}

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
