"""Forecast lab: tests each improvement on its own, then builds the final forecast and production plan.

Honest testing
  Rolling backtest origins 1403/07..1405/06, horizons 1-3, normal target months only.
  EARLY half = origins up to 1404/06: used to choose models and to decide which changes to keep.
  LATE half  = origins after 1404/06: never used for choices; it is the confirmation score.
  ML/DL are retrained at two cut-offs (targets up to 1403/06 for early origins, up to 1404/06 for late ones),
  so no forecast ever sees its own future.

Models (per product, units per Persian month)
  SN same month last year | WMA weighted last 3 months | SES exponential smoothing | SBA Croston-SBA
  TSB Teunter-Syntetos-Babai (intermittent, handles dying products) | ADIDA quarterly-aggregate smoothing
  TD_BRAND brand-level forecast split by product share | ML LightGBM | DL neural network (scikit-learn)
  MED4 median(WMA, SES, ML, DL) | MEAN4 mean of the same | MED_ALL median of all single models
  NAIVE "same as last month" (reference only)

Changes tested (one at a time against "base")
  stockout   leave out product-months with < 70% branch availability (KDB stock ledger)
  spikes     cap history at 3x the trailing 12-month median
  features   ML/DL extra inputs: branches selling the product, discount rate, price change,
             Ramadan days, Muharram days, last-two-weeks-of-Ramadan days
  tweedie    LightGBM trained on units with a Tweedie loss (instead of log units)
  smear      bias correction for log-scale models (Duan smearing)
  perclass   separate LightGBM models for A, B and C products
  pool       extra models in the candidate pool (TSB, ADIDA, TD_BRAND, MEAN4, MED_ALL)
"""
import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

import jdatetime
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor

warnings.filterwarnings("ignore")
T0 = time.time()

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "forecast" / "data"
LAB = ROOT / "forecast" / "lab"
LAB.mkdir(exist_ok=True)

MANUAL_EXCLUDE = ["1396/02", "1396/03", "1396/04", "1397/01", "1398/01", "1399/01", "1401/01",
                  "1403/01", "1404/10", "1404/11", "1404/12", "1405/01"]
TRAIN_START, LAST_FULL = "1397/02", "1405/07"
ROLL_FROM, ROLL_TO, SPLIT = "1403/07", "1405/06", "1404/06"
CUT_EARLY, CUT_LATE = "1403/06", "1404/06"
FINAL_TARGETS = ["1405/08", "1405/09", "1405/10", "1405/11"]
NEED_MONTHS = ["1405/09", "1405/10", "1405/11"]
H_MAX = 4
CLASSES = ["A", "B", "C", "N"]
SAFETY_Q = {"A": 0.95, "B": 0.90, "C": None, "N": None}   # service level per class (C/N: no safety stock)
FACTORY_STORES = {"1", "2", "3", "4"}
BASE_POOL = ["SN", "WMA", "SES", "SBA", "ML", "DL", "MED4"]
EXT_POOL = BASE_POOL + ["TSB", "ADIDA", "TD_BRAND", "MEAN4", "MED_ALL"]
LGB_PARAMS = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.9, random_state=0, verbose=-1, n_jobs=-1)


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def mon(label):
    return int(label[:4]) * 12 + int(label[5:]) - 1


def plabel(i):
    y, m = divmod(int(i), 12)
    return f"{y}/{m + 1:02d}"


def L(x):
    return np.log1p(np.clip(x, 0, None))


# =============================== data ===============================
sales = pd.read_csv(DATA / "kdb_sales_monthly.csv", dtype={"code": str})
sales["mi"] = sales["pm"].map(mon)
i_start, i_last = mon(TRAIN_START), mon(LAST_FULL)
idx = np.arange(i_start, i_last + 1)
T = len(idx)
net = sales.pivot_table(index="mi", columns="code", values="net_qty", aggfunc="sum").reindex(idx).fillna(0.0)
codes = sorted(net.columns)
n = len(codes)
k_idx = {c: k for k, c in enumerate(codes)}
branches = sales.groupby("mi")["branches"].max().reindex(idx).ffill().fillna(1).values.astype(float)
total = net[codes].sum(axis=1)
local_med = total.rolling(13, center=True, min_periods=5).median()
excluded = set(mon(m) for m in MANUAL_EXCLUDE) | set(int(i) for i in total.index[total < 0.3 * local_med])
valid_row = np.array([i not in excluded for i in idx])
Y = net[codes].to_numpy(copy=True)
Y[~valid_row] = np.nan
R = lambda g: int(g) - i_start   # global month -> row

# seasonal index (within-year ratios of the network total)
tot = np.where(valid_row, np.nansum(Y, axis=1), np.nan)
rat = {m: [] for m in range(12)}
for yy in range(idx[0] // 12, idx[-1] // 12 + 1):
    rows = [R(i) for i in range(yy * 12, yy * 12 + 12) if i_start <= i <= i_last and valid_row[R(i)]]
    if len(rows) >= 10:
        ym = np.nanmean(tot[rows])
        for r in rows:
            rat[idx[r] % 12].append(tot[r] / ym)
S = np.array([np.mean(rat[m]) for m in range(12)])
S = S / S.mean()
S_row = S[idx % 12]

# availability from the stock ledger (same method as v3)
mv = pd.read_csv(DATA / "kdb_stock_moves_monthly.csv", dtype={"code": str})
mv = mv[mv["code"].isin(k_idx)]
mv["mi"] = mv["pm"].map(mon)
mv = mv.groupby(["bid", "code", "mi"], as_index=False)[["net_move", "opening", "sales_out"]].sum()
pairs = mv.loc[mv["sales_out"] > 0, ["bid", "code"]].drop_duplicates().sort_values(["bid", "code"])
all_mi = np.arange(mon("1396/01"), i_last + 1)
grid = pairs.merge(pd.DataFrame({"mi": all_mi}), how="cross").merge(
    mv, on=["bid", "code", "mi"], how="left")
grid[["net_move", "opening", "sales_out"]] = grid[["net_move", "opening", "sales_out"]].fillna(0.0)
grid = grid.sort_values(["bid", "code", "mi"]).reset_index(drop=True)
grid["close"] = grid.groupby(["bid", "code", grid["mi"] // 12])["net_move"].cumsum()
grid["start"] = grid["close"] - grid["net_move"] + grid["opening"]
Mn, Pn = len(all_mi), len(pairs)
out_arr = np.where((grid["start"] <= 0) & (grid["close"] <= 0), 1.0,
                   np.where((grid["start"] <= 0) | (grid["close"] <= 0), 0.5, 0.0)).reshape(Pn, Mn)
so = grid["sales_out"].values.reshape(Pn, Mn)
cs = np.concatenate([np.zeros((Pn, 1)), np.cumsum(so, axis=1)], axis=1)
tt = np.arange(Mn)
hist = cs[:, tt] - cs[:, np.maximum(tt - 12, 0)]
pc = grid["code"].values[::Mn]
avail = (1 - pd.DataFrame(hist * out_arr).groupby(pc).sum() / pd.DataFrame(hist).groupby(pc).sum().replace(0, np.nan)).fillna(1.0)
AV = np.ones((T, n))
cols = [int(i - all_mi[0]) for i in idx]
for c, row in avail.iterrows():
    AV[:, k_idx[c]] = row.values[cols]
del grid, mv, out_arr, so, cs, hist

# extra feature inputs
BRC = sales.pivot_table(index="mi", columns="code", values="branches", aggfunc="max").reindex(idx).reindex(columns=codes).fillna(0.0).values
disc = pd.read_csv(DATA / "kdb_discount_monthly.csv", dtype={"code": str})
disc["mi"] = disc["pm"].map(mon)
pv = lambda col: disc.pivot_table(index="mi", columns="code", values=col, aggfunc="sum").reindex(idx).reindex(columns=codes)
_g, _d, _q = pv("gross"), pv("discount"), pv("qty")
DR = (_d / _g.replace(0, np.nan)).values
_price = _g / _q.replace(0, np.nan)
PCH = (_price / _price.shift(1).rolling(3, min_periods=1).mean() - 1).clip(-1, 3).values
RAMADAN = ["2017-05-27", "2018-05-16", "2019-05-06", "2020-04-24", "2021-04-13", "2022-04-02",
           "2023-03-23", "2024-03-11", "2025-03-01", "2026-02-18", "2027-02-08"]
MUHARRAM = ["2017-09-21", "2018-09-11", "2019-08-31", "2020-08-20", "2021-08-10", "2022-07-30",
            "2023-07-19", "2024-07-07", "2025-06-27", "2026-06-16", "2027-06-06"]


def event_days(starts, length, offset=0):
    out = {}
    for s0 in starts:
        d0 = date.fromisoformat(s0)
        for k in range(offset, offset + length):
            j = jdatetime.date.fromgregorian(date=d0 + timedelta(days=k))
            out[j.year * 12 + j.month - 1] = out.get(j.year * 12 + j.month - 1, 0) + 1
    return out


RAM, MUH, PREEID = event_days(RAMADAN, 30), event_days(MUHARRAM, 10), event_days(RAMADAN, 14, offset=16)
ev = lambda d, g: np.array([d.get(int(x), 0) for x in g], dtype=float)

# ABC class of every product at every month (trailing 12 valid months of actual sales)
Yz = np.nan_to_num(Y)
cz = np.vstack([np.zeros(n), np.cumsum(Yz, axis=0)])
CLS = np.full((T, n), 3, dtype=np.int8)   # 0=A 1=B 2=C 3=N
for t in range(T):
    w = cz[t + 1] - cz[max(t - 11, 0)]
    order = np.argsort(-w)
    tot_w = w.sum()
    if tot_w <= 0:
        continue
    before = np.concatenate([[0.0], np.cumsum(w[order])[:-1]]) / tot_w
    lab = np.where(before < 0.80, 0, np.where(before < 0.95, 1, 2))
    lab = np.where(w[order] > 0, lab, 3)
    CLS[t, order] = lab

goods = pd.read_csv(DATA / "kdb_goods.csv", dtype={"code": str}).drop_duplicates("code").set_index("code")
brand_of = [str(goods.loc[c, "brand"]) if c in goods.index and pd.notna(goods.loc[c, "brand"]) else f"_{c}" for c in codes]
log("data ready:", T, "months x", n, "products")


# =============================== vectorised statistical models ===============================
def nan_window(M, w):
    """per row t: sum and count of non-NaN values in rows t-w+1..t."""
    v = np.nan_to_num(M)
    c = (~np.isnan(M)).astype(float)
    cv = np.vstack([np.zeros(M.shape[1]), np.cumsum(v, axis=0)])
    cc = np.vstack([np.zeros(M.shape[1]), np.cumsum(c, axis=0)])
    t = np.arange(M.shape[0])
    lo = np.maximum(t - w + 1, 0)
    return cv[t + 1] - cv[lo], cc[t + 1] - cc[lo]


def wma_levels(Dm):
    v1 = v2 = v3 = np.full(Dm.shape[1], np.nan)
    out = np.full(Dm.shape, np.nan)
    for t in range(Dm.shape[0]):
        x = Dm[t]
        ok = ~np.isnan(x)
        v3 = np.where(ok, v2, v3)
        v2 = np.where(ok, v1, v2)
        v1 = np.where(ok, x, v1)
        vals = np.stack([v1, v2, v3])
        wts = np.array([0.5, 0.3, 0.2])[:, None] * ~np.isnan(vals)
        out[t] = np.where(wts.sum(0) > 0, np.nansum(np.nan_to_num(vals) * wts, 0) / np.maximum(wts.sum(0), 1e-12), np.nan)
    return out


def ses_levels(Dm, a=0.2):
    lvl = np.full(Dm.shape[1], np.nan)
    out = np.empty(Dm.shape)
    for t in range(Dm.shape[0]):
        x = Dm[t]
        lvl = np.where(np.isnan(x), lvl, np.where(np.isnan(lvl), x, a * x + (1 - a) * lvl))
        out[t] = lvl
    return out


def tsb_levels(Ym, a=0.1, b=0.1):
    z = np.full(Ym.shape[1], np.nan)
    p = np.full(Ym.shape[1], np.nan)
    out = np.empty(Ym.shape)
    for t in range(Ym.shape[0]):
        x = Ym[t]
        ok = ~np.isnan(x)
        dem = (np.nan_to_num(x) > 0).astype(float)
        z = np.where(ok & (dem > 0), np.where(np.isnan(z), x, z + b * (x - z)), z)
        p = np.where(ok, np.where(np.isnan(p), dem, p + a * (dem - p)), p)
        out[t] = np.nan_to_num(p) * np.nan_to_num(z)
    return out


def sba_rates(Ym, w=24, a=0.1):
    v = np.nan_to_num(np.clip(Ym, 0, None))
    nz = (v > 0).astype(float)
    sv, cnt = nan_window(Ym, w)
    snz, _ = nan_window(np.where(np.isnan(Ym), np.nan, nz), w)
    ssz, _ = nan_window(np.where(np.isnan(Ym), np.nan, v * nz), w)
    size = ssz / np.maximum(snz, 1)
    interval = np.where(snz > 1, cnt / np.maximum(snz, 1), cnt)
    return np.where(snz > 0, (1 - a / 2) * size / np.maximum(interval, 1e-9), 0.0)


def adida_at(Ym, p, a=0.3):
    """quarterly (3-month) buckets ending at row p, smoothed, returned per month."""
    lvl = np.full(Ym.shape[1], np.nan)
    starts = list(range(p - 2, -1, -3))[::-1]
    for s in starts:
        blk = Ym[s:s + 3]
        c = (~np.isnan(blk)).sum(0)
        q = np.where(c > 0, np.nansum(blk, 0) * 3 / np.maximum(c, 1), np.nan)
        lvl = np.where(np.isnan(q), lvl, np.where(np.isnan(lvl), q, a * q + (1 - a) * lvl))
    return np.nan_to_num(lvl) / 3


class StatModels:
    """precomputes every statistical model once for a history matrix."""

    def __init__(self, YH, Sx=S, brand=True):
        self.YH = YH
        self.D = YH / Sx[idx % 12][:, None]
        self.Sx = Sx
        self.wma = wma_levels(self.D)
        self.ses = ses_levels(self.D)
        self.sba = sba_rates(YH)
        self.tsb = tsb_levels(YH)
        self.brand = None
        if brand:
            df = pd.DataFrame(YH, columns=codes)
            G = df.T.groupby(brand_of).sum(min_count=1).T
            self.gnames = list(G.columns)
            Gm = G.to_numpy(copy=True)
            Gm[~valid_row] = np.nan
            GD = Gm / Sx[idx % 12][:, None]
            self.g_level = np.nanmedian(np.stack([wma_levels(GD), ses_levels(GD)]), axis=0)
            s_p, _ = nan_window(YH, 12)
            gi = {g: j for j, g in enumerate(self.gnames)}
            self.g_of = np.array([gi[b] for b in brand_of])
            s_g = np.zeros((T, len(self.gnames)))
            np.add.at(s_g.T, self.g_of, s_p.T)
            self.share = np.where(s_g[:, self.g_of] > 0, s_p / np.maximum(s_g[:, self.g_of], 1e-9), 0.0)
            self.brand = True

    def forecast(self, p, targets):
        """dict model -> (len(targets), n) units, for origin row p and global target months."""
        out = {}
        nn = self.YH.shape[1]
        for m in ["WMA", "SES", "SBA", "TSB", "ADIDA", "SN", "TD_BRAND", "NAIVE"]:
            out[m] = np.zeros((len(targets), nn))
        ad = adida_at(self.YH, p)
        for j, g in enumerate(targets):
            s = self.Sx[g % 12]
            out["WMA"][j] = np.nan_to_num(self.wma[p]) * s
            out["SES"][j] = np.nan_to_num(self.ses[p]) * s
            out["SBA"][j] = self.sba[p]
            out["TSB"][j] = self.tsb[p]
            out["ADIDA"][j] = ad
            ly = [self.YH[R(g - 12)] if g - 12 >= i_start else np.full(nn, np.nan),
                  self.YH[R(g - 24)] if g - 24 >= i_start else np.full(nn, np.nan)]
            sn = np.nanmean(np.stack(ly), axis=0)
            out["SN"][j] = np.where(np.isnan(sn), out["WMA"][j], sn)
            if self.brand:
                out["TD_BRAND"][j] = np.nan_to_num(self.g_level[p][self.g_of]) * s * self.share[p]
            last = self.YH[p]
            out["NAIVE"][j] = np.where(np.isnan(last), out["WMA"][j], last)
        return {m: np.clip(v, 0, None) for m, v in out.items()}


# =============================== features for ML / DL ===============================
class Features:
    def __init__(self, D, extras):
        self.D = D
        self.extras = extras
        s3, c3 = nan_window(D, 3)
        s12, c12 = nan_window(D, 12)
        self.m3 = np.where(c3 > 0, s3 / np.maximum(c3, 1), np.nan)
        self.m12 = np.where(c12 > 0, s12 / np.maximum(c12, 1), np.nan)
        nzs, _ = nan_window(np.where(np.isnan(D), np.nan, (np.nan_to_num(D) > 0).astype(float)), 12)
        self.nz = np.where(c12 > 0, nzs / np.maximum(c12, 1), np.nan)

    def shift(self, M, k, P):
        r = P - k
        out = np.full((len(P), n), np.nan)
        ok = r >= 0
        out[ok] = M[r[ok]]
        return out

    def block(self, P, h):
        """features for origin rows P and horizon h -> (len(P)*n, f), plus row validity."""
        P = np.asarray(P)
        g = idx[P] + h
        base = L(self.m12[P])
        fill = lambda x: np.where(np.isnan(x), base, L(x))
        f = [fill(self.D[P]), fill(self.shift(self.D, 1, P)), fill(self.shift(self.D, 2, P)),
             L(self.m3[P]), base, self.nz[P], fill(self.shift(self.D, 12 - h, P)),
             np.repeat(np.log(S[g % 12])[:, None], n, 1), np.repeat((g % 12 + 1)[:, None], n, 1).astype(float),
             np.full((len(P), n), float(h)), np.repeat(np.log(branches[P])[:, None], n, 1)]
        if self.extras:
            f += [np.log1p(BRC[P]), BRC[P] / np.maximum(branches[P], 1)[:, None],
                  np.nan_to_num(DR[P]), np.nan_to_num(PCH[P]),
                  np.repeat((ev(RAM, g) / 30)[:, None], n, 1), np.repeat((ev(MUH, g) / 10)[:, None], n, 1),
                  np.repeat((ev(PREEID, g) / 14)[:, None], n, 1)]
        X = np.stack(f, axis=-1).reshape(len(P) * n, len(f)).astype(np.float32)
        ok = (~np.isnan(self.m12[P])).reshape(-1)
        return X, ok


class Learners:
    def __init__(self, cfg, feats, cut_global):
        self.cfg = cfg
        self.feats = feats
        cut = R(cut_global)
        Xs, ys, cl = [], [], []
        for h in range(1, H_MAX + 1):
            P = np.arange(0, cut - h + 1)
            X, ok = feats.block(P, h)
            tgt = feats.D[P + h].reshape(-1)
            m = ok & ~np.isnan(tgt)
            Xs.append(X[m])
            ys.append(tgt[m])
            cl.append(CLS[P].reshape(-1)[m])
        X, yd, cl = np.vstack(Xs), np.concatenate(ys), np.concatenate(cl)
        yl = L(yd)
        groups = [[0], [1], [2, 3]] if cfg["perclass"] else [[0, 1, 2, 3]]
        self.gbms = []
        for gset in groups:
            m = np.isin(cl, gset)
            if cfg["tweedie"]:
                mdl = lgb.LGBMRegressor(objective="tweedie", tweedie_variance_power=1.2, **LGB_PARAMS).fit(X[m], np.clip(yd[m], 0, None))
                smear = 1.0
            else:
                mdl = lgb.LGBMRegressor(**LGB_PARAMS).fit(X[m], yl[m])
                smear = float(np.mean(np.exp(yl[m] - mdl.predict(X[m])))) if cfg["smear"] else 1.0
            self.gbms.append((gset, mdl, smear))
        self.mu, self.sd = np.nanmean(X, 0), np.nanstd(X, 0) + 1e-9
        Xm = np.nan_to_num((X - self.mu) / self.sd)
        self.mlp = MLPRegressor(hidden_layer_sizes=(32,), batch_size=4096, learning_rate_init=2e-3, max_iter=5,
                                random_state=0).fit(Xm, yl)
        self.mlp_smear = float(np.mean(np.exp(yl - self.mlp.predict(Xm)))) if cfg["smear"] else 1.0
        self.rows = len(yd)

    def forecast(self, p, targets):
        ml = np.zeros((len(targets), n))
        dl = np.zeros((len(targets), n))
        cl_p = CLS[p]
        for j, g in enumerate(targets):
            h = g - idx[p]
            X, ok = self.feats.block([p], h)
            s = S[g % 12]
            for gset, mdl, smear in self.gbms:
                m = np.isin(cl_p, gset)
                if not m.any():
                    continue
                pr = mdl.predict(X[m])
                d = pr if self.cfg["tweedie"] else np.exp(pr) * smear - 1
                ml[j, m] = np.where(ok[m], d, 0.0) * s
            pr = self.mlp.predict(np.nan_to_num((X - self.mu) / self.sd))
            dl[j] = np.where(ok, np.exp(pr) * self.mlp_smear - 1, 0.0) * s
        return {"ML": np.clip(ml, 0, None), "DL": np.clip(dl, 0, None)}


def history(cfg):
    YH = Y.copy()
    if cfg["stockout"]:
        YH[AV < 0.7] = np.nan
    if cfg["spikes"]:
        df = pd.DataFrame(YH)
        med = df.shift(1).rolling(12, min_periods=4).median()
        YH = df.where(~((df > 3 * med) & (med > 0)), 3 * med).to_numpy(copy=True)
    return YH


def ensembles(fc):
    four = np.stack([fc["WMA"], fc["SES"], fc["ML"], fc["DL"]])
    fc["MED4"] = np.median(four, axis=0)
    fc["MEAN4"] = four.mean(axis=0)
    fc["MED_ALL"] = np.median(np.stack([fc[m] for m in ["SN", "WMA", "SES", "SBA", "TSB", "ADIDA", "TD_BRAND", "ML", "DL"]]), axis=0)
    return fc


ROLL = [i for i in idx if ROLL_FROM <= plabel(i) <= ROLL_TO and valid_row[R(i)]]
PAIRS = [(o, t) for o in ROLL for t in (o + 1, o + 2, o + 3) if t <= i_last and valid_row[R(t)]]
ACT = np.stack([np.nan_to_num(Y[R(t)]) for _, t in PAIRS])
CLS_P = np.stack([CLS[R(o)] for o, _ in PAIRS])
LATE = np.array([plabel(o) > SPLIT for o, _ in PAIRS])
AV_T = np.stack([AV[R(t)] for _, t in PAIRS])
ORIG = np.array([o for o, _ in PAIRS])
TARG = np.array([t for _, t in PAIRS])


def run_backtest(cfg):
    YH = history(cfg)
    stat = StatModels(YH)
    feats = Features(stat.D, cfg["features"])
    learners = {}
    for cut in (CUT_EARLY, CUT_LATE):
        learners[cut] = Learners(cfg, feats, mon(cut))
        log(f"  {cfg['name']}: trained ML/DL up to {cut} on {learners[cut].rows:,} rows")
    preds = {}
    for o in ROLL:
        tg = [t for t in (o + 1, o + 2, o + 3) if t <= i_last and valid_row[R(t)]]
        if not tg:
            continue
        fc = stat.forecast(R(o), tg)
        fc.update(learners[CUT_EARLY if plabel(o) <= SPLIT else CUT_LATE].forecast(R(o), tg))
        fc = ensembles(fc)
        for m, v in fc.items():
            preds.setdefault(m, []).append(v)
    return {m: np.vstack(v).astype(np.float32) for m, v in preds.items()}


def wape(pred, mask):
    a = ACT[mask].sum()
    e = pred[mask] - ACT[mask]
    return (np.abs(e).sum() / a, e.sum() / a) if a > 0 else (np.nan, np.nan)


def evaluate(name, preds, pool):
    """per class: pick the best model on EARLY rows, score it on LATE rows."""
    rows, chosen, err_l, act_l, err_e, act_e = [], {}, 0.0, 0.0, 0.0, 0.0
    for ci, cl in enumerate(CLASSES):
        me = (CLS_P == ci) & ~LATE[:, None]
        ml = (CLS_P == ci) & LATE[:, None]
        scores = {m: wape(preds[m], me)[0] for m in pool}
        best = min(scores, key=lambda m: (np.inf if np.isnan(scores[m]) else scores[m]))
        chosen[cl] = best
        we, _ = wape(preds[best], me)
        wl, bl = wape(preds[best], ml)
        err_l += np.abs(preds[best][ml] - ACT[ml]).sum()
        act_l += ACT[ml].sum()
        err_e += np.abs(preds[best][me] - ACT[me]).sum()
        act_e += ACT[me].sum()
        nv = wape(preds["NAIVE"], ml)[0]
        rows.append({"config": name, "class": cl, "chosen": best, "WAPE_early": round(we, 4),
                     "WAPE_late": round(wl, 4), "bias_late": round(bl, 4), "naive_late": round(nv, 4)})
    rows.append({"config": name, "class": "ALL", "chosen": "", "WAPE_early": round(err_e / act_e, 4),
                 "WAPE_late": round(err_l / act_l, 4), "bias_late": None, "naive_late": round(wape(preds["NAIVE"], LATE[:, None] & (CLS_P < 4))[0], 4)})
    return rows, chosen


def model_table(name, preds):
    out = []
    for m in preds:
        for ci, cl in enumerate(CLASSES + ["ALL"]):
            for half, hm in (("early", ~LATE), ("late", LATE)):
                mask = hm[:, None] & ((CLS_P == ci) if cl != "ALL" else np.ones_like(CLS_P, bool))
                w, b = wape(preds[m], mask)
                out.append({"config": name, "model": m, "class": cl, "half": half,
                            "WAPE": round(w, 4), "bias": round(b, 4)})
    return out


BASE_CFG = dict(name="base", stockout=False, spikes=False, features=False, tweedie=False, smear=False, perclass=False)
TESTS = ["stockout", "spikes", "features", "tweedie", "smear", "perclass"]

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    summary, models_rows = [], []
    results = {}
    log(f"backtest pairs: {len(PAIRS)} (early {int((~LATE).sum())}, late {int(LATE.sum())})")

    def do(cfg, pool, label):
        if cfg["name"] not in results:
            results[cfg["name"]] = run_backtest(cfg)
            models_rows.extend(model_table(cfg["name"], results[cfg["name"]]))
        rows, chosen = evaluate(label, results[cfg["name"]], pool)
        summary.extend(rows)
        r_all = [r for r in rows if r["class"] == "ALL"][0]
        log(f"{label:>22}: early {r_all['WAPE_early']:.4f}  late {r_all['WAPE_late']:.4f}  chosen {chosen}")
        return r_all, chosen

    base_all, _ = do(BASE_CFG, BASE_POOL, "base")
    decisions = {}
    pool_all, _ = do(BASE_CFG, EXT_POOL, "base + pool")
    decisions["pool"] = pool_all["WAPE_early"] < base_all["WAPE_early"]
    for t in TESTS:
        cfg = dict(BASE_CFG, name=t, **{t: True})
        r, _ = do(cfg, BASE_POOL, f"base + {t}")
        decisions[t] = bool(r["WAPE_early"] < base_all["WAPE_early"])
    decisions["pool"] = bool(decisions["pool"])
    log("keep (decided on EARLY months only):", decisions)

    final_cfg = dict(BASE_CFG, name="final", **{t: decisions[t] for t in TESTS})
    final_pool = EXT_POOL if decisions["pool"] else BASE_POOL
    final_all, final_chosen = do(final_cfg, final_pool, "final (all kept)")
    do(final_cfg, BASE_POOL if decisions["pool"] else EXT_POOL, "final, other pool (info)")

    pd.DataFrame(summary).to_csv(LAB / "experiments_summary.csv", index=False)
    with pd.ExcelWriter(LAB / "experiments.xlsx") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Configs (honest)", index=False)
        pd.DataFrame(models_rows).to_excel(xw, sheet_name="All models", index=False)
        pd.DataFrame([{"change": k, "kept": v} for k, v in decisions.items()]).to_excel(xw, sheet_name="Decisions", index=False)
    np.savez_compressed(LAB / "final_backtest.npz", **{m: v for m, v in results["final"].items()})
    import json
    (LAB / "final_config.json").write_text(json.dumps({"cfg": final_cfg, "pool": final_pool, "chosen_early": final_chosen,
                                                       "decisions": decisions}, indent=1), encoding="utf-8")
    log("done. results in", LAB)
