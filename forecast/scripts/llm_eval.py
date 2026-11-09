"""Compare the LLM forecaster with the other models on exactly the same rows
(A/B products of each channel, at the LLM backtest origins 1403/10, 1404/03, 1405/02, 1405/04).
Also tests a hybrid: median of WMA, SES, ML, DL and LLM.
Output: forecast/lab/llm_comparison.xlsx and lab/llm_decision.json
"""
import json

import numpy as np
import pandas as pd

import channels as C
import forecast_lab2 as L2
import llm_forecaster as LF

F = C.F
llm = json.loads(LF.OUT.read_text(encoding="utf-8")) if LF.OUT.exists() else {}
codes_of = {"hybrid": F.codes, **{k: v[1] for k, v in C.RK.items()}}
rows, decision = [], {}
for ch in ("hybrid", "b2b", "export"):
    z = np.load(F.LAB / f"backtest_{ch}.npz")
    ACT, CLS_P, LATE, ORIG, TARG = z["ACT"], z["CLS_P"], z["LATE"], z["ORIG"], z["TARG"]
    codes = codes_of[ch]
    kidx = {c: k for k, c in enumerate(codes)}
    LLM = np.full(ACT.shape, np.nan)
    for o_lab, fc in llm.get(ch, {}).items():
        if o_lab == LF.FINAL_ORIGIN:
            continue
        o = F.mon(o_lab)
        for r in np.where(ORIG == o)[0]:
            h = int(TARG[r] - o)
            for c, v in fc.items():
                if c in kidx and h - 1 < len(v):
                    LLM[r, kidx[c]] = v[h - 1]
    mask = ~np.isnan(LLM)
    if not mask.any():
        continue
    preds = {m: z[m] for m in ("WMA", "SES", "ML", "DL", "MED4", "MEAN4", "SN", "TD_BRAND")}
    preds["LLM"] = np.where(mask, LLM, 0.0)
    preds["ENS_LLM"] = np.median(np.stack([preds["WMA"], preds["SES"], preds["ML"], preds["DL"], preds["LLM"]]), axis=0)
    choice = json.loads((F.LAB / f"choice_{ch}.json").read_text(encoding="utf-8"))["chosen"]
    chosen = np.zeros_like(ACT)
    for ci, cl in enumerate(F.CLASSES):
        chosen = np.where(CLS_P == ci, z[choice[cl]], chosen)
    preds["CHOSEN"] = chosen
    res = {}
    for half, hm in (("early", ~LATE), ("late", LATE)):
        m = mask & hm[:, None]
        for name, p in preds.items():
            r = L2.metrics(p, ACT, m)
            res[(name, half)] = r["tolWAPE"]
            rows.append({"channel": ch, "half": half, "model": name, "product-months": int(m.sum()),
                         **{k: round(v, 4) for k, v in r.items()}})
    use = res[("ENS_LLM", "early")] < res[("CHOSEN", "early")] and res[("ENS_LLM", "late")] <= res[("CHOSEN", "late")]
    use_llm = res[("LLM", "early")] < res[("CHOSEN", "early")] and res[("LLM", "late")] <= res[("CHOSEN", "late")]
    decision[ch] = "LLM" if use_llm and res[("LLM", "late")] <= res[("ENS_LLM", "late")] else ("ENS_LLM" if use else "none")
    F.log(ch, "decision:", decision[ch], "| late tolWAPE  chosen", round(res[("CHOSEN", "late")], 4),
          "LLM", round(res[("LLM", "late")], 4), "ENS_LLM", round(res[("ENS_LLM", "late")], 4))
pd.DataFrame(rows).to_excel(F.LAB / "llm_comparison.xlsx", index=False)
(F.LAB / "llm_decision.json").write_text(json.dumps(decision), encoding="utf-8")
print(pd.DataFrame(rows).pivot_table(index=["channel", "model"], columns="half", values=["WAPE", "tolWAPE"]).round(3).to_string())
