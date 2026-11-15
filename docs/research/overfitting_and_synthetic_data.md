# Avoiding overfitting when we only have 3 days, and how to make synthetic days

Written 2026-10-30 for Team #21. This doc is about method. The test results it refers to are in `notebooks/robustness/NOTES.md`.

## Why our situation is unusually exposed to overfitting

- **Very little data:** three days of 10,000 ticks, and a score based on **one** unseen day.
- **Lots of trials:** we've already run roughly 3,000 backtest configurations across the workstreams. The more configurations you try, the more likely the best one is lucky. Bailey et al. show that after only ~7 configurations, you'd expect at least one with an annualized Sharpe above 1 on a 2-year backtest even when the true Sharpe is 0 ([Bailey, Borwein, López de Prado & Zhu 2014](https://carmamaths.org/jon/backtest.pdf)).
- **Market replay:** our backtester can't react to our orders. Prices and other traders behave the same whether or not we're there, so fills and market impact are optimistic ([Balch et al. 2019](https://arxiv.org/abs/1906.12010)).
- **A generous fill rule:** a resting order fills whenever a historical trade prints at our price or better, ahead of any queue.

So the goal isn't the highest backtest number. It's choosing strategies and parameters whose PnL **doesn't depend on details of these three days**.

## Part 1: Methods for reducing overfitting, ranked by usefulness to us

### 1. Trade structure, not patterns (the most important one)
An edge with a mechanism we can name and test separately is much less likely to be noise than a parameter that happened to score well. Our best edges are like this:
- the pearl prices sum to 50,000, and PINK is the one that corrects (PCA, regression);
- PAPER_LANTERNS trends persist (smoothed autocorrelation +0.8 on every day);
- TOFFEE_CAKE reverts toward 5,000;
- each voucher's implied vol is stable while its price wanders.

Carr & López de Prado push this to its conclusion: estimate a model of the price process and *derive* the trading rule from it, instead of searching rules on the backtest ([Determining Optimal Trading Rules without Backtesting, 2014](https://www.arxiv.org/pdf/1408.1159); also *Advances in Financial Machine Learning*, ch. 13, "Backtesting on Synthetic Data", [O'Reilly](https://oreilly.com/library/view/advances-in-financial/9781119482086/c13.xhtml)).
**For us:** every parameter should have a reason in `NOTES.md` that comes from the data's structure, not just "it scored best".

### 2. Hold-out by day (done), extended to combinatorial cross-validation
We picked parameters on days −2/−1 and checked day 0. That caught real overfitting: the first TELLURIUM/JELLY picks made +15–18k a day in training and **lost about 23k on day 0**. A single hold-out is noisy, though, and the PBO paper explains why it's unreliable for backtests ([Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting*, J. Computational Finance 2017](https://papers.ssrn.com/abstract=2326253)).

**Combinatorially symmetric cross-validation (CSCV)** is the fix proposed in that paper:
1. Cut the 30,000 ticks into S equal blocks (for example S = 12, four per day). For every configuration we tried, record PnL per block. That gives a matrix of blocks × configurations.
2. For every way of choosing half the blocks as "training" (C(12, 6) = 924 splits), find the best configuration on the training half, then see where it ranks on the other half.
3. **PBO** is the share of splits where the training winner ranks below the median out-of-sample. Near 0 is good. Near 0.5 or above means our selection process is choosing noise.

Related: López de Prado's combinatorial *purged* CV produces many out-of-sample paths instead of one ([overview](https://en.wikipedia.org/wiki/Purged_cross-validation)). Purging matters less for us, since our features look back only hundreds of ticks.
**For us:** this is cheap. Our sweep scripts already record per-day PnL, and we'd switch to per-block PnL. It's next-step #1 below.

### 3. Pick plateaus, not peaks (parameter sensitivity) **(done, see robustness notes)**
Move each parameter one notch at a time, plus 2D heatmaps for the important pairs. A good choice has neighbours that do almost as well. If PnL collapses one step away, the "optimum" is a coincidence. This is standard advice in the walk-forward and robustness literature, and it's the easiest test to explain to judges. We prefer a point in the **middle** of a broad good region over the single best cell, and we rank by the **worst day**, not the total.

### 4. Correct for how many things we tried
- **Deflated Sharpe ratio** ([Bailey & López de Prado, JPM 2014](https://papers.ssrn.com/abstract=2460551)): adjusts a Sharpe ratio for the number of trials, the spread of Sharpe ratios across trials, and fat tails. It needs an honest trial count, which is one more reason to log every sweep (the CSVs in `outputs/` do).
- **Harvey & Liu "haircut" Sharpe** ([Backtesting, JPM 2015](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)): converts a Sharpe ratio to a t-statistic and adjusts the p-value for multiple tests. Marginal results get cut much harder than strong ones.
- **White's Reality Check** ([Econometrica 2000](https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping)) and **Hansen's SPA test** (J. Business & Economic Statistics 2005): bootstrap tests of whether the *best* of many strategies really beats a benchmark (for us, "don't trade this product"). They use the stationary bootstrap ([Politis & Romano, JASA 1994](https://gnosis.library.ucy.ac.cy/handle/7/57533)).

**For us:** the clean use is per product. Treat per-tick PnL changes as returns, run the stationary bootstrap, and ask whether the edge survives the trial count. Strong edges (PINK, PAPER_LANTERNS, TOFFEE_CAKE, options) will. Marginal ones (JELLY, PEANUT_BUTTER, BLUE/BLACK pearls, maybe the basket) probably won't, which tells us to keep them small.

### 5. Fewer free parameters, shared across similar products
Every extra knob is another chance to fit noise. We already share one market-making engine across products. More could be shared, for example one `make_edge` for all random-walk products instead of one each.

### 6. Stress beyond the data
Plausible day-1 conditions not seen in our three days: the TOFFEE_CAKE anchor moves, PAPER_LANTERNS bends more often, LYCHEE gets jumpy, fills get scarcer. The fill stress test (done) covers the last one, and synthetic data (Part 2) covers the rest.

## Part 2: Synthetic data and Monte Carlo

There are three levels, from cheapest to most ambitious. The key principle comes from both Carr & López de Prado and Sun & Lyuu ([Backtesting Trading Strategies with GAN To Avoid Overfitting, 2022](https://arxiv.org/abs/2209.04895)): **a strategy that isn't overfit should still do well on simulated days drawn from the same process as the real data.** Synthetic data is for *checking* parameters, not *tuning* them. Tuning on synthetic data just overfits to the generator.

### Level 1: Resample the real data (no model)
- **Stationary or block bootstrap** ([Politis & Romano 1994](https://gnosis.library.ucy.ac.cy/handle/7/57533)): build new days by stitching random blocks of real ticks with random lengths, taking **all products and the trades file together** so cross-product structure (the pearl sum, basket weights, options) survives inside each block. Shift each block's price level so the path is continuous.
- **What it tests:** whether PnL depends on the particular *ordering* of these three days, such as the one slow basket-premium cycle or long PAPER_LANTERNS trends.
- **Limit:** it can't create anything not already in the data.
- **Monte Carlo permutation tests** (Timothy Masters, [*Permutation and Randomization Tests for Trading System Development*, 2020](https://www.goodreads.com/book/show/51518758-permutation-and-randomization-tests-for-trading-system-development)): shuffle returns to destroy the signal, re-run the *whole* selection process each time, and see how often a shuffled market produces a result as good as ours. This estimates the chance that our result comes from selection luck.

### Level 2: A structural Monte Carlo generator for each product (recommended)
Fit a small model of each product's hidden fair value plus how its quotes and trades are generated, then simulate hundreds of days, **including deliberately perturbed parameters**. This is the López de Prado ch. 13 approach applied to our products. Every input below is something we've already measured:

| Product | Hidden fair-value model | Stress to apply |
|---|---|---|
| AMETHYST | constant 10,000 | none needed |
| TOFFEE_CAKE | mean-reverting around μ = 5,000, half-life ~70 ticks | μ moves to 4,950 / 5,050 or drifts slowly, half-life × 2 |
| PAPER_LANTERNS | straight-line segments: random lengths (mean ~1,000 ticks), slope ~ N(0, 0.033) per tick | segments ½ as long (more kinks) |
| TELLURIUM | random walk + ~10 jumps/day (size ~165) with partial reversal; trade sides persist (82% same side) and lead price | jumps ×2, flow less informative |
| JELLY, PEANUT_BUTTER | random walk (σ from data) | σ × 1.5 |
| Pearls | four free random walks; PINK = 50,000 − others with lagged correction; GOLDEN on 50-coin plateaus | slower PINK correction; sum target ≠ 50,000 |
| Basket | fruits = random walks; premium = slow mean reversion | premium with no reversion (pure random walk) |
| LYCHEE + vouchers | LYCHEE log-random walk at 1.6% per √day; vouchers = Black-Scholes at each strike's IV + a persistent pricing error (autocorr ≈ 0.99/tick, std ≈ 5) | realized vol up to or above IV; LYCHEE jumps |

**Quotes and trades:**
- **Book:** quotes are fair value ± a half-spread drawn from each product's observed spread distribution, at the observed level sizes.
- **Trades:** they arrive at the touch at each product's observed rate (Poisson, as in [Avellaneda & Stoikov 2008](https://math.nyu.edu/%7Eavellane/HighFrequencyTrading.pdf)), with sizes from the empirical distribution. TELLURIUM's clustered, informed flow fits a self-exciting process better ([Bacry, Mastromatteo & Muzy, *Hawkes processes in finance*, 2015](https://arxiv.org/abs/1502.04592)). A simple two-state Markov chain for trade side gets most of the effect.

**Realism checks before trusting it:** compare synthetic and real on the statistics we've measured. Return autocorrelation, variance ratio, spread distribution, trade rate, the adverse-selection curve, and cross-product correlations should all match. Cont's stylized facts are the standard checklist for return series ([Cont 2001, *Quantitative Finance* 1(2)](https://ideas.repec.org:443/a/taf/quantf/v1y2001i2p223-236.html)). Two practical checks:
- our strategies should score about the same on synthetic days with *unperturbed* parameters as on real days;
- a simple classifier shouldn't be able to tell real windows from synthetic ones.

**How to use the output:**
- For each strategy, report the PnL **distribution** over simulated days: median, 10th percentile, chance of a loss. Compare parameter choices by the **10th percentile**, not the mean (robust choice).
- Use the stress rows as "what if day 1 is different" for the abstract's risk section.

### Level 3: Learned generators (not worth it before the deadline)
- **GANs:** these learn the data distribution directly ([Quant GANs, Wiese et al., *Quantitative Finance* 2020](https://ideas.repec.org/a/taf/quantf/v20y2020i9p1419-1440.html); [Sun & Lyuu 2022](https://arxiv.org/abs/2209.04895)). They need far more data than three days.
- **Signature-based variational autoencoder** ([Bühler, Horvath, Lyons, Perez Arribas & Wood 2020, arXiv 2006.14498](https://arxiv.org/pdf/2006.14498)): designed for *small-data* settings, so it's the right reference if anyone asks "why not ML-generated data". It's still heavy for two days of work.
- **Agent-based simulation:** fake traders who *react* to our orders, as in [ABIDES (Byrd, Hybinette & Balch)](https://arxiv.org/pdf/1904.12066). This is the real cure for market-replay optimism, but it's a project in itself.

## Recommended plan before Nov 1

1. **Done:** walk-forward by day; parameter sensitivity (1D and 2D); fill stress. See `notebooks/robustness/NOTES.md`.
2. **~1–2 h, CSCV / PBO:** record PnL per 2,500-tick block in the existing sweeps, run CSCV, and report PBO per workstream. That gives us a single robustness number for the abstract.
3. **~3 h, structural Monte Carlo for the three assumptions that carry the most PnL:** the TOFFEE_CAKE anchor, PAPER_LANTERNS kink frequency, and LYCHEE realized vol vs IV. Report the 10th percentile and median PnL.
4. **In the abstract:** report PnL as a range across days and stress tests, name the trial count, and show one sensitivity heatmap. That's the "Depth" and "Communication" judges are scoring.

## Reference list

- Avellaneda, M. & Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance* 8(3), 217–224. [PDF](https://math.nyu.edu/%7Eavellane/HighFrequencyTrading.pdf)
- Bacry, E., Mastromatteo, I. & Muzy, J.-F. (2015). Hawkes processes in finance. *Market Microstructure and Liquidity*. [arXiv 1502.04592](https://arxiv.org/abs/1502.04592)
- Bailey, D., Borwein, J., López de Prado, M. & Zhu, Q. (2014). Pseudo-mathematics and financial charlatanism: the effects of backtest overfitting on out-of-sample performance. *Notices of the AMS* 61(5), 458–471. [PDF](https://carmamaths.org/jon/backtest.pdf)
- Bailey, D., Borwein, J., López de Prado, M. & Zhu, Q. (2017). The probability of backtest overfitting. *Journal of Computational Finance* 20(4). [SSRN](https://papers.ssrn.com/abstract=2326253)
- Bailey, D. & López de Prado, M. (2014). The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality. *Journal of Portfolio Management* 40(5), 94–107. [SSRN](https://papers.ssrn.com/abstract=2460551)
- Balch, T. H., Mahfouz, M., Lockhart, J., Hybinette, M. & Byrd, D. (2019). How to evaluate trading strategies: single agent market replay or multiple agent interactive simulation? [arXiv 1906.12010](https://arxiv.org/abs/1906.12010)
- Bühler, H., Horvath, B., Lyons, T., Perez Arribas, I. & Wood, B. (2020). A data-driven market simulator for small data environments. [arXiv 2006.14498](https://arxiv.org/pdf/2006.14498)
- Byrd, D., Hybinette, M. & Balch, T. H. (2020). ABIDES: towards high-fidelity market simulation for AI research. SIGSIM-PADS '20. [arXiv 1904.12066](https://arxiv.org/pdf/1904.12066)
- Carr, P. & López de Prado, M. (2014). Determining optimal trading rules without backtesting. [arXiv 1408.1159](https://www.arxiv.org/pdf/1408.1159)
- Cont, R. (2001). Empirical properties of asset returns: stylized facts and statistical issues. *Quantitative Finance* 1(2), 223–236. [RePEc](https://ideas.repec.org:443/a/taf/quantf/v1y2001i2p223-236.html)
- Hansen, P. R. (2005). A test for superior predictive ability. *Journal of Business & Economic Statistics* 23, 365–380.
- Harvey, C. & Liu, Y. (2015). Backtesting. *Journal of Portfolio Management* 41(1), 13–28. [PDF](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Ch. 7 (cross-validation in finance), ch. 13 (backtesting on synthetic data). [ch. 13](https://oreilly.com/library/view/advances-in-financial/9781119482086/c13.xhtml)
- Masters, T. (2020). *Permutation and Randomization Tests for Trading System Development: Algorithms in C++*. [Goodreads](https://www.goodreads.com/book/show/51518758-permutation-and-randomization-tests-for-trading-system-development)
- Politis, D. & Romano, J. (1994). The stationary bootstrap. *JASA* 89(428), 1303–1313. [record](https://gnosis.library.ucy.ac.cy/handle/7/57533)
- Sun, A. & Lyuu, Y.-D. (2022). Backtesting trading strategies with GAN to avoid overfitting. [arXiv 2209.04895](https://arxiv.org/abs/2209.04895)
- White, H. (2000). A reality check for data snooping. *Econometrica* 68(5), 1097–1126. [Econometric Society](https://www.econometricsociety.org/publications/econometrica/2000/09/01/reality-check-data-snooping)
- Wiese, M., Knobloch, R., Korn, R. & Kretschmer, P. (2020). Quant GANs: deep generation of financial time series. *Quantitative Finance* 20(9), 1419–1440. [RePEc](https://ideas.repec.org/a/taf/quantf/v20y2020i9p1419-1440.html)

Every citation above was checked against its abstract or publisher record on 2026-10-30. Claims about methods come from those abstracts and standard descriptions. Read the full papers before quoting specific formulas.
