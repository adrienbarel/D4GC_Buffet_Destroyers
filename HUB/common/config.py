"""Load config.yaml (the single source of truth) and resolve every path.

Usage:
    from common.config import load
    cfg = load()
    cfg["paths"]["parsed_dir"]      # pathlib.Path, absolute

Rules:
- Relative paths in config.yaml are resolved against the folder that holds
  config.yaml (the repository root), so scripts work from any working directory
  and on both Linux and Windows.
- Environment overrides (useful on a laptop where the data lives elsewhere):
      D4GC_DATA_ROOT     -> paths.data_root     (folder with Parsed/ and optionally Original/)
      D4GC_METADATA_CSV  -> paths.metadata_csv  (documentation.csv)
  Relative values in env vars are resolved against the current working directory.
- An optional, gitignored ``config.local.yaml`` next to config.yaml is deep-merged
  on top of config.yaml (for machine-specific settings).
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config.yaml"
LOCAL_CONFIG_NAME = "config.local.yaml"

# env var -> key in the `paths` section
ENV_OVERRIDES = {
    "D4GC_DATA_ROOT": "data_root",
    "D4GC_METADATA_CSV": "metadata_csv",
    "D4GC_HUB_DB": "hub_db",          # volunteers/credentials/sessions DB (tests use a temp file)
}

# Paths derived from data_root / work_dir when not set explicitly in config.yaml.
_DERIVED_FROM_DATA_ROOT = {"parsed_dir": "Parsed", "original_dir": "Original"}
_DERIVED_FROM_WORK_DIR = {
    "catalog_db": "catalog.sqlite",
    "hub_db": "hub.sqlite",
    "embeddings": "embeddings.npy",
    "chunk_ids": "chunk_ids.npy",
    "cloud_store": "cloud_store",
    "hub_store": "hub_store",
    "devices_dir": "devices",
    "eval_dir": "eval",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Return a copy of ``base`` with ``override`` merged in (nested dicts merged, rest replaced)."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _resolve(value: str | os.PathLike, base: Path) -> Path:
    """Expand ``~`` and make ``value`` absolute relative to ``base``."""
    path = Path(os.path.expanduser(str(value)))
    return path if path.is_absolute() else (base / path).resolve()


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load the config, apply local file + env overrides, and resolve all paths.

    Returns the config as a plain dict. ``cfg["paths"]`` holds absolute
    ``pathlib.Path`` objects, including derived ones (parsed_dir, catalog_db, ...).
    Loading has no side effects: no folder is created here.
    """
    cfg_path = Path(path).resolve() if path else DEFAULT_CONFIG
    cfg = _read_yaml(cfg_path)

    local_path = cfg_path.with_name(LOCAL_CONFIG_NAME)
    if local_path.exists():
        cfg = _deep_merge(cfg, _read_yaml(local_path))

    base = cfg_path.parent
    raw_paths: dict[str, Any] = dict(cfg.get("paths") or {})
    paths = {key: _resolve(val, base) for key, val in raw_paths.items() if val}

    for env_name, key in ENV_OVERRIDES.items():
        env_value = os.environ.get(env_name)
        if env_value:
            paths[key] = _resolve(env_value, Path.cwd())

    for required in ("data_root", "metadata_csv", "work_dir"):
        if required not in paths:
            raise KeyError(f"config.yaml: paths.{required} is required")

    for key, sub in _DERIVED_FROM_DATA_ROOT.items():
        paths.setdefault(key, paths["data_root"] / sub)
    for key, sub in _DERIVED_FROM_WORK_DIR.items():
        paths.setdefault(key, paths["work_dir"] / sub)

    cfg["paths"] = paths
    cfg["_config_file"] = cfg_path
    return cfg


def missing_inputs(cfg: dict[str, Any]) -> list[str]:
    """List the required input paths that do not exist (empty list = all good)."""
    p = cfg["paths"]
    required = {
        "paths.data_root": p["data_root"],
        "Parsed/ folder": p["parsed_dir"],
        "paths.metadata_csv": p["metadata_csv"],
    }
    return [f"{label}: {path}" for label, path in required.items() if not path.exists()]
