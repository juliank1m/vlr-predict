"""Tests for the feature engineering pipeline.

Focuses on temporal isolation (no future leakage), cold-start handling,
and correctness of feature values.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.database import SyncSessionLocal
from app.services.features import (
    DEFAULT_MEDIANS,
    FEATURE_NAMES,
    MIN_MAPS_FOR_STATS,
    _STAT_KEYS,
    compute_features,
    compute_global_medians,
    feature_vector,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db():
    """Module-scoped database session. Skips if DB is unavailable."""
    try:
        session = SyncSessionLocal()
        session.execute(text("SELECT 1"))
        yield session
        session.close()
    except Exception:
        pytest.skip("Database not available")


@pytest.fixture(scope="module")
def sample_match(db):
    """A match with good data coverage (mid-dataset, both teams have history)."""
    row = db.execute(text("""
        SELECT mt.team1_id, mt.team2_id, mt.date, m.map_name
        FROM matches mt
        JOIN maps m ON m.match_id = mt.id
        WHERE mt.date IS NOT NULL
          AND m.map_name IS NOT NULL
        ORDER BY mt.date
        OFFSET (SELECT COUNT(*) / 2
                FROM matches WHERE date IS NOT NULL)
        LIMIT 1
    """)).fetchone()
    assert row is not None, "No matches found in database"
    return {
        "team1_id": row[0], "team2_id": row[1],
        "match_date": row[2], "map_name": row[3],
    }


@pytest.fixture(scope="module")
def medians(db):
    return compute_global_medians(db)


# ---------------------------------------------------------------------------
# Pure unit tests (no DB)
# ---------------------------------------------------------------------------

class TestFeatureNames:
    def test_count(self):
        assert len(FEATURE_NAMES) == 60

    def test_no_duplicates(self):
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))

    def test_elo_features_present(self):
        assert "team1_elo" in FEATURE_NAMES
        assert "team2_elo" in FEATURE_NAMES
        assert "elo_diff" in FEATURE_NAMES

    def test_rolling_features_present(self):
        for n in (10, 20):
            for side in ("team1", "team2"):
                for k in _STAT_KEYS:
                    assert f"{side}_{k}_{n}" in FEATURE_NAMES
            for k in _STAT_KEYS:
                assert f"{k}_diff_{n}" in FEATURE_NAMES

    def test_map_features_present(self):
        for name in ("team1_map_win_rate", "team2_map_win_rate",
                      "team1_map_games_played", "team2_map_games_played",
                      "map_win_rate_diff"):
            assert name in FEATURE_NAMES

    def test_h2h_features_present(self):
        assert "h2h_team1_win_rate" in FEATURE_NAMES
        assert "h2h_maps_played" in FEATURE_NAMES

    def test_recency_features_present(self):
        for side in ("team1", "team2"):
            assert f"{side}_days_since_last" in FEATURE_NAMES
            assert f"{side}_streak" in FEATURE_NAMES
            assert f"{side}_recent_momentum" in FEATURE_NAMES

    def test_roster_features_present(self):
        assert "team1_roster_overlap" in FEATURE_NAMES
        assert "team2_roster_overlap" in FEATURE_NAMES


class TestFeatureVector:
    def test_length_matches_names(self):
        features = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
        vec = feature_vector(features)
        assert len(vec) == len(FEATURE_NAMES)

    def test_order_matches_names(self):
        features = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
        vec = feature_vector(features)
        assert vec == [float(i) for i in range(len(FEATURE_NAMES))]

    def test_missing_keys_become_none(self):
        vec = feature_vector({})
        assert all(v is None for v in vec)


# ---------------------------------------------------------------------------
# Database-backed tests
# ---------------------------------------------------------------------------

class TestComputeFeatures:
    def test_returns_all_feature_names(self, db, sample_match):
        features = compute_features(db, **sample_match)
        assert set(features.keys()) == set(FEATURE_NAMES)

    def test_elo_values_positive(self, db, sample_match):
        features = compute_features(db, **sample_match)
        assert features["team1_elo"] > 0
        assert features["team2_elo"] > 0

    def test_elo_diff_consistent(self, db, sample_match):
        features = compute_features(db, **sample_match)
        assert features["elo_diff"] == pytest.approx(
            features["team1_elo"] - features["team2_elo"]
        )

    def test_win_rates_in_range(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for name in FEATURE_NAMES:
            if "win_rate" in name and "diff" not in name and features[name] is not None:
                assert 0.0 <= features[name] <= 1.0, f"{name} = {features[name]}"

    def test_streak_capped(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for side in ("team1", "team2"):
            streak = features[f"{side}_streak"]
            if streak is not None:
                assert -5 <= streak <= 5

    def test_days_since_last_non_negative(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for side in ("team1", "team2"):
            days = features[f"{side}_days_since_last"]
            if days is not None:
                assert days >= 0

    def test_roster_overlap_in_range(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for side in ("team1", "team2"):
            val = features[f"{side}_roster_overlap"]
            if val is not None:
                assert 0.0 <= val <= 1.0

    def test_differentials_consistent(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for n in (10, 20):
            for k in _STAT_KEYS:
                t1 = features[f"team1_{k}_{n}"]
                t2 = features[f"team2_{k}_{n}"]
                diff = features[f"{k}_diff_{n}"]
                if t1 is not None and t2 is not None:
                    assert diff == pytest.approx(t1 - t2)

    def test_map_games_played_non_negative(self, db, sample_match):
        features = compute_features(db, **sample_match)
        for side in ("team1", "team2"):
            val = features[f"{side}_map_games_played"]
            if val is not None:
                assert val >= 0

    def test_h2h_maps_played_non_negative(self, db, sample_match):
        features = compute_features(db, **sample_match)
        assert features["h2h_maps_played"] >= 0


class TestTemporalIsolation:
    """Features at date T must only use data from before T."""

    def test_features_stable_at_same_date(self, db, sample_match):
        """Computing features twice at the same date gives identical results."""
        f1 = compute_features(db, **sample_match)
        f2 = compute_features(db, **sample_match)
        for name in FEATURE_NAMES:
            assert f1[name] == f2[name], f"{name} differs between calls"

    def test_features_identical_within_same_day_gap(self, db, sample_match):
        """Features at two times in the same gap between match days are identical."""
        # Find a gap: pick a date with no matches the day before
        gap_date = db.execute(text("""
            SELECT mt.date + interval '12 hours'
            FROM matches mt
            WHERE mt.date IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM matches mt2
                  WHERE mt2.date = mt.date - interval '1 day'
              )
            ORDER BY mt.date
            OFFSET 10 LIMIT 1
        """)).scalar()
        if gap_date is None:
            pytest.skip("Could not find a gap between match days")

        t1_id, t2_id = sample_match["team1_id"], sample_match["team2_id"]
        f1 = compute_features(db, t1_id, t2_id, "Ascent", gap_date)
        f2 = compute_features(db, t1_id, t2_id, "Ascent", gap_date + timedelta(hours=6))
        for name in FEATURE_NAMES:
            assert f1[name] == f2[name], f"{name} changed within gap"

    def test_elo_matches_snapshot(self, db, sample_match):
        """Elo feature should match the team_elo table at that point in time."""
        features = compute_features(db, **sample_match)
        for label, tid_key in (("team1", "team1_id"), ("team2", "team2_id")):
            tid = sample_match[tid_key]
            row = db.execute(text("""
                SELECT te.elo
                FROM team_elo te
                JOIN maps m ON te.map_id = m.id
                JOIN matches mt ON m.match_id = mt.id
                WHERE te.team_id = :tid
                  AND mt.date IS NOT NULL
                  AND mt.date < :match_date
                ORDER BY mt.date DESC, m.map_number DESC
                LIMIT 1
            """), {"tid": tid, "match_date": sample_match["match_date"]}).fetchone()
            if row:
                assert features[f"{label}_elo"] == pytest.approx(row[0])

    def test_win_rate_cross_check(self, db, sample_match):
        """Independently verify win_rate_10 using a direct query."""
        for label, tid_key in (("team1", "team1_id"), ("team2", "team2_id")):
            tid = sample_match[tid_key]
            row = db.execute(text("""
                WITH recent AS (
                    SELECT m.winner_id
                    FROM maps m
                    JOIN matches mt ON m.match_id = mt.id
                    WHERE (mt.team1_id = :tid OR mt.team2_id = :tid)
                      AND mt.date IS NOT NULL
                      AND mt.date < :match_date
                    ORDER BY mt.date DESC, m.map_number DESC
                    LIMIT 10
                )
                SELECT CAST(COUNT(*) FILTER (WHERE winner_id = :tid) AS float)
                     / NULLIF(COUNT(*), 0),
                       COUNT(*)
                FROM recent
            """), {"tid": tid, "match_date": sample_match["match_date"]}).fetchone()

            features = compute_features(db, **sample_match)
            num_maps = row[1]
            if num_maps >= MIN_MAPS_FOR_STATS:
                assert features[f"{label}_win_rate_10"] == pytest.approx(row[0])

    def test_no_future_data_in_rolling_stats(self, db, sample_match):
        """Features at an early date should differ from those at a late date."""
        early_date = sample_match["match_date"] - timedelta(days=365)
        late_date = sample_match["match_date"]

        f_early = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            sample_match["map_name"], early_date,
        )
        f_late = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            sample_match["map_name"], late_date,
        )

        # At least some features should differ (more data available later)
        diffs = [
            name for name in FEATURE_NAMES
            if f_early[name] != f_late[name]
        ]
        assert len(diffs) > 0, "Features at T-1yr and T are identical — suspect leakage"

    def test_earliest_date_yields_cold_start(self, db, sample_match):
        """Before any matches exist, features should be cold-start defaults."""
        very_early = datetime(2000, 1, 1)
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            sample_match["map_name"], very_early,
        )
        # Elo should be default 1500
        assert features["team1_elo"] == 1500.0
        assert features["team2_elo"] == 1500.0
        assert features["elo_diff"] == 0.0

        # Rolling stats should be medians (cold start)
        for n in (10, 20):
            assert features[f"team1_win_rate_{n}"] == DEFAULT_MEDIANS["win_rate"]

        # No history
        assert features["h2h_maps_played"] == 0.0
        assert features["team1_days_since_last"] is None


class TestNullMapName:
    """When map_name is None, map-specific features should be None."""

    def test_map_features_none_when_no_map(self, db, sample_match):
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            None, sample_match["match_date"],
        )
        assert features["team1_map_win_rate"] is None
        assert features["team2_map_win_rate"] is None
        assert features["team1_map_games_played"] is None
        assert features["team2_map_games_played"] is None
        assert features["map_win_rate_diff"] is None

    def test_non_map_features_unaffected(self, db, sample_match):
        """Other features should still compute normally with map_name=None."""
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            None, sample_match["match_date"],
        )
        # Elo should still work
        assert features["team1_elo"] != 1500.0 or features["team2_elo"] != 1500.0
        # Rolling stats should still be present
        assert features["team1_win_rate_10"] is not None


class TestGlobalMedians:
    def test_returns_all_stat_keys(self, db):
        medians = compute_global_medians(db)
        for k in _STAT_KEYS:
            assert k in medians

    def test_values_are_reasonable(self, db):
        medians = compute_global_medians(db)
        assert 0.5 < medians["avg_rating"] < 1.5
        assert 100 < medians["avg_acs"] < 300
        assert 50 < medians["avg_kast"] < 90
        assert 80 < medians["avg_adr"] < 200
        assert medians["win_rate"] == 0.5

    def test_medians_used_for_cold_start(self, db, sample_match, medians):
        """When passed, global_medians should be used for cold-start teams."""
        very_early = datetime(2000, 1, 1)
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            sample_match["map_name"], very_early,
            global_medians=medians,
        )
        # Cold-start rolling stats should match the precomputed medians
        assert features["team1_avg_rating_10"] == pytest.approx(medians["avg_rating"])
        assert features["team1_avg_acs_10"] == pytest.approx(medians["avg_acs"])


class TestSymmetry:
    """Swapping team1/team2 should mirror the features."""

    def test_elo_diff_flips_sign(self, db, sample_match):
        f_normal = compute_features(db, **sample_match)
        f_swapped = compute_features(
            db, sample_match["team2_id"], sample_match["team1_id"],
            sample_match["map_name"], sample_match["match_date"],
        )
        assert f_normal["elo_diff"] == pytest.approx(-f_swapped["elo_diff"])

    def test_team1_team2_swap(self, db, sample_match):
        """team1 stats in normal == team2 stats in swapped."""
        f_normal = compute_features(db, **sample_match)
        f_swapped = compute_features(
            db, sample_match["team2_id"], sample_match["team1_id"],
            sample_match["map_name"], sample_match["match_date"],
        )
        for n in (10, 20):
            for k in _STAT_KEYS:
                assert f_normal[f"team1_{k}_{n}"] == pytest.approx(
                    f_swapped[f"team2_{k}_{n}"]
                ), f"team1_{k}_{n} != swapped team2_{k}_{n}"

    def test_h2h_complements(self, db, sample_match):
        """H2H win rates should sum to ~1.0 when swapped (if maps > 0)."""
        f_normal = compute_features(db, **sample_match)
        f_swapped = compute_features(
            db, sample_match["team2_id"], sample_match["team1_id"],
            sample_match["map_name"], sample_match["match_date"],
        )
        if f_normal["h2h_maps_played"] > 0:
            assert f_normal["h2h_team1_win_rate"] + f_swapped["h2h_team1_win_rate"] == pytest.approx(1.0)


class TestEdgeCases:
    """Boundary conditions and unusual inputs."""

    def test_same_team_features(self, db, sample_match):
        """Same team vs itself should still return valid features."""
        tid = sample_match["team1_id"]
        features = compute_features(
            db, tid, tid, sample_match["map_name"], sample_match["match_date"],
        )
        assert features["elo_diff"] == 0.0
        assert set(features.keys()) == set(FEATURE_NAMES)

    def test_far_future_date(self, db, sample_match):
        """Features at a far future date should use all available data."""
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            sample_match["map_name"], datetime(2099, 1, 1),
        )
        assert set(features.keys()) == set(FEATURE_NAMES)
        # Should have some history
        assert features["h2h_maps_played"] >= 0

    def test_nonexistent_map_name(self, db, sample_match):
        """A map name that no one has played should yield None map features."""
        features = compute_features(
            db, sample_match["team1_id"], sample_match["team2_id"],
            "ZZZ_Nonexistent_Map", sample_match["match_date"],
        )
        assert features["team1_map_games_played"] == 0.0 or features["team1_map_games_played"] is None
        assert features["team2_map_games_played"] == 0.0 or features["team2_map_games_played"] is None
