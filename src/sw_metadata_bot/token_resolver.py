"""Token resolution helpers for API clients."""

import os
from pathlib import Path

from dotenv import dotenv_values


def resolve_token(
    *,
    explicit_token: str | None,
    env_var_name: str,
    dry_run: bool,
) -> str | None:
    """Resolve token with precedence: explicit > env > .env fallback."""
    if explicit_token:
        return explicit_token

    env_token = os.getenv(env_var_name)
    if env_token:
        return env_token

    env_path = Path.cwd() / ".env"
    if env_path.exists():
        env_values = dotenv_values(env_path)
        env_file_token = env_values.get(env_var_name)
        if isinstance(env_file_token, str) and env_file_token:
            return env_file_token

    if not dry_run:
        raise ValueError(f"{env_var_name} required (set in .env or environment)")

    return None
