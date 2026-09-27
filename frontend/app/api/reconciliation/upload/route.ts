import { NextResponse } from "next/server";
import {
  getReconciliationAccess,
  reconciliationBackendHeaders,
  reconciliationBackendUrl,
} from "../../../reconciliation-access";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  const access = await getReconciliationAccess();
  if (!access.allowed) {
    return NextResponse.json({ detail: "دسترسی غیرمجاز است." }, { status: 403 });
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("multipart/form-data")) {
    return NextResponse.json({ detail: "درخواست بارگذاری فایل معتبر نیست." }, { status: 415 });
  }

  try {
    // V90: Do not call request.formData() here. Mellat HTML/PDF statements can be
    // several megabytes and parsing/rebuilding multipart in the frontend proxy can
    // fail before FastAPI receives the file. Forward the original multipart bytes.
    const rawBody = await request.arrayBuffer();
    if (!rawBody.byteLength) {
      return NextResponse.json({ detail: "فایل صورتحساب ارسال نشده است." }, { status: 422 });
    }

    const headers = new Headers(reconciliationBackendHeaders());
    headers.set("Content-Type", contentType);
    headers.set("Content-Length", String(rawBody.byteLength));

    const response = await fetch(
      reconciliationBackendUrl("/reconciliation/auto-upload"),
      {
        method: "POST",
        headers,
        body: rawBody,
        cache: "no-store",
      },
    );

    const responseType = response.headers.get("content-type") ?? "";
    if (responseType.includes("application/json")) {
      const payload = await response.json().catch(() => ({
        detail: "پاسخ Backend قابل خواندن نیست.",
      }));
      return NextResponse.json(payload, { status: response.status });
    }

    const text = await response.text().catch(() => "");
    return NextResponse.json(
      {
        detail: response.ok
          ? "پاسخ سرویس مغایرت‌گیری نامعتبر است."
          : text.slice(0, 1000) || `سرویس مغایرت‌گیری خطای ${response.status} برگرداند.`,
      },
      { status: response.ok ? 502 : response.status },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json(
      {
        detail: `ارتباط با سرویس مغایرت‌گیری برقرار نشد.${message ? ` (${message})` : ""}`,
      },
      { status: 502 },
    );
  }
}
