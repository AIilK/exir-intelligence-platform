import { createHmac, timingSafeEqual } from "node:crypto";
import { defineConfig, loadEnv, type Plugin } from "vite";

const PROXY_PREFIX = "/__reconciliation_proxy";
const COOKIE_NAME = "exir_reconciliation_session";

function safeEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function validReconciliationCookie(cookieHeader: string | undefined, username: string, secret: string): boolean {
  if (!username || secret.length < 24) return false;
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
  const expected = createHmac("sha256", secret).update(encoded).digest("base64url");
  if (!safeEqual(received, expected)) return false;
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8"));
    return payload?.role === "reconciliation"
      && payload?.username === username
      && Number(payload?.exp ?? 0) > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

function reconciliationProxyGuard(username: string, secret: string): Plugin {
  return {
    name: "reconciliation-proxy-guard",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith(PROXY_PREFIX)) return next();
        if (!validReconciliationCookie(req.headers.cookie, username, secret)) {
          res.statusCode = 403;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ detail: "نشست مغایرت‌گیری معتبر نیست. دوباره وارد پنل شوید." }));
          return;
        }
        next();
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendBaseUrl = (env.BACKEND_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const apiKey = (env.RECONCILIATION_API_KEY || "").trim();
  const username = (env.RECONCILIATION_OPERATOR_USERNAME || "").trim();
  const sessionSecret = (env.RECONCILIATION_SESSION_SECRET || "").trim();

  return {
    plugins: [reconciliationProxyGuard(username, sessionSecret)],
    server: {
      host: "0.0.0.0",
      port: 3000,
      proxy: {
        [PROXY_PREFIX]: {
          target: backendBaseUrl,
          changeOrigin: true,
          secure: false,
          headers: apiKey ? { "X-Reconciliation-API-Key": apiKey } : {},
          rewrite: (path) => path.replace(PROXY_PREFIX, "/api/v1/treasury"),
        },
      },
    },
  };
});
