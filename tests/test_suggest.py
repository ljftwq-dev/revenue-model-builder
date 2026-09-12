"""Tests for revenue_model.suggest — profile auto-recommendation (v0.19)."""

from revenue_model import Driver, Segment, BASE, PENETRATION, SHARE, PRICE
from revenue_model.suggest import ProfileSuggestion, suggest_profile

Y = list(range(2018, 2026))


def _mk(base, pen, share, price):
    return Segment(
        "t", industry="",
        base=Driver("b", BASE, base),
        penetration=Driver("p", PENETRATION, pen),
        share=Driver("s", SHARE, share),
        price=Driver("r", PRICE, price),
    )


def _flat(v):
    return {y: v for y in Y}


LINEAR = dict(zip(Y, [100, 112, 119, 133, 138, 152, 161, 172]))   # noisy trend
SCURVE = dict(zip(Y, [10, 14, 19, 25, 31, 37, 43, 48]))           # decelerating
ARPU = dict(zip(Y, [100, 103, 106, 110, 113, 117, 120, 124]))     # slow rise
HYPER = dict(zip(Y, [10, 12, 15, 21, 30, 43, 62, 90]))            # breakout


class TestSuggestProfile:
    def test_steady_trend_prefers_trend_profiles(self):
        seg = _mk(LINEAR, _flat(0.15), _flat(0.2), _flat(100.0))
        out = suggest_profile(seg)
        keys = [s.key for s in out]
        assert "semiconductor" in keys[:3]      # base trend + price hold

    def test_s_curve_and_band_favor_saas(self):
        seg = _mk(SCURVE, _flat(0.5), _flat(1.0), ARPU)
        out = suggest_profile(seg)
        saas = next(s for s in out if s.key == "saas_subscription")
        assert any("inside the industry band" in r for r in saas.reasons)
        assert any(r.startswith("base: default net_growth") for r in saas.reasons)

    def test_hypergrowth_pins_regime_shift_first(self):
        seg = _mk(HYPER, _flat(0.5), _flat(1.0), _flat(100.0))
        out = suggest_profile(seg)
        assert out[0].key == "regime_shift_tech"
        assert any("regime-shift territory" in r for r in out[0].reasons)

    def test_reasons_carry_battery_evidence(self):
        seg = _mk(LINEAR, _flat(0.15), _flat(0.2), _flat(100.0))
        out = suggest_profile(seg)
        assert out[0].reasons                       # evidence, not bare scores
        assert any("battery" in r for s in out for r in s.reasons)

    def test_top_k_respected(self):
        seg = _mk(LINEAR, _flat(0.15), _flat(0.2), _flat(100.0))
        assert len(suggest_profile(seg, top_k=1)) == 1
        assert len(suggest_profile(seg, top_k=5)) == 5

    def test_too_short_history_refuses_to_guess(self):
        short = {2019: 100.0, 2020: 110.0, 2021: 121.0}   # < 4 points
        seg = _mk(short, short, short, short)
        assert suggest_profile(seg) == []

    def test_suggestion_shape(self):
        seg = _mk(LINEAR, _flat(0.15), _flat(0.2), _flat(100.0))
        s = suggest_profile(seg)[0]
        assert isinstance(s, ProfileSuggestion)
        assert s.score > 0
        assert s.label()              # renders the profile's label
        scores = [x.score for x in suggest_profile(seg)]
        assert scores == sorted(scores, reverse=True)
