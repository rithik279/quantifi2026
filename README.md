# QuantiFi 2026

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
