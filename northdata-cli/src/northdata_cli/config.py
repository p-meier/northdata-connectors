"""Config & secret resolution."""

from __future__ import annotations

import os


class ConfigError(Exception):
    pass


def resolve_api_key(cli_value: str | None = None) -> str:
    """Return the API key or raise ``ConfigError``.

    Precedence: ``--api-key`` flag > ``NORTHDATA_API_KEY`` env.
    """
    if cli_value:
        return cli_value
    env = os.environ.get("NORTHDATA_API_KEY", "").strip()
    if env:
        return env
    raise ConfigError(
        "No API key found. Set NORTHDATA_API_KEY in your environment or pass "
        "--api-key. You can obtain a key at https://www.northdata.com."
    )


