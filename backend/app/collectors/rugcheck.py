"""
RugCheck.xyz collector (MODULE 5 extension: Solana-specific risk detection).

Docs verified via their own Swagger UI (api.rugcheck.xyz/swagger/index.html)
and multiple independent third-party integration guides.

Base URL: https://api.rugcheck.xyz/v1
Endpoint used: GET /tokens/{mint}/report/summary (lightweight summary,
not the full report - cheaper and sufficient for a single risk number).

AUTH: genuinely uncertain, and handled conservatively rather than
guessed. Multiple sources describe read endpoints as requiring an
X-API-KEY header; at least one independent source (a third-party
integration skill description) states plainly "No API key required for
read endpoints." Rather than assume either way, this collector sends the
key if RUGCHECK_API_KEY is configured, and attempts the call without one
otherwise - if the unauthenticated attempt is rejected, it fails
gracefully like any other collector miss (logged, returns None), and the
per-coin loop moves on rather than treating it as a hard error.

FIELD POLARITY - handled conservatively due to a real ambiguity found
during research: RugCheck's API is documented in different places with
different score fields that do NOT all use the same direction. One
source confirms unambiguously that "score_normalised" is "Risk score
0-100, higher = riskier" - matching this project's own risk_score
convention exactly (see risk_service.py, GoPlus-based). A DIFFERENT
field, "trustScore", is described elsewhere as higher-is-SAFER (a
"trust" score, not a risk score) - the opposite polarity. Rather than
risk silently averaging or falling back between two fields with
uncertain, possibly-opposite meanings, this collector ONLY reads
"score_normalised" for the actual risk_score value. If that specific
field is absent from a response, the check is treated as "no usable
data" (returns None) rather than guessing.
"""

import logging

from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.rugcheck.xyz/v1"


class RugCheckCollector:
    name = "rugcheck"

    def _headers(self) -> dict:
        if settings.rugcheck_api_key:
            return {"X-API-KEY": settings.rugcheck_api_key}
        return {}

    def get_risk_summary(self, mint_address: str) -> dict | None:
        """Returns {"risk_score": float 0-100 (higher=riskier), "risks": list[str]}
        or None if the check failed or the response didn't contain the
        one field this collector trusts (score_normalised - see module
        docstring on why other score-like fields aren't used)."""
        url = f"{BASE_URL}/tokens/{mint_address}/report/summary"
        try:
            payload = get_json(url, headers=self._headers())
        except CollectorHTTPError as e:
            logger.info("RugCheck summary fetch miss for %s: %s", mint_address, e)
            return None

        if not isinstance(payload, dict):
            logger.warning("Unexpected RugCheck response shape for %s", mint_address)
            return None

        risk_score = payload.get("score_normalised")
        if risk_score is None:
            logger.info(
                "RugCheck response for %s had no score_normalised field - "
                "treating as no usable data rather than guessing at an "
                "alternate, possibly differently-poled field.",
                mint_address,
            )
            return None

        try:
            risk_score = max(0.0, min(100.0, float(risk_score)))
        except (TypeError, ValueError):
            logger.warning("RugCheck score_normalised for %s was not numeric: %r", mint_address, risk_score)
            return None

        raw_risks = payload.get("risks") or []
        risk_names = []
        if isinstance(raw_risks, list):
            for r in raw_risks:
                if isinstance(r, str):
                    risk_names.append(r)
                elif isinstance(r, dict):
                    name = r.get("name") or r.get("description")
                    if name:
                        risk_names.append(str(name))

        return {"risk_score": risk_score, "risks": risk_names}
