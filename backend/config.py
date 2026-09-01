"""Application configuration.

Deliberately tiny: this is a one-day hackathon demo, so there is no secrets
manager, no multi-environment config and no auth. The only real external
dependency is the Anthropic API key used by the AI layer (phase 5).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# SQLite lives next to the backend package so `python seed.py` and
# `python app.py` always agree on where the database is.
DB_PATH = BASE_DIR / "mathnova.db"


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    # AI layer (phase 5). If the key is absent the app still runs end to end --
    # the safety/fraud analysers fall back to a deterministic local explainer so
    # the demo never hard-fails on a missing key mid-presentation.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
    CLAUDE_MAX_TOKENS = 1000
