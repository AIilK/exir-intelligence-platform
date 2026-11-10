"""Monthly demand forecast per product code + factory production need (models agreed with the user).

Models (per product code, units per Persian month):
  SN        seasonal naive: same Persian month last year (falls back to WMA)
  WMA       simple average of the last 3 valid months, recent months weighted more (0.5/0.3/0.2),
            deseasonalised with the seasonal index
  SES       simple exponential smoothing (alpha 0.2) on the deseasonalised series
  SBA       Croston-SBA for intermittent demand
  ML        gradient-boosted decision trees (numpy implementation), trained on lag, calendar and month-of-year features
  DL        small neural network (1 hidden layer, numpy, Adam), same features
  LLM       OpenAI model (configured in backend/.env) reads each product's monthly history and predicts (A and B only)
  ENS_STAT  hybrid: median ("majority vote" for numbers) of WMA, SES, ML, DL
  ENS_ALL   hybrid: median of WMA, SES, ML, DL and LLM (where the LLM gave a forecast)

Each class (A/B/C) uses the model that had the lowest rolling-backtest error for that class.
Backtest: rolling origins 1403/07..1405/06, horizons 1-3, normal target months only.
Hold-out: forecasts from 1404/09 for 1405/02..1405/07.
Final:    forecasts from 1405/07 for 1405/08..1405/11; production need uses 1405/09..1405/11.
"""
import json
import sys
import time
import urllib.error
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.neural_network import MLPRegressor

warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "forecast" / "data"
OUT = ROOT / "forecast"
ENV_FILE = ROOT / "backend" / ".env"

MANUAL_EXCLUDE = ["1396/02", "1396/03", "1396/04", "1397/01", "1398/01", "1399/01", "1401/01",
                  "1403/01", "1404/10", "1404/11", "1404/12", "1405/01"]
TRAIN_START = "1397/02"
BT_TRAIN_CUT = "1403/06"          # ML/DL trained with targets up to here for the rolling backtest
HOLDOUT_ORIGIN = "1404/09"
HOLDOUT = ["1405/02", "1405/03", "1405/04", "1405/05", "1405/06", "1405/07"]
LAST_FULL = "1405/07"
FINAL_TARGETS = ["1405/08", "1405/09", "1405/10", "1405/11"]
NEED_MONTHS = ["1405/09", "1405/10", "1405/11"]
LLM_BT_ORIGINS = ["1403/10", "1404/03", "1404/06", "1405/02"]
LLM_CLASSES = ("A", "B")
MODELS = ["SN", "WMA", "SES", "SBA", "ML", "DL", "LLM", "ENS_STAT", "ENS_ALL"]
USE_LLM = False  # LLM part is switched off for now (user decision); ENS_ALL then equals ENS_STAT
EVAL_MODELS = MODELS if USE_LLM else [m for m in MODELS if m not in ("LLM", "ENS_ALL")]
TAG = sys.argv[1] if len(sys.argv) > 1 else "baseline"  # output files get this suffix
Z = {"A": 1.65, "B": 1.28, "C": 0.0, "N": 0.0}
FACTORY_STORES = {"1", "2", "3", "4"}
H_MAX = 10
NB = 32  # histogram bins for the tree model
PARAMS = {"gb_trees": 80, "gb_depth": 3, "gb_lr": 0.1, "mlp_hidden": 32, "mlp_epochs": 3}


def mon(label):
    return int(label[:4]) * 12 + int(label[5:]) - 1


def plabel(i):
    y, m = divmod(i, 12)
    return f"{y}/{m + 1:02d}"


def L(x):
    return np.log1p(np.clip(x, 0, None))


# ---------------- data ----------------
sales = pd.read_csv(DATA / "kdb_sales_monthly.csv", dtype={"code": str})
sales["mi"] = sales["pm"].map(mon)
i_start, i_last = mon(TRAIN_START), mon(LAST_FULL)
idx = np.arange(i_start, i_last + 1)
net = sales.pivot_table(index="mi", columns="code", values="net_qty", aggfunc="sum").reindex(idx).fillna(0.0)
codes = sorted(net.columns)
net = net[codes]
branches = sales.groupby("mi")["branches"].max().reindex(idx).ffill().fillna(1).values.astype(float)

total = net.sum(axis=1)
local_med = total.rolling(13, center=True, min_periods=5).median()
auto = [int(i) for i in total.index[total < 0.3 * local_med]]
excluded_idx = set(mon(m) for m in MANUAL_EXCLUDE) | set(auto)
valid_row = np.array([i not in excluded_idx for i in idx])
Y = net.values.copy()
Y[~valid_row, :] = np.nan
pos = {i: k for k, i in enumerate(idx)}

# seasonal index: within-year ratios of the network total (valid months only)
tot_valid = np.where(valid_row, np.nansum(Y, axis=1), np.nan)
ratios = {m: [] for m in range(12)}
for y in range(int(idx[0]) // 12, int(idx[-1]) // 12 + 1):
    rows = [pos[i] for i in range(y * 12, y * 12 + 12) if i in pos and valid_row[pos[i]]]
    if len(rows) >= 10:
        ym = np.nanmean(tot_valid[rows])
        for r in rows:
            ratios[idx[r] % 12].append(tot_valid[r] / ym)
S_arr = np.array([np.mean(ratios[m]) for m in range(12)])
S_arr = S_arr / S_arr.mean()
D = Y / S_arr[idx % 12][:, None]


def S_at(i):
    return S_arr[i % 12]


# ---------------- simple models ----------------
def wma_level(d, o):
    vals = [d[pos[i]] for i in range(o, i_start - 1, -1) if i in pos and not np.isnan(d[pos[i]])][:3]
    if not vals:
        return np.nan
    w = np.array([0.5, 0.3, 0.2][:len(vals)])
    return float(np.dot(w, vals) / w.sum())


def ses_level(d, o, alpha=0.2):
    lvl = np.nan
    for i in range(i_start, o + 1):
        if i not in pos or np.isnan(d[pos[i]]):
            continue
        x = d[pos[i]]
        lvl = x if np.isnan(lvl) else alpha * x + (1 - alpha) * lvl
    return lvl


def sba_rate(y, o, window=24, alpha=0.1):
    rows = [pos[i] for i in range(o - window + 1, o + 1) if i in pos and not np.isnan(y[pos[i]])]
    v = y[rows] if rows else np.array([])
    nz = np.nonzero(v > 0)[0]
    if len(nz) == 0:
        return 0.0
    size = v[nz].mean()
    interval = (len(v) / len(nz)) if len(nz) > 1 else float(len(v))
    return (1 - alpha / 2) * size / interval


# ---------------- features for the tree and neural models ----------------
def precompute(d):
    s = pd.Series(d)
    nzind = pd.Series(np.where(np.isnan(d), np.nan, (d > 0).astype(float)))
    return {"d": d, "s": s,
            "m3": s.rolling(3, min_periods=1).mean().values,
            "m12": s.rolling(12, min_periods=1).mean().values,
            "nz": nzind.rolling(12, min_periods=1).mean().values,
            "x2": s.shift(1).values, "x3": s.shift(2).values,
            "sh": {k: s.shift(k).values for k in range(1, 13)}}


FEATURE_NAMES = ["lag1", "lag2", "lag3", "mean3", "mean12", "share_nonzero12", "same_month_last_year",
                 "log_season_index", "month_of_year", "horizon", "log_branches"]


def features(pre, origin_i, h):
    p = pos[origin_i]
    d = pre["d"]
    base = L(pre["m12"][p])
    ly = pre["sh"][12 - h][p]
    tgt = origin_i + h
    row = [L(d[p]) if not np.isnan(d[p]) else base,
           L(pre["x2"][p]) if not np.isnan(pre["x2"][p]) else base,
           L(pre["x3"][p]) if not np.isnan(pre["x3"][p]) else base,
           L(pre["m3"][p]), base, pre["nz"][p],
           L(ly) if not np.isnan(ly) else base,
           np.log(S_at(tgt)), float(tgt % 12 + 1), float(h), np.log(branches[p])]
    return np.array(row), not np.isnan(pre["m12"][p])


def build_training(cut_target):
    Xs, ys = [], []
    for k in range(len(codes)):
        if not np.nansum(Y[:, k] > 0):
            continue
        pre = precompute(D[:, k])
        for h in range(1, H_MAX + 1):
            for i in range(i_start, cut_target - h + 1):
                if i not in pos or (i + h) not in pos:
                    continue
                tgt = pre["d"][pos[i + h]]
                if np.isnan(tgt):
                    continue
                f, ok = features(pre, i, h)
                if ok:
                    Xs.append(f)
                    ys.append(L(tgt))
    return np.vstack(Xs), np.array(ys)


# ---------------- ML: gradient-boosted trees (histogram, numpy) ----------------
def bin_edges(X, sample=300000, seed=0):
    rng = np.random.default_rng(seed)
    idx_s = rng.choice(len(X), min(sample, len(X)), replace=False)
    return [np.unique(np.quantile(X[idx_s, j], np.linspace(0, 1, NB + 1)[1:-1])) for j in range(X.shape[1])]


def bin_apply(X, edges):
    Xb = np.empty(X.shape, dtype=np.int64)
    for j, e in enumerate(edges):
        Xb[:, j] = np.searchsorted(e, X[:, j], side="right")
    return Xb


def gbdt_fit(Xb, y, n_trees=PARAMS["gb_trees"], depth=PARAMS["gb_depth"], lr=PARAMS["gb_lr"], lam=1.0):
    n, p = Xb.shape
    base = float(y.mean())
    pred = np.full(n, base)
    ar = np.arange(n)
    trees = []
    for _ in range(n_trees):
        r = y - pred
        node = np.zeros(n, dtype=np.int64)
        levels = []
        for d in range(depth):
            k = 2 ** d
            G_tot = np.bincount(node, weights=r, minlength=k)
            C_tot = np.bincount(node, minlength=k).astype(float)
            base_score = G_tot ** 2 / (C_tot + lam)
            best_gain = np.full(k, -np.inf)
            best_f = np.zeros(k, dtype=np.int64)
            best_t = np.full(k, NB - 1, dtype=np.int64)
            for j in range(p):
                key = node * NB + Xb[:, j]
                G = np.bincount(key, weights=r, minlength=k * NB).reshape(k, NB)
                C = np.bincount(key, minlength=k * NB).reshape(k, NB).astype(float)
                GL = np.cumsum(G, axis=1)[:, :-1]
                CL = np.cumsum(C, axis=1)[:, :-1]
                GR = G_tot[:, None] - GL
                CR = C_tot[:, None] - CL
                gain = GL ** 2 / (CL + lam) + GR ** 2 / (CR + lam) - base_score[:, None]
                gain = np.where((CL > 0) & (CR > 0), gain, -np.inf)
                t_best = gain.argmax(axis=1)
                g_best = gain[np.arange(k), t_best]
                better = g_best > best_gain
                best_gain = np.where(better, g_best, best_gain)
                best_f = np.where(better, j, best_f)
                best_t = np.where(better, t_best, best_t)
            best_t = np.where(np.isfinite(best_gain), best_t, NB - 1)
            levels.append((best_f, best_t))
            node = 2 * node + (Xb[ar, best_f[node]] > best_t[node]).astype(np.int64)
        s = np.bincount(node, weights=r, minlength=2 ** depth)
        c = np.bincount(node, minlength=2 ** depth).astype(float)
        leaf = lr * s / (c + lam)
        pred += leaf[node]
        trees.append((levels, leaf))
    return base, trees


def gbdt_predict(model, Xb):
    base, trees = model
    n = Xb.shape[0]
    ar = np.arange(n)
    out = np.full(n, base)
    for levels, leaf in trees:
        node = np.zeros(n, dtype=np.int64)
        for best_f, best_t in levels:
            node = 2 * node + (Xb[ar, best_f[node]] > best_t[node]).astype(np.int64)
        out += leaf[node]
    return out


# ---------------- DL: one-hidden-layer neural network (numpy, Adam) ----------------
def mlp_fit(X, y, hidden=PARAMS["mlp_hidden"], epochs=PARAMS["mlp_epochs"], bs=4096, lr=2e-3, seed=0):
    rng = np.random.default_rng(seed)
    mu, sd = X.mean(axis=0), X.std(axis=0) + 1e-9
    Xs = (X - mu) / sd
    n, p = Xs.shape
    P = {"W1": rng.normal(0, np.sqrt(2.0 / p), (p, hidden)), "b1": np.zeros(hidden),
         "W2": rng.normal(0, np.sqrt(1.0 / hidden), (hidden, 1)), "b2": np.zeros(1)}
    M = {k: np.zeros_like(v) for k, v in P.items()}
    V = {k: np.zeros_like(v) for k, v in P.items()}
    ymean = float(y.mean())
    beta1, beta2, eps, t = 0.9, 0.999, 1e-8, 0
    for _ in range(epochs):
        perm = rng.permutation(n)
        for s0 in range(0, n, bs):
            idb = perm[s0:s0 + bs]
            xb = Xs[idb]
            yb = y[idb] - ymean
            z1 = xb @ P["W1"] + P["b1"]
            a1 = np.maximum(z1, 0)
            out = (a1 @ P["W2"]).ravel() + P["b2"][0]
            g = (2.0 / len(idb)) * (out - yb)[:, None]
            grads = {"W2": a1.T @ g, "b2": np.array([g.sum()])}
            gz1 = (g @ P["W2"].T) * (z1 > 0)
            grads["W1"] = xb.T @ gz1
            grads["b1"] = gz1.sum(axis=0)
            t += 1
            for k in P:
                M[k] = beta1 * M[k] + (1 - beta1) * grads[k]
                V[k] = beta2 * V[k] + (1 - beta2) * grads[k] ** 2
                P[k] -= lr * (M[k] / (1 - beta1 ** t)) / (np.sqrt(V[k] / (1 - beta2 ** t)) + eps)
    return {"mu": mu, "sd": sd, "ymean": ymean, "P": P}


def mlp_predict(model, X):
    Xs = (X - model["mu"]) / model["sd"]
    P = model["P"]
    a1 = np.maximum(Xs @ P["W1"] + P["b1"], 0)
    return (a1 @ P["W2"]).ravel() + P["b2"][0] + model["ymean"]


def fit_learners(cut_target):
    """ML = LightGBM gradient-boosted trees; DL = scikit-learn MLP (one hidden layer). Both predict log demand."""
    t0 = time.time()
    X, y = build_training(cut_target)
    gbm = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=200,
                            subsample=0.8, subsample_freq=1, colsample_bytree=0.9, random_state=0, verbose=-1)
    gbm.fit(X, y)
    mu, sd = np.nanmean(X, axis=0), np.nanstd(X, axis=0) + 1e-9
    mlp = MLPRegressor(hidden_layer_sizes=(32,), batch_size=4096, learning_rate_init=2e-3, max_iter=5,
                       random_state=0)
    mlp.fit(np.nan_to_num((X - mu) / sd), y)  # missing values -> column mean (0 after scaling)
    print(f"  trained LightGBM (ML) and MLP (DL) on {len(y):,} rows up to {plabel(cut_target)} "
          f"in {time.time() - t0:.0f}s", flush=True)
    return {"gbm": gbm, "mlp": mlp, "mu": mu, "sd": sd}


# ---------------- LLM ----------------
def read_env_value(key):
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


CACHE_FILE = DATA / "llm_cache.json"


def llm_cache_load():
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def llm_cache_save(cache):
    CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")


def openai_chat(prompt, key, model):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(4):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                         data=json.dumps(body).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:200]
            print(f"  LLM HTTP {e.code}: {msg}", flush=True)
            if e.code in (400, 401, 403, 404):
                return "{}"
        except Exception as e:  # timeouts and network errors: retry
            print(f"  LLM error (attempt {attempt + 1}): {type(e).__name__}", flush=True)
        time.sleep(5 * (attempt + 1))
    return "{}"


def llm_prompt(origin_i, horizons, batch_codes):
    targets = [plabel(origin_i + h) for h in horizons]
    lines = []
    for c in batch_codes:
        k = k_of[c]
        hist = [f"{plabel(i)}:{Y[pos[i], k]:.0f}" for i in range(origin_i - 23, origin_i + 1)
                if i in pos and valid_row[pos[i]] and not np.isnan(Y[pos[i], k])]
        lines.append(f'"{c}": [{", ".join(hist)}]')
    return ("You are forecasting monthly unit sales for product codes sold by a retail network in Iran. "
            "Each history item is 'Persian yyyy/mm:units'. Months with abnormal disruption were removed. "
            "Consider seasonality (the same Persian month in earlier years) and the recent level and trend. "
            f"Predict the units for these months, in order: {', '.join(targets)}. "
            "Return only a JSON object mapping each code to a list of non-negative numbers, one per month.\n"
            "Histories:\n{" + ", ".join(lines) + "}")


def llm_forecast(origin_i, horizons, codes_subset, key, model):
    """returns {code: [value per horizon]} for the codes in codes_subset (cached per origin and horizon count)."""
    cache = llm_cache_load()
    ck = f"{plabel(origin_i)}|{len(horizons)}"
    done = cache.get(ck, {})
    todo = [c for c in codes_subset if c not in done]
    batches = [todo[i:i + 20] for i in range(0, len(todo), 20)]

    def run(batch):
        raw = openai_chat(llm_prompt(origin_i, horizons, batch), key, model)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = {}
        if not isinstance(obj, dict):
            obj = {}
        return {c: obj.get(c) for c in batch}

    if batches:
        with ThreadPoolExecutor(max_workers=6) as ex:
            for res in ex.map(run, batches):
                for c, v in res.items():
                    if isinstance(v, list) and len(v) >= len(horizons):
                        done[c] = [max(float(x), 0.0) for x in v[:len(horizons)]]
        cache[ck] = done
        llm_cache_save(cache)
    return {c: done[c] for c in codes_subset if c in done}


# ---------------- forecasting at an origin ----------------
k_of = {c: k for k, c in enumerate(codes)}


def forecast_all(origin_i, targets, learners, llm=None):
    n = len(codes)
    out = {m: np.full((n, len(targets)), np.nan) for m in MODELS}
    pre_all = [precompute(D[:, k]) for k in range(n)]
    for k in range(n):
        d, y = pre_all[k]["d"], Y[:, k]
        wl = wma_level(d, origin_i)
        sl = ses_level(d, origin_i)
        sba = sba_rate(y, origin_i)
        for j, t in enumerate(targets):
            out["WMA"][k, j] = wl * S_at(t) if not np.isnan(wl) else 0.0
            out["SES"][k, j] = sl * S_at(t) if not np.isnan(sl) else 0.0
            out["SBA"][k, j] = sba
            ly = y[pos[t - 12]] if (t - 12) in pos else np.nan
            ly2 = y[pos[t - 24]] if (t - 24) in pos else np.nan
            vals = [v for v in (ly, ly2) if not np.isnan(v)]
            out["SN"][k, j] = np.mean(vals) if vals else out["WMA"][k, j]
    for j, t in enumerate(targets):
        h = t - origin_i
        rows, ok = [], []
        for pre in pre_all:
            f, good = features(pre, origin_i, h)
            rows.append(f)
            ok.append(good)
        X = np.vstack(rows)
        ok = np.array(ok)
        g = learners["gbm"].predict(X)
        m = learners["mlp"].predict(np.nan_to_num((X - learners["mu"]) / learners["sd"]))
        out["ML"][:, j] = np.where(ok, np.expm1(g) * S_at(t), 0.0)
        out["DL"][:, j] = np.where(ok, np.expm1(m) * S_at(t), 0.0)
    if llm:
        for c, vals in llm.items():
            k = k_of[c]
            for j, t in enumerate(targets):
                hh = t - origin_i - 1
                if 0 <= hh < len(vals):
                    out["LLM"][k, j] = vals[hh]
    stat = np.stack([out["WMA"], out["SES"], out["ML"], out["DL"]])
    out["ENS_STAT"] = np.nanmedian(stat, axis=0)
    out["ENS_ALL"] = np.nanmedian(np.stack([out["WMA"], out["SES"], out["ML"], out["DL"], out["LLM"]]), axis=0)
    for m in MODELS:
        if m == "LLM":  # keep NaN where the LLM gave no forecast
            out[m] = np.clip(out[m], 0, None)
        else:
            out[m] = np.clip(np.nan_to_num(out[m], nan=0.0), 0, None)
    return out


def classes_at(origin_i):
    rows = [pos[i] for i in range(origin_i - 11, origin_i + 1) if i in pos and valid_row[pos[i]]]
    window = np.nansum(Y[rows, :], axis=0) if rows else np.zeros(len(codes))
    s = pd.Series(window, index=codes).sort_values(ascending=False)
    tot = s.sum()
    cls, cum = {}, 0.0
    for c, v in s.items():
        if v <= 0:
            cls[c] = "N"
            continue
        share_before = cum / tot
        cls[c] = "A" if share_before < 0.80 else ("B" if share_before < 0.95 else "C")
        cum += v
    for c in codes:
        cls.setdefault(c, "N")
    return cls, window


def sigma_at(origin_i):
    rows = [pos[i] for i in range(origin_i - 11, origin_i + 1) if i in pos and valid_row[pos[i]]]
    return np.nanstd(Y[rows, :], axis=0) if rows else np.zeros(len(codes))


def wape(pred, act):
    den = act.sum()
    return (np.abs(pred - act).sum() / den) if den > 0 else np.nan, ((pred - act).sum() / den) if den > 0 else np.nan


key = read_env_value("OPENAI_API_KEY") if USE_LLM else None
llm_model = read_env_value("OPENAI_MODEL") or "gpt-4o"
print("models:", "LLM =", llm_model, "| LLM key loaded:", bool(key), flush=True)

# ---------------- 1) rolling backtest ----------------
t0 = time.time()
bt_learners = fit_learners(mon(BT_TRAIN_CUT))
roll_origins = [i for i in idx if "1403/07" <= plabel(i) <= "1405/06" and valid_row[pos[i]]]
cls_cache = {}
codes_arr = np.array(codes)
roll_parts = []
ab_codes_bt = None
for o in roll_origins:
    tg = [t for t in (o + 1, o + 2, o + 3) if t in pos and valid_row[pos[t]] and t <= i_last]
    if not tg:
        continue
    cls_o, _ = classes_at(o)
    llm_o = None
    if plabel(o) in LLM_BT_ORIGINS and key:
        ab = [c for c in codes if cls_o[c] in LLM_CLASSES and np.nansum(Y[[pos[i] for i in range(o - 11, o + 1) if i in pos and valid_row[pos[i]]], k_of[c]]) > 0]
        llm_o = llm_forecast(o, [1, 2, 3], ab, key, llm_model)
        print(f"  LLM origin {plabel(o)}: {len(llm_o)} products", flush=True)
    fc_o = forecast_all(o, tg, bt_learners, llm_o)
    cls_vec = np.array([cls_o[c] for c in codes])
    for j, t in enumerate(tg):
        act = np.nan_to_num(Y[pos[t], :], nan=0.0)
        for m in EVAL_MODELS:
            roll_parts.append(pd.DataFrame({"origin": plabel(o), "target": plabel(t), "code": codes_arr,
                                            "class": cls_vec, "model": m, "pred": fc_o[m][:, j], "act": act}))
    print(f"  backtest origin {plabel(o)} done ({time.time() - t0:.0f}s)", flush=True)
roll = pd.concat(roll_parts, ignore_index=True)
roll = roll[roll["pred"].notna()]


def summarise(df, label_col="class"):
    rows = []
    for c_label in ["A", "B", "C", "N", "ALL"]:
        for m in EVAL_MODELS:
            sub = df[df["model"] == m]
            if c_label != "ALL":
                sub = sub[sub[label_col] == c_label]
            if not len(sub):
                continue
            w, b = wape(sub["pred"].values, sub["act"].values)
            rows.append({"class": c_label, "model": m, "rows": len(sub),
                         "WAPE": round(float(w), 4) if w == w else None,
                         "bias (+over/-under)": round(float(b), 4) if b == b else None,
                         "actual_units": round(float(sub["act"].sum()), 0)})
    return pd.DataFrame(rows)


rolling = summarise(roll)
rolling_llm = summarise(roll[roll["origin"].isin([plabel(mon(o)) for o in LLM_BT_ORIGINS])])

best = {}
for c_label in ["A", "B", "C"]:
    sub = rolling[(rolling["class"] == c_label) & (rolling["model"].isin(["SN", "WMA", "SES", "SBA", "ML", "DL", "ENS_STAT"]))
                  & rolling["WAPE"].notna()]
    best[c_label] = sub.sort_values("WAPE").iloc[0]["model"] if len(sub) else "ENS_STAT"
# A and B: use the LLM hybrid only if it beats the chosen model on the LLM origins
llm_switch = {}
for c_label in LLM_CLASSES:
    sub = rolling_llm[(rolling_llm["class"] == c_label) & rolling_llm["WAPE"].notna()]
    w = dict(zip(sub["model"], sub["WAPE"]))
    if USE_LLM and "ENS_ALL" in w and best[c_label] in w and w["ENS_ALL"] < w[best[c_label]]:
        best[c_label] = "ENS_ALL"
        llm_switch[c_label] = True
    else:
        llm_switch[c_label] = False
print("backtest done in", f"{time.time() - t0:.0f}s", flush=True)

# ---------------- 2) hold-out (earlier test: from 1404/09 for 1405/02..07) ----------------
o_h = mon(HOLDOUT_ORIGIN)
t_h = [mon(t) for t in HOLDOUT]
h_learners = fit_learners(o_h)
fc_h = forecast_all(o_h, t_h, h_learners, None)
cls_h, _ = classes_at(o_h)
act_h = np.nan_to_num(np.stack([Y[pos[t], :] for t in t_h], axis=1), nan=0.0)
hold_parts = []
cls_vec_h = np.array([cls_h[c] for c in codes])
for j in range(len(t_h)):
    for m in MODELS:
        if m == "LLM" or m == "ENS_ALL":
            continue
        hold_parts.append(pd.DataFrame({"class": cls_vec_h, "model": m, "pred": fc_h[m][:, j], "act": act_h[:, j]}))
holdout = summarise(pd.concat(hold_parts, ignore_index=True))

# ---------------- 3) final forecast ----------------
o_f = mon(LAST_FULL)
t_f = [mon(t) for t in FINAL_TARGETS]
f_learners = fit_learners(o_f)
cls, window = classes_at(o_f)
sig = sigma_at(o_f)
llm_final = None
if key:
    ab_final = [c for c in codes if cls[c] in LLM_CLASSES and window[k_of[c]] > 0]
    llm_final = llm_forecast(o_f, [1, 2, 3, 4], ab_final, key, llm_model)
    print(f"  LLM final: {len(llm_final)} products", flush=True)
fc = forecast_all(o_f, t_f, f_learners, llm_final)

# ---------------- 4) production need ----------------
goods = pd.read_csv(DATA / "kdb_goods.csv", dtype={"code": str}).drop_duplicates("code").set_index("code")
bstock = pd.read_csv(DATA / "kdb_branch_stock.csv", dtype={"code": str}).groupby("code")["qty"].sum()
fstock_df = pd.read_csv(DATA / "rk_factory_stock.csv", dtype={"code": str, "store": str})
fstock = fstock_df[fstock_df["store"].isin(FACTORY_STORES)].groupby("code")["qty"].sum()
oo = pd.read_csv(DATA / "rk_open_orders_lines.csv", dtype={"code": str})
open_orders = (oo["ordered"] - oo["issued"]).groupby(oo["code"]).sum()
prod = pd.read_csv(DATA / "rk_production_daily.csv", dtype={"code": str}, parse_dates=["d"])
last12 = prod[prod["d"] >= pd.Timestamp("2025-11-09")].groupby("code")["qty"].sum()
prod_codes = set(prod["code"].unique())

ids = sorted(set(codes) | set(open_orders.index) | set(fstock.index) | set(last12.index))
g = lambda s, c: float(s.get(c, 0.0)) if s is not None else 0.0

plan_rows, month_rows = [], []
for c in ids:
    k = k_of.get(c)
    cl = cls.get(c, "N")
    model = best.get(cl, "ENS_STAT") if cl in best else "NONE"
    if k is not None and model != "NONE":
        preds = fc[model][k]
    else:
        preds = np.zeros(len(t_f))
    dem3 = float(sum(preds[j] for j, t in enumerate(FINAL_TARGETS) if t in NEED_MONTHS))
    safety = Z.get(cl, 0.0) * float(sig[k]) if k is not None else 0.0
    fstk, bstk, opo = g(fstock, c), g(bstock, c), g(open_orders, c)
    need = max(0.0, dem3 + safety + opo - fstk - bstk)
    plan_rows.append({
        "code": c,
        "name": goods.loc[c, "name"] if c in goods.index else "",
        "brand": goods.loc[c, "brand"] if c in goods.index else "",
        "category": goods.loc[c, "category"] if c in goods.index else "",
        "class": cl, "model": model,
        "sold_last12m": round(float(window[k]), 1) if k is not None else 0.0,
        "forecast_1405/09": round(float(preds[1]), 1) if len(preds) > 1 else 0.0,
        "forecast_1405/10": round(float(preds[2]), 1) if len(preds) > 2 else 0.0,
        "forecast_1405/11": round(float(preds[3]), 1) if len(preds) > 3 else 0.0,
        "demand_next_3m": round(dem3, 1),
        "safety_stock": round(safety, 1),
        "open_factory_orders": round(opo, 1),
        "factory_stock_stores_1_4": round(fstk, 1),
        "branch_stock": round(bstk, 1),
        "production_need": round(need, 0),
        "produced_last12m": round(g(last12, c), 0),
        "in_kdb_goods": c in goods.index,
        "has_production_history": c in prod_codes,
    })
    month_rows.append({"code": c, "class": cl, "model": model,
                       **{f"forecast_{t}": round(float(preds[j]), 1) for j, t in enumerate(FINAL_TARGETS) if j < len(preds)}})

plan = pd.DataFrame(plan_rows)
monthly = pd.DataFrame(month_rows)
plan["class_order"] = plan["class"].map({"A": 0, "B": 1, "C": 2, "N": 3}).fillna(4)
plan = plan.sort_values(["class_order", "production_need"], ascending=[True, False]).drop(columns="class_order")
kdb_mask = plan["in_kdb_goods"].astype(bool)
plan_kdb = plan[kdb_mask].copy()
plan_rk = plan[~kdb_mask].copy()
monthly_kdb = monthly[monthly["code"].isin(plan_kdb["code"])]

summary = pd.DataFrame([
    ("KDB products forecast (codes)", int(len(plan_kdb))),
    ("sold last 12 valid months, units", round(float(plan_kdb["sold_last12m"].sum()))),
    ("demand next 3 months (1405/09-11), units", round(float(plan_kdb["demand_next_3m"].sum()))),
    ("safety stock, units", round(float(plan_kdb["safety_stock"].sum()))),
    ("open factory orders (Rahkaran), units", round(float(plan_kdb["open_factory_orders"].sum()))),
    ("factory stock stores 1-4, units", round(float(plan_kdb["factory_stock_stores_1_4"].sum()))),
    ("branch stock (KDB), units", round(float(plan_kdb["branch_stock"].sum()))),
    ("PRODUCTION NEED (KDB products), units", round(float(plan_kdb["production_need"].sum()))),
    ("codes with production need > 0", int((plan_kdb["production_need"] > 0).sum())),
    ("Rahkaran-only codes with production need > 0 (review)", int((plan_rk["production_need"] > 0).sum())),
    ("Rahkaran-only production need, units (review)", round(float(plan_rk["production_need"].sum()))),
])
for c_label in ["A", "B", "C", "N"]:
    sub = plan_kdb[plan_kdb["class"] == c_label]
    summary = pd.concat([summary, pd.DataFrame([(f"class {c_label}: production need, units",
                                                  round(float(sub["production_need"].sum())))],
                                                 columns=summary.columns)], ignore_index=True)

excluded = pd.DataFrame({"month": [plabel(i) for i in sorted(excluded_idx) if i >= i_start],
                         "reason": "manual list or automatic low-volume check"})
notes = pd.DataFrame({"note": [
    f"Training months {TRAIN_START} to {LAST_FULL}; excluded months listed on the Excluded sheet. "
    f"Partial month 1405/08 is forecast in full and not used for training.",
    "Seasonal index (Persian month 1..12): " + ", ".join(f"{m + 1}:{S_arr[m]:.2f}" for m in range(12)),
    "Models: SN, WMA, SES, SBA (statistical); ML = LightGBM gradient-boosted trees; DL = scikit-learn neural network "
    "(one hidden layer, 32 units); " + (f"LLM = {llm_model} for A and B products." if USE_LLM else "LLM switched off for this run."),
    "Hybrid: ENS_STAT and ENS_ALL = median of the models (majority vote for numbers).",
    "Best model per class (rolling backtest): " + ", ".join(f"{c}={best[c]}" for c in ["A", "B", "C"]),
    "LLM switched on for A/B only where it beat the best model on the LLM origins: "
    + ", ".join(f"{c}={llm_switch[c]}" for c in LLM_CLASSES),
    "production_need = max(0, demand_next_3m + safety + open_factory_orders - factory_stock_stores_1_4 - branch_stock).",
    "Safety: A z=1.65, B z=1.28, C z=0, times the monthly standard deviation of the last 12 valid months.",
    "Factory stock = Rahkaran stores 1-4. Open orders = Rahkaran orders minus issued, all customers.",
    "SCOPE: demand = KDB sales of the company's branches. Factory external customers are not forecast; "
    "their open orders are counted only in open_factory_orders.",
    "Codes in production but not in KDB goods are listed on their own sheet for review.",
    "Hold-out (from 1404/09) includes the 1404/10-1405/01 disruption, which none of the models predicted; "
    "the rolling backtest is the main accuracy measure.",
]})

roll.to_csv(DATA / f"backtest_rows_{TAG}.csv", index=False)  # row-level backtest, for comparing runs
with pd.ExcelWriter(OUT / f"forecast_output_{TAG}.xlsx") as xw:
    summary.to_excel(xw, sheet_name="Summary", index=False, header=["item", "value"])
    plan_kdb.to_excel(xw, sheet_name="Production plan (KDB)", index=False)
    plan_rk.to_excel(xw, sheet_name="Rahkaran-only codes (review)", index=False)
    monthly_kdb.to_excel(xw, sheet_name="Monthly forecast", index=False)
    rolling.to_excel(xw, sheet_name="Backtest rolling", index=False)
    rolling_llm.to_excel(xw, sheet_name="Backtest LLM origins", index=False)
    holdout.to_excel(xw, sheet_name="Backtest holdout", index=False)
    excluded.to_excel(xw, sheet_name="Excluded months", index=False)
    notes.to_excel(xw, sheet_name="Notes", index=False)
plan_kdb.to_csv(OUT / f"production_plan_kdb_{TAG}.csv", index=False, encoding="utf-8-sig")
plan_rk.to_csv(OUT / f"production_plan_rahkaran_only_{TAG}.csv", index=False, encoding="utf-8-sig")

print("\nROLLING backtest:")
print(rolling.to_string(index=False))
print("\nLLM origins only:")
print(rolling_llm[rolling_llm["class"].isin(["A", "B"])].to_string(index=False))
print("\nHOLDOUT:")
print(holdout[holdout["class"].isin(["A", "B", "C", "ALL"])].to_string(index=False))
print("\nbest:", best, "| llm switch:", llm_switch)
print(summary.to_string(index=False))
