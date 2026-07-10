"""Small environment helpers for local-first configuration."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = _clean_env_value(value.strip())
        if key and key not in os.environ:
            os.environ[key] = value


def first_env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
