from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np
from inventory.policy import normalize_weekdays, round_up_lot, rolling_std_proxy
from inventory.policy import compute_safety_stock, compute_reorder_point
from suggestions import get_suggestions


def schedule_specials(
    plan_df: pd.DataFrame,
    recipe: Dict[str, float],
    special_days: List[int],
    max_boost_per_day: int,
    start_stocks: Optional[Dict[str, int]] = None,
    restock_lot_sizes: Optional[Dict[str, int]] = None,
    vendor_weekday: Optional[int] = None,
    service_level: float = 0.95,
    lead_time_days: int = 2,
    shelf_life_days: Optional[Dict[str, int]] = None,
    suggestion_seed: int = 0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Inventory-aware, surplus-gated weekly special scheduler.

    Implements the spec: compute ROP, emit single BUY on vendor day when needed,
    and schedule SPECIAL only when quantified surplus exists.
    """
    if plan_df is None:
        raise ValueError("plan_df is required")

    df = plan_df.copy().sort_values("date").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    if "qty_total" not in df.columns:
        df["qty_total"] = df.get("qty_sold", 0)
    if "special_added" not in df.columns:
        df["special_added"] = 0

    # normalize weekdays
    special_days = normalize_weekdays(special_days)
    if vendor_weekday is not None:
        vendor_weekday = normalize_weekdays([vendor_weekday])[0] if isinstance(vendor_weekday, (list, tuple)) else normalize_weekdays([vendor_weekday])[0]

    ingredients = list(recipe.keys())
    stocks = {ing: int((start_stocks or {}).get(ing, 0)) for ing in ingredients}
    lots = dict(restock_lot_sizes or {})
    shelf_life_days = shelf_life_days or {}

    advisories = []

    # precompute rolling std proxy on qty_total for safety calculations
    df = df.sort_values("date").reset_index(drop=True)
    qty_series = df["qty_total"].astype(float)
    std_proxy = rolling_std_proxy(qty_series)

    # helper to compute lead-time demand (in items) for day i
    def lead_demand(i, lt=lead_time_days):
        return int(df["qty_total"].iloc[i:i+lt].sum()) if i+lt <= len(df) else int(df["qty_total"].iloc[i:].sum())

    def format_pred_summary(idx):
        # return a short human-friendly summary like 'Pred 7.1 (4.9–9.8)'
        if not all(c in df.columns for c in ("pred_mean", "pred_lower", "pred_upper")):
            return None
        try:
            pm = df.at[idx, "pred_mean"]
            pl = df.at[idx, "pred_lower"]
            pu = df.at[idx, "pred_upper"]
            return f"Pred {round(float(pm),1)} ({round(float(pl),1)}–{round(float(pu),1)})"
        except Exception:
            return None

    # iterate day-by-day
    for i, row in df.iterrows():
        d = row["date"]
        wd = int(d.weekday())

        # vendor restock happens at start of day BEFORE consumption
        if vendor_weekday is not None and wd == vendor_weekday:
            # per-vendor-day emission tracking to avoid duplicate BUYs on same vendor day
            buy_emitted_today = {ing: False for ing in ingredients}
            # for each ingredient, check if stock < ROP and emit BUY once (per vendor day)
            for ing in ingredients:
                # compute avg and std over history so far (in items)
                hist_slice = qty_series[max(0, i-28):i]
                avg_daily_items = float(hist_slice.mean()) * float(recipe.get(ing, 1.0)) if len(hist_slice) > 0 else float(qty_series.mean()) * float(recipe.get(ing, 1.0))
                raw_std = float(hist_slice.std(ddof=1)) if len(hist_slice) > 1 else float(std_proxy.iloc[max(0, i-1)])
                std_daily_ing = raw_std * float(recipe.get(ing, 1.0))

                safety = compute_safety_stock(std_daily_ing, lead_time_days, service_level)
                rop = compute_reorder_point(avg_daily_items, lead_time_days, safety)

                # current stock check (ingredient units)
                cur = stocks.get(ing, 0)
                if cur < rop and not buy_emitted_today[ing]:
                    # compute target cover: lead demand (items) in ingredient units + safety + 1 item buffer
                    lead_d_items = lead_demand(i, lead_time_days)
                    target = lead_d_items * float(recipe.get(ing, 1.0)) + safety + float(recipe.get(ing, 1.0))
                    order_qty = round_up_lot(max(0, target - cur), lots.get(ing, 0))
                    if order_qty > 0:
                        adv = {
                            "date": d.date().isoformat(),
                            "type": f"BUY_{ing.upper()}",
                            "ingredient": ing,
                            "qty": int(order_qty),
                            "message": f"{d.date()}: BUY {int(order_qty)} {ing} (stock {cur} < ROP {int(round(rop))}). Target cover={int(round(target))}.",
                            "special_qty": None,
                            "suggestions": None,
                            "reason": "below_ROP",
                        }
                        # attach prediction columns if available on input plan
                        for col in ("pred_mean", "pred_lower", "pred_upper"):
                            if col in df.columns:
                                adv[col] = df.at[i, col]
                        ps = format_pred_summary(i)
                        if ps:
                            adv["pred_summary"] = ps
                            adv["message"] = adv["message"] + f" — {ps}"
                        advisories.append(adv)
                        stocks[ing] = cur + int(order_qty)
                    buy_emitted_today[ing] = True
                # else: no buy

        # consume baseline demand (convert to ingredient units, integer)
        for ing in ingredients:
            need = int(round(float(row.get("qty_total", 0)) * float(recipe.get(ing, 1.0))))
            stocks[ing] = max(0, int(stocks.get(ing, 0) - need))

        # decide specials on special_days (after consumption) using surplus logic
        if wd in special_days:
            # compute surplus per ingredient: current stock - future need until expiry - safety
            surplus_map = {}
            for ing in ingredients:
                # expiry window = lead_time + half shelf life (fallback 3 days)
                sl = shelf_life_days.get(ing, 3)
                expiry = lead_time_days + int(sl / 2)
                future_need = int(round(df["qty_total"].iloc[i+1:i+1+expiry].sum() * float(recipe.get(ing, 1.0)))) if i+1 < len(df) else 0
                # compute safety based on recent std and scale to ingredient units
                hist_slice = qty_series[max(0, i-28):i+1]
                raw_std = float(hist_slice.std(ddof=1)) if len(hist_slice) > 1 else float(std_proxy.iloc[max(0, i)])
                std_daily_ing = raw_std * float(recipe.get(ing, 1.0))
                safety = compute_safety_stock(std_daily_ing, lead_time_days, service_level)
                surplus = stocks.get(ing, 0) - future_need - safety
                surplus_map[ing] = surplus

            # schedule specials for ingredients with positive surplus, largest first
            for ing in sorted(surplus_map.keys(), key=lambda k: -surplus_map[k]):
                s = surplus_map[ing]
                if s <= 0:
                    continue
                # convert surplus (ingredient units) to extra items possible
                per_item = float(recipe.get(ing, 1.0))
                if per_item <= 0:
                    continue
                max_extra_items = int(s // per_item)
                if max_extra_items <= 0:
                    continue
                # how many to add today, constrained by max_boost_per_day and not dipping below safety+nextday need
                today_add = min(max_boost_per_day, max_extra_items)
                # ensure we won't dip below safety after making them
                # compute post-production stock
                projected_stock = stocks[ing] - today_add * per_item
                if projected_stock < 0:
                    continue
                # apply special
                df.at[i, "special_added"] = int(df.at[i, "special_added"]) + int(today_add)
                df.at[i, "qty_total"] = int(df.at[i, "qty_total"]) + int(today_add)
                for k in ingredients:
                    dec = int(round(today_add * float(recipe.get(k, 1.0))))
                    stocks[k] = max(0, int(stocks.get(k, 0) - dec))
                # advisory with suggestions
                sugg = get_suggestions(ing, k=5, seed=suggestion_seed)
                adv = {
                    "date": d.date().isoformat(),
                    "type": f"SPECIAL_{ing.upper()}",
                    "ingredient": ing,
                    "qty": None,
                    "special_qty": int(today_add),
                    "suggestions": ", ".join(sugg),
                    "message": f"{d.date()}: Scheduled {today_add} extra items to burn surplus of {ing}.",
                    "reason": "surplus_burn",
                }
                for col in ("pred_mean", "pred_lower", "pred_upper"):
                    if col in df.columns:
                        adv[col] = df.at[i, col]
                ps = format_pred_summary(i)
                if ps:
                    adv["pred_summary"] = ps
                    adv["message"] = adv["message"] + f" — {ps}"
                advisories.append(adv)

    adv_df = pd.DataFrame(advisories).sort_values(["date", "type"]).reset_index(drop=True)
    return df, adv_df
