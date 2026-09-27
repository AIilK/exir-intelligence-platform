import { redirect } from "next/navigation";
import { getReconciliationAccess } from "../../reconciliation-access";
import ReconciliationLoginClient from "./reconciliation-login-client";
import "../reconciliation.css";

export const dynamic = "force-dynamic";

export default async function ReconciliationLoginPage() {
  const access = await getReconciliationAccess();
  if (access.allowed) redirect("/reconciliation");
  return <ReconciliationLoginClient configured={access.reason !== "not_configured"} />;
}
