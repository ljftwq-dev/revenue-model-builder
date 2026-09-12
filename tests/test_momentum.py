"""Tests for revenue_model.momentum — the v0.21a quarterly layer."""

from revenue_model.momentum import MomentumReading, detect_momentum, ttm_series


class TestTtmSeries:
    def test_rolling_four(self):
        assert ttm_series([10.0, 11.0, 12.0, 13.0, 14.0]) == [46.0, 50.0]

    def test_gap_poisons_window(self):
        # a zero/negative quarter kills only the windows that contain it
        assert ttm_series([10.0, 11.0, 12.0, 13.0, 0.0, 14.0]) == [46.0]


class TestDetectMomentum:
    def test_accelerating(self):
        # back half compounds faster than the front half
        revs = [10.0, 11.0, 12.0, 13.0, 14.0, 16.0, 19.5, 24.0, 30.0]
        m = detect_momentum(revs)
        assert m.state == "accelerating"
        assert m.recent_yoy > m.prior_yoy
        assert "UNDERSTATES" in m.evidence

    def test_decelerating(self):
        revs = [10.0, 12.0, 14.0, 16.0, 16.0, 16.0, 16.0, 16.0, 16.0]
        m = detect_momentum(revs)
        assert m.state == "decelerating"
        assert "OVERSTATES" in m.evidence

    def test_steady(self):
        m = detect_momentum([10.0] * 9)
        assert m.state == "steady"

    def test_insufficient_below_nine_quarters(self):
        m = detect_momentum([10.0] * 8)
        assert m.state == "insufficient"
        assert m.recent_yoy is None
        assert "refuse to guess" in m.evidence

    def test_reading_is_frozen_dataclass(self):
        m = detect_momentum([10.0] * 9)
        assert isinstance(m, MomentumReading)
