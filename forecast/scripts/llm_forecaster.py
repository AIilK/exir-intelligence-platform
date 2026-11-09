"""LLM forecaster: an OpenAI model (OPENAI_MODEL / OPENAI_API_KEY in backend/.env) reads each product's monthly
history plus price, inflation and calendar context and returns a forecast in units.

Products: class A and B of each channel (Hybrid, B2B, Export) at each origin, 15 per request.
Origins : backtest 1403/10, 1404/03 (early half), 1405/02, 1405/04 (late half), horizons 1-3; final 1405/07, horizons 1-4.
Data sent to OpenAI: product code, product name, brand, channel, monthly unit sales, company price-index changes,
event days. No customer names, prices in rials or stock levels.
Output: forecast/data/llm_preds.json  {channel: {origin: {code: [units per horizon]}}} (resumable cache)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

import channels as C

F = C.F
OUT = F.DATA / "llm_preds.json"
BACKTEST_ORIGINS = ["1403/10", "1404/03", "1405/02", "1405/04"]
FINAL_ORIGIN = "1405/07"
BATCH = 15
HISTORY = 36
CHANNEL_TEXT = {
    "hybrid": "sales of the company's own retail branches (Hybrid network) to customers",
    "b2b": "factory sales to domestic distributors/representatives (B2B), net of returns",
    "export": "factory sales to export customers (Iraq, Afghanistan, Armenia, ...), net of returns",
}


def env(key):
    for line in (F.ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KEY, MODEL = env("OPENAI_API_KEY"), env("OPENAI_MODEL") or "gpt-4o"


def channel_data():
    out = {"hybrid": (F.Y, F.codes)}
    out.update(C.RK)
    return out


def classes_at(Y, row):
    w = np.nansum(np.clip(Y[max(row - 11, 0):row + 1], 0, None), axis=0)
    order = np.argsort(-w)
    tot = w.sum()
    cls = np.full(Y.shape[1], "N", dtype=object)
    if tot <= 0:
        return cls
    before = np.concatenate([[0.0], np.cumsum(w[order])[:-1]]) / tot
    lab = np.where(w[order] <= 0, "N", np.where(before < 0.80, "A", np.where(before < 0.95, "B", "C")))
    cls[order] = lab
    return cls


def prompt(ch, Y, codes, ks, row, horizons, final):
    o = F.idx[row]
    targets = [F.plabel(o + h) for h in horizons]
    pi = C.PI
    ctx = [f"Channel: {CHANNEL_TEXT[ch]}.",
           "Months are Persian calendar (yyyy/mm). Units are pieces. Months with an internet outage or broken data "
           "(e.g. 1404/10-1405/01) are left out of the history.",
           f"Company list prices: +{pi['yoy'][row] * 100:.0f}% over the last 12 months, +{pi['q3'][row] * 100:.0f}% over the "
           f"last 3 months, +{pi['mom'][row] * 100:.0f}% in the last month. Big price rises can cause buying ahead of the rise "
           "and a dip afterwards.",
           "Ramadan days in the target months: " + ", ".join(f"{t}: {F.RAM.get(o + h, 0)}" for t, h in zip(targets, horizons)) + ".",
           "Persian new year (month 01) is usually a low month; months 10-11 are usually high."]
    if final:
        ctx.append("Official point-to-point consumer inflation (news reports): " +
                   ", ".join(f"{k}: {v}%" for k, v in C.OFFICIAL_INFLATION.items()) + ".")
    lines = []
    for k in ks:
        c = codes[k]
        name = F.goods.loc[c, "name"] if c in F.goods.index else ""
        brand = F.goods.loc[c, "brand"] if c in F.goods.index else ""
        hist = [f"{F.plabel(F.idx[r])}:{max(Y[r, k], 0):.0f}" for r in range(max(row - HISTORY + 1, 0), row + 1)
                if not np.isnan(Y[r, k])]
        lines.append(f'"{c}" ({name} | {brand}): ' + ", ".join(hist))
    return ("You forecast monthly unit sales per product for an Iranian cosmetics and hygiene manufacturer.\n"
            + "\n".join(ctx) +
            f"\nForecast the units for these months, in order: {', '.join(targets)}.\n"
            "Think about each product's level, trend, seasonality (same month in earlier years) and the price context. "
            "Reply with only a JSON object that maps each product code to a list of non-negative numbers, one per month.\n"
            "Products and history:\n" + "\n".join(lines))


def call(text):
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": text}]}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body,
                                         headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                content = json.loads(r.read())["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", content, re.S)
            return json.loads(m.group(0)) if m else {}
        except urllib.error.HTTPError as e:
            F.log(f"  HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:150]}")
            if e.code in (400, 401, 403, 404):
                return {}
        except Exception as e:
            F.log(f"  error {type(e).__name__} (attempt {attempt + 1})")
        time.sleep(5 * (attempt + 1))
    return {}


def run():
    if not KEY:
        sys.exit("OPENAI_API_KEY missing in backend/.env")
    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    jobs = [(o, [1, 2, 3], False) for o in BACKTEST_ORIGINS] + [(FINAL_ORIGIN, [1, 2, 3, 4], True)]
    for ch, (Y, codes) in channel_data().items():
        for o_lab, horizons, final in jobs:
            row = F.R(F.mon(o_lab))
            cls = classes_at(Y, row)
            ks = [k for k in range(len(codes)) if cls[k] in ("A", "B")]
            done = store.setdefault(ch, {}).setdefault(o_lab, {})
            todo = [k for k in ks if codes[k] not in done]
            batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
            F.log(f"{ch} {o_lab}: {len(ks)} A/B products, {len(batches)} requests to send")
            with ThreadPoolExecutor(max_workers=6) as ex:
                for res in ex.map(lambda b: call(prompt(ch, Y, codes, b, row, horizons, final)), batches):
                    for c, v in (res or {}).items():
                        if isinstance(v, list) and len(v) >= len(horizons):
                            try:
                                done[str(c)] = [max(float(x), 0.0) for x in v[:len(horizons)]]
                            except (TypeError, ValueError):
                                pass
                    OUT.write_text(json.dumps(store), encoding="utf-8")
            F.log(f"{ch} {o_lab}: {len(done)} forecasts stored")


if __name__ == "__main__":
    run()
