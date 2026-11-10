"""Per-channel forecast lab (Hybrid / B2B / Export) with the company's counting rules, inflation inputs and the
tolerance error the user asked for.

Error measures (per product per month, and per product over 3-month totals)
  WAPE        sum |forecast - actual| / sum actual
  tolWAPE     same, but a forecast from 5% below to 10% above actual counts as zero error
  hit         share of product-months whose forecast falls in that band
  hit_units   share of sold units whose forecast falls in that band
Configs per channel
  prev        setup kept earlier: capped spikes, extra features, extended model pool
  +inflation  adds company price-index changes (1, 3 and 12 months) as ML/DL inputs
Model per ABC class is chosen on EARLY origins (by tolWAPE) and scored on LATE origins.
Outputs: forecast/lab/channels_experiments.xlsx, lab/backtest_<channel>.npz, lab/final_<channel>.npz
"""
import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor

import channels as C

F = C.F
LO, HI = 0.95, 1.10
POOL = F.EXT_POOL
CFGS = {"prev": dict(spikes=True, features=True, inflation=False),
        "+inflation": dict(spikes=True, features=True, inflation=True)}


class Channel:
    def __init__(self, name, Y, codes):
        self.name, self.Y, self.codes, self.n = name, Y, list(codes), len(codes)
        self.hybrid = name == "hybrid"
        known = ~np.isnan(Y).all(axis=1)
        self.valid = F.valid_row & known
        self.first_row = int(np.argmax(known))
        tot = np.where(self.valid, np.nansum(Y, axis=1), np.nan)
        rat = {m: [] for m in range(12)}
        for yy in range(F.idx[0] // 12, F.idx[-1] // 12 + 1):
            rows = [F.R(i) for i in range(yy * 12, yy * 12 + 12) if F.i_start <= i <= F.i_last and self.valid[F.R(i)]]
            if len(rows) >= 10:
                for r in rows:
                    rat[F.idx[r] % 12].append(tot[r] / np.nanmean(tot[rows]))
        S = np.array([np.mean(rat[m]) if rat[m] else 1.0 for m in range(12)])
        self.S = S / S.mean()
        Yz = np.nan_to_num(np.clip(Y, 0, None))
        cz = np.vstack([np.zeros(self.n), np.cumsum(Yz, axis=0)])
        self.CLS = np.full((F.T, self.n), 3, dtype=np.int8)
        for t in range(F.T):
            w = cz[t + 1] - cz[max(t - 11, 0)]
            if w.sum() <= 0:
                continue
            o = np.argsort(-w)
            before = np.concatenate([[0.0], np.cumsum(w[o])[:-1]]) / w.sum()
            lab = np.where(w[o] <= 0, 3, np.where(before < 0.80, 0, np.where(before < 0.95, 1, 2)))
            self.CLS[t, o] = lab
        self.brand_of = [str(F.goods.loc[c, "brand"]) if c in F.goods.index and pd.notna(F.goods.loc[c, "brand"]) else f"_{c}"
                         for c in self.codes]
        self.DR, self.PCH = C.product_price_features(self.codes)
        if self.hybrid:
            self.BRC = F.BRC
        self.ROLL = [o for o in F.ROLL if F.R(o) >= self.first_row + 12 and self.valid[F.R(o)]]
        self.PAIRS = [(o, t) for o in self.ROLL for t in (o + 1, o + 2, o + 3) if t <= F.i_last and self.valid[F.R(t)]]
        self.ACT = np.stack([np.clip(np.nan_to_num(Y[F.R(t)]), 0, None) for _, t in self.PAIRS])
        self.CLS_P = np.stack([self.CLS[F.R(o)] for o, _ in self.PAIRS])
        self.LATE = np.array([F.plabel(o) > F.SPLIT for o, _ in self.PAIRS])
        self.ORIG = np.array([o for o, _ in self.PAIRS])

    def history(self, cfg):
        YH = self.Y.copy()
        YH[~self.valid] = np.nan
        if cfg["spikes"]:
            df = pd.DataFrame(YH)
            med = df.shift(1).rolling(12, min_periods=4).median()
            YH = df.where(~((df > 3 * med) & (med > 0)), 3 * med).to_numpy(copy=True)
        return YH


class Stat:
    def __init__(self, ch, YH):
        self.ch, self.YH = ch, YH
        self.D = YH / ch.S[F.idx % 12][:, None]
        self.wma, self.ses = F.wma_levels(self.D), F.ses_levels(self.D)
        self.sba, self.tsb = F.sba_rates(YH), F.tsb_levels(YH)
        G = pd.DataFrame(YH).T.groupby(ch.brand_of).sum(min_count=1).T
        names = list(G.columns)
        Gm = G.to_numpy(copy=True)
        Gm[~ch.valid] = np.nan
        GD = Gm / ch.S[F.idx % 12][:, None]
        self.g_level = np.nanmedian(np.stack([F.wma_levels(GD), F.ses_levels(GD)]), axis=0)
        gi = {g: j for j, g in enumerate(names)}
        self.g_of = np.array([gi[b] for b in ch.brand_of])
        s_p, _ = F.nan_window(YH, 12)
        s_g = np.zeros((F.T, len(names)))
        np.add.at(s_g.T, self.g_of, s_p.T)
        self.share = np.where(s_g[:, self.g_of] > 0, s_p / np.maximum(s_g[:, self.g_of], 1e-9), 0.0)

    def forecast(self, p, targets):
        n = self.ch.n
        out = {m: np.zeros((len(targets), n)) for m in ["WMA", "SES", "SBA", "TSB", "ADIDA", "SN", "TD_BRAND", "NAIVE"]}
        ad = F.adida_at(self.YH, p)
        for j, g in enumerate(targets):
            s = self.ch.S[g % 12]
            out["WMA"][j] = np.nan_to_num(self.wma[p]) * s
            out["SES"][j] = np.nan_to_num(self.ses[p]) * s
            out["SBA"][j], out["TSB"][j], out["ADIDA"][j] = self.sba[p], self.tsb[p], ad
            ly = [self.YH[F.R(g - 12)] if g - 12 >= F.i_start else np.full(n, np.nan),
                  self.YH[F.R(g - 24)] if g - 24 >= F.i_start else np.full(n, np.nan)]
            sn = np.nanmean(np.stack(ly), axis=0)
            out["SN"][j] = np.where(np.isnan(sn), out["WMA"][j], sn)
            out["TD_BRAND"][j] = np.nan_to_num(self.g_level[p][self.g_of]) * s * self.share[p]
            last = self.YH[p]
            out["NAIVE"][j] = np.where(np.isnan(last), out["WMA"][j], last)
        return {m: np.clip(v, 0, None) for m, v in out.items()}


class Feats:
    def __init__(self, ch, D, cfg):
        self.ch, self.D, self.cfg = ch, D, cfg
        s3, c3 = F.nan_window(D, 3)
        s12, c12 = F.nan_window(D, 12)
        self.m3 = np.where(c3 > 0, s3 / np.maximum(c3, 1), np.nan)
        self.m12 = np.where(c12 > 0, s12 / np.maximum(c12, 1), np.nan)
        nzs, _ = F.nan_window(np.where(np.isnan(D), np.nan, (np.nan_to_num(D) > 0).astype(float)), 12)
        self.nz = np.where(c12 > 0, nzs / np.maximum(c12, 1), np.nan)

    def shift(self, M, k, P):
        out = np.full((len(P), self.ch.n), np.nan)
        r = P - k
        out[r >= 0] = M[r[r >= 0]]
        return out

    def block(self, P, h):
        P = np.asarray(P)
        n, ch = self.ch.n, self.ch
        g = F.idx[P] + h
        rep = lambda v: np.repeat(np.asarray(v, float)[:, None], n, 1)
        base = F.L(self.m12[P])
        fill = lambda x: np.where(np.isnan(x), base, F.L(x))
        f = [fill(self.D[P]), fill(self.shift(self.D, 1, P)), fill(self.shift(self.D, 2, P)), F.L(self.m3[P]), base,
             self.nz[P], fill(self.shift(self.D, 12 - h, P)), rep(np.log(ch.S[g % 12])), rep(g % 12 + 1), rep([h] * len(P))]
        if ch.hybrid:
            f.append(rep(np.log(F.branches[P])))
        if self.cfg["features"]:
            if ch.hybrid:
                f += [np.log1p(ch.BRC[P]), ch.BRC[P] / np.maximum(F.branches[P], 1)[:, None]]
            f += [np.nan_to_num(ch.DR[P]), np.nan_to_num(ch.PCH[P]), rep(F.ev(F.RAM, g) / 30),
                  rep(F.ev(F.MUH, g) / 10), rep(F.ev(F.PREEID, g) / 14)]
        if self.cfg["inflation"]:
            f += [rep(C.PI["mom"][P]), rep(C.PI["q3"][P]), rep(C.PI["yoy"][P])]
        X = np.stack(f, axis=-1).reshape(len(P) * n, len(f)).astype(np.float32)
        return X, (~np.isnan(self.m12[P])).reshape(-1)


class Learn:
    def __init__(self, feats, cut_global):
        self.feats = feats
        cut = F.R(cut_global)
        Xs, ys = [], []
        for h in range(1, F.H_MAX + 1):
            P = np.arange(0, cut - h + 1)
            X, ok = feats.block(P, h)
            tgt = feats.D[P + h].reshape(-1)
            m = ok & ~np.isnan(tgt)
            Xs.append(X[m])
            ys.append(tgt[m])
        X, y = np.vstack(Xs), F.L(np.concatenate(ys))
        self.rows = len(y)
        self.gbm = lgb.LGBMRegressor(**F.LGB_PARAMS).fit(X, y)
        self.mu, self.sd = np.nanmean(X, 0), np.nanstd(X, 0) + 1e-9
        self.mlp = MLPRegressor(hidden_layer_sizes=(32,), batch_size=4096, learning_rate_init=2e-3, max_iter=5,
                                random_state=0).fit(np.nan_to_num((X - self.mu) / self.sd), y)

    def forecast(self, p, targets):
        n = self.feats.ch.n
        ml, dl = np.zeros((len(targets), n)), np.zeros((len(targets), n))
        for j, g in enumerate(targets):
            X, ok = self.feats.block([p], g - F.idx[p])
            s = self.feats.ch.S[g % 12]
            ml[j] = np.where(ok, np.expm1(self.gbm.predict(X)), 0.0) * s
            dl[j] = np.where(ok, np.expm1(self.mlp.predict(np.nan_to_num((X - self.mu) / self.sd))), 0.0) * s
        return {"ML": np.clip(ml, 0, None), "DL": np.clip(dl, 0, None)}


def backtest(ch, cfg):
    stat = Stat(ch, ch.history(cfg))
    feats = Feats(ch, stat.D, cfg)
    learners = {cut: Learn(feats, F.mon(cut)) for cut in (F.CUT_EARLY, F.CUT_LATE)}
    preds = {}
    for o in ch.ROLL:
        tg = [t for t in (o + 1, o + 2, o + 3) if t <= F.i_last and ch.valid[F.R(t)]]
        if not tg:
            continue
        fc = stat.forecast(F.R(o), tg)
        fc.update(learners[F.CUT_EARLY if F.plabel(o) <= F.SPLIT else F.CUT_LATE].forecast(F.R(o), tg))
        for m, v in F.ensembles(fc).items():
            preds.setdefault(m, []).append(v)
    return {m: np.vstack(v).astype(np.float32) for m, v in preds.items()}, stat, feats


def metrics(pred, act, mask):
    p, a = pred[mask].astype(float), act[mask].astype(float)
    if a.sum() <= 0:
        return dict(WAPE=np.nan, bias=np.nan, tolWAPE=np.nan, hit=np.nan, hit_units=np.nan)
    ok = np.where(a > 0, (p >= LO * a) & (p <= HI * a), p < 0.5)
    e = np.abs(p - a)
    active = (a > 0) | (p >= 0.5)
    return dict(WAPE=e.sum() / a.sum(), bias=(p - a).sum() / a.sum(), tolWAPE=(e * ~ok).sum() / a.sum(),
                hit=ok[active].mean() if active.any() else np.nan, hit_units=(a * ok).sum() / a.sum())


def three_month(ch, pred):
    """per product 3-month totals for origins that have all three target months."""
    P3, A3, C3, L3 = [], [], [], []
    for o in sorted(set(ch.ORIG)):
        rows = np.where(ch.ORIG == o)[0]
        if len(rows) == 3:
            P3.append(pred[rows].sum(0)); A3.append(ch.ACT[rows].sum(0))
            C3.append(ch.CLS_P[rows[0]]); L3.append(F.plabel(o) > F.SPLIT)
    return np.array(P3), np.array(A3), np.array(C3), np.array(L3)


def evaluate(ch, preds, label):
    rows, chosen = [], {}
    tot = {h: {"m": [], "3m": []} for h in ("early", "late")}
    tm = {m: three_month(ch, preds[m]) for m in POOL}
    for ci, cl in enumerate(F.CLASSES):
        # choose on 3-month totals (the production horizon): on single months a zero forecast wins for lumpy channels
        sc = {}
        for m in POOL:
            P3, A3, C3, L3 = tm[m]
            sc[m] = metrics(P3, A3, (C3 == ci) & ~L3[:, None])["tolWAPE"] if len(P3) else np.nan
        best = min(sc, key=lambda m: np.inf if np.isnan(sc[m]) else sc[m])
        chosen[cl] = best
        for half, hm in (("early", ~ch.LATE), ("late", ch.LATE)):
            mm = (ch.CLS_P == ci) & hm[:, None]
            r = metrics(preds[best], ch.ACT, mm)
            P3, A3, C3, L3 = three_month(ch, preds[best])
            m3 = (C3 == ci) & ((L3 if half == "late" else ~L3)[:, None]) if len(P3) else None
            r3 = metrics(P3, A3, m3) if len(P3) else {}
            rows.append({"channel": ch.name, "config": label, "class": cl, "half": half, "model": best,
                         **{k: round(v, 4) for k, v in r.items()},
                         **{f"3m_{k}": round(v, 4) for k, v in r3.items() if k in ("WAPE", "tolWAPE", "hit_units")}})
    # all classes combined, each with its chosen model
    for half, hm in (("early", ~ch.LATE), ("late", ch.LATE)):
        comb = np.zeros_like(ch.ACT)
        for ci, cl in enumerate(F.CLASSES):
            comb = np.where(ch.CLS_P == ci, preds[chosen[cl]], comb)
        r = metrics(comb, ch.ACT, np.broadcast_to(hm[:, None], ch.ACT.shape))
        P3, A3, C3, L3 = three_month(ch, comb)
        r3 = metrics(P3, A3, np.broadcast_to(((L3 if half == "late" else ~L3))[:, None], A3.shape)) if len(P3) else {}
        rows.append({"channel": ch.name, "config": label, "class": "ALL", "half": half, "model": "chosen per class",
                     **{k: round(v, 4) for k, v in r.items()},
                     **{f"3m_{k}": round(v, 4) for k, v in r3.items() if k in ("WAPE", "tolWAPE", "hit_units")}})
    return rows, chosen, comb


def all_models(ch, preds, label):
    out = []
    for m in preds:
        r = metrics(preds[m], ch.ACT, np.broadcast_to(ch.LATE[:, None], ch.ACT.shape))
        out.append({"channel": ch.name, "config": label, "model": m, **{k: round(v, 4) for k, v in r.items()}})
    return out


if __name__ == "__main__":
    chans = {"hybrid": Channel("hybrid", F.Y, F.codes)}
    for k, (Y, codes) in C.RK.items():
        chans[k] = Channel(k, Y, codes)
    summary, models_tab, decisions = [], [], {}
    for name, ch in chans.items():
        F.log(f"{name}: {ch.n} products, {len(ch.PAIRS)} backtest month-pairs (late {int(ch.LATE.sum())})")
        res = {}
        for label, cfg in CFGS.items():
            preds, stat, feats = backtest(ch, cfg)
            rows, chosen, comb = evaluate(ch, preds, label)
            summary += rows
            models_tab += all_models(ch, preds, label)
            res[label] = (preds, chosen, rows)
            e = [r for r in rows if r["class"] == "ALL" and r["half"] == "early"][0]
            l = [r for r in rows if r["class"] == "ALL" and r["half"] == "late"][0]
            F.log(f"  {name} {label:>11}: early tolWAPE {e['tolWAPE']:.4f} | late WAPE {l['WAPE']:.4f} "
                  f"tolWAPE {l['tolWAPE']:.4f} hit_units {l['hit_units']:.3f} | 3m late tolWAPE {l.get('3m_tolWAPE', float('nan')):.4f} | {chosen}")
        sc = lambda lab, half: [r for r in res[lab][2] if r["class"] == "ALL" and r["half"] == half][0]["tolWAPE"]
        # keep inflation inputs only if they help on early AND do not hurt on late months (safety check)
        keep = "+inflation" if sc("+inflation", "early") < sc("prev", "early") and sc("+inflation", "late") <= sc("prev", "late") else "prev"
        decisions[name] = keep
        preds, chosen, _ = res[keep]
        np.savez_compressed(F.LAB / f"backtest_{name}.npz", **preds, ACT=ch.ACT, CLS_P=ch.CLS_P, LATE=ch.LATE,
                            ORIG=ch.ORIG, TARG=np.array([t for _, t in ch.PAIRS]))
        # final forecast from 1405/07 with the kept setup
        cfg = CFGS[keep]
        stat = Stat(ch, ch.history(cfg))
        feats = Feats(ch, stat.D, cfg)
        learner = Learn(feats, F.mon(F.LAST_FULL))
        p = F.R(F.mon(F.LAST_FULL))
        tg = [F.mon(t) for t in F.FINAL_TARGETS]
        fc = stat.forecast(p, tg)
        fc.update(learner.forecast(p, tg))
        fc = F.ensembles(fc)
        np.savez_compressed(F.LAB / f"final_{name}.npz", **fc, CLS_NOW=ch.CLS[p], codes=np.array(ch.codes))
        (F.LAB / f"choice_{name}.json").write_text(json.dumps({"config": keep, "chosen": chosen}), encoding="utf-8")
        F.log(f"  {name}: kept {keep}, final forecasts saved")
    with pd.ExcelWriter(F.LAB / "channels_experiments.xlsx") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Chosen per class", index=False)
        pd.DataFrame(models_tab).to_excel(xw, sheet_name="All models (late)", index=False)
        pd.DataFrame([{"channel": k, "kept": v} for k, v in decisions.items()]).to_excel(xw, sheet_name="Decisions", index=False)
    F.log("done")
