# VLR Predict — Project Specification

Pre-match win probability predictions for professional Valorant, powered by historical performance features.

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + Alembic
- **Database**: PostgreSQL
- **ML**: XGBoost (primary), Logistic Regression (baseline)
- **Frontend**: Next.js + TypeScript
- **Infrastructure**: Docker Compose
- **Scheduling**: APScheduler (lightweight, no Redis needed for v1)

---

## Database Schema

### `teams`

Canonical team identity. Team names on VLR can vary slightly across matches (whitespace, casing), so this table normalizes them.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | Internal ID |
| `name` | VARCHAR UNIQUE | Normalized team name |
| `first_seen` | DATE | Earliest match date in dataset |

### `players`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | VLR player_id |
| `name` | VARCHAR | Display name (can change over time) |
| `url` | VARCHAR | VLR profile URL |

### `matches`

One row per series (Bo1, Bo3, Bo5).

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | VLR match_id |
| `date` | TIMESTAMP | Match date |
| `team1_id` | FK → teams | |
| `team2_id` | FK → teams | |
| `team1_score` | SMALLINT | Maps won by team1 |
| `team2_score` | SMALLINT | Maps won by team2 |
| `winner_id` | FK → teams | |
| `event` | VARCHAR | Tournament name |
| `stage` | VARCHAR | Tournament stage |
| `url` | VARCHAR | VLR match URL |

### `maps`

One row per map played within a match.

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | VLR game_id |
| `match_id` | FK → matches | |
| `map_number` | SMALLINT | 1, 2, 3... |
| `map_name` | VARCHAR | Ascent, Bind, Haven, etc. |
| `team1_score` | SMALLINT | Rounds won |
| `team2_score` | SMALLINT | Rounds won |
| `winner_id` | FK → teams | |

### `player_map_stats`

One row per player per map. This is the raw stat line.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `map_id` | FK → maps | |
| `player_id` | FK → players | |
| `team_id` | FK → teams | |
| `agent` | VARCHAR | Agent played |
| `rating` | FLOAT | VLR rating |
| `acs` | FLOAT | Average combat score |
| `kills` | SMALLINT | |
| `deaths` | SMALLINT | |
| `assists` | SMALLINT | |
| `kast` | FLOAT | Percentage (0-100) |
| `adr` | FLOAT | Average damage per round |
| `hs_percent` | FLOAT | Headshot % (0-100) |
| `first_kills` | SMALLINT | |
| `first_deaths` | SMALLINT | |

### `team_elo`

Snapshot of each team's Elo after every map. Enables point-in-time lookups.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `team_id` | FK → teams | |
| `map_id` | FK → maps | |
| `elo` | FLOAT | Elo after this map |
| `elo_delta` | FLOAT | Change from this map |

### `predictions` (populated by the model)

Stores model predictions for evaluation and display.

| Column | Type | Notes |
|--------|------|-------|
| `id` | SERIAL PK | |
| `map_id` | FK → maps | Null if upcoming/unplayed |
| `match_id` | FK → matches | |
| `team1_id` | FK → teams | |
| `team2_id` | FK → teams | |
| `map_name` | VARCHAR | Null if unknown |
| `team1_win_prob` | FLOAT | Model output (0-1) |
| `predicted_at` | TIMESTAMP | When prediction was made |
| `model_version` | VARCHAR | e.g. "xgb_v1" |
| `correct` | BOOLEAN | Null until resolved |

---

## Feature Engineering

This is the core of the project. Every feature must be computable using only data available before the match starts. No future leakage.

### Feature computation function signature

```
compute_features(team1_id, team2_id, map_name, match_date) → feature_dict
```

All rolling stats use only maps where `maps.match_id → matches.date < match_date`.

### Feature categories

#### 1. Team Elo (custom implementation)

| Feature | Description |
|---------|-------------|
| `team1_elo` | Team 1 Elo rating before the match |
| `team2_elo` | Team 2 Elo rating before the match |
| `elo_diff` | team1_elo - team2_elo |

**Elo implementation details:**
- Starting Elo: 1500 for all teams
- K-factor: 32 (standard), with margin-of-victory multiplier
- MoV multiplier: `ln(abs(round_diff) + 1)` — a 13-5 stomp shifts Elo more than a 13-11 nailbiter
- Inactivity decay: if a team hasn't played in 60+ days, decay Elo toward 1500 by 2% per additional week
- Process maps chronologically by match date, then map_number within a match

#### 2. Rolling team performance (last N maps)

Compute for N = 10, 20 (two horizons: recent form vs. medium-term).

| Feature | Description |
|---------|-------------|
| `team{1,2}_avg_rating_{N}` | Mean player rating across last N maps |
| `team{1,2}_avg_acs_{N}` | Mean ACS |
| `team{1,2}_avg_kast_{N}` | Mean KAST% |
| `team{1,2}_avg_adr_{N}` | Mean ADR |
| `team{1,2}_fk_rate_{N}` | First kills per map |
| `team{1,2}_fd_rate_{N}` | First deaths per map |
| `team{1,2}_win_rate_{N}` | Map win rate |

Plus differentials: `rating_diff_10`, `rating_diff_20`, `acs_diff_10`, etc.

#### 3. Map-specific performance

| Feature | Description |
|---------|-------------|
| `team{1,2}_map_win_rate` | Win rate on the specific map (last 20 maps on that map) |
| `team{1,2}_map_games_played` | How many times they've played this map recently |
| `map_win_rate_diff` | Difference in map-specific win rates |

#### 4. Head-to-head

| Feature | Description |
|---------|-------------|
| `h2h_team1_win_rate` | Team 1 win rate vs. Team 2 (all-time or last N encounters) |
| `h2h_maps_played` | Total maps played between these two teams |

#### 5. Recency and form

| Feature | Description |
|---------|-------------|
| `team{1,2}_days_since_last` | Days since last map played |
| `team{1,2}_streak` | Current win/loss streak (capped at ±5) |
| `team{1,2}_recent_momentum` | Win rate in last 5 maps minus last 20 maps |

#### 6. Roster stability

| Feature | Description |
|---------|-------------|
| `team{1,2}_roster_overlap` | Fraction of current 5 players who also played in the team's last 10 maps (0.0-1.0) |

How to compute: for a given team before a match, look at the 5 players in their most recent map. Then check how many of those 5 appeared in each of the team's previous 10 maps. Average overlap ratio.

#### 7. Agent composition (optional, stretch)

| Feature | Description |
|---------|-------------|
| `team{1,2}_duelist_count` | Number of duelist agents in their recent comps |
| `team{1,2}_controller_count` | Number of controllers |

This is lower priority since agent meta shifts frequently, but the data is there.

### Handling cold-start

Teams with < 10 maps of history get imputed features:
- Rolling stats: use whatever history exists, or global median if < 3 maps
- Elo: starts at 1500 (naturally handles cold-start)
- Map-specific: fall back to overall win rate if < 3 maps on that map

---

## Model Training

### Temporal cross-validation (walk-forward)

No random train/test splits. The data is time-ordered.

```
Fold 1: Train on months 1-6,  validate on month 7
Fold 2: Train on months 1-7,  validate on month 8
Fold 3: Train on months 1-8,  validate on month 9
...
Final:  Train on months 1-11, validate on month 12
Test:   Train on all data except last month, test on last month
```

### Metrics

- **Log-loss** (primary): measures calibration of probabilities
- **Brier score**: similar to log-loss, common in prediction markets
- **Accuracy**: secondary, for interpretability
- **Calibration curve**: plot predicted probability vs. actual win rate in bins

### Baseline comparison

1. **Coin flip**: 50% accuracy, 0.693 log-loss
2. **Elo-only**: logistic function of Elo difference
3. **Full model**: XGBoost with all features

The gap between Elo-only and the full model is the value-add of the feature engineering.

### Model artifacts

Save to `models/` directory:
- `model.joblib` — trained XGBoost model
- `feature_config.json` — feature names, order, imputation values
- `training_metadata.json` — date range, fold metrics, feature importances

---

## API Endpoints

### Predictions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/predictions/upcoming` | Predictions for upcoming matches |
| `POST` | `/api/predict` | Ad-hoc prediction: `{team1, team2, map_name}` |
| `GET` | `/api/predictions/history` | Past predictions with accuracy |

### Teams

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/teams` | List all teams (searchable) |
| `GET` | `/api/teams/{id}` | Team profile: Elo history, recent form, map pool |
| `GET` | `/api/teams/{id}/players` | Current and historical roster |

### Matches

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/matches` | Recent match results (paginated) |
| `GET` | `/api/matches/{id}` | Match detail with map scores and stats |

### Model

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/model/accuracy` | Rolling accuracy metrics over time |
| `GET` | `/api/model/features` | Feature importance rankings |

---

## Dashboard Pages (Next.js)

### 1. Home / Upcoming predictions
- Cards for each upcoming match with win probability bars
- Sortable by date, confidence level
- Click into match detail

### 2. Team profile
- Elo rating chart over time (like the VLR screenshot)
- Recent results table
- Map pool heatmap (win rate per map)
- Current roster with individual rolling stats

### 3. Head-to-head comparison
- Select two teams
- Side-by-side stats comparison
- Historical matchup record
- Model prediction for a hypothetical match

### 4. Model performance
- Calibration curve
- Rolling accuracy over time
- Feature importance bar chart
- Prediction log with correct/incorrect

### 5. Match detail
- Map-by-map breakdown
- Pre-match prediction vs. actual result
- Key stat differentials that drove the prediction

---

## Docker Compose Services

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: vlr_predict
      POSTGRES_USER: vlr
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  api:
    build: ./api
    depends_on: [db]
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://vlr:${DB_PASSWORD}@db/vlr_predict

  frontend:
    build: ./frontend
    depends_on: [api]
    ports: ["3000:3000"]

  worker:
    build: ./api
    command: python -m app.scheduler
    depends_on: [db]
```

---

## Project Structure

```
vlr-predict/
├── api/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── config.py            # Settings (DB URL, model path)
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── team.py
│   │   │   ├── player.py
│   │   │   ├── match.py
│   │   │   ├── map.py
│   │   │   ├── player_map_stat.py
│   │   │   ├── team_elo.py
│   │   │   └── prediction.py
│   │   ├── routers/             # API route handlers
│   │   │   ├── predictions.py
│   │   │   ├── teams.py
│   │   │   ├── matches.py
│   │   │   └── model.py
│   │   ├── services/            # Business logic
│   │   │   ├── elo.py           # Elo computation engine
│   │   │   ├── features.py      # Feature engineering pipeline
│   │   │   ├── predictor.py     # Model inference
│   │   │   └── scraper.py       # VLR scraping (adapted from vlr-scraper)
│   │   ├── ml/                  # Training scripts
│   │   │   ├── train.py         # Walk-forward training
│   │   │   ├── evaluate.py      # Metrics and calibration
│   │   │   └── feature_importance.py
│   │   └── scheduler.py         # APScheduler: scrape + retrain
│   ├── alembic/                 # DB migrations
│   ├── tests/
│   │   ├── test_elo.py
│   │   ├── test_features.py
│   │   └── test_predictions.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js app router
│   │   │   ├── page.tsx         # Home (upcoming predictions)
│   │   │   ├── teams/
│   │   │   │   └── [id]/page.tsx
│   │   │   ├── compare/page.tsx
│   │   │   ├── model/page.tsx
│   │   │   └── matches/
│   │   │       └── [id]/page.tsx
│   │   ├── components/
│   │   │   ├── PredictionCard.tsx
│   │   │   ├── EloChart.tsx
│   │   │   ├── MapPoolHeatmap.tsx
│   │   │   ├── CalibrationCurve.tsx
│   │   │   └── FeatureImportance.tsx
│   │   └── lib/
│   │       └── api.ts           # API client
│   ├── Dockerfile
│   └── package.json
├── models/                      # Trained model artifacts
├── docker-compose.yml
└── README.md
```

---

## Week-by-Week Plan

### Week 1: Data layer + Elo + feature pipeline

- [ ] Set up repo, Docker Compose with Postgres
- [ ] Define SQLAlchemy models + Alembic migrations
- [ ] Write CSV→Postgres import script (from existing scraped data)
- [ ] Implement Elo engine with MoV adjustment
- [ ] Build `compute_features()` function with all feature categories
- [ ] Write tests for Elo and feature correctness (especially temporal isolation)

### Week 2: Model training + FastAPI

- [ ] Implement walk-forward cross-validation
- [ ] Train XGBoost, compare to Elo-only baseline
- [ ] Generate calibration curves and feature importance
- [ ] Build FastAPI app with all endpoints
- [ ] Serve predictions through the API
- [ ] Write API tests

### Week 3: Dashboard + scheduler

- [ ] Set up Next.js project with TypeScript
- [ ] Build home page (upcoming predictions)
- [ ] Build team profile page with Elo chart
- [ ] Build head-to-head comparison page
- [ ] Build model performance page
- [ ] Integrate APScheduler for periodic scraping

### Week 4: Polish + deploy

- [ ] Dockerize everything end-to-end
- [ ] Deploy (Railway, Fly.io, or VPS)
- [ ] Write README with architecture diagram
- [ ] Add comprehensive tests for feature pipeline
- [ ] Performance optimization (feature caching, DB indexes)
- [ ] Final UI polish
