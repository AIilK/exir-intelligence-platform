import "server-only";
import { getChatGPTUser, type ChatGPTUser } from "./chatgpt-auth";
import {
  getReconciliationSession,
  localReconciliationAuthConfigured,
} from "./reconciliation-session";

export type ReconciliationAccess =
  | { allowed: true; user: ChatGPTUser; method: "local" | "chatgpt" }
  | { allowed: false; reason: "not_signed_in" | "not_configured" | "forbidden" };

export async function getReconciliationAccess(): Promise<ReconciliationAccess> {
  const operatorEmail = (
    process.env.RECONCILIATION_OPERATOR_EMAIL ?? ""
  ).trim().toLowerCase();
  const user = await getChatGPTUser();
  if (user && operatorEmail) {
    if (user.email.trim().toLowerCase() !== operatorEmail) {
      return { allowed: false, reason: "forbidden" };
    }
    return { allowed: true, user, method: "chatgpt" };
  }

  const localSession = await getReconciliationSession();
  if (localSession) {
    return {
      allowed: true,
      method: "local",
      user: {
        displayName: localSession.username,
        email: localSession.username,
        fullName: null,
      },
    };
  }

  if (!operatorEmail && !localReconciliationAuthConfigured()) {
    return { allowed: false, reason: "not_configured" };
  }
  if (user && operatorEmail && user.email.trim().toLowerCase() !== operatorEmail) {
    return { allowed: false, reason: "forbidden" };
  }
  return { allowed: false, reason: "not_signed_in" };
}

export function reconciliationBackendUrl(path: string): string {
  const origin = (
    process.env.BACKEND_BASE_URL ?? "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  return `${origin}/api/v1/treasury${path}`;
}

export function reconciliationBackendHeaders(): HeadersInit {
  const apiKey = (process.env.RECONCILIATION_API_KEY ?? "").trim();
  return apiKey ? { "X-Reconciliation-API-Key": apiKey } : {};
}
