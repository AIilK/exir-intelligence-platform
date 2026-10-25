import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, loadEnv } from "vite";

const PROXY_PREFIX = "/__reconciliation_proxy";

// پنل مغایرت‌گیری صفحه ورود ندارد. کلید API بک‌اند را Proxy همین فرانت اضافه می‌کند تا مرورگر
// اپراتور کلید را نبیند. اگر فرانت .env.local نداشت، کلید از backend/.env خوانده می‌شود.
function backendEnvValue(name: string): string {
  try {
    const text = readFileSync(resolve(process.cwd(), "../backend/.env"), "utf8");
    const line = text.split(/\r?\n/).find((row) => row.trim().startsWith(`${name}=`));
    return line ? line.slice(line.indexOf("=") + 1).trim().replace(/^["']|["']$/g, "") : "";
  } catch {
    return "";
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendBaseUrl = (env.BACKEND_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const apiKey = (env.RECONCILIATION_API_KEY || backendEnvValue("RECONCILIATION_API_KEY")).trim();
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
    server: { host: "0.0.0.0", port: 3000, proxy },
    preview: { host: "0.0.0.0", port: 3000, proxy },
  };
});
