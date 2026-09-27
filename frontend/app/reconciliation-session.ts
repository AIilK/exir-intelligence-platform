import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

const COOKIE_NAME = "exir_reconciliation_session";
const SESSION_SECONDS = 8 * 60 * 60;

function secureCookieEnabled(): boolean {
  return (process.env.RECONCILIATION_COOKIE_SECURE ?? "false")
    .trim()
    .toLowerCase() === "true";
}

type SessionPayload = {
  role: "reconciliation";
  username: string;
  exp: number;
};

function configuredCredentials() {
  return {
    username: (process.env.RECONCILIATION_OPERATOR_USERNAME ?? "").trim(),
    password: (process.env.RECONCILIATION_OPERATOR_PASSWORD ?? "").trim(),
    secret: (process.env.RECONCILIATION_SESSION_SECRET ?? "").trim(),
  };
}

function safeEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}

function signature(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

export function localReconciliationAuthConfigured(): boolean {
  const config = configuredCredentials();
  return Boolean(config.username && config.password && config.secret.length >= 24);
}

export function validateReconciliationCredentials(
  username: string,
  password: string,
): boolean {
  if (!localReconciliationAuthConfigured()) return false;
  const config = configuredCredentials();
  return safeEqual(username.trim(), config.username) && safeEqual(password, config.password);
}

export async function createReconciliationSession(username: string) {
  const config = configuredCredentials();
  if (!localReconciliationAuthConfigured()) {
    throw new Error("Local reconciliation authentication is not configured.");
  }
  const payload: SessionPayload = {
    role: "reconciliation",
    username: username.trim(),
    exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
  };
  const encoded = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  const token = `${encoded}.${signature(encoded, config.secret)}`;
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "strict",
    // Internal LAN installations usually use HTTP. Enable this only after HTTPS.
    secure: secureCookieEnabled(),
    path: "/",
    maxAge: SESSION_SECONDS,
  });
}

export async function clearReconciliationSession() {
  const store = await cookies();
  store.set(COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: secureCookieEnabled(),
    path: "/",
    maxAge: 0,
  });
}

export async function getReconciliationSession(): Promise<SessionPayload | null> {
  if (!localReconciliationAuthConfigured()) return null;
  const config = configuredCredentials();
  const store = await cookies();
  const token = store.get(COOKIE_NAME)?.value ?? "";
  const [encoded, receivedSignature, ...rest] = token.split(".");
  if (!encoded || !receivedSignature || rest.length) return null;
  if (!safeEqual(receivedSignature, signature(encoded, config.secret))) return null;

  try {
    const payload = JSON.parse(
      Buffer.from(encoded, "base64url").toString("utf8"),
    ) as SessionPayload;
    if (
      payload.role !== "reconciliation" ||
      payload.username !== config.username ||
      payload.exp <= Math.floor(Date.now() / 1000)
    ) return null;
    return payload;
  } catch {
    return null;
  }
}
