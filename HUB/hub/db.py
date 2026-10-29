"""SQLite schema and helpers (PROJECT_SPEC section 7.1).

The same module creates:
- the master catalog ``data/catalog.sqlite`` (built offline by preprocess/build_catalog.py):
  documents, chunks, chunks_fts, cards_fts;
- the hub-only tables (hub_store, devices, requests, ...), created by the hub at start-up.

Notes:
- ``documents.countries`` holds countries *mentioned* in the text (dictionary match),
  NOT countries where the document is officially applicable.
- FTS5 tables use ``unicode61 remove_diacritics 2`` (works for en/fr/es and for
  space-separated Arabic words). ``bm25()`` is lower-is-better.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY, title TEXT, title_source TEXT, genre TEXT,
  language TEXT,                                  -- from documentation.csv (source of truth)
  language_detected TEXT,                         -- stop-word/script heuristic; flags CSV errors (e.g. P22)
  group_primary TEXT, groups_secondary TEXT,      -- JSON list
  countries TEXT, keywords TEXT, summary TEXT,    -- JSON lists / text (countries = mentioned)
  text_bytes INTEGER, original_bytes INTEGER, original_ext TEXT,
  sha256 TEXT, is_junk INTEGER DEFAULT 0, duplicate_of TEXT, version INTEGER DEFAULT 1,
  n_chunks INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id INTEGER PRIMARY KEY, doc_id TEXT NOT NULL, ord INTEGER NOT NULL,
  heading TEXT,                                   -- nearest Markdown section heading (for citations)
  text TEXT NOT NULL                              -- exact source text (only PDF ligature glyphs expanded)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, ord);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, content='chunks', content_rowid='chunk_id', tokenize='unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
  doc_id UNINDEXED, title, summary, keywords, tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value TEXT);
"""

HUB_SCHEMA = """
CREATE TABLE IF NOT EXISTS hub_store (doc_id TEXT PRIMARY KEY, has_text INTEGER, has_original INTEGER,
  tier TEXT,                                      -- 'text_only' | 'core' | 'reserve'
  score_p_need REAL, score_cost_missing REAL, score_priority REAL, reason TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, grp TEXT, budget_mb REAL, url TEXT,
  last_seen TEXT, manifest_version INTEGER);
CREATE TABLE IF NOT EXISTS device_holdings (device_id TEXT, doc_id TEXT, has_text INTEGER,
  has_original INTEGER, PRIMARY KEY (device_id, doc_id));
CREATE TABLE IF NOT EXISTS views (doc_id TEXT, device_id TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS requests (req_id INTEGER PRIMARY KEY, doc_id TEXT, device_id TEXT, want TEXT,
  reason TEXT, status TEXT, path TEXT, eta_s REAL, cost_estimate REAL,
  created_at TEXT, updated_at TEXT, log TEXT);    -- log = JSON list of {ts, msg}
CREATE TABLE IF NOT EXISTS access_log (ts TEXT, device_id TEXT, doc_id TEXT, action TEXT,
  allowed INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS relay_log (ts TEXT, msg_id INTEGER, src TEXT, dst TEXT, type TEXT,
  bytes INTEGER, hex TEXT, note TEXT);

-- volunteer login + access (hub/auth.py, hub/rotation.py). Times are ISO-8601 UTC strings.
-- grp = one of the 4 staff groups = the existing document permissions (no new permission model).
CREATE TABLE IF NOT EXISTS volunteers (
  volunteer_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, grp TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('volunteer', 'admin')),
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'expired')),
  mission_start TEXT, mission_end TEXT NOT NULL, last_rotation TEXT, next_rotation TEXT,
  rotation_pending INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS credentials (            -- old rows are kept: a username is never reused
  volunteer_id TEXT NOT NULL, username TEXT NOT NULL UNIQUE, pin_hash TEXT NOT NULL, salt TEXT NOT NULL,
  created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
  delivered_at TEXT);                               -- NULL + active=0: rotated, waiting for "Confirmed delivered"
CREATE TABLE IF NOT EXISTS sessions (               -- token = SHA-256 of the bearer token (raw token never stored)
  token TEXT PRIMARY KEY, volunteer_id TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_log (               -- NEVER contains a PIN
  ts TEXT, volunteer_id TEXT, event TEXT, ok INTEGER, detail TEXT);
"""


def connect(path: str | Path, readonly: bool = False) -> sqlite3.Connection:
    """Open a SQLite connection with Row access. ``readonly`` uses a URI so the file is never created."""
    if readonly:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_catalog(conn: sqlite3.Connection) -> None:
    """Create the catalog tables (idempotent)."""
    conn.executescript(CATALOG_SCHEMA)


def init_hub(conn: sqlite3.Connection) -> None:
    """Create the hub-only tables (idempotent)."""
    conn.executescript(HUB_SCHEMA)
