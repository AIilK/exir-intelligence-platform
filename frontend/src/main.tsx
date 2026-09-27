import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import DashboardClient from "../app/dashboard-client";
import ReconciliationClient from "../app/reconciliation/reconciliation-client";
import ReconciliationLoginClient from "../app/reconciliation/reconciliation-login-client";
import "../app/globals.css";
import "../app/agent.css";
import "../app/reconciliation/reconciliation.css";

const root = createRoot(document.getElementById("root")!);

type ReconciliationSession = { configured: boolean; signedIn: boolean; username: string };

function Reconciliation({ loginPage }: { loginPage: boolean }) {
  const [session, setSession] = useState<ReconciliationSession | null>(null);

  useEffect(() => {
    fetch("/api/reconciliation/session", { cache: "no-store" })
      .then((response) => response.json())
      .then(setSession)
      .catch(() => setSession({ configured: false, signedIn: false, username: "" }));
  }, []);

  useEffect(() => {
    if (!session) return;
    if (loginPage && session.signedIn) window.location.replace("/reconciliation");
    if (!loginPage && !session.signedIn) window.location.replace("/reconciliation/login");
  }, [session, loginPage]);

  if (!session || session.signedIn === loginPage) return null;
  if (loginPage) return <ReconciliationLoginClient configured={session.configured} />;
  return <ReconciliationClient displayName={session.username || "اپراتور خزانه"} signOutPath={null} />;
}

function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  if (path === "/reconciliation/login") return <Reconciliation loginPage />;
  if (path === "/reconciliation" || path.startsWith("/reconciliation/")) {
    return <Reconciliation loginPage={false} />;
  }

  return <DashboardClient />;
}

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
