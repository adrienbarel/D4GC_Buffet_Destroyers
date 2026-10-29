"""Group-based access rules (PROJECT_SPEC 7.5). Shared by device roles and signed-in volunteers.

- Everyone can see every document card.
- Opening a document of your own group (primary or secondary) is allowed.
- Outside your group: 'log' (opens + access_log row) or 'needs_approval', per config.
- restricted_genres (Financial Report) always need hub-operator approval outside their group.
"""
from __future__ import annotations


def decide(group: str, doc: dict, approved: bool, cfg: dict) -> str:
    """Return 'allowed' | 'log' | 'needs_approval' for ``group`` opening ``doc``."""
    if doc["group_primary"] == group or group in doc["groups_secondary"]:
        return "allowed"
    if approved:
        return "allowed"
    if doc["genre"] in cfg["access"]["restricted_genres"]:
        return "needs_approval"
    return "log" if cfg["access"]["out_of_group_policy"] == "log_and_allow" else "needs_approval"
