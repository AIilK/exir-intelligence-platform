// رنگ سازمانی برندها (از لوگوها)؛ dark = نسخه روشن‌تر برای حالت تاریک، وقتی رنگ اصلی روی زمینه تیره دیده نمی‌شود.
// برندی که اینجا نیست با رنگ خنثی نمایش داده می‌شود.
export const BRAND_COLORS = {
  'پادینا': { light: '#a5567f', dark: '#c4709c' },   // ارغوانی Padina
  'جوو': { light: '#2e3192', dark: '#6268d6' },      // سرمه‌ای JEVO
  'بیس': { light: '#d71920', dark: '#ec4b41' },      // قرمز Base Color Beauty
  'وینا': { light: '#a41d37', dark: '#cf3c58' },     // زرشکی VINA
  'مولهنس': { light: '#231f20', dark: '#a8a69e' },   // مشکی MULHENS
  'آرکیا': { light: '#62b146', dark: '#6fbf52' },    // سبز Arkia
  'کالیون': { light: '#8a9a5b', dark: '#a6b56f' },   // سبز زیتونی Kalyon
  'لورینت': { light: '#8b2381', dark: '#b84cab' },   // بنفش Lorient
  'تاکوری': { light: '#b8976b', dark: '#c9a87c' },   // طلایی TACORI
  'اورادنت': { light: '#3e9c9b', dark: '#4fb3b2' },  // فیروزه‌ای ORADENT
}

/** رنگ برند برای تم فعلی نمودار (t از useTheme)؛ برند ناشناخته = رنگ خنثی محور */
export const brandColor = (name, t) => {
  const c = BRAND_COLORS[name]
  return c ? (t.dark ? c.dark : c.light) : t.axis
}
