import { redirect } from "next/navigation";
import DashboardClient from "./dashboard-client";
import {
  chatGPTSignInPath,
  getChatGPTUser,
} from "./chatgpt-auth";
import { getReconciliationAccess } from "./reconciliation-access";

export const dynamic = "force-dynamic";

function dashboardEmails(): Set<string> {
  return new Set(
    (process.env.DASHBOARD_ALLOWED_EMAILS ?? "")
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
}

export default async function HomePage() {
  const reconciliationAccess = await getReconciliationAccess();
  if (reconciliationAccess.allowed && reconciliationAccess.method === "local") {
    redirect("/reconciliation");
  }
  const user = await getChatGPTUser();
  const operatorEmail = (
    process.env.RECONCILIATION_OPERATOR_EMAIL ?? ""
  ).trim().toLowerCase();
  const allowedDashboardUsers = dashboardEmails();

  if (
    user &&
    operatorEmail &&
    user.email.toLowerCase() === operatorEmail &&
    !allowedDashboardUsers.has(operatorEmail)
  ) {
    redirect("/reconciliation");
  }

  // Setting DASHBOARD_ALLOWED_EMAILS enables strict dashboard access control.
  // It stays backward-compatible when the variable is intentionally empty.
  if (allowedDashboardUsers.size > 0) {
    if (!user) redirect(chatGPTSignInPath("/"));
    if (!allowedDashboardUsers.has(user.email.toLowerCase())) {
      redirect("/reconciliation");
    }
  }

  return <DashboardClient />;
}
