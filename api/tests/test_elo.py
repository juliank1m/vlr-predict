"""Tests for the Elo engine."""

from datetime import datetime, timedelta

import pytest

from app.services.elo import EloEngine


@pytest.fixture
def engine() -> EloEngine:
    return EloEngine(k_factor=32.0, start_elo=1500.0, decay_days=60, decay_rate=0.02)


class TestEloBasics:
    def test_new_team_gets_start_elo(self, engine: EloEngine):
        assert engine.get_elo(1) == 1500.0

    def test_expected_score_equal_teams(self, engine: EloEngine):
        score = engine.expected_score(1500.0, 1500.0)
        assert score == pytest.approx(0.5)

    def test_expected_score_higher_rated_favored(self, engine: EloEngine):
        score = engine.expected_score(1600.0, 1400.0)
        assert score > 0.5
        # 200 point gap should give roughly 76% expected
        assert score == pytest.approx(0.76, abs=0.01)

    def test_expected_scores_sum_to_one(self, engine: EloEngine):
        s1 = engine.expected_score(1600.0, 1400.0)
        s2 = engine.expected_score(1400.0, 1600.0)
        assert s1 + s2 == pytest.approx(1.0)


class TestMarginOfVictory:
    def test_stomp_has_higher_multiplier(self, engine: EloEngine):
        stomp = engine.margin_of_victory_multiplier(8)  # 13-5
        close = engine.margin_of_victory_multiplier(2)  # 13-11
        assert stomp > close

    def test_zero_diff_gives_zero_multiplier(self, engine: EloEngine):
        # ln(0 + 1) = ln(1) = 0
        assert engine.margin_of_victory_multiplier(0) == 0.0

    def test_one_round_diff(self, engine: EloEngine):
        # ln(1 + 1) = ln(2) ≈ 0.693
        assert engine.margin_of_victory_multiplier(1) == pytest.approx(0.693, abs=0.01)


class TestUpdate:
    def test_winner_gains_loser_loses(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        u1, u2 = engine.update(1, 2, 13, 9, now)

        assert u1.delta > 0  # Winner gained
        assert u2.delta < 0  # Loser lost
        assert u1.delta == pytest.approx(-u2.delta)  # Zero-sum

    def test_equal_teams_winner_gains_expected_amount(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        u1, u2 = engine.update(1, 2, 13, 9, now)

        # Equal teams: expected = 0.5, actual = 1.0 for winner
        # K * MoV * (1.0 - 0.5) = 32 * ln(5) * 0.5 ≈ 25.7
        assert u1.delta == pytest.approx(25.7, abs=1.0)

    def test_upset_gives_bigger_shift(self, engine: EloEngine):
        """A lower-rated team beating a higher-rated team should shift more."""
        now = datetime(2025, 1, 1)
        engine.ratings[1] = 1400.0
        engine.ratings[2] = 1600.0

        u1, u2 = engine.update(1, 2, 13, 9, now)

        # Team 1 was the underdog and won, should gain more than a fair match
        fair_engine = EloEngine()
        fair_u1, _ = fair_engine.update(1, 2, 13, 9, now)

        assert u1.delta > fair_u1.delta

    def test_stomp_shifts_more_than_close_game(self, engine: EloEngine):
        now = datetime(2025, 1, 1)

        stomp_engine = EloEngine()
        stomp_u1, _ = stomp_engine.update(1, 2, 13, 5, now)

        close_engine = EloEngine()
        close_u1, _ = close_engine.update(1, 2, 13, 11, now)

        assert abs(stomp_u1.delta) > abs(close_u1.delta)

    def test_sequential_updates_accumulate(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        engine.update(1, 2, 13, 9, now)
        engine.update(1, 2, 13, 9, now)

        assert engine.get_elo(1) > 1500.0
        assert engine.get_elo(2) < 1500.0


class TestDecay:
    def test_no_decay_within_threshold(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        engine.update(1, 2, 13, 9, now)
        elo_after_match = engine.get_elo(1)

        # 30 days later, within threshold
        later = now + timedelta(days=30)
        decayed = engine.apply_decay(1, later)
        assert decayed == elo_after_match

    def test_decay_after_threshold(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        engine.update(1, 2, 13, 9, now)
        elo_after_match = engine.get_elo(1)

        # 90 days later, past threshold
        later = now + timedelta(days=90)
        decayed = engine.apply_decay(1, later)

        # Should be closer to 1500 than the post-match elo
        assert abs(decayed - 1500.0) < abs(elo_after_match - 1500.0)

    def test_heavy_decay_approaches_start(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        engine.ratings[1] = 1800.0
        engine.last_played[1] = now

        # 1 year of inactivity
        much_later = now + timedelta(days=365)
        decayed = engine.apply_decay(1, much_later)

        # Should be meaningfully closer to 1500 than 1800
        assert abs(decayed - 1500.0) < abs(1800.0 - 1500.0)

    def test_decay_applied_before_update(self, engine: EloEngine):
        now = datetime(2025, 1, 1)
        engine.ratings[1] = 1800.0
        engine.last_played[1] = now

        much_later = now + timedelta(days=120)
        u1, _ = engine.update(1, 2, 13, 9, much_later)

        # The old_elo should reflect decay, not the raw 1800
        assert u1.old_elo < 1800.0
