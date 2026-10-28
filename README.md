# QuantiFi 2026

Workspace for the 2026 QuantiFi competition (UofT).

## Layout

| Path | Purpose |
|---|---|
| `docs/context/` | Competition brief, rules, case documents, reference material |
| `data/raw/` | Original datasets, untouched (git-ignored) |
| `data/processed/` | Cleaned / derived data (git-ignored) |
| `notebooks/` | Exploration and analysis notebooks |
| `src/` | Reusable code (models, backtests, utilities) |
| `outputs/` | Figures, tables, and final deliverables |

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
