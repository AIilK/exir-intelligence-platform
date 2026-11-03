"use client";
// «لینک چت‌بات»: چت‌بات می‌گوید کدام صفحه با چه فیلتری باز شود (مثلاً ریز چک‌های باز «شمس» در راهکاران،
// پرونده یک مشتری، بدهی یک تأمین‌کننده، توزیع یک ماه/هیبرید، اسناد خرید مهر). صفحه مقصد با useChatLink
// آن را می‌گیرد، فیلتر را خودش اعمال می‌کند و با flashChatTarget به بخش فیلترشده می‌رود.
import { useEffect, useState } from "react";

export type ChatLink = {
  view: string;
  source?: "rahkaran" | "karamad";
  search?: string;
  ref?: string;          // کد مشتری/طرف حساب (مثلاً counterpart_ref راهکاران یا کد تفصیلی)
  tab?: string;          // زیربخش صفحه (مثلاً trade/nontrade یا documents/items)
  year?: number | null;
  month?: number | null;
  at: number;
};

const EVENT = "exir:chat-link";
let pending: ChatLink | null = null;

export function sendChatLink(link: Omit<ChatLink, "at">) {
  pending = { ...link, at: Date.now() };
  window.dispatchEvent(new CustomEvent<ChatLink>(EVENT, { detail: pending }));
}

/** آخرین لینک چت برای این صفحه (چه قبل از باز شدن صفحه فرستاده شده باشد چه بعدش). */
export function useChatLink(view: string): ChatLink | null {
  const [link, setLink] = useState<ChatLink | null>(() => (pending?.view === view ? pending : null));
  useEffect(() => {
    if (pending?.view === view) { setLink(pending); pending = null; }
    const on = (e: Event) => {
      const l = (e as CustomEvent<ChatLink>).detail;
      if (l.view === view) { setLink(l); pending = null; }
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [view]);
  return link;
}

/** به بخش فیلترشده اسکرول کن و لحظه‌ای برجسته‌اش کن (کلاس chat-linked در chatbot.css). */
export function flashChatTarget(el: Element | null | undefined, delay = 300) {
  window.setTimeout(() => {
    if (!el) return;
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 90, behavior: "smooth" });
    el.classList.add("chat-linked");
    window.setTimeout(() => el.classList.remove("chat-linked"), 2600);
  }, delay);
}
