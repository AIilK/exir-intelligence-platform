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

  if (path === "/reconciliation" || path.startsWith("/reconciliation/")) {
    return (
      <ReconciliationClient
        displayName="اپراتور خزانه"
        signOutPath={null}
      />
    );
  }

  return <DashboardClient />;
}

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
