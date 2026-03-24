# VLR Predict

Pre-match win probability predictions for professional Valorant, powered by historical performance features and XGBoost.

## Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **ML:** XGBoost with 60 engineered features (Elo, rolling stats, map-specific, H2H, roster stability)
- **Frontend:** Next.js + TypeScript (planned)

## Setup

```bash
# Start Postgres
docker compose up -d db

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt

# Run migrations
cd api && alembic upgrade head

# Import data & compute Elo
python -m app.services.import_csv --data-dir /path/to/data/raw
python -m app.services.compute_elo

# Start API
uvicorn app.main:app --reload
```

## Tests

```bash
cd api && python -m pytest tests/ -v
```

## Project Structure

```
api/
  app/
    models/          # SQLAlchemy ORM (teams, matches, maps, player stats, Elo)
    services/        # Elo engine, feature pipeline, data import
    routers/         # FastAPI endpoints
    ml/              # Training & evaluation (WIP)
  tests/
```
