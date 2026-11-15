# QuantiFi 2026

## 🏆 1st place out of 32 teams

**Team #21 won the UTEFA QuantiFi 2026 algorithmic trading competition (National Bank).**

Team: Selena Zhang, Michael Xu, Jeffery Hu, Rithik Singh.

**What we built:** one Python trader covering every product in the competition, in four families:
- **Market making on single products** (AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS, JELLY, PEANUT_BUTTER), each with its own fair value.
- **The fruit basket** against its contents.
- **An options book on LYCHEE vouchers**, priced off a fitted volatility smile.
- **The five pearls**, using the rule that their prices sum to 50,000.

Plus two directional overlays: the TELLURIUM post-jump drift and the GOLDEN_PEARLS plateaus.

**How we got there:**
- **Our own backtester** that mirrors the official fill rules. It stayed within about 3% of the official site.
- **Stress testing:** 24 edited "what might the judges change?" scenarios, fill-rate stress, leave-one-day-out checks and overlap-aware error bars on every claim. We kept edges we could explain and dropped ones we couldn't.
- **Steady iteration:** 316k → 357k → 361k → 366k on the official site, then a merged team version at **487,376** locally on days −2..0.

**Where to look:**
- **Final trader:** [`submission/Team21_Trader.py`](submission/Team21_Trader.py). It's frozen, and its known limitations are in [`submission/README.md`](submission/README.md).
- **Abstract:** [`submission/Team21_Abstract.pdf`](submission/Team21_Abstract.pdf).
- **Research and decisions:** `notebooks/*/NOTES.md`.

---

Workspace for the 2026 QuantiFi competition (UofT).

## Layout

| Path | Purpose |
|---|---|
| `docs/context/Official Information/` | Official QuantiFi wiki (format, products, TradingState, writing the algo) |
| `docs/context/GeneratedDocs/` | Team notes and earlier analysis write-ups |
| `data/raw/` | Organizer `prices_day_*.csv` / `trades_day_*.csv` for days -2, -1, 0 (semicolon-separated, committed) |
| `data/processed/` | Cleaned / derived data (git-ignored) |
| `notebooks/` | Exploration and analysis notebooks |
| `src/` | Reusable code (models, backtests, utilities) |
| `src/GivenScripts/` | Organizer-provided `datamodel.py` and example AMETHYST traders |
| `outputs/` | Figures, tables, and final deliverables |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Before making this repo public

This repo is private and shared with the team only. Before it is ever made public:

- [ ] **Remove the organizer data from git history.** `data/raw/*.csv` (prices and trades, days -2, -1, 0) is committed. Deleting the files in a new commit is not enough; scrub history with `git filter-repo --path data/raw --invert-paths` and force-push.
- [ ] **Check UTEFA's terms** on redistributing the competition data, wiki PDFs, and given scripts (`docs/context/Official Information/`, `src/GivenScripts/`).
- [ ] **Review `docs/context/GeneratedDocs/`** for anything internal (team names, notes).
- [ ] **Scan for secrets** (API keys, credentials). `Logic_for_Basket1.pdf` is git-ignored for this reason and should stay out.
