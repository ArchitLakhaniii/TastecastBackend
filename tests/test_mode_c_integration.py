import os
import shutil
import tempfile
import unittest

import pandas as pd

from ingestion.loaders import ingest_mode_c
from engine.pipeline import run_pipeline_mode_c
from artifacts.writers import write_run_artifacts
from artifacts.readers import read_run_artifacts


class TestModeCIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tastecast_test_")
        self.prev_cwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs("artifacts", exist_ok=True)

    def tearDown(self):
        os.chdir(self.prev_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sales_df(self):
        # Ensure last historical date is Wednesday so first forecast date is Thursday (specials-eligible)
        return pd.DataFrame(
            [
                {"business_date": "2026-01-05", "store": "s1", "item": "PieA", "units": 5},
                {"business_date": "2026-01-06", "store": "s1", "item": "PieA", "units": 6},
                {"business_date": "2026-01-07", "store": "s1", "item": "PieA", "units": 4},
                {"business_date": "2026-01-05", "store": "s1", "item": "PieB", "units": 2},
                {"business_date": "2026-01-06", "store": "s1", "item": "PieB", "units": 1},
                {"business_date": "2026-01-07", "store": "s1", "item": "PieB", "units": 2},
            ]
        )

    def _recipe_df(self):
        # PieA uses lots of ing_apples; PieB uses fewer
        return pd.DataFrame(
            [
                {"menu_item_id": "item_0000", "ingredient_id": "apples", "ingredient_qty_per_unit": 3, "uom": "unit"},
                {"menu_item_id": "item_0001", "ingredient_id": "apples", "ingredient_qty_per_unit": 1, "uom": "unit"},
            ]
        )

    def _ingredient_dim(self):
        return pd.DataFrame(
            [
                {
                    "ingredient_id": "apples",
                    "ingredient_name": "Apples",
                    "uom": "unit",
                    "lead_time_days_avg": 2,
                    "service_level_target": 0.95,
                    "lot_size": 10,
                    "case_multiple": 0,
                    "min_order_qty": 0,
                    "shelf_life_days": 5,
                }
            ]
        )

    def _inventory_snapshot(self, on_hand_qty: int):
        return pd.DataFrame(
            [
                {
                    "store_id": "s1",
                    "ingredient_id": "apples",
                    "snapshot_date": "2026-01-07",
                    "on_hand_qty": on_hand_qty,
                    "reserved_qty": 0,
                    "on_order_qty": 0,
                    "backorder_qty": 0,
                }
            ]
        )

    def test_end_to_end_with_specials_and_consistency(self):
        ing = ingest_mode_c(
            self._sales_df(),
            recipe_df_raw=self._recipe_df(),
            ingredient_df_raw=self._ingredient_dim(),
            inventory_df_raw=self._inventory_snapshot(on_hand_qty=500),
            mapping_override={"date": "business_date", "qty_sold": "units", "store_id": "store", "menu_item_name": "item"},
        )
        self.assertTrue(ing.report["ok"])

        out = run_pipeline_mode_c(
            ing.sales_fact,
            recipe_fact=ing.recipe_fact,
            ingredient_dim=ing.ingredient_dim,
            inventory_snapshot=ing.inventory_snapshot,
            horizon_days=7,
        )
        # Should produce a run_id and core frames
        self.assertIsNotNone(out.run_id)
        self.assertGreater(len(out.forecast_df), 0)
        self.assertGreater(len(out.daily_plan_df), 0)
        self.assertIsNotNone(out.ingredient_plan_df)

        # Specials should be eligible on Thu; with huge inventory they should likely trigger at least once.
        self.assertIn("qty_total", out.daily_plan_df.columns)
        self.assertIn("special_added", out.daily_plan_df.columns)

        # Internal consistency: qty_total = baseline_qty + special_added
        chk = out.daily_plan_df.copy()
        chk["baseline_qty"] = pd.to_numeric(chk["baseline_qty"], errors="coerce").fillna(0.0)
        chk["special_added"] = pd.to_numeric(chk["special_added"], errors="coerce").fillna(0.0)
        chk["qty_total"] = pd.to_numeric(chk["qty_total"], errors="coerce").fillna(0.0)
        self.assertTrue(((chk["baseline_qty"] + chk["special_added"]) - chk["qty_total"]).abs().max() < 1e-6)

        # Write artifacts and read them back
        written = write_run_artifacts(
            run_id=out.run_id,
            daily_plan_df=out.daily_plan_df,
            ingredient_plan_df=out.ingredient_plan_df,
            advisories_df=out.advisories_df,
            forecast_df=out.forecast_df,
            forecast_summary=out.summary,
            explanations=out.explanations,
            status=out.status,
            base_dir="artifacts/runs",
            mirror_current=False,
        )
        self.assertTrue(os.path.exists(written.daily_plan_csv))

        loaded = read_run_artifacts(out.run_id, base_dir="artifacts/runs")
        self.assertIsNotNone(loaded["daily_plan_df"])
        self.assertEqual(len(loaded["daily_plan_df"]), len(out.daily_plan_df))

    def test_graceful_degradation_missing_recipe(self):
        ing = ingest_mode_c(
            self._sales_df(),
            recipe_df_raw=None,
            ingredient_df_raw=self._ingredient_dim(),
            inventory_df_raw=self._inventory_snapshot(on_hand_qty=10),
            mapping_override={"date": "business_date", "qty_sold": "units", "store_id": "store", "menu_item_name": "item"},
        )
        out = run_pipeline_mode_c(ing.sales_fact, recipe_fact=None, ingredient_dim=ing.ingredient_dim, inventory_snapshot=ing.inventory_snapshot, horizon_days=7)
        self.assertIsNone(out.ingredient_plan_df)
        self.assertGreaterEqual(len(out.advisories_df), 1)

    def test_graceful_degradation_missing_inventory(self):
        ing = ingest_mode_c(
            self._sales_df(),
            recipe_df_raw=self._recipe_df(),
            ingredient_df_raw=self._ingredient_dim(),
            inventory_df_raw=None,
            mapping_override={"date": "business_date", "qty_sold": "units", "store_id": "store", "menu_item_name": "item"},
        )
        out = run_pipeline_mode_c(ing.sales_fact, recipe_fact=ing.recipe_fact, ingredient_dim=ing.ingredient_dim, inventory_snapshot=None, horizon_days=7)
        self.assertIsNotNone(out.ingredient_plan_df)
        self.assertIsNone(out.inventory_sim_df)


if __name__ == "__main__":
    unittest.main()

