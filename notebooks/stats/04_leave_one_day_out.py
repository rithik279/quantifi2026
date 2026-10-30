# %% [markdown]
# # Item 5: validated, not fitted: leave-one-day-out on every parameter choice
# Until now we picked on days -2/-1 and checked day 0: one split. Here every decision is re-checked with
# all three rotations (hold out each day in turn), using the sweep CSVs we already saved (no new backtests).
# For each rotation:
#   - "LODO pick": the config that maximises the worse of the two training days (our usual rule);
#   - its PnL on the held-out day, and whether it is the config we actually chose;
#   - our chosen config's held-out percentile among all configs tried.
# Rule: a choice is VALIDATED if, in all three rotations, our config is in the top quartile on the held-out
# day AND the LODO pick makes money on the held-out day (the selection procedure itself generalises).
# Run from repo root:  python notebooks/stats/04_leave_one_day_out.py

# %%
import ast
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
O = lambda *p: os.path.join(ROOT, "outputs", *p)  # noqa: E731
DAYS = ["d_2", "d_1", "d0"]


def sens_family(unit, param, base_value, chosen_value):
    """One-at-a-time sensitivity runs (outputs/robustness/01_sensitivity_runs.csv) for one parameter."""
    df = pd.read_csv(O("robustness", "01_sensitivity_runs.csv"))
    sub = df[(df.unit == unit) & (df.tag.isin([param, "base"]))].copy()
    sub["label"] = sub.apply(lambda r: base_value if r.tag == "base" else ast.literal_eval(r.overrides)[param], axis=1)
    return sub[["label"] + DAYS], chosen_value


def decisions():
    out = {}
    s10 = pd.read_csv(O("standalone", "10_param_sweep_all.csv"))
    t = s10[s10["product"] == "TOFFEE_CAKE"].rename(columns={"params": "label"})
    out["TOFFEE_CAKE (span, anchor weight, take/make, skew)"] = (
        t[["label"] + DAYS], "{'fair': 'ema', 'span': 10, 'anchor': 5000, 'anchor_w': 0.5, 'take_edge': 8, 'make_edge': 2, 'skew': 0}")
    ln = pd.read_csv(O("standalone", "15_lanterns_trend_sweep.csv")).rename(columns={"params": "label"})
    out["PAPER_LANTERNS trend (span, window, lead, ...)"] = (
        ln[["label"] + DAYS], "{'fair': 'trend', 'span': 20, 'slope_window': 100, 'lead': 100, 'take_edge': 1, 'make_edge': 1, 'skew': 2}")
    p6 = pd.read_csv(O("pearls", "06_param_sweep_all.csv"))
    pk = p6[p6["product"] == "PINK_PEARLS"].rename(columns={"params": "label"})
    out["PINK_PEARLS (k, take/make, skew, cap)"] = (
        pk[["label"] + DAYS], "{'fair': 'sum', 'k': 0.5, 'take_edge': 1, 'make_edge': 0.5, 'skew': 0, 'soft_cap': 20}")
    op = pd.read_csv(O("options", "06_param_sweep_global.csv")).rename(columns={"key": "label"})
    out["Options (iv_span, take, make, cap)"] = (op[["label"] + DAYS], "{'iv_span': 1000, 'take_edge': 4, 'make_edge': 0.5, 'soft_cap': 50, 'skew': 1}")
    tg = pd.read_csv(O("weak", "13_tellurium_fade_backtests.csv"))
    tg = tg[tg.kind == "glide"].rename(columns={"params": "label"})
    out["TELLURIUM glide (wait, gmin, stall window, ...)"] = (
        tg[["label"] + DAYS], "{'J': 60, 'W': 20, 'gmin': 15, 'K': 20, 'flat': 0.0, 'H': 300}")
    gs = pd.read_csv(O("weak", "21_golden_slide.csv")).rename(columns={"params": "label"})
    out["GOLDEN slide (move, window, stall)"] = (gs[["label"] + DAYS], "{'move': 3, 'L': 5, 'K': 10, 'flat': 1.0}")
    # the three robustness "cliff" fixes, chosen with all three days visible
    out["Cliff fix: TELLURIUM soft_cap 10 -> 15"] = sens_family("TELLURIUM", "soft_cap", 10, 15)
    out["Cliff fix: GOLDEN skew 5 -> 2"] = sens_family("GOLDEN_PEARLS", "skew", 5, 2)
    out["Cliff fix: basket min_trade 2 -> 4"] = sens_family("BASKET_GROUP", "min_trade", 2, 4)
    out["Options hedge band (60 chosen)"] = sens_family("OPTIONS_BOOK", "hedge_band", 60, 60)
    return out


def lodo(df, chosen):
    df = df.copy()
    df["label"] = df["label"].astype(str)
    chosen = str(chosen)
    if chosen not in set(df.label):
        return None
    rows = []
    for held in DAYS:
        train = [d for d in DAYS if d != held]
        score = df[train].min(axis=1) * 1e6 + df[train].sum(axis=1)  # worst training day, then the sum
        pick = df.loc[score.idxmax()]
        ch = df[df.label == chosen].iloc[0]
        pct = (df[held] < ch[held]).mean() + 0.5 * (df[held] == ch[held]).mean()
        rows.append(dict(held_out=held, lodo_pick_is_ours=pick.label == chosen, lodo_pick_heldout=pick[held],
                         ours_heldout=ch[held], ours_percentile=pct, best_heldout=df[held].max()))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    summary = []
    for name, (df, chosen) in decisions().items():
        r = lodo(df, chosen)
        if r is None:
            print(f"\n{name}: chosen config not in the saved sweep, skipped"); continue
        ok = bool((r.ours_percentile >= 0.75).all() and (r.lodo_pick_heldout > 0).all())
        print(f"\n=== {name}  ({len(df)} configs)  ->  {'VALIDATED' if ok else 'NOT validated'}")
        print(r.round(2).to_string(index=False))
        summary.append(dict(decision=name, configs=len(df), validated=ok,
                            ours_min_percentile=r.ours_percentile.min(), lodo_pick_matches_ours=int(r.lodo_pick_is_ours.sum()),
                            # weaker test: on each held-out day, does our choice do at least as well as the config
                            # the leave-one-day-out procedure would have picked from the other two days?
                            ours_ge_lodo_pick=f"{int((r.ours_heldout >= r.lodo_pick_heldout).sum())}/3",
                            ours_minus_pick_total=(r.ours_heldout - r.lodo_pick_heldout).sum(),
                            lodo_pick_min_heldout=r.lodo_pick_heldout.min(), ours_min_heldout=r.ours_heldout.min()))
    S = pd.DataFrame(summary)
    print("\nSummary")
    print(S.round(2).to_string(index=False))
    S.round(3).to_csv(os.path.join(ROOT, "outputs", "stats", "05_leave_one_day_out.csv"), index=False)
