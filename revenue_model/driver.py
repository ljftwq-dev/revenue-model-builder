"""Driver — a single revenue driver factor (market base / penetration / share / price)."""

from dataclasses import dataclass
from typing import Dict

BASE = "base"
PENETRATION = "penetration"
SHARE = "share"
PRICE = "price"

LEVEL_A = "A"
LEVEL_B = "B"
LEVEL_C = "C"

_KIND_LABELS = {
    BASE: "市场基数",
    PENETRATION: "渗透率",
    SHARE: "市占率",
    PRICE: "单价",
}


@dataclass
class Driver:
    name: str
    kind: str
    values: Dict[int, float]
    level: str = LEVEL_C
    unit: str = ""
    source: str = ""

    def __post_init__(self):
        if self.kind not in _KIND_LABELS:
            raise ValueError(f"unknown driver kind: {self.kind!r}")

    def get(self, year: int) -> float:
        if year not in self.values:
            raise KeyError(f"{self.name}: no value for year {year}")
        return self.values[year]

    def years(self):
        return sorted(self.values.keys())

    def kind_label(self):
        return _KIND_LABELS[self.kind]
