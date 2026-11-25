"""Rahkaran customer classification shared by forecasting and database exports."""
from pathlib import Path

import pandas as pd


PROJECT = next(parent for parent in Path(__file__).resolve().parents if (parent / "sales" / "backend").is_dir())
EXPORT_LIST = PROJECT / "sales" / "data" / "rahkaran" / "export_customers.csv"
COUNTRIES = (
    "عراق", "بغداد", "اربیل", "سلیمانیه", "افغانستان", "هرات", "کابل", "مزار", "ارمنستان", "یروان", "ایروان",
    "تاجکستان", "آذربایجان", "باکو", "روسیه", "سنگال", "ترکیه", "عمان", "امارات", "دبی", "قطر", "کویت",
    "ترکمنستان", "ازبکستان", "گرجستان",
)


def normalize(name):
    return str(name).replace("ي", "ی").replace("ك", "ک").strip()


EXPORT_NAMES = set(map(normalize, pd.read_csv(EXPORT_LIST, encoding="utf-8-sig")["name"]))


def channel_of(name):
    customer = normalize(name)
    if any(word in customer for word in ("هیبرید", "زنجیره", "اینترنت")):
        return "own"
    if "اهدایی" in customer or "مواد" in customer:
        return "drop"
    if customer in EXPORT_NAMES or any(country in customer for country in COUNTRIES):
        return "export"
    return "b2b"
