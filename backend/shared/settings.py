"""Settings + secrets loader.

Reads from:
  config/settings.yaml         (committed defaults)
  config/settings.local.yaml   (gitignored local overrides — optional)
  config/secrets.yaml          (committed schema, empty values)
  config/secrets.local.yaml    (gitignored real secrets — optional)

Local files override defaults via deep merge.

Override paths via env:
  LUMEN_SETTINGS_PATH, LUMEN_SETTINGS_LOCAL_PATH
  LUMEN_SECRETS_PATH,  LUMEN_SECRETS_LOCAL_PATH
"""

from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Override wins on scalar / list keys."""
    out = deepcopy(base)
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        return {}
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    base = _load_yaml(Path(os.environ.get("LUMEN_SETTINGS_PATH", CONFIG_DIR / "settings.yaml")))
    override = _load_yaml(
        Path(os.environ.get("LUMEN_SETTINGS_LOCAL_PATH", CONFIG_DIR / "settings.local.yaml"))
    )
    return _deep_merge(base, override)


@lru_cache(maxsize=1)
def secrets() -> dict[str, Any]:
    base = _load_yaml(Path(os.environ.get("LUMEN_SECRETS_PATH", CONFIG_DIR / "secrets.yaml")))
    override = _load_yaml(
        Path(os.environ.get("LUMEN_SECRETS_LOCAL_PATH", CONFIG_DIR / "secrets.local.yaml"))
    )
    return _deep_merge(base, override)


def reload() -> None:
    """Force reload (used by tests + future SIGHUP handler)."""
    settings.cache_clear()
    secrets.cache_clear()


def get(path: str, default: Any = None, *, source: str = "settings") -> Any:
    """Dot-path lookup, e.g. get('llm.default_provider')."""
    root = settings() if source == "settings" else secrets()
    cur: Any = root
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def secret(path: str, default: Any = None) -> Any:
    """Convenience for secrets lookup; treats empty string as 'not set'."""
    val = get(path, default, source="secrets")
    if isinstance(val, str) and val == "":
        return default
    return val
