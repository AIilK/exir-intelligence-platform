import { redirect } from "next/navigation";
import { chatGPTSignOutPath } from "../chatgpt-auth";
import { getReconciliationAccess } from "../reconciliation-access";
import ReconciliationClient from "./reconciliation-client";
import "./reconciliation.css";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "پنل مغایرت‌گیری بانک | اکسیر کادوس",
  description: "بارگذاری صورتحساب و دریافت خروجی مغایرت‌گیری خزانه",
};

export default async function ReconciliationPage() {
  const access = await getReconciliationAccess();
  if (!access.allowed && access.reason === "not_signed_in") {
    redirect("/reconciliation/login");
  }

  if (!access.allowed) {
    return (
      <main className="rc-shell rc-denied">
        <section>
          <span className="rc-lock">◈</span>
          <p className="rc-eyebrow">دسترسی محدود</p>
          <h1>این بخش برای شما فعال نیست</h1>
          <p>
            پنل مغایرت‌گیری فقط برای اپراتور تعیین‌شده خزانه قابل استفاده است.
          </p>
        </section>
      </main>
    );
  }

  return (
    <ReconciliationClient
      displayName={access.user.displayName}
      signOutPath={
        access.method === "chatgpt"
          ? chatGPTSignOutPath("/reconciliation")
          : null
      }
    />
  );
}
