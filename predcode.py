import os
import numpy as np
import pandas as pd
from datetime import date, timedelta
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from sklearn.model_selection import TimeSeriesSplit

# ==== ONE NUMBER TO CHANGE ====
FORECAST_AHEAD_DAYS = 30     # e.g., 7 for next week, 30 for next month
FORECAST_YEAR = 2026
# ==============================

DATA_CSV = "tastecast_one_item_2023_2025.csv"  # old or new file; script will auto-upgrade

# Recipe + policy
APPLES_PER = 3
DOUGH_PER  = 1

# Reorder thresholds
APPLE_REORDER_POINT = 50
DOUGH_REORDER_POINT = 20

# Safety policy
SAFETY_DAYS = 2
SURPLUS_FACTOR = 1.5  # how far above safety counts as “big surplus”

# Restock policy (weekly, on Monday)
RESTOCK_WEEKDAY = 0            # 0=Mon ... 6=Sun
APPLE_RESTOCK_AMT = 300
DOUGH_RESTOCK_AMT = 120

# SPECIAL (surplus-burn) policy
SPECIAL_DAYS_IN_WEEK = [3,4,5,6]  # Thu–Sun
SPECIAL_BOOST_MAX_PER_DAY = 5     # cap extra pies/day during special

FEATS = ["dow","month","is_weekend","is_xmas","is_july4","is_piday","is_thanksgiving","lag_1","lag_7","roll7","roll28"]

def is_thanksgiving_ts(ts):
    first = date(ts.year, 11, 1)
    off = (3 - first.weekday()) % 7
    tg = pd.Timestamp(first) + pd.Timedelta(days=off) + pd.Timedelta(weeks=3)
    return int(ts.normalize() == tg.normalize())

def add_features(df):
    f = df.copy()
    f["date"] = pd.to_datetime(f["date"])
    f["dow"] = f["date"].dt.weekday
    f["month"] = f["date"].dt.month
    f["is_weekend"] = (f["dow"] >= 5).astype(int)
    f["is_xmas"] = ((f["date"].dt.month==12) & (f["date"].dt.day==25)).astype(int)
    f["is_july4"] = ((f["date"].dt.month==7) & (f["date"].dt.day==4)).astype(int)
    f["is_piday"] = ((f["date"].dt.month==3) & (f["date"].dt.day==14)).astype(int)
    f["is_thanksgiving"] = f["date"].apply(is_thanksgiving_ts).astype(int)
    f["lag_1"] = f["qty_sold"].shift(1)
    f["lag_7"] = f["qty_sold"].shift(7)
    f["roll7"] = f["qty_sold"].shift(1).rolling(7).mean()
    f["roll28"] = f["qty_sold"].shift(1).rolling(28).mean()
    return f

def upgrade_to_per_ingredient_restock_flags(df):
    # If new columns already exist, keep them. Otherwise, infer from stock jumps.
    if {"restocked_apples","restocked_dough"}.issubset(df.columns):
        return df.copy()
    df = df.sort_values("date").reset_index(drop=True).copy()
    restocked_apples = [0]
    restocked_dough  = [0]
    for i in range(1, len(df)):
        restocked_apples.append(int(df.loc[i,"apples_start"] > df.loc[i-1,"apples_end"]))
        restocked_dough.append(int(df.loc[i,"dough_start"]  > df.loc[i-1,"dough_end"]))
    df["restocked_apples"] = restocked_apples
    df["restocked_dough"]  = restocked_dough
    return df

def fit_model(df):
    df = df.sort_values("date")
    train = df[df["date"] <= "2024-12-31"].copy()
    test  = df[df["date"] >= "2025-01-01"].copy()
    train_f = add_features(train)
    test_f  = add_features(test)
    # ensure full history rows only
    min_date = train_f["date"].min() + pd.Timedelta(days=28)
    train_f = train_f[train_f["date"] >= min_date].copy()
    test_f  = test_f.dropna(subset=["lag_1","lag_7","roll7","roll28"]).copy()
    X_train, y_train = train_f[FEATS], train_f["qty_sold"]
    X_test,  y_test  = test_f[FEATS],  test_f["qty_sold"]
    # time-series CV for alpha
    tscv = TimeSeriesSplit(n_splits=5)
    best_alpha, best_mae = 1.0, float("inf")
    for alpha in [0.1, 0.3, 1.0, 3.0, 10.0]:
        maes = []
        for tr_idx, va_idx in tscv.split(X_train):
            X_tr, X_va = X_train.iloc[tr_idx], X_train.iloc[va_idx]
            y_tr, y_va = y_train.iloc[tr_idx], y_train.iloc[va_idx]
            pipe = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=alpha))])
            pipe.fit(X_tr, y_tr)
            pred = pipe.predict(X_va)
            maes.append(mean_absolute_error(y_va, pred))
        m = float(np.mean(maes))
        if m < best_mae:
            best_mae, best_alpha = m, alpha
    model = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=best_alpha))])
    model.fit(X_train, y_train)
    pred_test = model.predict(X_test)
    mae = mean_absolute_error(y_test, pred_test)
    mape = mean_absolute_percentage_error(y_test, pred_test)
    print({"test_MAE": round(mae,2), "test_MAPE": round(mape*100,2)})
    return model

def forecast_next_days_window(df_all, model, days_ahead):
    hist = df_all[["date","qty_sold"]].copy().sort_values("date").reset_index(drop=True)
    start_date = pd.to_datetime(hist["date"].max()) + pd.Timedelta(days=1)
    end_cutoff = pd.Timestamp(f"{FORECAST_YEAR}-12-31")
    end_date = min(start_date + pd.Timedelta(days=days_ahead-1), end_cutoff)
    out, work, current_date = [], hist.copy(), start_date
    while current_date <= end_date:
        tmp = pd.concat([work, pd.DataFrame([{"date": current_date}])], ignore_index=True)
        tmp = add_features(tmp).iloc[-1:]
        X = tmp[FEATS]
        yhat = model.predict(X).item()
        qty = max(0, int(round(yhat)))
        out.append({"date": current_date, "qty_sold": qty})
        work = pd.concat([work, pd.DataFrame([{"date": current_date, "qty_sold": qty}])], ignore_index=True)
        current_date += pd.Timedelta(days=1)
    return pd.DataFrame(out)

def suggest_menu_items(ingredient, k=5):
    apples = ["Apple Crumble Cups","Apple Turnovers","Apple Cider Donuts","Caramel Apple Slices","Mini Apple Hand Pies","Apple Compote Pancakes","Apple-Oat Parfait","Cheddar Apple Grilled Cheese","Apple Galette Slices"]
    dough = ["Garlic Knots","Cinnamon Rolls","Mini Calzones","Savory Hand Pies","Flatbread Special","Herb Breadsticks","Stuffed Bread Bites","Chocolate Swirl Rolls","Cheese Twists"]
    pool = apples if ingredient == "apples" else dough
    picks = np.random.choice(pool, size=min(k, len(pool)), replace=False)
    return ", ".join(picks)

def per_ingredient_weekly_advisories_and_balance(df_hist, future, a0, d0):
    """
    Simulates forward week-by-week, producing per-ingredient advisories and
    adjusting SPECIAL production (Thu–Sun) to burn surplus per ingredient.
    Returns the adjusted daily plan with per-ingredient signals and the advisory list.
    """
    plan = future.copy()
    plan["date"] = pd.to_datetime(plan["date"])
    plan["special_added"] = 0
    plan["qty_total"] = plan["qty_sold"]  # baseline production (ML forecast)

    advisories = []
    a_stock, d_stock = int(a0), int(d0)

    # iterate weeks within the window
    dfw = plan.copy()
    dfw["week"] = dfw["date"].dt.isocalendar().week
    for _, wk_idx in dfw.groupby("week").groups.items():
        wk = plan.loc[wk_idx].sort_values("date")
        if not (wk["date"].dt.year == FORECAST_YEAR).any():
            continue

        # per-week safety based on week demand
        avg_qty = max(1, int(wk["qty_total"].mean()))
        safety_apples = SAFETY_DAYS * avg_qty * APPLES_PER
        safety_dough  = SAFETY_DAYS * avg_qty * DOUGH_PER

        # MONDAY BUY advisories per ingredient (simulate without adding stock yet)
        monday = wk.iloc[0]["date"]
        a_sim, d_sim = a_stock, d_stock
        need_buy_ap, need_buy_dg = False, False
        for _, r in wk.iterrows():
            a_sim -= int(r["qty_total"]) * APPLES_PER
            d_sim -= int(r["qty_total"]) * DOUGH_PER
            if a_sim < max(APPLE_REORDER_POINT, safety_apples): need_buy_ap = True
            if d_sim < max(DOUGH_REORDER_POINT, safety_dough):  need_buy_dg = True

        if monday.weekday() == RESTOCK_WEEKDAY:
            if need_buy_ap:
                advisories.append({"date": monday.date().isoformat(), "type": "BUY_APPLES",
                                   "message": f"{monday.date()}: BUY EXTRA apples this week — projected shortage ahead."})
                a_stock += APPLE_RESTOCK_AMT
            if need_buy_dg:
                advisories.append({"date": monday.date().isoformat(), "type": "BUY_DOUGH",
                                   "message": f"{monday.date()}: BUY EXTRA dough this week — projected shortage ahead."})
                d_stock += DOUGH_RESTOCK_AMT

        # Consume for the week
        for _, r in wk.iterrows():
            a_stock -= int(r["qty_total"]) * APPLES_PER
            d_stock -= int(r["qty_total"]) * DOUGH_PER

        # End-of-week SURPLUS checks per ingredient
        wk_end = wk.iloc[-1]["date"]
        big_surplus_apples = a_stock > safety_apples * SURPLUS_FACTOR
        big_surplus_dough  = d_stock  > safety_dough  * SURPLUS_FACTOR

        if big_surplus_apples or big_surplus_dough:
            ingr = "apples" if (a_stock - safety_apples) >= (d_stock - safety_dough) else "dough"
            ideas = suggest_menu_items(ingr, k=5)
            advisories.append({"date": wk_end.date().isoformat(),
                               "type": f"SPECIAL_{ingr.upper()}",
                               "message": f"{wk_end.date()}: SURPLUS projected — run a {ingr} special. Suggested items: {ideas}."})
            # Try to burn surplus with specials Thu–Sun
            target_ap = max(safety_apples, APPLE_REORDER_POINT)
            target_dg = max(safety_dough,  DOUGH_REORDER_POINT)
            extra_by_ap = max(0, (a_stock - target_ap) // APPLES_PER)
            extra_by_dg = max(0, (d_stock  - target_dg) // DOUGH_PER)
            extra_pies_total = int(min(extra_by_ap, extra_by_dg))
            if extra_pies_total > 0:
                wk_days = wk.copy()
                wk_days["dow"] = wk_days["date"].dt.weekday
                special_days = wk_days[wk_days["dow"].isin(SPECIAL_DAYS_IN_WEEK)].index.tolist()
                for idx in special_days:
                    if extra_pies_total <= 0: break
                    add = int(min(SPECIAL_BOOST_MAX_PER_DAY, extra_pies_total))
                    plan.loc[idx, "special_added"] += add
                    plan.loc[idx, "qty_total"] += add
                    a_stock -= add * APPLES_PER
                    d_stock -= add * DOUGH_PER
                    extra_pies_total -= add

    # Build per-ingredient daily signals with the adjusted qty_total
    plan = plan.sort_values("date").reset_index(drop=True)
    plan["apples_need"] = plan["qty_total"] * APPLES_PER
    plan["dough_need"]  = plan["qty_total"] * DOUGH_PER

    # Re-simulate day-by-day for signals per ingredient
    a_stock2, d_stock2 = int(a0), int(d0)
    avg_est_all = max(1, int(plan["qty_total"].mean()))
    safety_ap_all = SAFETY_DAYS * avg_est_all * APPLES_PER
    safety_dg_all = SAFETY_DAYS * avg_est_all * DOUGH_PER

    sig_apples, sig_dough = [], []
    for _, r in plan.iterrows():
        need_a = int(r["apples_need"]); need_d = int(r["dough_need"])
        a_after = a_stock2 - need_a;    d_after = d_stock2 - need_d

        buy_ap = a_after < max(APPLE_REORDER_POINT, safety_ap_all)
        buy_dg = d_after < max(DOUGH_REORDER_POINT, safety_dg_all)

        # apples
        if buy_ap:
            sig_apples.append(1); a_stock2 += APPLE_RESTOCK_AMT; a_after = a_stock2 - need_a
        else:
            if a_after > safety_ap_all * SURPLUS_FACTOR: sig_apples.append(-1)
            else: sig_apples.append(0)
        # dough
        if buy_dg:
            sig_dough.append(1); d_stock2 += DOUGH_RESTOCK_AMT; d_after = d_stock2 - need_d
        else:
            if d_after > safety_dg_all * SURPLUS_FACTOR: sig_dough.append(-1)
            else: sig_dough.append(0)

        a_stock2, d_stock2 = a_after, d_after

    plan["signal_apples"] = sig_apples
    plan["signal_dough"]  = sig_dough
    return plan, pd.DataFrame(advisories)

def main():
    if not os.path.exists(DATA_CSV):
        raise FileNotFoundError(f"Missing data file: {DATA_CSV}")
    hist = pd.read_csv(DATA_CSV, parse_dates=["date"]).sort_values("date")
    hist = upgrade_to_per_ingredient_restock_flags(hist)

    model = fit_model(hist)
    future = forecast_next_days_window(hist, model, FORECAST_AHEAD_DAYS)

    # starting stocks from last historical day
    last = hist.iloc[-1]
    a0, d0 = int(last["apples_end"]), int(last["dough_end"])

    # build per-ingredient plan and advisories
    plan, advisories = per_ingredient_weekly_advisories_and_balance(hist, future, a0, d0)

    # outputs
    start_str = pd.to_datetime(future["date"].iloc[0]).date().isoformat()
    end_str   = pd.to_datetime(future["date"].iloc[-1]).date().isoformat()
    daily_path = f"tastecast_daily_plan_{start_str}_to_{end_str}_per_ingredient.csv"
    adv_path   = f"tastecast_weekly_advisories_{start_str}_to_{end_str}_per_ingredient.csv"
    plan.to_csv(daily_path, index=False)
    advisories.to_csv(adv_path, index=False)
    print({"saved_daily_plan": daily_path, "saved_weekly_advisories": adv_path})

if __name__ == "__main__":
    main()
