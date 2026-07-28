"""Stochastic revenue modeling — financial stochastic processes for drivers.

Experimental, pure-stdlib layer. Upgrades the uniform Monte Carlo in
``monte_carlo.py`` with driver-specific stochastic processes:

- **price**     — geometric Brownian motion (GBM):   dS = μS dt + σS dW
- **pen/share** — logit-OU: Ornstein-Uhlenbeck in logit space, mapped back
                 through the sigmoid so values stay in (0, 1).

Numerics are pure standard library: Box-Muller for standard normals,
Euler-Maruyama for SDE discretization, a hand-rolled Cholesky factorization for
correlated Brownian motion. No numpy.

This module does **not** replace ``monte_carlo.py`` (the zero-dependency uniform
baseline); it is a parallel path for stochastic drivers. Analytic-solution
tests in ``tests/test_stochastic.py`` verify the numerics.
"""
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Protocol, Union

from .monte_carlo import MCResult, _summarize
from .segment import Segment


# --------------------------------------------------------------------------- #
# Numerical primitives (pure stdlib)
# --------------------------------------------------------------------------- #

def randn(rng: random.Random) -> float:
    """Standard normal via the Box-Muller transform.

    Draws two U(0,1) variates and returns one N(0,1). The second normal is
    discarded for simplicity (sampling is not the bottleneck here).
    """
    u1 = rng.random()
    while u1 <= 0.0:
        u1 = rng.random()
    u2 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def cholesky(matrix: List[List[float]]) -> List[List[float]]:
    """Lower-triangular L with A = L Lᵀ for a symmetric positive-definite A.

    Pure stdlib (nested lists). Used to induce correlation between independent
    standard normals: if Z ~ N(0, I) then L Z ~ N(0, A).
    """
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                diag = matrix[i][i] - s
                if diag <= 0.0:
                    raise ValueError(
                        f"correlation matrix not positive-definite at [{i}][{i}]")
                L[i][j] = math.sqrt(diag)
            else:
                L[i][j] = (matrix[i][j] - s) / L[j][j]
    return L


def sigmoid(x: float) -> float:
    """Logistic sigmoid, numerically stable for large |x|."""
    if x >= 0.0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def logit(p: float) -> float:
    """Log-odds; p must be in (0, 1)."""
    return math.log(p / (1.0 - p))


# --------------------------------------------------------------------------- #
# Stochastic drivers
# --------------------------------------------------------------------------- #

class StochasticDriver(Protocol):
    """A driver whose future value is a draw from a stochastic process.

    Concrete drivers expose ``name`` and ``sample(n, rng) -> list[float]`` (n
    independent terminal values). Internally each advances an SDE via
    Euler-Maruyama with a driver-specific drift, diffusion, and output map.
    """
    name: str

    def sample(self, n: int, rng: random.Random) -> List[float]: ...


def _simulate(driver, n: int, rng: random.Random) -> List[float]:
    """Shared Euler-Maruyama loop for any driver with _init_state/_step/_out."""
    m = max(1, int(round(driver.T / driver.dt)))
    h = driver.T / m
    sqrt_h = math.sqrt(h)
    out: List[float] = []
    for _ in range(n):
        state = driver._init_state()
        for _ in range(m):
            state = driver._step(state, h, sqrt_h, randn(rng))
        out.append(driver._out(state))
    return out


@dataclass
class GBMDriver:
    """Geometric Brownian motion for a price-like driver: dS = μS dt + σS dW.

    Euler-Maruyama on S directly. GBM keeps S non-negative in the continuous
    limit; EM can dip slightly negative for coarse dt, so values are floored
    at 0. For tighter accuracy on the mean, use a smaller ``dt``.
    """
    name: str
    S0: float
    mu: float
    sigma: float
    T: float = 1.0
    dt: float = 0.01

    def _init_state(self) -> float:
        return self.S0

    def _step(self, s: float, h: float, sqrt_h: float, z: float) -> float:
        s = s * (1.0 + self.mu * h + self.sigma * sqrt_h * z)
        return s if s > 0.0 else 0.0

    def _out(self, s: float) -> float:
        return s

    def sample(self, n: int, rng: random.Random) -> List[float]:
        return _simulate(self, n, rng)


@dataclass
class OUDriver:
    """Ornstein-Uhlenbeck (mean-reverting) driver: dx = θ(μ−x) dt + σ dW.

    Unbounded (Gaussian). For a driver that must stay in (0, 1) — like a
    penetration or market share — use :class:`LogitOUDriver` instead.
    """
    name: str
    x0: float
    theta: float
    mu: float
    sigma: float
    T: float = 1.0
    dt: float = 0.01

    def _init_state(self) -> float:
        return self.x0

    def _step(self, x: float, h: float, sqrt_h: float, z: float) -> float:
        return x + self.theta * (self.mu - x) * h + self.sigma * sqrt_h * z

    def _out(self, x: float) -> float:
        return x

    def sample(self, n: int, rng: random.Random) -> List[float]:
        return _simulate(self, n, rng)


@dataclass
class LogitOUDriver:
    """Bounded mean-reverting driver in (0, 1): logit(p) follows an OU process.

    The state ``y = logit(p)`` evolves as ``dy = θ(μ_bar − y) dt + σ dW``; the
    output ``p = sigmoid(y)`` stays in (0, 1) by construction. ``mu_bar`` is the
    long-run logit-mean — pass ``logit(target_level)`` so the process reverts
    toward a target penetration/share. Larger ``theta`` = faster reversion;
    larger ``sigma`` = more noise.
    """
    name: str
    p0: float
    theta: float
    mu_bar: float
    sigma: float
    T: float = 1.0
    dt: float = 0.01

    def _init_state(self) -> float:
        return logit(self.p0)

    def _step(self, y: float, h: float, sqrt_h: float, z: float) -> float:
        return y + self.theta * (self.mu_bar - y) * h + self.sigma * sqrt_h * z

    def _out(self, y: float) -> float:
        return sigmoid(y)

    def sample(self, n: int, rng: random.Random) -> List[float]:
        return _simulate(self, n, rng)


# --------------------------------------------------------------------------- #
# Correlated bundle
# --------------------------------------------------------------------------- #

@dataclass
class CorrelatedBundle:
    """Drivers simulated with correlated Brownian increments.

    All ``drivers`` must share a common horizon ``T`` and step ``dt``. At each
    Euler step a correlated normal vector is drawn via the Cholesky factor of
    ``rho`` and each driver advances with its own component — so their paths
    co-move (e.g. a negative base shock can coincide with a positive
    penetration shock).
    """
    drivers: List[StochasticDriver]
    rho: List[List[float]]
    T: float = 1.0
    dt: float = 0.01

    def __post_init__(self):
        k = len(self.drivers)
        if len(self.rho) != k or any(len(row) != k for row in self.rho):
            raise ValueError("rho must be k×k matching the number of drivers")
        for i in range(k):
            if abs(self.rho[i][i] - 1.0) > 1e-9:
                raise ValueError("rho diagonal must be 1.0")
        self._L = cholesky(self.rho)

    def sample(self, n: int, rng: random.Random) -> Dict[str, List[float]]:
        k = len(self.drivers)
        m = max(1, int(round(self.T / self.dt)))
        h = self.T / m
        sqrt_h = math.sqrt(h)
        L = self._L
        results: Dict[str, List[float]] = {d.name: [] for d in self.drivers}
        for _ in range(n):
            states = [d._init_state() for d in self.drivers]
            for _ in range(m):
                z_indep = [randn(rng) for _ in range(k)]
                z_corr = [sum(L[i][j] * z_indep[j] for j in range(k))
                          for i in range(k)]
                for i, d in enumerate(self.drivers):
                    states[i] = d._step(states[i], h, sqrt_h, z_corr[i])
            for i, d in enumerate(self.drivers):
                results[d.name].append(d._out(states[i]))
        return results


# --------------------------------------------------------------------------- #
# Revenue distribution from stochastic drivers
# --------------------------------------------------------------------------- #

StochasticSpec = Union[CorrelatedBundle, Dict[str, StochasticDriver]]


def simulate_revenue(segment: Segment, year: int, stochastic: StochasticSpec,
                     n: int = 10000, seed: int = 0) -> MCResult:
    """Revenue distribution when some drivers follow stochastic processes.

    ``stochastic`` is either a :class:`CorrelatedBundle` or a dict
    ``{driver_name: driver}``. Drivers named there are sampled from their
    process; the remaining drivers use ``segment``'s value at ``year`` (the
    segment must carry data for that year for every non-stochastic driver).

    Returns an :class:`MCResult` over segment revenue (million yuan), reusing
    the same summary statistics as the uniform Monte Carlo — so ``percentiles``
    and :func:`~revenue_model.monte_carlo.scenarios` work identically.
    """
    rng = random.Random(seed)
    drv = {d.name: d for d in segment.drivers()}

    if isinstance(stochastic, CorrelatedBundle):
        stoch_names = {d.name for d in stochastic.drivers}
        stoch_samples = stochastic.sample(n, rng)
    else:
        stoch_names = set(stochastic)
        stoch_samples = {name: proc.sample(n, rng)
                         for name, proc in stochastic.items()}

    unknown = stoch_names - set(drv)
    if unknown:
        raise KeyError(f"stochastic names not in segment: {unknown}")

    det = {name: d.get(year) for name, d in drv.items() if name not in stoch_names}

    samples: List[float] = []
    for i in range(n):
        rev = 1.0
        for name, d in drv.items():
            v = stoch_samples[name][i] if name in stoch_names else det[name]
            rev *= v
        samples.append(rev)
    return _summarize(samples, year)
