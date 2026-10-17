"""
MODULE 7: Narrative AI.

Calls the Anthropic Messages API directly (not the anthropic Python SDK, to
keep this dependency-light - it's a single POST with a well-established,
stable contract). Requires ANTHROPIC_API_KEY; if unset, narrative analysis
is skipped entirely (see NarrativeScannerService), not faked.

One call answers both MODULE 7's qualitative questions (why are people
talking about this, emotion, funny/controversial/relatable, could it spread
beyond crypto) and produces the MODULE 2 narrative_score - combined into one
request since they're both narrative-LLM tasks operating on the same input
(the collected posts), and splitting them would double the API cost for no
real benefit.
"""

import json
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = """You are a crypto market analyst helping a meme coin intelligence \
platform assess why a token is being talked about. You will be given a coin's \
name/symbol and a sample of recent posts mentioning it (from Reddit, X, and/or \
crypto news). Analyze the narrative and respond with ONLY a JSON object (no \
markdown fences, no preamble) matching exactly this shape:

{
  "main_topic": "short phrase describing what people are actually discussing",
  "meme_category": "one of: animal, political, celebrity, in-joke, event-driven, absurdist, other",
  "related_events": "brief note on any real-world event driving this, or null",
  "similar_historical_memes": "brief note on comparable past meme coins/trends, or null",
  "emotion": "the dominant emotion the posts express, one short word",
  "is_funny": true or false,
  "is_controversial": true or false,
  "is_relatable": true or false,
  "could_spread_beyond_crypto": true or false,
  "narrative_summary": "2-3 sentence summary of why people are talking about this",
  "virality_score": integer 0-100 estimating how likely this narrative is to keep spreading,
  "narrative_score": integer 0-100 rating overall narrative strength/momentum as a trading signal
}

Base every judgment strictly on the provided posts. If posts are sparse or \
low-quality, reflect that with lower scores rather than inventing signal that \
isn't there. Never fabricate specifics (event names, meme references) you \
can't support from the given text."""


class NarrativeAIService:
    def is_configured(self) -> bool:
        return bool(settings.anthropic_api_key)

    def analyze(self, coin_label: str, posts: list[dict]) -> dict | None:
        """posts: list of {source, text, engagement_score}. Returns a dict
        matching the Narrative model's fields, or None if not configured or
        the call fails - callers treat None as 'analysis unavailable',
        leaving narrative_score as null rather than guessing."""
        if not self.is_configured() or not posts:
            return None

        user_content = self._build_user_content(coin_label, posts)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    ANTHROPIC_API_URL,
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": ANTHROPIC_VERSION,
                        "content-type": "application/json",
                    },
                    json={
                        "model": settings.anthropic_model,
                        "max_tokens": 1000,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": user_content}],
                    },
                )
                if resp.status_code >= 400:
                    logger.warning("Anthropic API call failed: %s %s", resp.status_code, resp.text[:300])
                    return None
                payload = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Anthropic API request errored: %s", e)
            return None

        text_blocks = [b["text"] for b in payload.get("content", []) if b.get("type") == "text"]
        raw_text = "".join(text_blocks).strip()

        parsed = self._parse_json_response(raw_text)
        if parsed is None:
            logger.warning("Could not parse Anthropic response as JSON: %s", raw_text[:300])
            return None

        return self._validate(parsed)

    def _build_user_content(self, coin_label: str, posts: list[dict]) -> str:
        # Cap total input to keep cost/latency bounded; sort by engagement
        # first so the most representative posts survive the cap.
        top_posts = sorted(posts, key=lambda p: p.get("engagement_score", 0), reverse=True)[:30]
        lines = [f"Coin: {coin_label}", "", "Posts:"]
        for p in top_posts:
            snippet = (p.get("text") or "")[:400].replace("\n", " ")
            lines.append(f"- [{p.get('source', '?')}] {snippet}")
        return "\n".join(lines)

    def _parse_json_response(self, text: str) -> dict | None:
        # Models occasionally wrap JSON in markdown fences despite instructions.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            return json.loads(cleaned.strip())
        except (json.JSONDecodeError, ValueError):
            return None

    def _validate(self, parsed: dict) -> dict:
        def _clip_score(value) -> float | None:
            try:
                return max(0.0, min(100.0, float(value)))
            except (TypeError, ValueError):
                return None

        return {
            "main_topic": _str_or_none(parsed.get("main_topic")),
            "meme_category": _str_or_none(parsed.get("meme_category")),
            "related_events": _str_or_none(parsed.get("related_events")),
            "similar_historical_memes": _str_or_none(parsed.get("similar_historical_memes")),
            "emotion": _str_or_none(parsed.get("emotion")),
            "is_funny": _bool_or_none(parsed.get("is_funny")),
            "is_controversial": _bool_or_none(parsed.get("is_controversial")),
            "is_relatable": _bool_or_none(parsed.get("is_relatable")),
            "could_spread_beyond_crypto": _bool_or_none(parsed.get("could_spread_beyond_crypto")),
            "narrative_summary": _str_or_none(parsed.get("narrative_summary")),
            "virality_score": _clip_score(parsed.get("virality_score")),
            "narrative_score": _clip_score(parsed.get("narrative_score")),
        }


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() != "null" else None


def _bool_or_none(value) -> bool | None:
    return value if isinstance(value, bool) else None
