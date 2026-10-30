# %% [markdown]
# # Item 3: block-level PnL, honest t-stats, and a sign test against each edge's naive version
# Cut the 30,000 ticks into 30 blocks of 1,000 and record each strategy's PnL per block. For each:
#   mean / median per block, hit rate (share of positive blocks), Newey-West t of the mean (lag 2),
#   one-sided sign-test p, and how concentrated the PnL is (share from the top 3 blocks).
# Then pair each edge with its OWN naive version (same blocks) and test the difference:
#   PINK without the sum signal (k=0), PAPER_LANTERNS without the trend lead (plain EMA), TOFFEE without
#   the anchor, TELLURIUM without the glide and without flow, GOLDEN without the slide, options with the
#   fixed take threshold. The noise products are tested against not trading at all (zero).
# Run from repo root:  python notebooks/stats/02_block_pnl.py

# %%
import copy
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import basket  # noqa: E402
import options  # noqa: E402
import pearls  # noqa: E402
import standalone  # noqa: E402
from stats_lib import block_stats, hac_mean_t, sign_test_p  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "stats")
BLOCK_TS = 100_000  # 1,000 ticks
PE = pearls.PEARLS
OPT = [options.UNDERLYING] + list(options.VOUCHERS)
BSK = [basket.BASKET] + list(basket.WEIGHTS)


def sp(p, **over):
    prm = copy.deepcopy(standalone.PARAMS[p]); prm.update(over); return prm


def pp(p, **over):
    prm = copy.deepcopy(pearls.PARAMS[p]); prm.update(over); return prm


# name -> (group, products in book, factory-args, products to score)
RUNS = {
    "submission": ("submission", None, None, None),
    "TOFFEE base": ("standalone", ["TOFFEE_CAKE"], {"TOFFEE_CAKE": sp("TOFFEE_CAKE")}, ["TOFFEE_CAKE"]),
    "TOFFEE no anchor": ("standalone", ["TOFFEE_CAKE"], {"TOFFEE_CAKE": sp("TOFFEE_CAKE", anchor_w=0.0)}, ["TOFFEE_CAKE"]),
    "LANTERNS base": ("standalone", ["PAPER_LANTERNS"], {"PAPER_LANTERNS": sp("PAPER_LANTERNS")}, ["PAPER_LANTERNS"]),
    "LANTERNS no trend lead": ("standalone", ["PAPER_LANTERNS"], {"PAPER_LANTERNS": sp("PAPER_LANTERNS", fair="ema")}, ["PAPER_LANTERNS"]),
    "TELLURIUM base": ("standalone", ["TELLURIUM"], {"TELLURIUM": sp("TELLURIUM")}, ["TELLURIUM"]),
    "TELLURIUM no glide": ("standalone", ["TELLURIUM"], {"TELLURIUM": {k: v for k, v in sp("TELLURIUM").items() if k != "glide"}}, ["TELLURIUM"]),
    "TELLURIUM plain MM": ("standalone", ["TELLURIUM"], {"TELLURIUM": {k: v for k, v in sp("TELLURIUM").items() if k not in ("glide", "flow_beta", "flow_decay")}}, ["TELLURIUM"]),
    "PINK base": ("pearls", PE, {"PINK_PEARLS": pp("PINK_PEARLS")}, ["PINK_PEARLS"]),
    "PINK no sum signal": ("pearls", PE, {"PINK_PEARLS": pp("PINK_PEARLS", k=0.0)}, ["PINK_PEARLS"]),
    "GOLDEN base": ("pearls", PE, {"GOLDEN_PEARLS": pp("GOLDEN_PEARLS")}, ["GOLDEN_PEARLS"]),
    "GOLDEN no slide": ("pearls", PE, {"GOLDEN_PEARLS": {k: v for k, v in pp("GOLDEN_PEARLS").items() if k != "slide"}}, ["GOLDEN_PEARLS"]),
    "options base": ("options", OPT, {}, OPT),
    "options fixed take threshold": ("options", OPT, {"take_mode": "fixed"}, OPT),
}
PAIRS = [("TOFFEE base", "TOFFEE no anchor"), ("LANTERNS base", "LANTERNS no trend lead"),
         ("TELLURIUM base", "TELLURIUM no glide"), ("TELLURIUM base", "TELLURIUM plain MM"),
         ("TELLURIUM no glide", "TELLURIUM plain MM"), ("PINK base", "PINK no sum signal"),
         ("GOLDEN base", "GOLDEN no slide"), ("options base", "options fixed take threshold")]


def blocks_from(res, products):
    """Per-block PnL (30 values) for the sum of `products` (None = every product), plus per product."""
    out = {}
    for d in res.days:
        c = d.pnl_curve.drop(columns="TOTAL", errors="ignore")
        # block ends: 100k, 200k, ..., 900k and the day's last timestamp; each day starts from 0 PnL
        ends = sorted(set([ts for ts in c.index if ts % BLOCK_TS == 0 and ts > 0] + [c.index[-1]]))
        for p in c.columns:
            v = c[p].reindex(ends).ffill().fillna(0.0).to_numpy()
            out.setdefault(p, []).extend(np.diff(np.r_[0.0, v]).tolist())
    if products is None:
        products = list(out)
    tot = np.sum([out.get(p, [0.0] * 30) for p in products], axis=0)
    return np.asarray(tot), {p: np.asarray(v) for p, v in out.items()}


def run(name):
    group, book, args, score = RUNS[name]
    if group == "submission":
        T = bt._load_trader(os.path.join(ROOT, "submission", "trader.py"))
        res = bt.backtest(T, (-2, -1, 0), None, record_every=100)
    elif group == "standalone":
        res = bt.backtest(lambda: standalone.Trader(args), (-2, -1, 0), book, record_every=100)
    elif group == "pearls":
        res = bt.backtest(lambda: pearls.Trader(args), (-2, -1, 0), book, record_every=100)
    else:
        res = bt.backtest(lambda: options.Trader(args), (-2, -1, 0), book, record_every=100)
    tot, per = blocks_from(res, score)
    return name, tot, per


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        results = {n: (tot, per) for n, tot, per in ex.map(run, RUNS)}

    # A. every product of the actual submission, against zero
    _, per = results["submission"]
    groups = {"options (11)": OPT, "basket (4)": BSK, "pearls (5)": PE,
              "standalone (6)": list(standalone.PARAMS)}
    rows = []
    for p in sorted(per, key=lambda p: -per[p].sum()):
        rows.append(dict(series=p, **block_stats(per[p])))
    for g, ps in groups.items():
        rows.append(dict(series=f"GROUP {g}", **block_stats(np.sum([per[p] for p in ps if p in per], axis=0))))
    rows.append(dict(series="TOTAL", **block_stats(np.sum(list(per.values()), axis=0))))
    A = pd.DataFrame(rows)
    pd.set_option("display.width", 230)
    print(f"A. best-366k per 1,000-tick block (30 blocks). t_hac = Newey-West t of the mean (lag 2); "
          f"sign_p = one-sided sign test vs 0; top3_share = share of the total from the best 3 blocks")
    print(A.round(3).to_string(index=False))
    A.round(4).to_csv(os.path.join(OUT, "03_block_pnl_by_product.csv"), index=False)

    # B. each edge against its own naive version, paired by block
    rows = []
    for a, b in PAIRS:
        d = results[a][0] - results[b][0]
        rows.append(dict(edge=a, vs=b, edge_total=results[a][0].sum(), naive_total=results[b][0].sum(),
                         diff_total=d.sum(), blocks_edge_better=float((d > 0).mean()),
                         t_hac_diff=hac_mean_t(d), sign_p=sign_test_p(d)))
    B = pd.DataFrame(rows)
    print("\nB. Each edge vs its own naive version, paired over the same 30 blocks")
    print(B.round(3).to_string(index=False))
    B.round(4).to_csv(os.path.join(OUT, "03_edge_vs_naive.csv"), index=False)

    # chart: per-block PnL distributions for the main products
    show = [p for p in ["TOFFEE_CAKE", "PAPER_LANTERNS", "TELLURIUM", "PINK_PEARLS", "VOUCHER_7400", "VOUCHER_7300",
                        "GOLDEN_PEARLS", "AMETHYST", "JELLY", "PEANUT_BUTTER", "WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS",
                        "FRUIT_BASKET"] if p in per]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for i, p in enumerate(show):
        v = per[p] / 1000
        ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(-0.2, 0.2, len(v)), v, s=10, alpha=0.7)
        ax.plot([i - 0.3, i + 0.3], [np.median(v)] * 2, color="k", lw=1.5)
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xticks(range(len(show))); ax.set_xticklabels([s.replace("_PEARLS", "").replace("VOUCHER_", "V") for s in show], rotation=30, fontsize=8)
    ax.set_ylabel("PnL per 1,000-tick block (k coins)")
    ax.set_title("best-366k: PnL of each of the 30 blocks per product (black bar = median)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_block_pnl.png"), dpi=110)
