"""Extractor — turn an annual report's "main business analysis" into segment skeletons.

This module automates the labor-intensive part of segment revenue build-up:
locating the right section is upstream (PyMuPDF), but here we take that text and
ask an LLM to pull out a structured segment skeleton — business lines, revenue,
share, YoY, gross margin, a driver-type tag, and driver hints — plus an
"unmodeled" bucket that flows into the residual line.

Design choices:
- **Pure stdlib** (``urllib`` + ``json``). No SDK dependency; the LLM call is a
  plain HTTP POST to any OpenAI-compatible endpoint (Zhipu GLM by default).
- **The LLM call is injectable.** ``extract_segments(text, llm=fn)`` lets tests
  pass a fake LLM, so the test suite (and CI) needs no API key and no network.
- **API key is a runtime argument, never hardcoded.** Load it via your secrets
  manager (e.g. ``secrets_loader.get_zhipu_config()["api_key"]``) and pass it in.

The output is a dict matching the schema in
[docs/proposal-segment-extraction.md](../docs/proposal-segment-extraction.md) §4.
Filling concrete driver *values* (C-grade estimates) is the next, human step —
see the proposal's semi-automated boundary (§7).
"""

import json
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional

# Controlled vocabulary for driver_type — the LLM must pick one. Maps type to
# the canonical driver tree (all normalize to base × penetration × share × price).
DRIVER_TYPES: Dict[str, str] = {
    "hardware_product": "market base (unit sales) × penetration × share × ASP",
    "software_subscription": "customer / install base × penetration × share × per-unit fee (ARPU)",
    "service_project": "capacity / person-days × utilization × price",
    "advertising": "traffic (DAU × time) × ad_load × share × eCPM",
    "financial_interest": "interest-earning assets × yield",
    "retail_store": "store count × sales per store",
}

SYSTEM_PROMPT = (
    "You are a meticulous sell-side equity analyst. Given the 'main business "
    "analysis' section text from an annual report, extract the company's "
    "business structure (segment revenue build-up). Output ONE JSON object and "
    "nothing else."
)

SCHEMA_PROMPT = """\
Output JSON schema (revenue in yuan; share / yoy / gross_margin as decimals,
e.g. 0.1617 = 16.17%):
{
  "company": "short name",
  "fiscal_year": 2024,
  "total_revenue": <main business revenue, yuan>,
  "segments": [
    {
      "name": "segment name",
      "revenue": <yuan>,
      "share": <decimal>,
      "yoy": <decimal>,
      "gross_margin": <decimal>,
      "driver_type": "<one of the controlled vocabulary below>",
      "driver_hints": {
        "base": "data clue for market base (e.g. global smartphone shipments)",
        "penetration": "penetration clue",
        "share": "market-share clue",
        "price": "unit price / license fee clue"
      },
      "evidence": "verbatim snippet from the text with the numbers (auditable)",
      "confidence": "A | B | C"
    }
  ],
  "unmodeled": {"name": "misc / not separately modeled", "revenue": <yuan>, "share": <decimal>, "note": "goes to residual line"}
}

driver_type controlled vocabulary (pick exactly one per segment):
""" + "\n".join(f"- {k}: {v}" for k, v in DRIVER_TYPES.items()) + """

Rules:
1. Extract segments by product line where possible (most representative); fall
   back to industry if the report only discloses by industry.
2. Items below ~5% or of unclear nature go to 'unmodeled' (residual), not a
   segment. Aim for 3-5 core segments covering 70-80% (the 80/20 rule).
3. Share must sum to ~1: Σ(segments.share) + unmodeled.share ≈ 1.
4. Every number must trace to 'evidence' (a verbatim snippet). No fabrication.
5. confidence: A = hard data from the report (revenue/margin); C = estimates
   (most driver_hints are C).
"""


def build_prompt(text: str) -> List[Dict[str, str]]:
    """Build the chat messages for the LLM from the annual-report text."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": SCHEMA_PROMPT + "\n\nAnnual-report text:\n\n" + text},
    ]


def call_llm(messages: List[Dict[str, str]], api_key: str,
             base_url: str = "https://open.bigmodel.cn/api/paas/v4",
             model: str = "glm-4-plus", timeout: int = 120) -> str:
    """Call an OpenAI-compatible chat endpoint (Zhipu GLM by default).

    Returns the assistant message content. Raises ``urllib.error.URLError`` on
    network failure — surface that to the user (do not silently retry).
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)["choices"][0]["message"]["content"]


def parse_segments(content: str) -> Dict:
    """Parse the LLM's JSON content and run the share-sum sanity check.

    Adds ``_share_sum`` and ``_aligned`` (True if shares sum to ~1.0) to the
    returned dict. Raises ``json.JSONDecodeError`` if the content isn't JSON.
    """
    data = json.loads(content)
    segs = data.get("segments", []) or []
    unm = data.get("unmodeled", {}) or {}
    share_sum = sum(float(s.get("share", 0)) for s in segs) + float(unm.get("share", 0))
    data["_share_sum"] = share_sum
    data["_aligned"] = abs(share_sum - 1.0) < 0.02
    return data


def extract_segments(
    text: str,
    *,
    api_key: Optional[str] = None,
    base_url: str = "https://open.bigmodel.cn/api/paas/v4",
    model: str = "glm-4-plus",
    llm: Optional[Callable[[List[Dict[str, str]]], str]] = None,
    timeout: int = 120,
) -> Dict:
    """Extract a segment skeleton from annual-report text.

    Either pass ``api_key`` (load via your secrets manager; never hardcode) for
    a real LLM call, or pass ``llm`` (a ``messages -> content`` callable) for
    testing/offline. Returns the parsed, sanity-checked schema dict.
    """
    messages = build_prompt(text)
    if llm is not None:
        content = llm(messages)
    else:
        if not api_key:
            raise ValueError(
                "extract_segments needs api_key (for a real call) or llm= (for "
                "testing). Load the key via your secrets manager; never hardcode.")
        content = call_llm(messages, api_key, base_url=base_url, model=model,
                           timeout=timeout)
    return parse_segments(content)


def alignment_check(parsed: Dict, total_revenue_key: str = "total_revenue") -> Dict[str, float]:
    """Verify Σ(segments.revenue) + unmodeled.revenue ≈ reported total.

    Returns a small report dict. This is the empirical check that the
    structural residual (Principle 1) holds on the extracted data.
    """
    segs = parsed.get("segments", []) or []
    unm = parsed.get("unmodeled", {}) or {}
    seg_sum = sum(float(s.get("revenue", 0)) for s in segs)
    unm_rev = float(unm.get("revenue", 0))
    total = float(parsed.get(total_revenue_key, 0))
    residual = total - seg_sum
    return {
        "segment_sum": seg_sum,
        "unmodeled": unm_rev,
        "reported_total": total,
        "residual": residual,
        "residual_ratio": (residual / total) if total else 0.0,
        "aligned": abs((seg_sum + unm_rev) - total) < total * 0.01,
    }
