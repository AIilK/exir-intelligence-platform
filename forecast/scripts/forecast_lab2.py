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
from copy import copy
from tempfile import TemporaryFile
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor

import channels as C
from channel_rules import channel_of, normalize

F = C.F
LO, HI = 0.95, 1.10
POOL = F.EXT_POOL
NON_TWEEDIE_C_POOL = ("WMA", "SES", "SBA", "TSB", "ADIDA", "SN", "TD_BRAND")
EID_FETR = F.event_days(F.RAMADAN, 3, offset=30)
SAFAR_ARBAEEN = F.event_days(F.MUHARRAM, 20, offset=30)
MOTHERS_DAY = F.event_days(F.RAMADAN, 7, offset=-70)
BLACK_FRIDAY = F.event_days([f"{y}-11-23" for y in range(2017, 2028)], 7)
CFGS = {
    "prev": dict(spikes=True, features=True, inflation=False),
    "+inflation": dict(spikes=True, features=True, inflation=True),
    "tweedie_recency": dict(spikes=True, features=True, inflation=False,
                            tweedie=True, recency_half_life=18.0, no_dl=True, stockout_av=True),
    "hybrid_v2": dict(spikes=True, features=True, inflation=False,
                      tweedie=True, recency_half_life=18.0, no_dl=True, stockout_av=True,
                      cat_feats=True, extra_events=True, c_route=True,
                      ml_blend={"tweedie": 0.6, "lgb_l1": 0.2, "ridge_log": 0.2},
                      reconcile=("category", 0.5)),
    "b2b_v2": dict(spikes=True, features=True, inflation=False,
                   tweedie=True, recency_half_life=18.0, no_dl=True,
                   b2b_cust=True, reorder_due=True, top20_blend=0.30, c_route=True,
                   ml_blend={"tweedie": 0.8, "ridge_log": 0.2},
                   reconcile=("brand", 0.5), bias_damp=0.5),
}


class Channel:
    def __init__(self, name, Y, codes, *, valid_months=None, season_cutoff=None):
        self.name, self.Y, self.codes, self.n = name, Y, list(codes), len(codes)
        self.hybrid = name == "hybrid"
        known = ~np.isnan(Y).all(axis=1)
        valid_months = F.valid_row if valid_months is None else valid_months
        self.valid = valid_months & known
        self.season_cutoff = F.i_last if season_cutoff is None else season_cutoff
        self.first_row = int(np.argmax(known))
        self.S = self.seasonality(self.season_cutoff)
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

    def seasonality(self, cutoff):
        """Estimate seasonal factors using observations available by cutoff only."""
        tot = np.where(self.valid, np.nansum(self.Y, axis=1), np.nan)
        rat = {m: [] for m in range(12)}
        for yy in range(F.idx[0] // 12, F.idx[-1] // 12 + 1):
            rows = [F.R(i) for i in range(yy * 12, yy * 12 + 12) if F.i_start <= i <= cutoff and self.valid[F.R(i)]]
            if len(rows) >= 10:
                annual_mean = np.mean(tot[rows])
                if annual_mean > 0:
                    for r in rows:
                        rat[F.idx[r] % 12].append(tot[r] / annual_mean)
        season = np.array([np.mean(rat[m]) if rat[m] else 1.0 for m in range(12)])
        season = np.where(np.isfinite(season) & (season > 0), season, 1.0)
        return season / season.mean()

    def at_cutoff(self, cutoff):
        channel = copy(self)
        channel.season_cutoff = cutoff
        channel.S = self.seasonality(cutoff)
        return channel

    def history(self, cfg):
        YH = self.Y.copy()
        YH[~self.valid] = np.nan
        if self.hybrid and cfg.get("stockout_av"):
            YH[F.AV < 0.70] = np.nan
        if cfg["spikes"]:
            cap = 3.0 if cfg["spikes"] is True else float(cfg["spikes"])
            df = pd.DataFrame(YH)
            med = df.shift(1).rolling(12, min_periods=4).median()
            YH = df.where(~((df > cap * med) & (med > 0)), cap * med).to_numpy(copy=True)
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


def _b2b_customer_signals(ch):
    """Build strictly causal B2B customer counts, reorder-due scores, and Top-20 baskets."""
    cached = getattr(ch, "_b2b_signals", None)
    if cached is not None:
        return cached
    inv = pd.read_csv(F.data_path("rk_invoices_daily.csv"), dtype={"code": str})
    ret = pd.read_csv(F.data_path("rk_returns_daily.csv"), dtype={"code": str})
    ret = ret[ret["status"] == 11].copy()
    ret["qty"] = -ret["qty"]
    df = pd.concat([inv, ret], ignore_index=True)
    df = df.loc[df["code"].isin(ch.codes)].copy()
    df["ch"] = df["cust"].map(channel_of)
    df = df.loc[df["ch"] == "b2b"].copy()
    df["cust_n"] = df["cust"].map(normalize)
    df["mi"] = C._pm_index(df["d"])
    df = df.loc[df["mi"].isin(F.idx)].copy()

    cust_list = sorted(df["cust_n"].unique())
    c_idx = {c: i for i, c in enumerate(cust_list)}
    k_idx = {c: i for i, c in enumerate(ch.codes)}
    df["ci"] = df["cust_n"].map(c_idx)
    df["ki"] = df["code"].map(k_idx)
    df["t"] = df["mi"] - F.i_start

    n_cust, n_sku = len(cust_list), ch.n
    cu = np.zeros((F.T, n_sku), dtype=np.float32)
    cu_grp = df.groupby(["t", "ki"])["cust_n"].nunique()
    if len(cu_grp):
        idx_t = cu_grp.index.get_level_values(0).to_numpy()
        idx_k = cu_grp.index.get_level_values(1).to_numpy()
        cu[idx_t, idx_k] = cu_grp.to_numpy(dtype=np.float32)
    cu[~ch.valid] = np.nan
    cs3, cc3 = F.nan_window(cu, 3)
    cu_m3 = np.where(cc3 > 0, cs3 / np.maximum(cc3, 1), 0.0)

    grp = df.groupby(["t", "ci", "ki"], as_index=False)["qty"].sum()
    grp = grp[grp["qty"] > 0]
    month_mats = [sparse.csr_matrix((n_cust, n_sku), dtype=np.float32) for _ in range(F.T)]
    for t_val, sub in grp.groupby("t"):
        if ch.valid[int(t_val)]:
            month_mats[int(t_val)] = sparse.csr_matrix(
                (sub["qty"].to_numpy(dtype=np.float32), (sub["ci"].to_numpy(), sub["ki"].to_numpy())),
                shape=(n_cust, n_sku),
            )

    c_tot = np.vstack([np.asarray(m.sum(axis=1)).ravel() for m in month_mats]).astype(np.float32)
    c_tot[~ch.valid] = np.nan

    reorder_due = np.zeros((F.T, n_sku), dtype=np.float32)
    tail_share = np.ones((F.T, n_sku), dtype=np.float32)
    w12_mats = [None] * F.T
    last_active = np.full(n_cust, -1, dtype=np.int32)
    gaps = [[] for _ in range(n_cust)]

    win = sparse.csr_matrix((n_cust, n_sku), dtype=np.float32)
    for t in range(F.T):
        win = win + month_mats[t]
        if t >= 12:
            win = win - month_mats[t - 12]
        w12_mats[t] = win
        if ch.valid[t]:
            row_v = np.nan_to_num(c_tot[t], nan=0.0)
            for ci in np.flatnonzero(row_v > 0):
                if last_active[ci] >= 0:
                    gaps[ci].append(t - int(last_active[ci]))
                last_active[ci] = t

        due_c = np.zeros(n_cust, dtype=np.float32)
        for ci in range(n_cust):
            if last_active[ci] >= 0 and gaps[ci]:
                med_gap = float(np.median(gaps[ci]))
                since = float(t - int(last_active[ci]))
                due_c[ci] = min(since / max(med_gap, 1.0), 3.0)

        sku_tot = np.asarray(win.sum(axis=0)).ravel()
        inv_tot = np.where(sku_tot > 0, 1.0 / np.maximum(sku_tot, 1e-9), 0.0)
        share_cs = win @ sparse.diags(inv_tot)
        reorder_due[t] = (share_cs.T @ due_c).astype(np.float32)

        c12 = np.asarray(win.sum(axis=1)).ravel()
        top20 = np.argsort(-c12)[:20]
        top20_sku = np.asarray(share_cs[top20, :].sum(axis=0)).ravel()
        tail_share[t] = np.clip(1.0 - top20_sku, 0.0, 1.0).astype(np.float32)

    signals = {
        "b2b_cust_now": np.log1p(np.nan_to_num(cu)).astype(np.float32),
        "b2b_cust_m3": np.log1p(np.nan_to_num(cu_m3)).astype(np.float32),
        "reorder_due": reorder_due,
        "c_tot": c_tot,
        "w12": w12_mats,
        "tail_share": tail_share,
    }
    ch._b2b_signals = signals
    return signals


def _top20_forecast_at(ch, signals, p, targets):
    """Causal Top-20 distributor-level forecast distributed by trailing 12m SKU basket."""
    win = signals["w12"][p]
    c12 = np.asarray(win.sum(axis=1)).ravel()
    top20 = np.argsort(-c12)[:20]
    hist_c = signals["c_tot"][: p + 1, top20]
    valid_c = ch.valid[: p + 1]
    m_idx = F.idx[: p + 1] % 12
    mean_all = np.nanmean(hist_c, axis=0)
    season = np.ones((20, 12), dtype=np.float64)
    for m in range(12):
        rm = valid_c & (m_idx == m)
        cnt = np.sum(~np.isnan(hist_c[rm]), axis=0)
        sm = np.nansum(hist_c[rm], axis=0)
        season[:, m] = np.where(
            (cnt > 0) & (mean_all > 0),
            (sm + 2.0 * mean_all) / ((cnt + 2.0) * np.maximum(mean_all, 1e-9)),
            1.0,
        )
    season /= np.maximum(season.mean(axis=1, keepdims=True), 1e-9)
    deseas = hist_c / season[np.arange(20)[None, :], m_idx[:, None]]
    val_rows = np.flatnonzero(valid_c)
    lvl12 = np.nanmean(deseas[val_rows[-12:]], axis=0)
    lvl3 = np.nanmean(deseas[val_rows[-3:]], axis=0)
    cust_lvl = np.nan_to_num(0.5 * lvl3 + 0.5 * lvl12, nan=0.0)

    b_mat = win[top20, :]
    b_sum = np.asarray(b_mat.sum(axis=1)).ravel()
    inv_b = np.where(b_sum > 0, 1.0 / np.maximum(b_sum, 1e-9), 0.0)
    basket_share = sparse.diags(inv_b) @ b_mat

    out = np.zeros((len(targets), ch.n), dtype=np.float32)
    for j, g in enumerate(targets):
        cust_fc = cust_lvl * season[:, g % 12]
        out[j] = np.clip(cust_fc @ basket_share, 0, None).astype(np.float32)
    return out, signals["tail_share"][p]


class Feats:
    def __init__(self, ch, D, cfg):
        self.ch, self.D, self.cfg = ch, D, cfg
        self.cat_indices = []
        s3, c3 = F.nan_window(D, 3)
        s12, c12 = F.nan_window(D, 12)
        self.m3 = np.where(c3 > 0, s3 / np.maximum(c3, 1), np.nan)
        self.m12 = np.where(c12 > 0, s12 / np.maximum(c12, 1), np.nan)
        nzs, _ = F.nan_window(np.where(np.isnan(D), np.nan, (np.nan_to_num(D) > 0).astype(float)), 12)
        self.nz = np.where(c12 > 0, nzs / np.maximum(c12, 1), np.nan)
        if cfg.get("cat_feats"):
            goods = F.goods
            brands = [str(goods.loc[c, "brand"]) if c in goods.index and pd.notna(goods.loc[c, "brand"]) else "_NONE" for c in ch.codes]
            cats = [str(goods.loc[c, "category"]) if c in goods.index and pd.notna(goods.loc[c, "category"]) else "_NONE" for c in ch.codes]
            b_map = {b: i for i, b in enumerate(sorted(set(brands)))}
            c_map = {c: i for i, c in enumerate(sorted(set(cats)))}
            self.brand_id = np.array([b_map[b] for b in brands], dtype=np.float32)
            self.cat_id = np.array([c_map[c] for c in cats], dtype=np.float32)
            cat_df = pd.DataFrame(ch.history(cfg)).T.groupby(cats).sum(min_count=1).T
            cat_mat = cat_df.to_numpy(copy=True)
            cat_mat[~ch.valid] = np.nan
            cs3, cc3 = F.nan_window(cat_mat, 3)
            cs12, cc12 = F.nan_window(cat_mat, 12)
            cm3 = np.where(cc3 > 0, cs3 / np.maximum(cc3, 1), np.nan)
            cm12 = np.where(cc12 > 0, cs12 / np.maximum(cc12, 1), np.nan)
            mom_cat = np.nan_to_num(F.L(cm3) - F.L(cm12))
            cat_names = list(cat_df.columns)
            c_idx = np.array([cat_names.index(c) for c in cats])
            self.cat_mom = mom_cat[:, c_idx].astype(np.float32)
        if ch.name == "b2b" and any(cfg.get(k) for k in ("b2b_cust", "reorder_due", "top20_blend")):
            sig = _b2b_customer_signals(ch)
            self.b2b_signals = sig
            self.b2b_cust_now = sig["b2b_cust_now"]
            self.b2b_cust_m3 = sig["b2b_cust_m3"]
            self.reorder_due = sig["reorder_due"]

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
        self.cat_indices = []
        if self.cfg.get("cat_feats"):
            self.cat_indices = [len(f), len(f) + 1]
            f += [np.broadcast_to(self.brand_id[None, :], (len(P), n)),
                  np.broadcast_to(self.cat_id[None, :], (len(P), n)),
                  self.cat_mom[P]]
        if self.cfg.get("extra_events"):
            f += [rep(F.ev(EID_FETR, g) / 3), rep(F.ev(SAFAR_ARBAEEN, g) / 20),
                  rep(F.ev(MOTHERS_DAY, g) / 7), rep(F.ev(BLACK_FRIDAY, g) / 7)]
        if self.cfg.get("b2b_cust") and hasattr(self, "b2b_cust_now"):
            f += [self.b2b_cust_now[P], self.b2b_cust_m3[P]]
        if self.cfg.get("reorder_due") and hasattr(self, "reorder_due"):
            f += [self.reorder_due[P]]
        X = np.stack(f, axis=-1).reshape(len(P) * n, len(f)).astype(np.float32)
        return X, (~np.isnan(self.m12[P])).reshape(-1)


def ensembles(fc):
    if "DL" in fc:
        return F.ensembles(fc)
    three = np.stack([fc["WMA"], fc["SES"], fc["ML"]])
    fc["MED4"] = np.median(three, axis=0)
    fc["MEAN4"] = three.mean(axis=0)
    singles = [fc[m] for m in ("SN", "WMA", "SES", "SBA", "TSB", "ADIDA", "TD_BRAND", "ML") if m in fc]
    fc["MED_ALL"] = np.median(np.stack(singles), axis=0)
    return fc


_GOODS_CACHE = None


def _goods_meta():
    global _GOODS_CACHE
    if _GOODS_CACHE is not None:
        return _GOODS_CACHE
    goods = F.goods.copy()
    rk_path = F.data_path("rk_goods.csv")
    if rk_path.is_file():
        rk = pd.read_csv(rk_path, dtype={"code": str}).drop_duplicates("code").set_index("code")
        rk = rk.reindex(columns=goods.columns)
        goods = goods.reindex(goods.index.union(rk.index))
        for col in ("brand", "category"):
            if col in goods.columns and col in rk.columns:
                cur = goods[col].fillna("").astype(str).str.strip()
                fb = rk[col].reindex(goods.index).fillna("").astype(str).str.strip()
                goods[col] = cur.where(cur.ne(""), fb)
    _GOODS_CACHE = goods
    return goods


def group_map_for(ch, level):
    """Return integer group index per SKU and group count for brand or category reconciliation."""
    cached = getattr(ch, "_group_maps", None)
    if cached is not None and level in cached:
        return cached[level]
    goods = _goods_meta()
    if level == "category":
        groups = [
            str(goods.loc[c, "category"]).strip()
            if c in goods.index and pd.notna(goods.loc[c, "category"]) and str(goods.loc[c, "category"]).strip()
            else f"_CAT_{goods.loc[c, 'brand']}" if c in goods.index and pd.notna(goods.loc[c, "brand"])
            else f"_{c}"
            for c in ch.codes
        ]
    else:
        groups = [
            str(goods.loc[c, "brand"]).strip()
            if c in goods.index and pd.notna(goods.loc[c, "brand"]) and str(goods.loc[c, "brand"]).strip()
            else f"_{c}"
            for c in ch.codes
        ]
    names = sorted(set(groups))
    g_idx = np.array([names.index(g) for g in groups], dtype=np.int32)
    res = (g_idx, len(names))
    ch._group_maps = {**(cached or {}), level: res}
    return res


def reconcile_origin(origin_ch, cfg, fc, p, targets, level, alpha):
    """Proportionally reconcile SKU predictions at origin p to causal group-level WMA/SES totals."""
    if not alpha or alpha <= 0:
        return fc
    g_idx, ng = group_map_for(origin_ch, level)
    YH = origin_ch.history(cfg)
    Gm = np.zeros((p + 1, ng), dtype=np.float64)
    for j in range(ng):
        cols = YH[: p + 1, g_idx == j]
        valid_c = ~np.isnan(cols).all(axis=1)
        Gm[:, j] = np.where(valid_c, np.nansum(cols, axis=1), np.nan)
    Gm[~origin_ch.valid[: p + 1]] = np.nan
    GD = Gm / origin_ch.S[F.idx[: p + 1] % 12][:, None]
    lvl = np.nan_to_num(np.nanmedian(np.stack([F.wma_levels(GD)[p], F.ses_levels(GD)[p]]), axis=0), nan=0.0)
    grp_fc = np.vstack([np.clip(lvl * origin_ch.S[g % 12], 0, None) for g in targets])

    reconciled_models = {"ML", "WMA", "SES", "MEAN4", "MED4", "MED_ALL", "SN", "SBA", "TSB", "ADIDA", "TD_BRAND"}
    out = {}
    for m, arr in fc.items():
        if m not in reconciled_models:
            out[m] = arr
            continue
        gsum = np.zeros((arr.shape[0], ng), dtype=np.float64)
        for j in range(ng):
            gsum[:, j] = arr[:, g_idx == j].sum(axis=1)
        ratio = np.clip(np.where(gsum > 1e-6, grp_fc / np.maximum(gsum, 1e-6), 1.0), 0.5, 1.8)
        mult = (1.0 - alpha) + alpha * ratio[:, g_idx]
        out[m] = np.clip(arr * mult, 0, None).astype(np.float32)
    return out


def compute_causal_bias(ch, preds, damp=0.5, lo=0.90, hi=1.30, *, independent=True):
    """Estimate per-model, per-class multiplicative bias strictly from early (target <= SPLIT) rows."""
    early_mask = ~ch.LATE & ((np.array([t for _, t in ch.PAIRS]) <= F.mon(F.SPLIT)) if independent else True)
    factors = {}
    adjusted = {}
    for m, arr in preds.items():
        corr = arr.copy()
        f_cls = {}
        for ci, cl in enumerate(F.CLASSES):
            mm = (ch.CLS_P == ci) & early_mask[:, None]
            ps, ac = float(arr[mm].sum()), float(ch.ACT[mm].sum())
            fac = 1.0
            if ps > 1.0 and ac > 1.0:
                raw_fac = float(np.clip(ac / ps, lo, hi))
                fac = 1.0 + damp * (raw_fac - 1.0)
                corr = np.where(ch.CLS_P == ci, arr * fac, corr)
            f_cls[cl] = round(float(fac), 6)
        factors[m] = f_cls
        adjusted[m] = corr
    return adjusted, factors


class Learn:
    def __init__(self, feats, cut_global, *, batch_size=4096):
        self.feats = feats
        self.tweedie = bool(feats.cfg.get("tweedie"))
        self.no_dl = bool(feats.cfg.get("no_dl"))
        blend = feats.cfg.get("ml_blend")
        if blend:
            self.ml_blend = dict(blend)
        else:
            self.ml_blend = {"tweedie": 1.0} if self.tweedie else {"log_lgb": 1.0}
        half_life = feats.cfg.get("recency_half_life")
        cut = F.R(cut_global)
        training = []
        for h in range(1, F.H_MAX + 1):
            P = np.arange(0, cut - h + 1)
            tgt = feats.D[P + h].reshape(-1)
            mask = (~np.isnan(feats.m12[P])).reshape(-1) & ~np.isnan(tgt)
            training.append((P, h, mask))
        sample, _ = feats.block(np.array([cut]), 1)
        size = sum(mask.sum() for _, _, mask in training)
        raw_d_arr = np.empty(size, dtype=np.float32)
        weights = np.empty(size, dtype=np.float32) if half_life else None
        self.rows = len(raw_d_arr)
        self.learners = {}
        self.ridge_meta = None
        with TemporaryFile() as store:
            X = np.memmap(store, dtype=np.float32, mode="w+", shape=(size, sample.shape[1]))
            start = 0
            for P, h, mask in training:
                mask = mask.reshape(len(P), -1)
                for offset in range(0, len(P), 8):
                    band = slice(offset, offset + 8)
                    block, _ = feats.block(P[band], h)
                    keep = mask[band].reshape(-1)
                    end = start + keep.sum()
                    X[start:end] = block[keep]
                    raw_d_arr[start:end] = np.clip(feats.D[P[band] + h].reshape(-1)[keep], 0, None)
                    if weights is not None:
                        age = (cut - np.repeat(P[band], feats.ch.n)[keep]).astype(np.float32)
                        weights[start:end] = 0.5 ** (age / half_life)
                    start = end
            del training, sample, block
            fit_kw = {"sample_weight": weights}
            if feats.cat_indices:
                fit_kw["categorical_feature"] = feats.cat_indices
            if "tweedie" in self.ml_blend:
                params = {**F.LGB_PARAMS, "objective": "tweedie",
                          "tweedie_variance_power": float(feats.cfg.get("tweedie_p", 1.5))}
                self.learners["tweedie"] = ("unit", lgb.LGBMRegressor(**params).fit(X, raw_d_arr, **fit_kw))
            if "log_lgb" in self.ml_blend:
                self.learners["log_lgb"] = ("log1p", lgb.LGBMRegressor(**F.LGB_PARAMS).fit(X, F.L(raw_d_arr), **fit_kw))
            if "lgb_l1" in self.ml_blend:
                params = {**F.LGB_PARAMS, "objective": "regression_l1"}
                self.learners["lgb_l1"] = ("log1p", lgb.LGBMRegressor(**params).fit(X, F.L(raw_d_arr), **fit_kw))
            if "ridge_log" in self.ml_blend:
                cat_set = set(feats.cat_indices or [])
                num_cols = [j for j in range(X.shape[1]) if j not in cat_set]
                Xn = X[:, num_cols].astype(np.float64)
                mu_r = np.nanmean(Xn, axis=0)
                mu_r = np.where(np.isfinite(mu_r), mu_r, 0.0)
                Xn_imp = np.where(np.isfinite(Xn), Xn, mu_r)
                sd_r = np.std(Xn_imp, axis=0) + 1e-9
                Xs_r = np.clip((Xn_imp - mu_r) / sd_r, -10.0, 10.0)
                max_log = float(np.log1p(np.max(raw_d_arr) * 3.0)) if len(raw_d_arr) else 15.0
                ridge = Ridge(alpha=50.0).fit(Xs_r, F.L(raw_d_arr).astype(np.float64), sample_weight=weights)
                self.ridge_meta = (num_cols, mu_r, sd_r, max_log)
                self.learners["ridge_log"] = ("ridge", ridge)
            self.gbm = self.learners.get("tweedie", self.learners.get("log_lgb", next(iter(self.learners.values()))))[1]
            if self.no_dl:
                self.mlp = self.mu = self.sd = None
            else:
                y_dl = raw_d_arr if self.tweedie else F.L(raw_d_arr)
                self.mu = np.empty(X.shape[1], dtype=np.float32)
                self.sd = np.empty_like(self.mu)
                for j in range(X.shape[1]):
                    values = X[:, j]
                    self.mu[j] = np.nanmean(values)
                    self.sd[j] = np.nanstd(values) + 1e-9
                    values -= self.mu[j]
                    values /= self.sd[j]
                    np.nan_to_num(values, copy=False)
                del values
                self.mlp = MLPRegressor(hidden_layer_sizes=(32,), batch_size=batch_size, learning_rate_init=2e-3, max_iter=5,
                                        random_state=0).fit(X, y_dl)
            del X

    def forecast(self, p, targets):
        n = self.feats.ch.n
        ml = np.zeros((len(targets), n))
        dl = None if self.mlp is None else np.zeros((len(targets), n))
        for j, g in enumerate(targets):
            X, ok = self.feats.block([p], g - F.idx[p])
            s = self.feats.ch.S[g % 12]
            blended = np.zeros(n, dtype=np.float64)
            for name, weight in self.ml_blend.items():
                kind, est = self.learners[name]
                if kind == "unit":
                    pr = np.clip(est.predict(X), 0, None)
                elif kind == "log1p":
                    pr = np.expm1(np.clip(est.predict(X), 0, 20.0))
                else:
                    num_cols, mu_r, sd_r, max_log = self.ridge_meta
                    Xn = X[:, num_cols].astype(np.float64)
                    Xn = np.where(np.isfinite(Xn), Xn, mu_r)
                    Xs_r = np.clip((Xn - mu_r) / sd_r, -10.0, 10.0)
                    pr = np.expm1(np.clip(est.predict(Xs_r), 0, max_log))
                blended += float(weight) * np.clip(pr, 0, None)
            ml[j] = np.where(ok, blended, 0.0) * s
            if dl is not None:
                dl[j] = np.where(ok, np.expm1(self.mlp.predict(np.nan_to_num((X - self.mu) / self.sd))), 0.0) * s
        ml = np.clip(ml, 0, None)
        blend = float(self.feats.cfg.get("top20_blend") or 0.0)
        if blend > 0 and hasattr(self.feats, "b2b_signals"):
            top20_fc, tail_sh = _top20_forecast_at(self.feats.ch, self.feats.b2b_signals, p, targets)
            decomp = top20_fc + ml * tail_sh[None, :]
            ml = blend * decomp + (1.0 - blend) * ml
        out = {"ML": np.clip(ml, 0, None)}
        if dl is not None:
            out["DL"] = np.clip(dl, 0, None)
        return out


def backtest(ch, cfg, *, causal=True, horizons=(1, 2, 3)):
    stat = Stat(ch, ch.history(cfg))
    feats = Feats(ch, stat.D, cfg)
    learners = {}
    for cut in (F.CUT_EARLY, F.CUT_LATE):
        training = ch.at_cutoff(F.mon(cut)) if causal else ch
        training_stat = Stat(training, training.history(cfg))
        learners[cut] = Learn(Feats(training, training_stat.D, cfg), F.mon(cut))
    preds = {}
    rec = cfg.get("reconcile")
    for o in ch.ROLL:
        tg = [o + h for h in horizons if o + h <= F.i_last and ch.valid[F.R(o + h)]]
        if not tg:
            continue
        origin = ch.at_cutoff(o) if causal else ch
        origin_stat = Stat(origin, origin.history(cfg)) if causal else stat
        fc = origin_stat.forecast(F.R(o), tg)
        fc.update(learners[F.CUT_EARLY if F.plabel(o) <= F.SPLIT else F.CUT_LATE].forecast(F.R(o), tg))
        fc = ensembles(fc)
        if rec:
            fc = reconcile_origin(origin, cfg, fc, F.R(o), tg, rec[0], rec[1])
        for m, v in fc.items():
            preds.setdefault(m, []).append(v)
    out = {m: np.vstack(v).astype(np.float32) for m, v in preds.items()}
    damp = float(cfg.get("bias_damp") or 0.0)
    if damp > 0 and horizons == (1, 2, 3):
        out, _ = compute_causal_bias(ch, out, damp=damp)
    return out, stat, feats


def metrics(pred, act, mask):
    p, a = pred[mask].astype(float), act[mask].astype(float)
    if a.sum() <= 0:
        return dict(WAPE=np.nan, bias=np.nan, tolWAPE=np.nan, hit=np.nan, hit_units=np.nan)
    ok = np.where(a > 0, (p >= LO * a) & (p <= HI * a), p < 0.5)
    e = np.abs(p - a)
    active = (a > 0) | (p >= 0.5)
    return dict(WAPE=e.sum() / a.sum(), bias=(p - a).sum() / a.sum(), tolWAPE=(e * ~ok).sum() / a.sum(),
                hit=ok[active].mean() if active.any() else np.nan, hit_units=(a * ok).sum() / a.sum())


def three_month(ch, pred, *, independent=True):
    """per product 3-month totals for origins that have all three target months."""
    P3, A3, C3, L3 = [], [], [], []
    for o in sorted(set(ch.ORIG)):
        rows = np.where(ch.ORIG == o)[0]
        # Early calibration must not consume outcomes from the late period.
        crosses_split = independent and F.plabel(o) <= F.SPLIT and max(t for origin, t in ch.PAIRS if origin == o) > F.mon(F.SPLIT)
        if len(rows) == 3 and not crosses_split:
            P3.append(pred[rows].sum(0)); A3.append(ch.ACT[rows].sum(0))
            C3.append(ch.CLS_P[rows[0]]); L3.append(F.plabel(o) > F.SPLIT)
    return np.array(P3), np.array(A3), np.array(C3), np.array(L3)


def evaluate(ch, preds, label, *, independent=True, c_route=False):
    rows, chosen = [], {}
    tot = {h: {"m": [], "3m": []} for h in ("early", "late")}
    pool_all = [m for m in POOL if m in preds]
    tm = {m: three_month(ch, preds[m], independent=independent) for m in pool_all}
    for ci, cl in enumerate(F.CLASSES):
        # choose on 3-month totals (the production horizon): on single months a zero forecast wins for lumpy channels
        pool = [m for m in NON_TWEEDIE_C_POOL if m in preds] if (c_route and cl == "C") else pool_all
        sc = {}
        for m in pool:
            P3, A3, C3, L3 = tm[m]
            sc[m] = metrics(P3, A3, (C3 == ci) & ~L3[:, None])["tolWAPE"] if len(P3) else np.nan
        best = min(sc, key=lambda m: np.inf if np.isnan(sc[m]) else sc[m])
        chosen[cl] = best
        early = ~ch.LATE & ((np.array([t for _, t in ch.PAIRS]) <= F.mon(F.SPLIT)) if independent else True)
        for half, hm in (("early", early), ("late", ch.LATE)):
            mm = (ch.CLS_P == ci) & hm[:, None]
            r = metrics(preds[best], ch.ACT, mm)
            P3, A3, C3, L3 = three_month(ch, preds[best], independent=independent)
            m3 = (C3 == ci) & ((L3 if half == "late" else ~L3)[:, None]) if len(P3) else None
            r3 = metrics(P3, A3, m3) if len(P3) else {}
            rows.append({"channel": ch.name, "config": label, "class": cl, "half": half, "model": best,
                         **{k: round(v, 4) for k, v in r.items()},
                         **{f"3m_{k}": round(v, 4) for k, v in r3.items() if k in ("WAPE", "tolWAPE", "hit_units")}})
    # all classes combined, each with its chosen model
    early = ~ch.LATE & ((np.array([t for _, t in ch.PAIRS]) <= F.mon(F.SPLIT)) if independent else True)
    for half, hm in (("early", early), ("late", ch.LATE)):
        comb = np.zeros_like(ch.ACT)
        for ci, cl in enumerate(F.CLASSES):
            comb = np.where(ch.CLS_P == ci, preds[chosen[cl]], comb)
        r = metrics(comb, ch.ACT, np.broadcast_to(hm[:, None], ch.ACT.shape))
        P3, A3, C3, L3 = three_month(ch, comb, independent=independent)
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


def choose_configuration(rows_by_config):
    """Late scores are deliberately inaccessible to configuration selection."""
    def score(label):
        value = next(row["tolWAPE"] for row in rows_by_config[label]
                     if row["class"] == "ALL" and row["half"] == "early")
        return value if np.isfinite(value) else np.inf
    return min(rows_by_config, key=score)


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
            rows, chosen, comb = evaluate(ch, preds, label, c_route=bool(cfg.get("c_route")))
            summary += rows
            models_tab += all_models(ch, preds, label)
            res[label] = (preds, chosen, rows)
            e = [r for r in rows if r["class"] == "ALL" and r["half"] == "early"][0]
            l = [r for r in rows if r["class"] == "ALL" and r["half"] == "late"][0]
            F.log(f"  {name} {label:>11}: early tolWAPE {e['tolWAPE']:.4f} | late WAPE {l['WAPE']:.4f} "
                  f"tolWAPE {l['tolWAPE']:.4f} hit_units {l['hit_units']:.3f} | 3m late tolWAPE {l.get('3m_tolWAPE', float('nan')):.4f} | {chosen}")
        sc = lambda lab, half: [r for r in res[lab][2] if r["class"] == "ALL" and r["half"] == half][0]["tolWAPE"]
        # Freeze configuration before examining the independent late period.
        keep = choose_configuration({label: result[2] for label, result in res.items()})
        decisions[name] = keep
        preds, chosen, _ = res[keep]
        np.savez_compressed(F.LAB / f"backtest_{name}.npz", **preds, ACT=ch.ACT, CLS_P=ch.CLS_P, LATE=ch.LATE,
                            ORIG=ch.ORIG, TARG=np.array([t for _, t in ch.PAIRS]))
        # final forecast from last full month with the kept setup
        cfg = CFGS[keep]
        stat = Stat(ch, ch.history(cfg))
        feats = Feats(ch, stat.D, cfg)
        learner = Learn(feats, F.mon(F.LAST_FULL))
        p = F.R(F.mon(F.LAST_FULL))
        tg = [F.mon(t) for t in F.FINAL_TARGETS]
        fc = stat.forecast(p, tg)
        fc.update(learner.forecast(p, tg))
        fc = ensembles(fc)
        rec = cfg.get("reconcile")
        if rec:
            fc = reconcile_origin(ch, cfg, fc, p, tg, rec[0], rec[1])
        bias_factors = None
        damp = float(cfg.get("bias_damp") or 0.0)
        if damp > 0:
            raw_cfg = {k: v for k, v in cfg.items() if k != "bias_damp"}
            raw_preds, _, _ = backtest(ch, raw_cfg)
            _, all_factors = compute_causal_bias(ch, raw_preds, damp=damp)
            bias_factors = {cl: all_factors[chosen[cl]][cl] for cl in F.CLASSES}
            cls_now = np.array(F.CLASSES)[ch.CLS[p]]
            mult = np.array([bias_factors[cl] for cl in cls_now], dtype=np.float32)
            for m in fc:
                if m != "NAIVE":
                    fc[m] = np.clip(fc[m] * mult[None, :], 0, None)
        np.savez_compressed(F.LAB / f"final_{name}.npz", **fc, CLS_NOW=ch.CLS[p], codes=np.array(ch.codes))
        choice_doc = {"config": keep, "chosen": chosen}
        if bias_factors is not None:
            choice_doc["bias_factors"] = bias_factors
        (F.LAB / f"choice_{name}.json").write_text(json.dumps(choice_doc), encoding="utf-8")
        F.log(f"  {name}: kept {keep}, final forecasts saved")
    with pd.ExcelWriter(F.LAB / "channels_experiments.xlsx") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Chosen per class", index=False)
        pd.DataFrame(models_tab).to_excel(xw, sheet_name="All models (late)", index=False)
        pd.DataFrame([{"channel": k, "kept": v} for k, v in decisions.items()]).to_excel(xw, sheet_name="Decisions", index=False)
    F.log("done")
