"""Search over data/catalog.sqlite (PROJECT_SPEC 8.1), shared by hub and devices.

Pipeline: BM25 on chunks + BM25 on doc cards -> Reciprocal Rank Fusion -> group/intent
boosts -> small same-language bonus -> confidence filter (limits false positives).
Every result carries its full score breakdown so the UI can explain the ranking.
Embeddings are not used yet (search.use_embeddings: false); the RRF already accepts
more ranked lists, so a vector list can be added without changing the rest.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path
from typing import Any

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_ARABIC = re.compile(r"[\u0600-\u06FF]")
STOPWORDS = set("""
a an and are as at be by for from in is it of on or the to with what how when which who about
le la les de des du et en un une pour par sur au aux est que qui dans avec ou chez
el los las del y una para por con se es al lo como
""".split())

# Query language hints (queries are short, so word lists beat statistical detectors here).
_LANG_HINTS = {
    "en": set("""the of and for in with to child children treatment failure generator procedure emergency
        evacuation diagnosis dose management killed severe adult pulmonary outbreak security staff""".split()),
    "fr": set("""le la les des du de et pour dans sur avec chez enfant enfants traitement paludisme panne
        générateur procédure urgence évacuation diagnostic posologie tuberculose pulmonaire grave adulte""".split()),
    "es": set("""el los las del y para por con niño niños tratamiento paludismo fallo generador procedimiento
        emergencia evacuación diagnóstico dosis grave adulto pulmonar brote""".split()),
}
EMERGENCY_WORDS = {"emergency", "urgent", "urgence", "urgent", "urgencia", "emergencia", "evacuation",
                   "évacuation", "evacuación", "طوارئ", "عاجل", "إخلاء", "severe", "grave", "triage"}

CHUNK_SQL = """
SELECT doc_id, chunk_id, MIN(s) AS s FROM (
  SELECT c.doc_id AS doc_id, c.chunk_id AS chunk_id, bm25(chunks_fts) AS s
  FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.rowid
  WHERE chunks_fts MATCH ? ORDER BY s LIMIT 400)
GROUP BY doc_id ORDER BY s LIMIT ?"""            # bm25(): lower = better
CARD_SQL = "SELECT doc_id, bm25(cards_fts) AS s FROM cards_fts WHERE cards_fts MATCH ? ORDER BY s LIMIT ?"


def fold(text: str) -> str:
    """Lower-case and strip diacritics (same idea as the FTS5 remove_diacritics tokenizer)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def query_terms(q: str) -> list[str]:
    """Distinct content words of the query (stop words and 1-letter tokens dropped)."""
    seen, out = set(), []
    for tok in _TOKEN.findall(q):
        key = fold(tok)
        if len(key) > 1 and key not in STOPWORDS and key not in seen:
            seen.add(key)
            out.append(tok)
    return out[:12]


def fts_match(terms: list[str]) -> str:
    """Quote every term so punctuation can never break FTS5 syntax; OR = ranked recall."""
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)


def detect_language(q: str) -> dict[str, Any]:
    """Return {lang, confidence, method}. lang is None when the query is too ambiguous."""
    if _ARABIC.search(q):
        return {"lang": "ar", "confidence": 0.99, "method": "arabic script"}
    words = [w.lower() for w in _TOKEN.findall(q)]
    hits = {lang: sum(1 for w in words if w in hint) for lang, hint in _LANG_HINTS.items()}
    if any(ch in q for ch in "ñ¿¡"):
        hits["es"] += 2
    if any(ch in q for ch in "çàèùâêîôûœ"):
        hits["fr"] += 1
    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    (best, n1), (_, n2) = ranked[0], ranked[1]
    if n1 == 0 or n1 == n2:
        return {"lang": None, "confidence": 0.0, "method": "too short / ambiguous"}
    return {"lang": best, "confidence": round(n1 / (n1 + n2), 2), "method": "keyword heuristic"}


class Catalog:
    """Read-only access to catalog.sqlite plus the search algorithm."""

    def __init__(self, db_path: Path, cfg: dict):
        self.cfg = cfg
        self.scfg = cfg["search"]
        self.parsed_dir: Path = cfg["paths"]["parsed_dir"]
        self.conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.docs: dict[str, dict] = {}
        for row in self.conn.execute("SELECT * FROM documents"):
            d = dict(row)
            for key in ("groups_secondary", "countries", "keywords"):
                d[key] = json.loads(d[key] or "[]")
            d["doc_language"] = d.get("language_detected") or d["language"]
            self.docs[d["doc_id"]] = d
        self.intent_words = {fold(w) for w in self.scfg.get("clinical_intent_words", [])}
        self.n_searchable = sum(1 for d in self.docs.values() if not d["is_junk"] and not d["duplicate_of"])
        self.n_chunks = self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0] or 1
        self._idf: dict[str, float] = {}

    def idf(self, term: str) -> float:
        """log(1 + N / (1 + df)) over chunks: rare words weigh more in the confidence score."""
        key = fold(term)
        if key not in self._idf:
            with self.lock:
                df = self.conn.execute("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
                                       (fts_match([term]),)).fetchone()[0]
            self._idf[key] = math.log(1 + self.n_chunks / (1 + df))
        return self._idf[key]

    # ------------------------------------------------------------------ helpers
    def chunk(self, chunk_id: int) -> dict:
        with self.lock:
            row = self.conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return dict(row) if row else {}

    def text(self, doc_id: str) -> str:
        return (self.parsed_dir / f"{doc_id}.md").read_text(encoding="utf-8", errors="replace")

    def _boosts(self, doc: dict, group: str | None, intent: bool) -> list[tuple[str, float]]:
        b = self.scfg["boosts"]
        out = []
        if group and doc["group_primary"] == group:
            out.append((f"same group ({group})", b["same_group"]))
        elif group and group in doc["groups_secondary"]:
            out.append((f"secondary group ({group})", b["secondary_group"]))
        if intent and doc["genre"] == "Clinical Guideline Chapter":
            out.append(("clinical intent + guideline", b["guideline_clinical_intent"]))
        if intent and doc["genre"] in ("Financial Report", "Legal Encyclopedia Entry"):
            out.append(("clinical intent + admin doc", b["admin_clinical_intent"]))
        return out

    @staticmethod
    def _snippet(text: str, folded_terms: list[str], width: int = 420) -> str:
        folded = fold(text)
        positions = [folded.find(t) for t in folded_terms if folded.find(t) >= 0]
        start = max(0, min(positions) - 120) if positions else 0
        snippet = text[start:start + width].strip()
        return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")

    # ------------------------------------------------------------------ search
    def search(self, q: str, group: str | None = None, k: int = 10, lang_mode: str = "auto",
               lang_override: str | None = None, genres: set[str] | None = None) -> dict[str, Any]:
        """Rank documents for ``q``. lang_mode: 'auto' (prefer same language), 'only', 'all'."""
        lang_info = detect_language(q)
        if lang_override:
            lang_info = {"lang": lang_override, "confidence": 1.0, "method": "manual override"}
        qlang = lang_info["lang"]
        terms = query_terms(q)
        base = {"query": q, "terms": terms, "language": lang_info, "lang_mode": lang_mode,
                "emergency_intent": any(fold(t) in {fold(w) for w in EMERGENCY_WORDS} for t in terms)}
        if not terms:
            return {**base, "results": [], "no_confident_match": True, "maybe": []}

        top_k = int(self.scfg.get("bm25_top_k", 50))
        if genres:  # genre-restricted search (Emergency Mode): rank a much wider pool first
            top_k = 600
        match = fts_match(terms)
        with self.lock:
            chunk_rows = self.conn.execute(CHUNK_SQL.replace("LIMIT 400", f"LIMIT {max(400, top_k * 8)}"),
                                           (match, top_k)).fetchall()
            card_rows = self.conn.execute(CARD_SQL, (match, top_k)).fetchall()

        cand: dict[str, dict] = {}
        for rank, r in enumerate(chunk_rows, 1):
            cand.setdefault(r["doc_id"], {})["bm25_chunk_rank"] = rank
            cand[r["doc_id"]]["chunk_id"] = r["chunk_id"]
        for rank, r in enumerate(card_rows, 1):
            cand.setdefault(r["doc_id"], {})["bm25_card_rank"] = rank

        rrf_k = int(self.scfg.get("rrf_k", 60))
        folded_terms = [fold(t) for t in terms]
        weights = [self.idf(t) for t in terms]
        intent = any(t in self.intent_words for t in folded_terms)
        results = []
        for doc_id, info in cand.items():
            doc = self.docs.get(doc_id)
            if not doc or doc["is_junk"] or doc["duplicate_of"]:
                continue
            if genres and doc["genre"] not in genres:
                continue
            if lang_mode == "only" and qlang and doc["doc_language"] != qlang:
                continue
            ranks = [info[key] for key in ("bm25_chunk_rank", "bm25_card_rank") if key in info]
            rrf = sum(1.0 / (rrf_k + r) for r in ranks)
            boosts = self._boosts(doc, group, intent)
            factor = 1.0
            for _, f in boosts:
                factor *= f
            lang_match = bool(qlang) and doc["doc_language"] == qlang
            lang_bonus = 1.05 if (lang_match and lang_mode == "auto") else 1.0
            chunk = self.chunk(info["chunk_id"]) if "chunk_id" in info else {}
            evidence = fold(" ".join([doc["title"] or "", doc["summary"] or "", chunk.get("text", "")]))
            # IDF-weighted share of query terms found in the best chunk + title + summary
            confidence = sum(w for t, w in zip(folded_terms, weights) if t in evidence) / (sum(weights) or 1)
            warnings = ["Publication date unknown", "Validation status unknown (not verified by MSF)"]
            if doc["countries"]:
                warnings.append("Countries are mentioned in the text; applicability not verified")
            if doc.get("language_detected") and doc["language_detected"] != doc["language"]:
                warnings.append(f"CSV tags this '{doc['language']}' but the text looks '{doc['language_detected']}'")
            results.append({
                "doc_id": doc_id, "title": doc["title"], "genre": doc["genre"], "group": doc["group_primary"],
                "language": doc["doc_language"], "countries_mentioned": doc["countries"],
                "original_ext": doc["original_ext"], "original_mb": round((doc["original_bytes"] or 0) / 1e6, 2),
                "snippet": self._snippet(chunk.get("text", doc["summary"] or ""), folded_terms),
                "section": chunk.get("heading"), "chunk_ord": chunk.get("ord"), "chunk_id": info.get("chunk_id"),
                "score": rrf * factor * lang_bonus,
                "breakdown": {
                    "bm25_chunk_rank": info.get("bm25_chunk_rank"), "bm25_card_rank": info.get("bm25_card_rank"),
                    "rrf": round(rrf, 5), "text_relevance": round(min(1.0, rrf / (2 / (rrf_k + 1))), 3),
                    "boosts": [[label, f] for label, f in boosts], "language_match": lang_match,
                    "language_bonus": lang_bonus, "confidence": round(confidence, 2),
                },
                "language_label": None if (lang_match or not qlang) else f"Available in {doc['doc_language'].upper()}",
                "warnings": warnings,
            })
        results.sort(key=lambda r: -r["score"])
        top = results[0]["score"] if results else 1.0
        for r in results:
            r["score_pct"] = round(100 * r["score"] / top)
        min_conf = float(self.scfg.get("min_confidence", 0.35))
        confident = [r for r in results if r["breakdown"]["confidence"] >= min_conf]
        return {**base, "results": confident[:k], "no_confident_match": not confident,
                "maybe": results[:3] if not confident else [], "candidates": len(results)}
