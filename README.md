# QuantiFi 2026

Workspace for the 2026 QuantiFi competition (UofT).

## Layout

| Path | Purpose |
|---|---|
| `docs/context/Official Information/` | Official QuantiFi wiki (format, products, TradingState, writing the algo) |
| `docs/context/GeneratedDocs/` | Team notes and earlier analysis write-ups |
| `data/raw/` | Organizer `prices_day_*.csv` / `trades_day_*.csv` for days -2, -1, 0 (semicolon-separated, git-ignored) |
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
