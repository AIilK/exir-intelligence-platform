"""تبدیل تاریخ میلادی به شمسی (بدون وابستگی خارجی)."""
import datetime as dt


def to_jalali(d: dt.date):
    gy, gm, gd = d.year, d.month, d.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


def jalali_date(d):
    y, m, dd = to_jalali(d.date() if isinstance(d, dt.datetime) else d)
    return f"{y}/{m:02d}/{dd:02d}"


def jalali_str(ts: float, with_time=True):
    t = dt.datetime.fromtimestamp(ts)
    s = jalali_date(t)
    return f"{s} {t:%H:%M}" if with_time else s
