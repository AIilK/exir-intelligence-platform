import { createHmac, timingSafeEqual } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import { defineConfig, loadEnv, type Connect, type Plugin } from "vite";

const PROXY_PREFIX = "/__reconciliation_proxy";
const SESSION_PATH = "/api/reconciliation/session";
const COOKIE_NAME = "exir_reconciliation_session";
const SESSION_SECONDS = 8 * 60 * 60;
const MAX_BODY_BYTES = 16 * 1024;

type ReconciliationAuthConfig = {
  username: string;
  password: string;
  secret: string;
  secureCookie: boolean;
};

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function signature(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value).digest("base64url");
}

function authConfigured(config: ReconciliationAuthConfig): boolean {
  return Boolean(config.username && config.password && config.secret.length >= 24);
}

function sendJson(res: ServerResponse, status: number, body: unknown, cookie?: string) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  if (cookie) res.setHeader("Set-Cookie", cookie);
  res.end(JSON.stringify(body));
}

function sessionCookie(config: ReconciliationAuthConfig, token: string, maxAge: number): string {
  // Internal LAN installations usually use HTTP. Enable Secure only after HTTPS.
  const secure = config.secureCookie ? "; Secure" : "";
  return `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure}`;
}

function createSessionToken(config: ReconciliationAuthConfig): string {
  const payload = {
    role: "reconciliation",
    username: config.username,
    exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
  };
  const encoded = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  return `${encoded}.${signature(encoded, config.secret)}`;
}

function validReconciliationCookie(cookieHeader: string | undefined, config: ReconciliationAuthConfig): boolean {
  if (!authConfigured(config)) return false;
  const cookies = Object.fromEntries(
    (cookieHeader ?? "")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const index = part.indexOf("=");
        return index < 0 ? [part, ""] : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
      }),
  );
  const token = cookies[COOKIE_NAME] ?? "";
  const pieces = token.split(".");
  if (pieces.length !== 2) return false;
  const [encoded, received] = pieces;
  if (!safeEqual(received, signature(encoded, config.secret))) return false;
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    return payload?.role === "reconciliation"
      && payload?.username === config.username
      && Number(payload?.exp ?? 0) > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

function readJsonBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        req.destroy();
        resolve({});
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        resolve(parsed && typeof parsed === "object" ? parsed : {});
      } catch {
        resolve({});
      }
    });
    req.on("error", () => resolve({}));
  });
}

function reconciliationAuthMiddleware(config: ReconciliationAuthConfig): Connect.NextHandleFunction {
  return (req, res, next) => {
    const path = (req.url ?? "").split("?")[0];

    if (path === SESSION_PATH) {
      if (req.method === "GET") {
        sendJson(res, 200, {
          configured: authConfigured(config),
          signedIn: validReconciliationCookie(req.headers.cookie, config),
          username: config.username,
        });
        return;
      }
      if (req.method === "DELETE") {
        sendJson(res, 200, { status: "success" }, sessionCookie(config, "", 0));
        return;
      }
      if (req.method === "POST") {
        if (!authConfigured(config)) {
          sendJson(res, 503, { detail: "ورود محلی هنوز تنظیم نشده است." });
          return;
        }
        void readJsonBody(req).then((payload) => {
          const username = typeof payload.username === "string" ? payload.username.trim() : "";
          const password = typeof payload.password === "string" ? payload.password : "";
          if (!safeEqual(username, config.username) || !safeEqual(password, config.password)) {
            sendJson(res, 401, { detail: "نام کاربری یا رمز عبور صحیح نیست." });
            return;
          }
          sendJson(res, 200, { status: "success" }, sessionCookie(config, createSessionToken(config), SESSION_SECONDS));
        });
        return;
      }
      sendJson(res, 405, { detail: "Method not allowed." });
      return;
    }

    if (path.startsWith(PROXY_PREFIX) && !validReconciliationCookie(req.headers.cookie, config)) {
      sendJson(res, 403, { detail: "نشست مغایرت‌گیری معتبر نیست. دوباره وارد پنل شوید." });
      return;
    }
    next();
  };
}

function reconciliationAuth(config: ReconciliationAuthConfig): Plugin {
  const middleware = reconciliationAuthMiddleware(config);
  return {
    name: "reconciliation-auth",
    // Registered directly (not via a returned hook) so it runs before Vite's proxy.
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendBaseUrl = (env.BACKEND_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const apiKey = (env.RECONCILIATION_API_KEY || "").trim();
  const authConfig: ReconciliationAuthConfig = {
    username: (env.RECONCILIATION_OPERATOR_USERNAME || "").trim(),
    password: (env.RECONCILIATION_OPERATOR_PASSWORD || "").trim(),
    secret: (env.RECONCILIATION_SESSION_SECRET || "").trim(),
    secureCookie: (env.RECONCILIATION_COOKIE_SECURE || "false").trim().toLowerCase() === "true",
  };
  const proxy = {
    [PROXY_PREFIX]: {
      target: backendBaseUrl,
      changeOrigin: true,
      secure: false,
      headers: apiKey ? { "X-Reconciliation-API-Key": apiKey } : {},
      rewrite: (path: string) => path.replace(PROXY_PREFIX, "/api/v1/treasury"),
    },
  };

  return {
    plugins: [reconciliationAuth(authConfig)],
    server: { host: "0.0.0.0", port: 3000, proxy },
    preview: { host: "0.0.0.0", port: 3000, proxy },
  };
});
