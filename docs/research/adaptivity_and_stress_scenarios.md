# Adapting when the game changes, and testing against "judge tricks": what the research says

Written 2026-10-30 for Team #21. A companion to `overfitting_and_synthetic_data.md`. The code is in `src/scenarios.py` and `notebooks/adaptive/`.

## The question
Our strategies lean on facts we measured on three days: TOFFEE_CAKE centres on 5,000, the pearls sum to 50,000, the basket is 2/3/1, and so on. If the scoring day changes one of these, can the algorithm notice and re-estimate the fact on a rolling window? And how do we build many realistic "what if" days to check that?

## What the research says

### 1. Expect the rules to drift; don't treat them as constants
- **Edges change over time.** Lo's *Adaptive Markets Hypothesis* argues that market behaviour and the profitability of strategies change as conditions change; a strategy that works in one environment can stop working in the next ([Lo 2004, *J. Portfolio Management* 30, 15–29](https://papers.ssrn.com/abstract=602222)).
- **Regime switching.** Hamilton models a series whose parameters switch between unobserved regimes, and infers the regime probabilistically from the data ([Hamilton 1989, *Econometrica* 57(2), 357–384](https://ideas.repec.org/a/ecm/emetrp/v57y1989i2p357-84.html)).
- **What that means for us:** TOFFEE's "centre 5,000" is better thought of as "a centre near 5,000 that might move", with the algorithm estimating where it currently is.

### 2. Rolling windows face a bias vs noise trade-off, and averaging windows helps
- **The trade-off:** a short window adapts fast after a change but gives a noisy estimate. A long window is precise but keeps using stale data after a break.
- **The remedy:** Pesaran & Timmermann study exactly this. They propose choosing the window by cross-validation, or *combining* estimates from several window lengths, which tends to be safer than betting on one ([Pesaran & Timmermann 2007, *J. Econometrics* 137(1), 134–161](https://rady.ucsd.edu/_files/faculty-research/timmermann/estimation-window.pdf)).
- **Rossi's survey on forecasting under instability:** good in-sample fit says little about out-of-sample performance when relationships shift. Window choice matters, and modelling the instability helps only sometimes, depending on how it's done ([Rossi 2013, *Handbook of Economic Forecasting* vol. 2](https://bse.eu/node/1747)).
- **What that means for us:** for each fact (anchor, sum, weights), blend three estimates:
  - the historical value (the prior);
  - a slow rolling estimate;
  - a fast rolling estimate.

  We'd test the blend on the scenarios rather than trusting any single window.

### 3. Detect the change instead of always adapting
- **CUSUM** keeps a running sum of deviations from the assumed value and raises an alarm when the sum drifts too far. It's the classic quick, low-false-alarm detector for a shift in the mean ([Page 1954, *Biometrika* 41, 100–115](https://en.wikipedia.org/wiki/CUSUM)).
- **Bayesian online changepoint detection** tracks a probability distribution over "how long since the last change", updated every observation ([Adams & MacKay 2007, arXiv 0710.3742](https://arxiv.org/abs/0710.3742)). That gives a natural weight for how much to trust old data versus new.
- **What that means for us:** keep trusting the historical value while the evidence agrees with it, which costs nothing when nothing changed. Switch to the rolling estimate only when CUSUM fires, and cut position size until the new value settles.

### 4. Kalman filters for a slowly moving "fair value"
- Elliott, van der Hoek & Malcolm model the spread between two related prices as a hidden mean-reverting process observed with noise, estimated online with a Kalman filter, and trade when the observed spread departs from the estimate ([Elliott, van der Hoek & Malcolm 2005, *Quantitative Finance* 5(3), 271–276](https://ideas.repec.org/a/taf/quantf/v5y2005i3p271-276.html)).
- **What that means for us:** this is our basket premium, the pearl-sum deviation and the TOFFEE anchor. A Kalman filter is the principled version of "a rolling estimate that adapts at the right speed given how noisy the data is".

### 5. Train and test across many varied, even adversarial, worlds
- **Domain randomization (robotics):** train only in simulators with deliberately randomised conditions, so the real world "may appear to the model as just another variation". Tobin et al. used this to transfer a detector trained purely on simulated images to a real robot ([Tobin et al. 2017, arXiv 1703.06907](https://arxiv.org/abs/1703.06907)). This is the formal version of your idea: **many synthetic days with reasonable guesses of what could change, then pick the algorithm that copes with all of them.**
- **Adversarial market making:** Spooner & Savani pit a market maker against an *adversary* who controls parts of the market environment, as a zero-sum game. The result is more risk-averse behaviour that is more robust to model uncertainty, without hand-written penalties ([Spooner & Savani 2020, IJCAI, arXiv 2003.01820](https://arxiv.org/abs/2003.01820v2)). "Judges trying to throw us off" is exactly that adversary.
- **Synthetic histories in finance:** generate many synthetic price histories from a model estimated on the real data, and test trading rules on those rather than on the single real path. That's López de Prado's *Advances in Financial Machine Learning* ch. 13, and [Carr & López de Prado 2014](https://www.arxiv.org/pdf/1408.1159). Full references are in `overfitting_and_synthetic_data.md`.

### 6. Choose for the bad cases, not the average
- **Across scenarios, prefer the version with the best worst case** (or 10th percentile), subject to a small cost on the normal data. This is the "robust" rather than "optimal" choice, and it's also how the adversarial approach above behaves.
- **Caveat:** the scenario set is itself a hypothesis. Scenarios that don't depend on our guesses (mirror images, block-reshuffled days) count for more than tailor-made ones, and the overfitting warnings in the companion doc apply to choosing among adaptive variants too.

## How this maps onto our build

| Research idea | Our implementation |
|---|---|
| Synthetic / randomised worlds (Tobin; López de Prado) | `src/scenarios.py`: 20 edits of the real days (anchor shifts, mid-day breaks, drifts, mirror image, volatility ×1.5/×0.6, wider spreads, broken pearl and basket rules, option vol shocks, block reshuffles) plus a back-to-back-days mode |
| Adversary / worst case (Spooner & Savani) | Scorecard (`notebooks/adaptive/01_scorecard.py`): every version × every scenario; choose by worst case |
| Prior + rolling window, combined windows (Pesaran & Timmermann) | Next: adaptive anchors that blend the historical value with slow and fast rolling estimates |
| Change detection (Page; Adams & MacKay) | Next: CUSUM on "price − assumed fair value", switching to the rolling estimate and cutting size |
| Kalman filter for a hidden fair value (Elliott et al.) | Next: Kalman-filtered anchor for TOFFEE, the pearl sum and the basket premium, compared with the simpler blend |
