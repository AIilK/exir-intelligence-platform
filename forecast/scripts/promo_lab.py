"""Does training on promotions improve the Hybrid forecast?

Promotion inputs per product per month (KDB invoice discounts by type, sales lines only):
  promo rate     (offer + festival + management discount) / gross sales
  offer rate, festival rate, breadth (share of invoices of the product that carried a promotion)
Configs (all on top of the Hybrid setup kept earlier: capped spikes, extra features, inflation):
  base          no promotion inputs
  promo_past    promotion inputs of the last two months (known when the forecast is made)
  promo_known   also the promotion inputs of the forecast month itself, as if a promotion calendar existed,
                plus WMA_PROMO = weighted average x promotion uplift learned from earlier months
Scored like the channel lab: model per class chosen on early origins (3-month tolWAPE), confirmed on late origins.
Output: forecast/lab/promo_experiments.xlsx
"""
import numpy as np
import pandas as pd

import channels as C
import forecast_lab2 as L2

F = C.F
BINS = [0, 0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 10]

pr = pd.read_csv(F.DATA / "kdb_promotions_monthly.csv", dtype={"code": str})
for col in ("gross", "offer", "festival", "mgmt", "invoices", "promo_invoices"):
    pr[col] = pd.to_numeric(pr[col], errors="coerce").astype(float)
pr["mi"] = pr["pm"].map(F.mon)
pv = lambda col: pr.pivot_table(index="mi", columns="code", values=col, aggfunc="sum").reindex(F.idx).reindex(columns=F.codes)
G = pv("gross").replace(0, np.nan)
PROMO = {"rate": ((pv("offer") + pv("festival") + pv("mgmt")) / G).fillna(0).clip(0, 1).values,
         "offer": (pv("offer") / G).fillna(0).clip(0, 1).values,
         "festival": (pv("festival") / G).fillna(0).clip(0, 1).values,
         "breadth": (pv("promo_invoices") / pv("invoices").replace(0, np.nan)).fillna(0).values}


class PromoFeats(L2.Feats):
    def __init__(self, ch, D, cfg, known):
        super().__init__(ch, D, cfg)
        self.known = known

    def block(self, P, h):
        X, ok = super().block(P, h)
        P = np.asarray(P)
        n = self.ch.n
        cols = []
        arrays = list(PROMO.values()) + ([PROMO_REL] if getattr(self, "rel", False) else [])
        for arr in arrays:
            cols.append(arr[P])
            cols.append(np.where((P - 1)[:, None] >= 0, arr[np.maximum(P - 1, 0)], 0.0))
            if self.known:
                t = P + h
                cols.append(np.where((t < F.T)[:, None], arr[np.minimum(t, F.T - 1)], 0.0))
        extra = np.stack(cols, axis=-1).reshape(len(P) * n, len(cols)).astype(np.float32)
        return np.hstack([X, extra]), ok


# relative promotion: this month's promotion rate minus the product's average of the previous 6 months
_prev6 = pd.DataFrame(PROMO["rate"]).shift(1).rolling(6, min_periods=1).mean().fillna(0).values
PROMO_REL = PROMO["rate"] - _prev6
REL_BINS = [-10, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 10]


def uplift_table(ch, YH, cut_row, rel=False):
    """median of sales / normal level by promotion bin, from months up to cut_row only."""
    base = pd.DataFrame(YH).shift(1).rolling(12, min_periods=6).median().values
    ratio = YH / np.where(base > 0, base, np.nan)
    rows = np.arange(F.T) <= cut_row
    x, bins = (PROMO_REL, REL_BINS) if rel else (PROMO["rate"], BINS)
    U = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = rows[:, None] & (x >= lo) & (x < hi) & (ch.CLS <= 2) & ~np.isnan(ratio)
        U.append(float(np.nanmedian(ratio[m])) if m.sum() > 200 else np.nan)
    U = np.array(U)
    return np.where(np.isnan(U), np.nanmedian(U), U)


def bin_of(x, bins=BINS):
    return np.clip(np.searchsorted(bins, x, side="right") - 1, 0, len(bins) - 2)


def run(ch, cfg, mode):
    stat = L2.Stat(ch, ch.history(cfg))
    known = mode.startswith("promo_known")
    rel = mode == "promo_known_rel"
    feats = L2.Feats(ch, stat.D, cfg) if mode == "base" else PromoFeats(ch, stat.D, cfg, known=known)
    if rel:
        feats.rel = True
    learners = {cut: L2.Learn(feats, F.mon(cut)) for cut in (F.CUT_EARLY, F.CUT_LATE)}
    U = {cut: uplift_table(ch, stat.YH, F.R(F.mon(cut)), rel=rel) for cut in (F.CUT_EARLY, F.CUT_LATE)}
    preds = {}
    for o in ch.ROLL:
        tg = [t for t in (o + 1, o + 2, o + 3) if t <= F.i_last and ch.valid[F.R(t)]]
        if not tg:
            continue
        cut = F.CUT_EARLY if F.plabel(o) <= F.SPLIT else F.CUT_LATE
        p = F.R(o)
        fc = stat.forecast(p, tg)
        fc.update(learners[cut].forecast(p, tg))
        fc = F.ensembles(fc)
        if mode == "promo_known":
            recent = PROMO["rate"][max(p - 2, 0):p + 1].mean(axis=0)
            mult = np.stack([np.clip(U[cut][bin_of(PROMO["rate"][F.R(t)])] / U[cut][bin_of(recent)], 0.5, 2.0) for t in tg])
            fc["WMA_PROMO"] = fc["WMA"] * mult
        if rel:
            recent = PROMO_REL[max(p - 2, 0):p + 1].mean(axis=0)
            mult = np.stack([np.clip(U[cut][bin_of(PROMO_REL[F.R(t)], REL_BINS)] / U[cut][bin_of(recent, REL_BINS)], 0.5, 2.0)
                             for t in tg])
            fc["WMA_PROMO"] = fc["WMA"] * mult
        for m, v in fc.items():
            preds.setdefault(m, []).append(v)
    return {m: np.vstack(v).astype(np.float32) for m, v in preds.items()}, U


if __name__ == "__main__":
    ch = L2.Channel("hybrid", F.Y, F.codes)
    cfg = L2.CFGS["+inflation"]
    summary, per_model = [], []
    for mode in ("base", "promo_past", "promo_known", "promo_known_rel"):
        preds, U = run(ch, cfg, mode)
        L2.POOL = F.EXT_POOL + (["WMA_PROMO"] if mode.startswith("promo_known") else [])
        rows, chosen, _ = L2.evaluate(ch, preds, mode)
        summary += rows
        for m in preds:
            for half, hm in (("early", ~ch.LATE), ("late", ch.LATE)):
                mask = hm[:, None] & (ch.CLS_P <= 1)
                r = L2.metrics(preds[m], ch.ACT, mask)
                P3, A3, C3, L3 = L2.three_month(ch, preds[m])
                r3 = L2.metrics(P3, A3, ((L3 if half == "late" else ~L3)[:, None]) & (C3 <= 1))
                per_model.append({"config": mode, "model": m, "half": half, "WAPE (A+B)": round(r["WAPE"], 4),
                                  "tolWAPE (A+B)": round(r["tolWAPE"], 4), "3m tolWAPE (A+B)": round(r3["tolWAPE"], 4),
                                  "bias": round(r["bias"], 4)})
        l = [r for r in rows if r["class"] == "ALL" and r["half"] == "late"][0]
        e = [r for r in rows if r["class"] == "ALL" and r["half"] == "early"][0]
        F.log(f"{mode:>12}: early tolWAPE {e['tolWAPE']:.4f} 3m {e['3m_tolWAPE']:.4f} | late tolWAPE {l['tolWAPE']:.4f} "
              f"3m {l['3m_tolWAPE']:.4f} | chosen {chosen}")
        if mode.startswith("promo_known"):
            b = REL_BINS if mode.endswith("rel") else BINS
            F.log(f"{mode} uplift (sales / normal), learned up to 1404/06:",
                  {f"{lo:+.0%}..{hi:+.0%}": round(float(u), 2) for lo, hi, u in zip(b[:-1], b[1:], U[F.CUT_LATE])})
    with pd.ExcelWriter(F.LAB / "promo_experiments.xlsx") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Chosen per class", index=False)
        pd.DataFrame(per_model).to_excel(xw, sheet_name="Models A+B", index=False)
    pm = pd.DataFrame(per_model)
    print(pm[pm.model.isin(["WMA", "WMA_PROMO", "ML", "DL", "MED4", "MEAN4"])].pivot_table(
        index=["model"], columns=["config", "half"], values="3m tolWAPE (A+B)").round(3).to_string())
