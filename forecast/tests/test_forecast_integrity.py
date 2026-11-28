"""Regression checks for historical cutoffs and empirical safety buffers."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import numpy as np
import pandas as pd
import forecast_lab2 as L
from production_plan_io import production_quantities
from production_dashboard_data import publish_plan
from safety_calibration import apply, empirical_upper, fit


class IntegrityTests(unittest.TestCase):
    def test_future_sales_cannot_change_origin_seasonality_or_stat_prediction(self):
        f = L.F
        history = np.tile(np.arange(f.T)[:, None] % 12 + 1, (1, 2)).astype(float)
        ch = L.Channel("b2b", history, f.codes[:2], valid_months=np.ones(f.T, dtype=bool))
        cutoff = f.mon("1403/06")
        at_origin = ch.at_cutoff(cutoff)
        before = L.Stat(at_origin, at_origin.history(L.CFGS["prev"])).forecast(f.R(cutoff), [cutoff + 1])
        ch.Y[f.R(cutoff) + 1:] *= 100000
        perturbed = ch.at_cutoff(cutoff)
        after = L.Stat(perturbed, perturbed.history(L.CFGS["prev"])).forecast(f.R(cutoff), [cutoff + 1])
        np.testing.assert_array_equal(at_origin.S, perturbed.S)
        for key in before:
            np.testing.assert_allclose(before[key], after[key])

    def test_early_three_month_score_excludes_late_outcomes(self):
        split = L.F.mon(L.F.SPLIT)
        origins = [split - 1, split + 1]
        ch = SimpleNamespace(ORIG=np.repeat(origins, 3),
                             PAIRS=[(o, o + h) for o in origins for h in (1, 2, 3)],
                             ACT=np.ones((6, 1)), CLS_P=np.zeros((6, 1), dtype=int))
        p, a, cls, late = L.three_month(ch, np.ones((6, 1)))
        self.assertEqual(len(p), 1)
        self.assertTrue(late[0])

    def test_insufficient_calibration_is_rejected(self):
        with self.assertRaises(ValueError):
            empirical_upper([1, 2], 0.95)

    def test_late_scores_cannot_change_configuration_choice(self):
        rows = {"prev": [{"class": "ALL", "half": "early", "tolWAPE": 0.5},
                          {"class": "ALL", "half": "late", "tolWAPE": 0.1}],
                "+inflation": [{"class": "ALL", "half": "early", "tolWAPE": 0.4},
                               {"class": "ALL", "half": "late", "tolWAPE": 100}]}
        self.assertEqual(L.choose_configuration(rows), "+inflation")
        rows["+inflation"][1]["tolWAPE"] = 0
        rows["prev"][1]["tolWAPE"] = 100
        self.assertEqual(L.choose_configuration(rows), "+inflation")

    def calibration(self):
        prediction = np.full((20, 4), 30.0)
        labels = np.tile(["A", "A", "B", "B"], (20, 1))
        return fit(np.tile(np.arange(1, 21)[:, None], (1, 4)), prediction, labels)

    def test_missing_sku_rmse_uses_empirical_class_pool(self):
        plan = pd.DataFrame({"hybrid_class": ["A"], "b2b_class": ["B"],
                             "hybrid_3m": [30.0], "b2b_3m": [0.0],
                             "hybrid_rmse": [np.nan], "b2b_rmse": [np.nan]}, index=["x"])
        calibrated = apply(plan, self.calibration())
        goods = pd.DataFrame({"active": [True], "name": ["x"], "brand": ["b"]}, index=["x"])
        result = production_quantities(calibrated, ("hybrid", "b2b"), goods, pd.Series(dtype=float), pd.Series(dtype=float))
        self.assertGreater(result.loc["x", "safety"], 0)
        self.assertGreater(result.loc["x", "production_need"], 30)

    def test_publish_retains_calibration_and_stock_only_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safety_calibration.json").write_text(json.dumps(self.calibration()))
            pd.DataFrame({"code": ["x", "stock"], "active": [True, True], "name": ["x", "s"],
                          "brand": ["b", "b"], "category": ["cat", "cat"]}).to_csv(root / "kdb_goods.csv", index=False)
            pd.DataFrame({"code": ["stock"], "store": ["1"], "qty": [5]}).to_csv(root / "rk_factory_stock.csv", index=False)
            pd.DataFrame({"code": ["stock"], "branch": ["b"], "qty": [2]}).to_csv(root / "kdb_branch_stock.csv", index=False)
            months = ["1405/09", "1405/10", "1405/11"]
            model = {"code": ["x"], "name": ["x"]}
            for channel in ("hybrid", "b2b"):
                model.update({f"{channel}_class": ["A"], f"{channel}_model": ["WMA"],
                              f"{channel}_rmse": [np.nan], f"{channel}_3m": [30],
                              **{f"{channel}_{month}": [10] for month in months}})
            pd.DataFrame(model).to_csv(root / "model.csv", index=False)
            publish_plan(root / "model.csv", root, root, "1405/07", "historical")
            published = json.loads((root / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(published["overview"]["safety"]["method"], "joint_empirical_3m")
            stock = next(row for row in published["products"] if row["code"] == "stock")
            self.assertEqual(stock["production_need"], 0)
            self.assertEqual(stock["safety"], 0)


if __name__ == "__main__":
    unittest.main()
