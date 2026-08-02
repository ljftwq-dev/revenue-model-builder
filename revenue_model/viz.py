"""Visualization helpers — matplotlib charts for revenue uncertainty & forecasts.

Optional dependency: matplotlib. Install via ``pip install -e ".[viz]"``.
This module is **not** imported by ``import revenue_model`` — import it
explicitly (``from revenue_model.viz import plot_tornado``) so the
zero-dependency core stays clean. If matplotlib is missing, a clear error names
the extra to install.

Four complementary views of one model's uncertainty, each returning a matplotlib
``Axes`` (pass ``ax=`` to embed in your own figure):

* :func:`plot_revenue_distribution` — *how uncertain is the number?*
  Monte Carlo histogram with P5/P25/median/P75/P95 markers and optional
  Bear/Base/Bull bands.
* :func:`plot_tornado` — *which assumption matters most?*
  Ranked horizontal bars around the base case (one-at-a-time sensitivity).
* :func:`plot_waterfall` — *how do the swings stack up?*
  Cumulative build from the base case as each driver is moved to its upside
  (or downside) — the classic "upside bridge".
* :func:`plot_forecast` — *how does revenue walk into the future?*
  Historical (solid) vs extrapolated (dashed) trajectory per segment.

Plus :func:`plot_dashboard` — a 2×2 panel combining all four for a single
segment / model, the fastest way to "see" a forecast.

Convention: revenue is plotted in **亿元 (100M yuan)** — divide the engine's
million-yuan output by 100 — which reads naturally for A-share names whose
revenue runs into the hundreds/thousands of 亿.
"""

# Lazy import: keep the zero-dependency core untouched. ``import revenue_model``
# never triggers this; only an explicit ``from revenue_model.viz import ...`` does.
try:
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
except ImportError as exc:  # pragma: no cover - exercised only without matplotlib
    raise ImportError(
        "revenue_model.viz requires matplotlib. "
        'Install it with:  pip install -e ".[viz]"'
    ) from exc

from typing import Dict, List, Optional, Sequence

from .model import RevenueModel
from .monte_carlo import MCResult, Scenario, SensitivityItem

# CJK glyph fallback so Chinese segment/driver names (e.g. 立讯's 消费电子) render
# instead of showing as tofu boxes. Prepended so they win, DejaVu kept as fallback.
_CJK_FONTS = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "PingFang SC"]
plt.rcParams["font.sans-serif"] = _CJK_FONTS + [
    f for f in plt.rcParams.get("font.sans-serif", []) if f not in _CJK_FONTS
]
plt.rcParams["axes.unicode_minus"] = False

_YI = 100.0  # million yuan -> 亿元 (100M yuan)

# A small, color-blind-friendly palette reused across the four charts.
_C_BASE = "#3b6ea8"      # base / neutral
_C_LOW = "#d9534f"       # downside / bear
_C_HIGH = "#4f9d69"      # upside / bull
_C_MEDIAN = "#1a1a1a"    # median emphasis
_C_BAND = "#a78bfa"      # distribution body
_C_DASH = "#8a8a8a"      # forecast dashed accent


def _ax_or_new(ax):
    return ax if ax is not None else plt.gca()


def _label_unit(ax, which: str) -> None:
    ax.set_ylabel("收入 (亿元)" if which == "y" else ax.get_ylabel())
    if which == "y":
        ax.set_ylabel("收入 (亿元)")
    else:
        ax.set_xlabel("收入 (亿元)")


def plot_revenue_distribution(
    mc: MCResult,
    *,
    ax=None,
    scenarios: Optional[Sequence[Scenario]] = None,
    bins: int = 50,
    title: Optional[str] = None,
):
    """Monte Carlo revenue histogram with percentile markers.

    Draws the empirical distribution from ``mc.samples``, overlays the P5/P25 /
    P75/P95 guides and a emphasized median line, and (if ``scenarios`` is given,
    e.g. the output of :func:`~revenue_model.scenarios`) shades/marks the
    Bear / Base / Bull cuts. Pass the ``scenarios`` returned by
    ``scenarios(mc)`` to label the three cases on the same axis.

    Revenue is shown in 亿元.
    """
    ax = _ax_or_new(ax)
    samples_yi = [s / _YI for s in mc.samples]
    ax.hist(samples_yi, bins=bins, color=_C_BAND, alpha=0.55,
            edgecolor="white", linewidth=0.4)

    pct_style = {"p5": (_C_LOW, "--"), "p25": (_C_DASH, ":"),
                 "p75": (_C_DASH, ":"), "p95": (_C_HIGH, "--")}
    for key, (color, ls) in pct_style.items():
        v = mc.percentiles[key] / _YI
        ax.axvline(v, color=color, linestyle=ls, linewidth=1.2, alpha=0.8)
        ax.text(v, ax.get_ylim()[1], f" {key.upper()}", color=color,
                fontsize=8, va="top", rotation=90)

    median_yi = mc.median / _YI
    ax.axvline(median_yi, color=_C_MEDIAN, linewidth=2.0)
    ax.text(median_yi, ax.get_ylim()[1], f" 中位数 {median_yi:.0f}",
            color=_C_MEDIAN, fontsize=9, fontweight="bold", va="top")

    if scenarios:
        name_color = {"Bear": _C_LOW, "Base": _C_MEDIAN, "Bull": _C_HIGH}
        for sc in scenarios:
            color = name_color.get(sc.name, _C_DASH)
            ax.axvline(sc.revenue / _YI, color=color, linewidth=1.6, alpha=0.5)
            ax.annotate(f"{sc.name}\n{sc.revenue / _YI:.0f}",
                        xy=(sc.revenue / _YI, 0), xycoords=("data", "axes fraction"),
                        xytext=(6, 4), textcoords="offset points",
                        color=color, fontsize=8)

    ax.set_xlabel("收入 (亿元)")
    ax.set_ylabel("频次")
    ax.set_title(title or f"收入分布 · 蒙特卡洛 n={mc.n:,} ({mc.year}年)")
    ax.spines[["top", "right"]].set_visible(False)
    return ax


def plot_tornado(
    items: Sequence[SensitivityItem],
    *,
    ax=None,
    title: Optional[str] = None,
):
    """Tornado (sensitivity) chart — ranked horizontal bars around the base case.

    ``items`` is the output of :func:`~revenue_model.tornado` (already ranked by
    swing). Each driver is drawn as a horizontal bar spanning its low→high
    revenue, centered visually on the base case (marked with a vertical line).
    The longer the bar, the more that single assumption swings the forecast —
    the chart that answers *"if I had one day to research one driver, which?"*.

    Revenue is shown in 亿元.
    """
    ax = _ax_or_new(ax)
    ranked = sorted(items, key=lambda i: i.swing)  # smallest at bottom for barh
    labels = [f"{i.driver}\n[{i.segment}]" if _multi_segment(items) else i.driver
              for i in ranked]
    pos = list(range(len(ranked)))

    for y, it in zip(pos, ranked):
        lo, base, hi = it.low_revenue / _YI, it.base_revenue / _YI, it.high_revenue / _YI
        ax.barh(y, hi - lo, left=lo, height=0.6,
                color=_C_BAND, alpha=0.45, edgecolor=_C_BASE, linewidth=0.6)
        ax.plot([lo, hi], [y, y], color=_C_BASE, linewidth=2.4, solid_capstyle="butt")
        ax.scatter([lo, hi], [y, y], color=[_C_LOW, _C_HIGH], zorder=5, s=22)

    base_yi = ranked[-1].base_revenue / _YI if ranked else 0.0
    ax.axvline(base_yi, color=_C_MEDIAN, linewidth=1.4, linestyle="--", alpha=0.7)
    ax.text(base_yi, len(ranked) - 0.4, f" 基准 {base_yi:.0f}", color=_C_MEDIAN,
            fontsize=8, va="top")

    ax.set_yticks(pos, labels, fontsize=9)
    ax.set_xlabel("收入 (亿元)")
    ax.set_title(title or "敏感度龙卷风图（单 driver 摆动，按影响排序）")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    return ax


def plot_waterfall(
    items: Sequence[SensitivityItem],
    *,
    ax=None,
    direction: str = "high",
    title: Optional[str] = None,
):
    """Waterfall / "upside bridge" — how each driver's swing accumulates.

    Starts at the base case, then cumulatively adds each driver's move (to its
    ``high`` by default, or ``low`` for a downside bridge), ranked largest-swing
    first, ending at the all-moved total. Floating green/red bars show each
    driver's contribution; solid neutral bars anchor the start and end.

    Note: revenue is a *product* of drivers, so summing single-driver moves is
    an additive approximation — this chart is a communication device ("where
    could upside come from, and how much"), not an exact decomposition.

    Revenue is shown in 亿元.
    """
    ax = _ax_or_new(ax)
    if direction not in ("high", "low"):
        raise ValueError(f"direction must be 'high' or 'low', got {direction!r}")
    ranked = sorted(items, key=lambda i: i.swing, reverse=True)
    base = ranked[0].base_revenue if ranked else 0.0
    deltas = [(it.high_revenue if direction == "high" else it.low_revenue) - it.base_revenue
              for it in ranked]

    labels = ["基准"] + [it.driver for it in ranked] + ["合计"]
    totals = [base, *(base + sum(deltas[:k + 1]) for k in range(len(deltas))),
              base + sum(deltas)]

    n = len(labels)
    # Build floating bars: bottom + height per column.
    bottoms, heights, colors = [], [], []
    for k in range(n):
        if k == 0 or k == n - 1:        # anchor bars span from 0
            bottoms.append(0.0)
            heights.append(totals[k])
            colors.append(_C_BASE)
        else:
            d = deltas[k - 1]
            prev = totals[k - 1]
            bottoms.append(min(prev, prev + d))
            heights.append(abs(d))
            colors.append(_C_HIGH if d >= 0 else _C_LOW)

    xs = list(range(n))
    ax.bar(xs, [h / _YI for h in heights], bottom=[b / _YI for b in bottoms],
           width=0.62, color=colors, alpha=0.82, edgecolor="white", linewidth=0.5)

    # Connectors: dashed line from each bar's top to the next bar's bottom.
    for k in range(n - 1):
        top_yi = totals[k] / _YI
        ax.plot([k + 0.31, k + 1 - 0.31], [top_yi, top_yi],
                color=_C_DASH, linestyle=":", linewidth=1)
        ax.text(k, top_yi + max(heights) / _YI * 0.02, f"{top_yi:.0f}",
                ha="center", fontsize=8, color=_C_MEDIAN)

    ax.text(n - 1, totals[-1] / _YI + max(heights) / _YI * 0.02,
            f"{totals[-1] / _YI:.0f}", ha="center", fontsize=9,
            color=_C_MEDIAN, fontweight="bold")

    ax.set_xticks(xs, labels, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("收入 (亿元)")
    arrow = "↗ 上行" if direction == "high" else "↘ 下行"
    ax.set_title(title or f"瀑布图 · 基准→逐 driver {arrow}累积（近似）")
    ax.spines[["top", "right"]].set_visible(False)
    return ax


def plot_forecast(
    model: RevenueModel,
    *,
    forecast_years: Optional[Sequence[int]] = None,
    ax=None,
    show_total: bool = True,
    title: Optional[str] = None,
):
    """Historical (solid) vs forecast (dashed) revenue trajectory per segment.

    Each segment is drawn as a solid line over its historical years and a
    *same-color* dashed line over the forecast years — the two connect at the
    boundary, so one segment's history and future read as a single
    color-coded story (rather than all forecast lines collapsing into one gray
    mush). When ``show_total`` is set and the model carries reported
    ``total_revenue``, a black line overlays it: solid + square markers for the
    reported history, dashed for the forecast (where total = Σ segment
    revenues, since there is no reported total to align to ahead of time and
    the residual line does not extend).

    Revenue is shown in 亿元.
    """
    ax = _ax_or_new(ax)
    all_years = sorted(set().union(*[seg.base.years() for seg in model.segments]))
    if not all_years:
        raise ValueError("model has no years to plot")
    fc = set(forecast_years) if forecast_years else set()
    palette = plt.rcParams["axes.prop_cycle"].by_key().get("color") or ["C0", "C1", "C2"]

    for i, seg in enumerate(model.segments):
        color = palette[i % len(palette)]
        seg_years = sorted(seg.base.years())
        seg_hist = [y for y in seg_years if y not in fc]
        seg_fc = [y for y in seg_years if y in fc]
        if seg_hist:
            ax.plot(seg_hist, [seg.revenue(y) / _YI for y in seg_hist],
                    color=color, linestyle="-", marker="o", markersize=4,
                    linewidth=2.2, label=seg.name)
        if seg_fc:
            connect = ([seg_hist[-1]] + seg_fc) if seg_hist else seg_fc
            ax.plot(connect, [seg.revenue(y) / _YI for y in connect],
                    color=color, linestyle="--", marker="o", markersize=4,
                    linewidth=2.2)

    if show_total and model.total_revenue:
        ty = sorted(model.total_revenue)
        ax.plot(ty, [model.total_revenue[y] / _YI for y in ty], color="black",
                linestyle="-", marker="s", markersize=5, linewidth=1.8, zorder=6,
                label="总收入(年报)")
        fc_years_all = sorted(y for y in all_years if y in fc)
        if fc_years_all:
            tot_fc = [sum(s.revenue(y) for s in model.segments) / _YI
                      for y in fc_years_all]
            start_y = ty[-1] if ty else fc_years_all[0]
            start_v = (model.total_revenue[ty[-1]] / _YI) if ty else tot_fc[0]
            ax.plot([start_y] + fc_years_all, [start_v] + tot_fc, color="black",
                    linestyle="--", marker="s", markersize=5, linewidth=1.8, zorder=6,
                    label="总收入(预测Σ)")

    hist_years = [y for y in all_years if y not in fc]
    fc_years = sorted(y for y in all_years if y in fc)
    if fc_years and hist_years:
        boundary = (hist_years[-1] + fc_years[0]) / 2
        ax.axvline(boundary, color=_C_DASH, linestyle=":", linewidth=1)
        ax.text(boundary, ax.get_ylim()[1], " 预测→", color=_C_DASH,
                fontsize=8, va="top")

    ax.set_xlabel("年份")
    ax.set_ylabel("收入 (亿元)")
    ax.set_title(title or f"{model.company} · 历史(实线)+预测(同色虚线)收入轨迹")
    ax.legend(fontsize=8, loc="best", framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    return ax


def plot_dashboard(
    model: RevenueModel,
    *,
    segment_name: Optional[str] = None,
    year: Optional[int] = None,
    ranges: Optional[Dict[str, tuple]] = None,
    forecast_years: Optional[Sequence[int]] = None,
    figsize=(13, 9),
) -> "Figure":
    """2×2 panel combining distribution / tornado / waterfall / forecast.

    The fastest one-call way to *see* a model. Picks one segment (the first by
    default, or ``segment_name``) for the three single-segment charts, runs
    ``simulate_segment`` + ``tornado`` from the optional ``ranges`` (or sensible
    ±10% bands if omitted), and draws the model-wide forecast trajectory.

    Returns the ``Figure`` (use ``fig.savefig(...)`` or ``st.pyplot(fig)``).
    """
    from .monte_carlo import simulate_segment, tornado

    seg = _pick_segment(model, segment_name)
    yr = year or max(seg.base.years())
    rng = ranges or _default_ranges(seg, yr)

    mc = simulate_segment(seg, yr, rng, n=10000, seed=0)
    items = tornado(seg, yr, rng)

    fig, axes = plt.subplots(2, 2, figsize=figsize)
    fig.suptitle(f"{model.company} · {seg.name} ({yr}年) — 不确定性总览",
                 fontsize=13, fontweight="bold", y=0.995)
    plot_revenue_distribution(mc, ax=axes[0, 0])
    plot_tornado(items, ax=axes[0, 1])
    plot_waterfall(items, ax=axes[1, 0])
    plot_forecast(model, forecast_years=forecast_years, ax=axes[1, 1])
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


# ---- helpers ---------------------------------------------------------------

def _multi_segment(items: Sequence[SensitivityItem]) -> bool:
    return len({i.segment for i in items}) > 1


def _pick_segment(model: RevenueModel, name: Optional[str]):
    if not model.segments:
        raise ValueError("model has no segments")
    if name is None:
        return model.segments[0]
    for seg in model.segments:
        if seg.name == name:
            return seg
    raise KeyError(f"segment {name!r} not found; have "
                   f"{[s.name for s in model.segments]}")


def _default_ranges(seg, year: int) -> Dict[str, tuple]:
    """±10% bands per driver when the caller supplies none — enough to make the
    charts non-degenerate for a quick look. Real analysis should pass bands that
    reflect each driver's A/B/C grade (narrow for hard data, wide for guesses)."""
    ranges: Dict[str, tuple] = {}
    for d in seg.drivers():
        v = d.get(year)
        ranges[d.name] = (v * 0.9, v * 1.1)
    return ranges
