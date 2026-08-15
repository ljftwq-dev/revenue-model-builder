"""news_impact — honest event-study statistics (Direction-3 analysis layer).

Turns "did these events move that outcome?" into a defensible answer. The
API encodes the lessons of the news-impact validation case study
(``docs/news-impact-validation.md``), where a seductive single-company
p-value (SDGR p=0.033) dissolved under pooling, market adjustment and
multiplicity control:

1. **Pool across issuers** — single-company event studies manufacture
   p<0.05 findings out of noise.
2. **Adjust prices for the market** — event months overlap bull runs; an
   unadjusted "significant positive" is often just beta.
3. **Count your tests** — scanning k categories on h horizons multiplies
   false positives; :func:`bonferroni_alpha` is applied automatically and
   surfaced per row.
4. **Respect small samples** — categories below ``min_n`` are reported
   without a test, never silently pooled into "Other".

Pure stdlib: Welch's t via a hand-rolled regularized incomplete beta
(Lentz continued fraction), Mann-Whitney U via the tie-corrected normal
approximation. Precision is verified against scipy references in the test
suite (constants, not imports).
"""
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import NormalDist
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "welch_test", "mann_whitney_u", "align_first_after",
    "bonferroni_alpha", "event_study", "CategoryResult", "EventStudyResult",
    "WelchResult", "MWUResult",
]


# ---------------------------------------------------------------------------
# distributions (stdlib)
# ---------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float, itmax: int = 200,
            eps: float = 3e-12) -> float:
    """Continued fraction for the incomplete beta function (NR 6.4)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc_reg(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b))
    front = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    complement = math.exp(ln_beta + b * math.log(1.0 - x)
                          + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b
    return 1.0 - complement


def _t_sf_two_sided(t: float, df: float) -> float:
    """Two-sided p-value P(|T| >= |t|) for Student-t with ``df`` dof."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    return _betainc_reg(df / 2.0, 0.5, x)


# ---------------------------------------------------------------------------
# two-sample tests
# ---------------------------------------------------------------------------

@dataclass
class WelchResult:
    t: float
    df: float
    p: float


@dataclass
class MWUResult:
    u: float
    z: float
    p: float


def welch_test(a: Sequence[float], b: Sequence[float]) -> WelchResult:
    """Welch's unequal-variance t-test, two-sided."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        raise ValueError("welch_test needs >=2 observations per sample")
    ma = sum(a) / na
    mb = sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se2 = va / na + vb / nb
    if se2 == 0:
        raise ValueError("welch_test: both samples are constant")
    t = (ma - mb) / math.sqrt(se2)
    df = se2 * se2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return WelchResult(t=t, df=df, p=_t_sf_two_sided(t, df))


def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> MWUResult:
    """Mann-Whitney U, two-sided, tie-corrected normal approximation."""
    na, nb = len(a), len(b)
    if na < 1 or nb < 1:
        raise ValueError("mann_whitney_u needs >=1 observation per sample")
    ranks_pairs = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    n = na + nb
    ranks = [0.0] * n
    i = 0
    tie_term = 0.0
    while i < n:
        j = i
        while j + 1 < n and ranks_pairs[j + 1][0] == ranks_pairs[i][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0  # 1-based average rank of the tie block
        ties = j - i + 1
        tie_term += ties ** 3 - ties
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    rank_sum_a = sum(r for r, (_, g) in zip(ranks, ranks_pairs) if g == 0)
    u1 = rank_sum_a - na * (na + 1) / 2.0
    u = min(u1, na * nb - u1)
    mu = na * nb / 2.0
    var = na * nb * (n + 1) / 12.0 - na * nb * tie_term / (12.0 * n * (n - 1)) \
        if n > 1 else 0.0
    if var <= 0:
        return MWUResult(u=u, z=0.0, p=1.0)
    # continuity correction: u is the smaller statistic (u <= mu), so shift
    # toward mu by half a unit (matches scipy's asymptotic default)
    z = (u - mu + 0.5) / math.sqrt(var)
    p = 2.0 * (1.0 - NormalDist().cdf(abs(z)))
    p = min(max(p, 0.0), 1.0)
    return MWUResult(u=u, z=z, p=p)


# ---------------------------------------------------------------------------
# alignment
# ---------------------------------------------------------------------------

def align_first_after(event_date: Union[date, datetime],
                      series: Dict) -> Optional[object]:
    """First key of ``series`` strictly after ``event_date`` -> its value.

    ``series`` maps dates (``date``/``datetime``) to outcomes (a fiscal
    quarter's YoY growth, a month's return, ...). ``None`` when the event
    postdates every observation. ``date`` vs ``datetime`` are compared
    safely (datetime is coerced to its date part).
    """
    d = event_date.date() if isinstance(event_date, datetime) else event_date

    def as_date(k):
        return k.date() if isinstance(k, datetime) else k

    after = [k for k in series if as_date(k) > d]
    if not after:
        return None
    return series[min(after, key=as_date)]


# ---------------------------------------------------------------------------
# multiplicity + pooled study
# ---------------------------------------------------------------------------

def bonferroni_alpha(n_tests: int, alpha: float = 0.05) -> float:
    """Family-wise corrected significance level for ``n_tests`` comparisons."""
    if n_tests < 1:
        return alpha
    return alpha / n_tests


@dataclass
class CategoryResult:
    category: str
    n: int
    mean: float
    median: float
    baseline_mean: float
    welch_p: Optional[float] = None
    mwu_p: Optional[float] = None
    significant: bool = False
    bonferroni_significant: bool = False
    note: str = ""


@dataclass
class EventStudyResult:
    rows: List[CategoryResult] = field(default_factory=list)
    baseline_n: int = 0
    n_tests: int = 0
    bonferroni_alpha: float = 0.05
    min_n: int = 8


def event_study(events_by_sample: Dict[str, List[Tuple[Union[date, datetime], str]]],
                outcomes_by_sample: Dict[str, Dict],
                baseline_by_sample: Optional[Dict[str, Sequence[float]]] = None,
                *, min_n: int = 8, alpha: float = 0.05
                ) -> EventStudyResult:
    """Pooled event study across samples, with honest significance.

    Parameters
    ----------
    events_by_sample : {sample_id: [(event_date, category), ...]}
        E.g. ``{"NVDA": [(date, "Earnings"), ...], "AMD": [...]}`` — pool
        events across companies/issuers, do not run them one at a time.
    outcomes_by_sample : {sample_id: {outcome_date: value}}
        The outcome series per sample (e.g. market-adjusted monthly returns,
        or fiscal-quarter YoY growth from
        ``sec_adapter.fetch_fiscal_quarters``).
    baseline_by_sample : {sample_id: [value, ...]}, optional
        The all-period distribution per sample the events are compared
        against. Defaults to each sample's full outcome series.
    min_n : int
        Categories with fewer pooled events get a row with ``note`` and no
        test — never a p-value from noise, and never silent pooling.
    alpha : float
        Nominal significance level; the Bonferroni-corrected threshold for
        the *family* of tests actually run is reported on the result.

    Returns
    -------
    EventStudyResult
        One :class:`CategoryResult` per category, plus the multiplicity
        bookkeeping. ``significant`` flags the nominal level;
        ``bonferroni_significant`` flags the family-wise level — the one
        to trust.
    """
    pooled: Dict[str, List[float]] = {}
    baseline_all: List[float] = []
    for sid, events in events_by_sample.items():
        series = outcomes_by_sample.get(sid, {})
        if baseline_by_sample is not None:
            base = list(baseline_by_sample.get(sid, series.values()))
        else:
            base = list(series.values())
        baseline_all.extend(base)
        for ev_date, cat in events:
            v = align_first_after(ev_date, series)
            if v is not None and isinstance(v, (int, float)) \
                    and not isinstance(v, bool) and math.isfinite(v):
                pooled.setdefault(cat, []).append(float(v))

    rows: List[CategoryResult] = []
    testable: List[CategoryResult] = []
    for cat in sorted(pooled):
        xs = pooled[cat]
        mean = sum(xs) / len(xs)
        med = sorted(xs)[len(xs) // 2]
        if len(xs) < min_n:
            rows.append(CategoryResult(
                category=cat, n=len(xs), mean=mean, median=med,
                baseline_mean=(sum(baseline_all) / len(baseline_all)
                               if baseline_all else float("nan")),
                note=f"n < {min_n}: reported without test"))
            continue
        row = CategoryResult(category=cat, n=len(xs), mean=mean, median=med,
                             baseline_mean=(sum(baseline_all) / len(baseline_all)
                                            if baseline_all else float("nan")))
        try:
            row.welch_p = welch_test(xs, baseline_all).p
        except ValueError:
            pass
        try:
            row.mwu_p = mann_whitney_u(xs, baseline_all).p
        except ValueError:
            pass
        rows.append(row)
        testable.append(row)

    n_tests = len(testable)
    b_alpha = bonferroni_alpha(n_tests, alpha)
    for row in testable:
        ps = [p for p in (row.welch_p, row.mwu_p)
              if p is not None and math.isfinite(p)]
        if ps:
            row.significant = min(ps) < alpha
            row.bonferroni_significant = min(ps) < b_alpha
    return EventStudyResult(rows=rows, baseline_n=len(baseline_all),
                            n_tests=n_tests, bonferroni_alpha=b_alpha,
                            min_n=min_n)
