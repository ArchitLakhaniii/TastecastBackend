import os
import re
import numpy as np
import pandas as pd

# ======= EDIT THIS TO POINT AT YOUR PLAN CSV =======
PLAN_CSV = "tastecast_daily_plan_2026-01-01_to_2026-01-30_per_ingredient.csv"
# ===================================================

# Menu ideas per ingredient (add more keys as you add ingredients)
MENU_SUGGESTIONS = {
    "apples": [
        "Apple Crumble Cups","Apple Turnovers","Apple Cider Donuts","Caramel Apple Slices",
        "Mini Apple Hand Pies","Apple Compote Pancakes","Apple-Oat Parfait",
        "Cheddar Apple Grilled Cheese","Apple Galette Slices"
    ],
    "dough": [
        "Garlic Knots","Cinnamon Rolls","Mini Calzones","Savory Hand Pies",
        "Flatbread Special","Herb Breadsticks","Stuffed Bread Bites",
        "Chocolate Swirl Rolls","Cheese Twists"
    ],
    "_default": [
        "Chef’s Choice Special 1","Chef’s Choice Special 2","Chef’s Choice Special 3",
        "Chef’s Choice Special 4","Chef’s Choice Special 5","Chef’s Choice Special 6"
    ],
}

def detect_ingredients_from_plan(df: pd.DataFrame):
    return sorted([re.sub(r"^signal_", "", c) for c in df.columns if c.startswith("signal_")])

def suggest_menu_items(ingredient: str, k: int = 5):
    pool = MENU_SUGGESTIONS.get(ingredient, MENU_SUGGESTIONS["_default"])
    picks = np.random.choice(pool, size=min(k, len(pool)), replace=False)
    return ", ".join(picks)


def get_suggestions(ingredient: str, k: int = 5, seed: int = 0):
    """Deterministic suggestion helper used by scheduler/tests.

    Returns a list of up to k suggested menu items for an ingredient.
    """
    pool = MENU_SUGGESTIONS.get(ingredient, MENU_SUGGESTIONS["_default"])[:]
    rng = np.random.default_rng(seed)
    if len(pool) <= k:
        return pool
    idx = rng.choice(len(pool), size=k, replace=False)
    return [pool[i] for i in idx]

def make_weekly_advisories(plan_df: pd.DataFrame):
    df = plan_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["iso_week"] = df["date"].dt.isocalendar().week
    df["iso_year"] = df["date"].dt.isocalendar().year

    ingredients = detect_ingredients_from_plan(df)
    if not ingredients:
        raise ValueError("No ingredients found. Expected columns like 'signal_apples', 'signal_dough', ...")

    advisories = []
    for (year, week), wk in df.groupby(["iso_year", "iso_week"]):
        wk = wk.sort_values("date")
        week_start = wk["date"].iloc[0].date().isoformat()
        week_end   = wk["date"].iloc[-1].date().isoformat()
        start_day  = wk["date"].iloc[0].date().isoformat()   # message day for BUY
        end_day    = wk["date"].iloc[-1].date().isoformat()  # message day for SPECIAL

        for ing in ingredients:
            sig_col = f"signal_{ing}"
            if sig_col not in wk.columns:
                continue
            sigs = wk[sig_col].astype(int)

            # BUY: if any shortage signal (1) appears in the week → announce at start of week
            if (sigs == 1).any():
                advisories.append({
                    "date": start_day,
                    "type": f"BUY_{ing.upper()}",
                    "ingredient": ing,
                    "week": int(week),
                    "window_start": week_start,
                    "window_end": week_end,
                    "message": f"{start_day}: BUY EXTRA {ing} this week — projected shortage ahead."
                })

            # SPECIAL: if end-of-week is -1 OR at least 2 days show -1 → announce at end of week
            if (sigs.iloc[-1] == -1) or ((sigs == -1).sum() >= 2):
                ideas = suggest_menu_items(ing, k=5)
                advisories.append({
                    "date": end_day,
                    "type": f"SPECIAL_{ing.upper()}",
                    "ingredient": ing,
                    "week": int(week),
                    "window_start": week_start,
                    "window_end": week_end,
                    "message": f"{end_day}: SURPLUS projected — run a {ing} special. Suggested items: {ideas}."
                })

    adv_df = pd.DataFrame(advisories).sort_values(["date","type","ingredient"]).reset_index(drop=True)
    return adv_df, ingredients

def main():
    if not os.path.exists(PLAN_CSV):
        raise FileNotFoundError(f"Plan CSV not found: {PLAN_CSV}")

    plan_df = pd.read_csv(PLAN_CSV)
    adv_df, ingredients = make_weekly_advisories(plan_df)

    base = os.path.splitext(os.path.basename(PLAN_CSV))[0]
    out_csv = f"{base.replace('_per_ingredient','')}_advisories_from_plan.csv"
    adv_df.to_csv(out_csv, index=False)

    print({
        "ingredients": ingredients,
        "advisory_rows": len(adv_df),
        "saved_advisories_csv": out_csv
    })

if __name__ == "__main__":
    main()
