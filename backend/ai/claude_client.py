"""Thin Anthropic wrapper: one call, strict JSON out, never raises.

Both analysers ask Claude for JSON only. Models sometimes wrap JSON in markdown
fences anyway, so `parse_strict_json` strips fences before json.loads and gives
up quietly rather than taking down a request that was really about consent.

If ANTHROPIC_API_KEY is unset the call is skipped entirely and the caller falls
back to its own offline heuristics. That is a demo-resilience decision, not the
intended path: with a key present, every explanation you see is Claude's.
"""

import json
import re

from flask import current_app

_client = None
_client_key = None


def _get_client(api_key):
    """Lazily construct (and cache) the Anthropic SDK client."""
    global _client, _client_key
    if not api_key:
        return None
    if _client is not None and _client_key == api_key:
        return _client
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency is in requirements.txt
        return None
    _client = anthropic.Anthropic(api_key=api_key)
    _client_key = api_key
    return _client


def is_live():
    """True when a real Claude call is possible."""
    return bool(current_app.config.get("ANTHROPIC_API_KEY"))


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def parse_strict_json(text):
    """Defensive parse: strip code fences, then fall back to the outermost
    {...} span if the model added prose around the JSON."""
    if not text:
        return None

    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def ask_claude(system_prompt, user_prompt):
    """Return (parsed_json | None, error_string | None).

    Never raises: an AI outage must not stop a prescription being recorded or a
    consent decision being honoured.
    """
    api_key = current_app.config.get("ANTHROPIC_API_KEY")
    client = _get_client(api_key)
    if client is None:
        return None, "no ANTHROPIC_API_KEY configured"

    try:
        message = client.messages.create(
            model=current_app.config.get("CLAUDE_MODEL", "claude-sonnet-5"),
            max_tokens=current_app.config.get("CLAUDE_MAX_TOKENS", 1000),
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:  # noqa: BLE001 - any SDK/network error degrades gracefully
        return None, f"Claude call failed: {exc}"

    text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
    parsed = parse_strict_json(text)
    if parsed is None:
        return None, "Claude returned unparseable JSON"
    return parsed, None


def normalise_flags(parsed, allowed_types, default_type):
    """Coerce whatever Claude returned into our flag shape and drop junk rows."""
    if not isinstance(parsed, dict):
        return []
    raw = parsed.get("flags")
    if not isinstance(raw, list):
        return []

    flags = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        explanation = str(item.get("explanation") or "").strip()
        if not explanation:
            continue
        flag_type = str(item.get("type") or default_type).strip().lower().replace(" ", "_")
        if allowed_types and flag_type not in allowed_types:
            flag_type = default_type
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in ("low", "medium", "high"):
            severity = "medium"
        flags.append({"type": flag_type, "severity": severity, "explanation": explanation})
    return flags
