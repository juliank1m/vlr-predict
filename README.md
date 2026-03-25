# VLR Predict

Pre-match win probability predictions for professional Valorant, powered by historical performance features and XGBoost.

## Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL
- **ML:** XGBoost with 60 engineered features (Elo, rolling stats, map-specific, H2H, roster stability)
- **Frontend:** Next.js 16 + TypeScript + Tailwind CSS + shadcn/ui + Recharts
- **Scheduling:** APScheduler (daily scrape + weekly retrain placeholders)
- **Infrastructure:** Docker Compose

## Setup

```bash
# Start Postgres
docker compose up -d db

# Install Python dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r api/requirements.txt

# Run migrations
cd api && alembic upgrade head

# Import data & compute Elo
python -m app.services.import_csv --data-dir /path/to/data/raw
python -m app.services.compute_elo

# Train model
python -m app.ml.train

# Start API (from api/)
uvicorn app.main:app --reload
```

```bash
# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 (frontend) and http://localhost:8000/docs (API docs).

## Tests

```bash
cd api && python -m pytest tests/ -v
```

## Project Structure

```
vlr-predict/
├── api/
│   ├── app/
│   │   ├── models/          # SQLAlchemy ORM
│   │   ├── services/        # Elo engine, feature pipeline, predictor
│   │   ├── routers/         # FastAPI endpoints
│   │   ├── ml/              # XGBoost training & evaluation
│   │   └── scheduler.py     # APScheduler cron jobs
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/             # Next.js pages (home, teams, compare, model, matches)
│       ├── components/      # TeamSearch, WinProbBar, shadcn/ui
│       └── lib/             # Typed API client
├── models/                  # Trained model artifacts (gitignored)
└── docker-compose.yml
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/predictions/upcoming` | Predictions for upcoming matches |
| `POST` | `/api/predict` | Ad-hoc prediction: `{team1_id, team2_id}` |
| `GET` | `/api/predictions/history` | Past predictions with accuracy |
| `GET` | `/api/teams` | List teams (searchable) |
| `GET` | `/api/teams/{id}` | Team profile with Elo history and map pool |
| `GET` | `/api/teams/{id}/players` | Roster info |
| `GET` | `/api/matches` | Paginated match results |
| `GET` | `/api/matches/{id}` | Match detail with map scores and player stats |
| `GET` | `/api/model/accuracy` | Rolling accuracy metrics and CV folds |
| `GET` | `/api/model/features` | Feature importance rankings |

## Dashboard Pages

- **/** — Upcoming predictions + quick ad-hoc prediction widget + recent matches
- **/teams/[id]** — Elo chart, map pool win rates, recent results, roster
- **/compare** — Head-to-head team comparison with model prediction
- **/model** — Test metrics, rolling accuracy/log-loss charts, feature importance
- **/matches/[id]** — Map-by-map breakdown with player stat tables
