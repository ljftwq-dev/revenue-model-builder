"""Tests for revenue_model.damodaran_adapter — parse, bands, diff (no network)."""

import pytest

from revenue_model.damodaran_adapter import (
    CLUSTERS, HistgrRow, _quantile, cluster_bands, diff_bands, parse_histgr,
    _to_fraction,
)


MINI_HTML = """
<html><body><table>
<tr><td>Industry Name</td>
    <td>Number
\t        of Firms</td>
    <td>CAGR
\t        in Revenues- Last 5 years</td>
    <td>Expected Growth in Revenues - Next 2 years</td>
    <td>Unused column</td></tr>
<tr><td>Semiconductor</td><td>66</td><td>11.18%</td><td>40.91%</td><td>x</td></tr>
<tr><td>Semiconductor Equip</td><td>31</td><td>9.38%</td><td>11.97%</td><td>x</td></tr>
<tr><td>Retail (General)</td><td>24</td><td>9.92%</td><td>NA</td><td>x</td></tr>
<tr><td>Total Market</td><td>abc</td><td>7%</td><td>5%</td><td>x</td></tr>
</table></body></html>
"""


class TestParse:
    def test_mini_table(self):
        parsed = parse_histgr(MINI_HTML)
        row = parsed["Semiconductor"]
        assert row.n_firms == 66
        assert row.cagr_5y == pytest.approx(0.1118)
        assert row.exp_2y == pytest.approx(0.4091)
        assert parsed["Retail (General)"].exp_2y is None     # NA -> None
        assert "Total Market" not in parsed                  # bad firm count

    def test_to_fraction(self):
        assert _to_fraction("11.18%") == pytest.approx(0.1118)
        assert _to_fraction("0.5") == 0.5
        assert _to_fraction("") is None
        assert _to_fraction("NA") is None
        assert _to_fraction("junk") is None


class TestBands:
    def test_semiconductor_cluster(self):
        bands = cluster_bands({
            "Semiconductor": HistgrRow(66, 0.1118, 0.4091),
            "Semiconductor Equip": HistgrRow(31, 0.0938, 0.1197),
        })
        c5 = bands["semiconductor"]["revenue_cagr_5y"]
        assert c5[0] == pytest.approx(0.0983, abs=1e-4)
        assert c5[1] == pytest.approx(0.1028, abs=1e-4)
        assert c5[2] == pytest.approx(0.1073, abs=1e-4)
        assert c5[3] == 97

    def test_missing_industry_skipped(self):
        bands = cluster_bands({"Semiconductor": HistgrRow(66, 0.10, 0.20)})
        c5 = bands["semiconductor"]["revenue_cagr_5y"]
        assert c5[:3] == (0.10, 0.10, 0.10)          # single-industry band

    def test_all_real_clusters_covered_by_upstream_names(self):
        # every cluster key maps to a real registry profile (structure only;
        # upstream coverage itself is verified by the network verify run)
        from revenue_model.industry import INDUSTRY_PROFILES
        assert set(CLUSTERS) == {
            k for k in INDUSTRY_PROFILES
            if INDUSTRY_PROFILES[k].benchmarks}


class TestQuantile:
    def test_matches_linear_interpolation(self):
        assert _quantile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)
        assert _quantile([1.0, 2.0, 3.0, 4.0], 0.50) == pytest.approx(2.5)
        assert _quantile([5.0], 0.75) == 5.0


class TestDiff:
    _CL = {"semiconductor": ("Semiconductor", "Semiconductor Equip")}

    def _profile_stubs(self, p25, p50, p75):
        from revenue_model.industry import Benchmark

        class P:
            benchmarks = (
                Benchmark("revenue_cagr_5y", p25, p50, p75),)
        return {"semiconductor": P()}

    def _fresh(self, p25, p50, p75):
        return {"semiconductor":
                {"revenue_cagr_5y": (p25, p50, p75, 97)}}

    def test_match_silent(self):
        assert diff_bands(self._profile_stubs(0.0983, 0.1028, 0.1073),
                          self._fresh(0.0983, 0.1028, 0.1073),
                          clusters=self._CL) == []

    def test_drift_reported(self):
        out = diff_bands(self._profile_stubs(0.0983, 0.1028, 0.1073),
                         self._fresh(0.09, 0.10, 0.11),
                         clusters=self._CL)
        assert len(out) == 1 and "drift" in out[0]

    def test_missing_metric_reported(self):
        out = diff_bands(self._profile_stubs(0.0983, 0.1028, 0.1073),
                         {"semiconductor": {}},
                         clusters=self._CL)
        assert any("no value" in l for l in out)
