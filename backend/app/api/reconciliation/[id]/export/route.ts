import { NextResponse } from "next/server";
import {
  getReconciliationAccess,
  reconciliationBackendHeaders,
  reconciliationBackendUrl,
} from "../../../../reconciliation-access";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const access = await getReconciliationAccess();
  if (!access.allowed) {
    return NextResponse.json({ detail: "دسترسی غیرمجاز است." }, { status: 403 });
  }

  const { id } = await context.params;
  if (!/^[a-f0-9]{32}$/i.test(id)) {
    return NextResponse.json({ detail: "شناسه گزارش معتبر نیست." }, { status: 422 });
  }

  try {
    const response = await fetch(
      reconciliationBackendUrl(`/reconciliation/${id}/export.xlsx`),
      { headers: reconciliationBackendHeaders(), cache: "no-store" },
    );
    if (!response.ok) {
      const payload = await response.json().catch(() => ({
        detail: "دریافت خروجی با خطا مواجه شد.",
      }));
      return NextResponse.json(payload, { status: response.status });
    }

    return new Response(await response.arrayBuffer(), {
      status: 200,
      headers: {
        "Content-Type": response.headers.get("content-type") ??
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": response.headers.get("content-disposition") ??
          `attachment; filename=reconciliation-${id}.xlsx`,
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "ارتباط با سرویس خروجی برقرار نشد." },
      { status: 502 },
    );
  }
}
