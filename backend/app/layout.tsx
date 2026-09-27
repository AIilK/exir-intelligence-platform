import type { Metadata } from "next";
import "./globals.css";
import "./agent.css";

export const metadata: Metadata = {
  title: "داشبورد هوشمند رفتار مشتری اکسیر کادوس",
  description: "پایش هوشمند رفتار مشتری، ریسک چک، سررسید و پیش‌بینی نقدینگی",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl">
      <body className="antialiased">{children}</body>
    </html>
  );
}
