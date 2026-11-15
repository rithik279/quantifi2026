# %% [markdown]
# # Hybrid: the full robustness suite on several submission files, side by side
# For every file:
#   1. real days: PnL per product and day, and 30 blocks of 1,000 ticks (hit rate, Newey-West t, worst block)
#   2. every scenario in src/scenarios.py, plus the three days run back to back ("continuous")
#   3. fill stress: half the passive fills (3 seeds), only fills that print THROUGH our price ("worse"),
#      and a noise band (5% of passive fills dropped, 5 seeds)
# Run from repo root:
#   python notebooks/hybrid/02_robustness.py tag1=path1.py tag2=path2.py ...
# Outputs: outputs/hybrid/02_*.csv, 02_scenarios.png

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "notebooks", "stats"))
import backtester as bt  # noqa: E402
import scenarios as sc  # noqa: E402
from stats_lib import block_stats  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "hybrid")
GROUP = {p: "standalone" for p in sc.STANDALONE}
GROUP.update({p: "pearls" for p in sc.PEARLS})
GROUP.update({p: "basket" for p in sc.BASKET_GROUP})
GROUP.update({p: "options" for p in sc.OPTION_PRODUCTS})
STRESS = {"fill_50%_seed0": dict(passive_fill_rate=0.5, seed=0), "fill_50%_seed1": dict(passive_fill_rate=0.5, seed=1),
          "fill_50%_seed2": dict(passive_fill_rate=0.5, seed=2), "fill_through_only": dict(passive_mode="worse")}
STRESS.update({f"noise_95%_seed{s}": dict(passive_fill_rate=0.95, seed=s) for s in range(5)})
BLOCK_TS = 100_000


def run(job):
    tag, path, run_name = job
    Trader = bt._load_trader(path)
    if run_name == "continuous":
        res = bt.backtest(Trader, record_every=0, continuous=True)
    elif run_name in STRESS:
        res = bt.backtest(Trader, record_every=0, **STRESS[run_name])
    else:
        res = bt.backtest(Trader, record_every=100 if run_name == "real" else 0,
                          scenario=None if run_name == "real" else run_name)
    rows = [dict(tag=tag, run=run_name, day=d.day, product=p, pnl=v) for d in res.days for p, v in d.pnl_by_product.items()]
    blocks = []
    if run_name == "real":
        for d in res.days:
            c = d.pnl_curve.drop(columns="TOTAL", errors="ignore")
            ends = sorted(set([ts for ts in c.index if ts % BLOCK_TS == 0 and ts > 0] + [c.index[-1]]))
            for p in c.columns:
                v = c[p].reindex(ends).ffill().fillna(0.0).to_numpy()
                for i, x in enumerate(np.diff(np.r_[0.0, v])):
                    blocks.append(dict(tag=tag, day=d.day, block=i, product=p, pnl=x))
    return rows, blocks


def main():
    files = dict(a.split("=", 1) for a in sys.argv[1:])
    names = list(sc.SCENARIOS) + ["continuous"] + list(STRESS)
    jobs = [(tag, os.path.abspath(path), n) for n in names for tag, path in files.items()]
    print(f"{len(jobs)} backtests ({len(files)} files x {len(names)} runs)")
    with ProcessPoolExecutor() as ex:
        out = list(ex.map(run, jobs))
    df = pd.DataFrame([r for rows, _ in out for r in rows])
    df["group"] = df["product"].map(GROUP)
    B = pd.DataFrame([b for _, bl in out for b in bl])
    df.to_csv(os.path.join(OUT, "02_runs.csv"), index=False)
    B.to_csv(os.path.join(OUT, "02_blocks.csv"), index=False)
    summarize(df, B, list(files))


def summarize(df, B, tags):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    real = df[df.run == "real"]

    print("1. Real days: total per day (coins)")
    print(real.pivot_table(index="tag", columns="day", values="pnl", aggfunc="sum").reindex(tags).assign(
        TOTAL=lambda x: x.sum(axis=1)).round(0).to_string())
    print("\n   per product (3 days, coins)")
    pp = real.pivot_table(index=["group", "product"], columns="tag", values="pnl", aggfunc="sum")[tags].fillna(0)
    print(pp.round(0).to_string())

    print("\n2. Real days, 30 blocks of 1,000 ticks")
    rows = []
    for t in tags:
        bt_ = B[B.tag == t]
        tot = bt_.groupby(["day", "block"]).pnl.sum().to_numpy()
        s = block_stats(tot)
        rows.append(dict(tag=t, scope="TOTAL", total=s["total"], hit=s["hit_rate"], t_hac=s["t_hac"], worst_block=tot.min(),
                         top3_share=s["top3_share"]))
        for g in ("standalone", "pearls", "basket", "options"):
            v = bt_[bt_["product"].map(GROUP) == g].groupby(["day", "block"]).pnl.sum().to_numpy()
            s = block_stats(v)
            rows.append(dict(tag=t, scope=g, total=s["total"], hit=s["hit_rate"], t_hac=s["t_hac"], worst_block=v.min(),
                             top3_share=s["top3_share"]))
    BS = pd.DataFrame(rows)
    print(BS.round(2).to_string(index=False))
    BS.round(3).to_csv(os.path.join(OUT, "02_block_stats.csv"), index=False)

    print("\n3. Scenarios (k coins over 3 days; worst = worst single day)")
    scen = [n for n in list(sc.SCENARIOS) + ["continuous"]]
    S = df[df.run.isin(scen)]
    tot = S.pivot_table(index="run", columns="tag", values="pnl", aggfunc="sum").reindex(scen)[tags] / 1e3
    worst = S.groupby(["run", "tag", "day"]).pnl.sum().groupby(["run", "tag"]).min().unstack().reindex(scen)[tags] / 1e3
    T = tot.copy()
    for t in tags:
        T[f"{t} worst day"] = worst[t]
        T[f"{t} vs real %"] = 100 * (tot[t] / tot.loc["real", t] - 1)
    print(T.round(1).to_string())
    summ = pd.DataFrame({"real": tot.loc["real"], "mean": tot.mean(), "worst": tot.min(), "worst_scenario": tot.idxmin(),
                         "worst_single_day": worst.min()})
    print("\n   summary over scenarios\n", summ.round(1).to_string())
    T.round(2).to_csv(os.path.join(OUT, "02_scenarios.csv"))

    print("\n4. Fill stress (k coins over 3 days)")
    F = df[df.run.isin(list(STRESS))].pivot_table(index="run", columns="tag", values="pnl", aggfunc="sum")[tags] / 1e3
    noise = F.loc[[r for r in F.index if r.startswith("noise")]]
    F.loc["noise band (sd of 5 seeds)"] = noise.std()
    print(F.round(1).to_string())
    F.round(2).to_csv(os.path.join(OUT, "02_fill_stress.csv"))

    fig, ax = plt.subplots(figsize=(11, 0.33 * len(scen) + 1.5))
    y = np.arange(len(scen))
    h = 0.8 / len(tags)
    for i, t in enumerate(tags):
        ax.barh(y + i * h, tot[t].to_numpy(), height=h, label=t)
    ax.set_yticks(y + 0.4 - h / 2)
    ax.set_yticklabels(scen, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("PnL over days -2..0 (k coins)")
    ax.legend(fontsize=8)
    ax.set_title("Every stress scenario, each submission file", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "02_scenarios.png"), dpi=100)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reuse":
        d = pd.read_csv(os.path.join(OUT, "02_runs.csv"))
        summarize(d, pd.read_csv(os.path.join(OUT, "02_blocks.csv")), list(dict.fromkeys(d.tag)))
    else:
        main()
