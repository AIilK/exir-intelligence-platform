import { NextResponse } from "next/server";
import {
  clearReconciliationSession,
  createReconciliationSession,
  localReconciliationAuthConfigured,
  validateReconciliationCredentials,
} from "../../../reconciliation-session";

export async function POST(request: Request) {
  if (!localReconciliationAuthConfigured()) {
    return NextResponse.json({ detail: "ورود محلی هنوز تنظیم نشده است." }, { status: 503 });
  }
  const payload = await request.json().catch(() => ({}));
  const username = typeof payload.username === "string" ? payload.username : "";
  const password = typeof payload.password === "string" ? payload.password : "";
  if (!validateReconciliationCredentials(username, password)) {
    return NextResponse.json({ detail: "نام کاربری یا رمز عبور صحیح نیست." }, { status: 401 });
  }
  await createReconciliationSession(username);
  return NextResponse.json({ status: "success" });
}

export async function DELETE() {
  await clearReconciliationSession();
  return NextResponse.json({ status: "success" });
}
