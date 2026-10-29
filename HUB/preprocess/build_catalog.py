#!/usr/bin/env python3
"""Build the master catalog (PROJECT_SPEC section 6). Run once, off-site.

    python preprocess/build_catalog.py               # everything, as configured
    python preprocess/build_catalog.py --no-copy     # skip the cloud_store copy

Inputs (from config.yaml, see common/config.py):
    Parsed/*.md, documentation.csv, originals_manifest.csv, and Original/ only if present.
Outputs (in paths.work_dir, gitignored):
    catalog.sqlite          documents, chunks, chunks_fts, cards_fts, catalog_meta
    cloud_store/text/       a copy of every .md (what the cloud server serves)
    cloud_store/original/   a copy of the originals, only if Original/ exists
    catalog_report.json     the numbers printed at the end (for the pitch slide)

Honesty rules applied here:
- ``countries`` = countries *mentioned* in the text, never "officially applicable".
- No date, validation status or authority is invented: the CSV has none.
- Chunk text is the exact source text; the only change is expanding PDF ligature
  glyphs ("Eﬀ ective" -> "Effective") so keyword search can match them.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.config import load, missing_inputs  # noqa: E402
from common.log import get_logger  # noqa: E402
from hub import db  # noqa: E402

log = get_logger("build_catalog")

JUNK_MIN_GROUP = 4            # 4+ files with the same hash = scraped boilerplate
JUNK_MAX_CHARS = 2000
JUNK_MARKER = "Get Involved"
TITLE_MAX = 120
SUMMARY_MAX = 300
SUMMARY_MIN_SENTENCE = 40
COUNTRY_SCAN_CHARS = 20_000
MAX_COUNTRIES = 5
N_KEYWORDS = 10
KEYWORD_SCAN_CHARS = 100_000

COUNTRIES_FILE = Path(__file__).with_name("countries.json")


# --------------------------------------------------------------------------- data model
@dataclass
class Doc:
    """One document as it flows through the pipeline."""

    doc_id: str
    md_path: Path
    text: str
    genre: str
    language: str
    sha256: str
    original_ext: str | None = None
    original_bytes: int | None = None
    original_title: str = ""
    original_path: Path | None = None
    title: str = ""
    title_source: str = ""
    group_primary: str | None = None
    groups_secondary: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    summary: str = ""
    is_junk: bool = False
    duplicate_of: str | None = None
    language_detected: str | None = None
    chunks: list[tuple[str | None, str]] = field(default_factory=list)

    @property
    def searchable(self) -> bool:
        return not self.is_junk and self.duplicate_of is None


# --------------------------------------------------------------------------- text helpers
_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_LIG_TABLE = str.maketrans(_LIGATURES)
_LIG_SPACE = re.compile("([ﬀﬁﬂﬃﬄﬅﬆ]) (?=[a-zà-ÿ])")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_MARKS = re.compile(r"[*_`#>|]+")
_WS = re.compile(r"\s+")
_HEADING_LINE = re.compile(r"^#{1,6}\s+\S")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*+•·▪◦]|\d{1,3}[.)])\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")
_LETTER = re.compile(r"[^\W\d_]")
_CITATION_LINE = re.compile(r"^\s*(?:\[\d+\]|\d+\.\s*[A-Z][^.]{0,80}\.\s*\d{4}|doi:|citation\s*\d)", re.I)


def fix_ligatures(text: str) -> str:
    """Undo the PDF-extraction ligature artefact: 'Eﬀ ective' -> 'Effective'."""
    return _LIG_SPACE.sub(r"\1", text).translate(_LIG_TABLE)


def to_plain(md: str) -> str:
    """Markdown -> plain text for keywords/summaries/countries (links kept as their label, URLs dropped)."""
    text = _MD_LINK.sub(r"\1", html.unescape(md))
    text = _URL.sub(" ", text)
    return _MD_MARKS.sub(" ", text)


def collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


def truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and add an ellipsis if needed."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def fold(text: str) -> str:
    """Remove diacritics (and Arabic tatweel) for dictionary matching."""
    decomposed = unicodedata.normalize("NFKD", text.replace("\u0640", ""))
    return unicodedata.normalize("NFC", "".join(c for c in decomposed if not unicodedata.combining(c)))


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


# --------------------------------------------------------------------------- 1. list documents
def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def load_manifest(path: Path) -> dict[str, dict]:
    """originals_manifest.csv -> {id: {ext, bytes, title}} (empty dict if the file is absent)."""
    if not path or not path.exists():
        return {}
    out = {}
    for row in read_csv_rows(path):
        size = row.get("original_bytes") or ""
        out[row["id"]] = {
            "ext": row.get("original_ext") or None,
            "bytes": int(size) if size.isdigit() else None,
            "title": row.get("original_title") or "",
        }
    return out


def read_original_title(path: Path) -> str:
    """Title from an original file: HTML <title> or PDF metadata. Empty string on any failure."""
    try:
        if path.suffix.lower() in (".html", ".htm"):
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            return soup.title.get_text(" ", strip=True) if soup.title else ""
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            meta = PdfReader(str(path)).metadata
            return (meta.title or "") if meta else ""
    except Exception as exc:  # a broken original must not stop the build
        log.warning("could not read title of %s: %s", path.name, exc)
    return ""


def list_documents(cfg: dict) -> tuple[list[Doc], dict]:
    """Step 1: every Parsed/*.md joined with the CSV and the originals (manifest or Original/)."""
    paths = cfg["paths"]
    meta = {row["id"]: row for row in read_csv_rows(paths["metadata_csv"])}
    manifest = load_manifest(paths.get("originals_manifest"))
    original_dir: Path = paths["original_dir"]
    originals = (
        {f.stem: f for f in original_dir.iterdir() if f.is_file()} if original_dir.is_dir() else {}
    )

    docs: list[Doc] = []
    no_metadata: list[str] = []
    for md_path in sorted(paths["parsed_dir"].glob("*.md")):
        doc_id = md_path.stem
        row = meta.get(doc_id)
        if row is None:
            no_metadata.append(doc_id)
            continue
        raw = md_path.read_bytes()
        doc = Doc(
            doc_id=doc_id,
            md_path=md_path,
            text=raw.decode("utf-8", errors="replace"),
            genre=row.get("genre", ""),
            language=row.get("language", ""),
            sha256=hashlib.sha256(raw).hexdigest(),
        )
        man = manifest.get(doc_id, {})
        doc.original_ext, doc.original_bytes, doc.original_title = man.get("ext"), man.get("bytes"), man.get("title", "")
        if doc_id in originals:  # real files win over the manifest
            orig = originals[doc_id]
            doc.original_path = orig
            doc.original_ext = orig.suffix.lstrip(".").lower()
            doc.original_bytes = orig.stat().st_size
            doc.original_title = doc.original_title or read_original_title(orig)
        docs.append(doc)

    file_ids = {d.doc_id for d in docs}
    stats = {
        "csv_rows": len(meta),
        "csv_rows_without_file": len(set(meta) - file_ids),
        "md_files_without_metadata": no_metadata,
        "originals_source": "Original/ folder" if originals else ("manifest" if manifest else "none"),
        "docs_without_original_info": sorted(d.doc_id for d in docs if d.original_bytes is None),
    }
    return docs, stats


# --------------------------------------------------------------------------- 2. junk + duplicates
def mark_junk_and_duplicates(docs: list[Doc]) -> list[list[str]]:
    """Step 2: flag scraped boilerplate as junk; keep the first ID of exact duplicates."""
    by_hash: dict[str, list[Doc]] = defaultdict(list)
    for doc in docs:
        by_hash[doc.sha256].append(doc)
    duplicate_groups = []
    for group in by_hash.values():
        if len(group) >= JUNK_MIN_GROUP:
            for doc in group:
                doc.is_junk = True
        elif len(group) > 1:
            keep, *others = sorted(group, key=lambda d: d.doc_id)
            for doc in others:
                doc.duplicate_of = keep.doc_id
            duplicate_groups.append([keep.doc_id] + [d.doc_id for d in others])
    for doc in docs:
        if len(doc.text) < JUNK_MAX_CHARS and JUNK_MARKER in doc.text:
            doc.is_junk = True
    return duplicate_groups


# --------------------------------------------------------------------------- 3. title
_BAD_TITLES = {"untitled", "powerpoint presentation", "title", "document", "untitled document"}
_FILE_EXT = re.compile(r"\.(indd|docx?|pptx?|xlsx?|pdf|qxd|ai|rtf)\s*$", re.I)
_SITE_SUFFIX_MAX = 45


def clean_title(raw: str) -> str:
    """Unescape entities and strip site-name suffixes ('Title | MSF', 'Title | MSF Medical Guidelines')."""
    title = collapse(html.unescape(raw or ""))
    while " | " in title:
        head, tail = title.rsplit(" | ", 1)
        if not head.strip() or len(tail) > _SITE_SUFFIX_MAX:
            break
        title = head.strip()
    return title


def usable_title(title: str) -> bool:
    """Reject empty, generic or file-name titles ('untitled', 'Financial Report pms 032C.indd')."""
    return (
        len(title) >= 4
        and title.lower() not in _BAD_TITLES
        and not _FILE_EXT.search(title)
        and not title.lower().startswith("microsoft ")
        and bool(_LETTER.search(title))
    )


# Front-matter lines of PDF articles/reports that are never a title.
_BOILERPLATE_LINE = re.compile(
    r"^(?:©|\(c\)|www\.|https?:|"
    r"(?:copyright|presented by|conflict of interest|this (?:article|is an open)|published|received|"
    r"accepted|doi|vol(?:ume)?\.?\s*\d|journal of|correspondence|open access|research article|"
    r"original (?:article|research)|s u p p l e m e n t|supplement|page\s*\d|contents|table of contents|"
    r"abstract|summary|keywords?|the authors?|authors?|editorial|issn|isbn)\b)",
    re.I,
)
_MIN_FALLBACK_WORDS = 3
_MIN_FALLBACK_CHARS = 15
_TITLE_SCAN_LINES = 40


def _fallback_title_ok(line: str) -> bool:
    """A first-line title must look like a phrase, not a page number, header or byline."""
    digits = sum(ch.isdigit() for ch in line)
    return (
        usable_title(line)
        and len(line) >= _MIN_FALLBACK_CHARS
        and len(line.split()) >= _MIN_FALLBACK_WORDS
        and not _BOILERPLATE_LINE.match(line)
        and digits <= 0.2 * len(line)
        and "et al" not in line
    )


def title_from_markdown(md: str) -> tuple[str, str]:
    """First Markdown heading, else the first phrase-like line (bullets/markup/boilerplate skipped)."""
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    for line in lines:
        if _HEADING_LINE.match(line):
            candidate = collapse(to_plain(line))
            if usable_title(candidate):
                return candidate, "md_heading"
    plain = [collapse(to_plain(_BULLET_PREFIX.sub("", ln))) for ln in lines[:_TITLE_SCAN_LINES]]
    for candidate in plain:
        if _fallback_title_ok(candidate):
            return candidate, "first_line"
    for candidate in plain:  # last resort: anything with letters
        if usable_title(candidate):
            return candidate, "first_line"
    return "", "none"


def pick_title(doc: Doc) -> None:
    """Step 3: original title (manifest / file) -> first Markdown heading -> first text line."""
    title = clean_title(doc.original_title)
    if usable_title(title):
        doc.title, doc.title_source = truncate(title, TITLE_MAX), "original"
        return
    title, source = title_from_markdown(fix_ligatures(doc.text))
    doc.title, doc.title_source = truncate(title or doc.doc_id, TITLE_MAX), source


# --------------------------------------------------------------------------- 4. groups
def assign_groups(doc: Doc, cfg: dict) -> None:
    """Step 4: genre -> primary group, plus secondary groups (config.yaml groups/secondary)."""
    for group, genres in cfg["groups"].items():
        if doc.genre in genres:
            doc.group_primary = group
            break
    doc.groups_secondary = list(cfg.get("secondary", {}).get(doc.genre, []))


# --------------------------------------------------------------------------- 5. countries
class CountryMatcher:
    """Dictionary matcher: longest alias first, word boundaries, diacritics ignored.

    One big alternation sorted by length: at any position the longest alias wins and
    the matched text is consumed, so 'South Sudan' never also counts as 'Sudan' and
    'Nigeria' never counts as 'Niger'. ALL-CAPS short aliases (DRC, CAR) are
    case-sensitive. Arabic aliases accept the attached prefixes و ف ب ك ل.
    """

    _AR_PREFIX = "(?:[وفبكل]{1,2})?"

    def __init__(self, path: Path = COUNTRIES_FILE):
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for code, info in data.items():
            if code.startswith("_"):
                continue
            for alias in info["aliases"]:
                case_sensitive = alias.isupper() and len(alias) <= 4
                entries.append((fold(alias), code, case_sensitive))
        entries.sort(key=lambda e: -len(e[0]))
        self.lookup_cs = {a: c for a, c, cs in entries if cs}
        self.lookup_ci = {a.casefold(): c for a, c, cs in entries if not cs}
        self.re_cs = self._compile([a for a, _, cs in entries if cs], 0)
        self.re_ci = self._compile([a for a, _, cs in entries if not cs], re.IGNORECASE)

    @classmethod
    def _compile(cls, aliases: list[str], flags: int) -> re.Pattern:
        alternation = "|".join(r"\s+".join(re.escape(w) for w in a.split()) for a in aliases)
        return re.compile(rf"(?<!\w){cls._AR_PREFIX}({alternation})(?!\w)", flags)

    def find(self, text: str) -> list[str]:
        """ISO-2 codes mentioned in ``text``, most mentioned first."""
        folded = fold(text)
        counts: Counter[str] = Counter()
        for m in self.re_cs.finditer(folded):
            counts[self.lookup_cs[" ".join(m.group(1).split())]] += 1
        for m in self.re_ci.finditer(folded):
            counts[self.lookup_ci[" ".join(m.group(1).split()).casefold()]] += 1
        return [code for code, _ in counts.most_common(MAX_COUNTRIES)]


# --------------------------------------------------------------------------- 5b. language check
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
_LATIN_WORD = re.compile(r"[a-zà-ÿ]+")
_FUNCTION_WORDS = {
    "en": set("the and of to in is that for with as are was on by this be from or at which have an not were has".split()),
    "fr": set("le la les des et est une dans pour que qui du au sur par pas avec sont ce aux plus ont été cette".split()),
    "es": set("el la los las del y en que por con para una es se al su lo como más fue sus son ha".split()),
}


def detect_language(text: str) -> str | None:
    """Cheap document-level check: Arabic script ratio, else most frequent function words.

    Used only to flag disagreements with documentation.csv; the CSV stays authoritative.
    Returns None when there is too little text to decide.
    """
    sample = text[:30_000]
    n_ar, n_lat = len(_ARABIC.findall(sample)), len(_LATIN.findall(sample))
    if n_ar + n_lat < 200:
        return None
    if n_ar > 0.3 * (n_ar + n_lat):
        return "ar"
    words = _LATIN_WORD.findall(sample.lower())
    hits = {lang: sum(1 for w in words if w in fw) for lang, fw in _FUNCTION_WORDS.items()}
    best = max(hits, key=hits.get)
    return best if hits[best] >= 20 else None


# --------------------------------------------------------------------------- 6. keywords
_STOP_FR = set("""
au aux avec ce ces cet cette dans de des du elle elles en et eux il ils je la le les leur leurs lui
ma mais me même mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses son sur ta
te tes toi ton tu un une vos votre vous est sont été être avoir ont fait faire plus peut comme aussi
tout tous toutes entre sans sous selon après avant chez dont lors ainsi alors donc car très bien
deux trois cas non oui leurs celle celui ceux cela ceci quand depuis encore autre autres
""".split())
_STOP_ES = set("""
el la los las un una unos unas de del al y o u e en con por para sin sobre entre es son fue ser
estar está están ha han hay se su sus lo le les que qui como más pero muy ya también todo todos
este esta estos estas ese esa eso nos nuestro nuestra cuando donde desde hasta porque cual cuales
otro otra otros otras dos tres puede pueden según durante ante tras así sí no
""".split())
_STOP_AR = set("""
في من على إلى الى عن مع هذا هذه ذلك تلك التي الذي الذين أن إن ان كان كانت يكون لا ما لم لن قد
ثم أو او و هو هي هم نحن كل بعد قبل بين حتى عند منذ خلال حيث كما أي اي أيضا ايضا غير بعض
""".split())
_STOP_ALL = {"msf", "médecins", "medecins", "frontières", "frontieres", "sans", "https", "http", "www",
             "com", "org", "html", "pdf", "أطباء", "بلا", "حدود"}


_INLINE_CITATION = re.compile(r"\[\d+\]\s*Citation\s*\d+\.[^\n]*", re.I)
_REFERENCE_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:\[?\d{1,3}[.)\]]\s*\S.*|.*\[Accessed[^\]]*\].*|.*\bdoi\b.*)$",
                             re.I | re.M)


def strip_references(text: str) -> str:
    """Drop citation lines and inline 'Citation n. ...' notes (keyword extraction only)."""
    return _REFERENCE_LINE.sub(" ", _INLINE_CITATION.sub(" ", text))


def extract_keywords(docs: list[Doc]) -> None:
    """Step 6: TF-IDF per language, top N terms per searchable document.

    Documents are grouped by detected language when available (the CSV mislabels a
    few, e.g. P22 is French but tagged 'en'), so the right stop-word list is used.
    """
    import numpy as np
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    stop_by_lang = {"en": set(ENGLISH_STOP_WORDS), "fr": _STOP_FR, "es": _STOP_ES, "ar": _STOP_AR}
    by_lang: dict[str, list[Doc]] = defaultdict(list)
    for doc in docs:
        if doc.searchable:
            by_lang[doc.language_detected or doc.language].append(doc)
    for lang, items in by_lang.items():
        vectorizer = TfidfVectorizer(
            stop_words=sorted(stop_by_lang.get(lang, set()) | _STOP_ALL),
            token_pattern=r"(?u)\b[^\W\d_]{3,}\b",
            max_df=0.5 if len(items) >= 10 else 1.0,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(
            [to_plain(strip_references(fix_ligatures(d.text[:KEYWORD_SCAN_CHARS]))) for d in items]
        )
        terms = vectorizer.get_feature_names_out()
        for i, doc in enumerate(items):
            row = matrix.getrow(i)
            order = np.argsort(-row.data)[:N_KEYWORDS]
            doc.keywords = [str(terms[j]) for j in row.indices[order]]
    by_id = {d.doc_id: d for d in docs}
    for doc in docs:
        if doc.duplicate_of:
            doc.keywords = list(by_id[doc.duplicate_of].keywords)


# --------------------------------------------------------------------------- 7. summary
def _is_noise_line(line: str) -> bool:
    """Lines skipped by the summary: headings, bare bullets, links/URLs only, citations."""
    if _HEADING_LINE.match(line):
        return True
    bare = collapse(to_plain(_BULLET_PREFIX.sub("", line)))
    return not _LETTER.search(bare) or bool(_CITATION_LINE.match(line))


def extract_summary(md: str) -> str:
    """Step 7: the first 2-3 real sentences (> 40 chars), at most 300 chars. Purely extractive."""
    sentences: list[str] = []
    for block in re.split(r"\n\s*\n", md):
        lines = [_BULLET_PREFIX.sub("", ln.strip()) for ln in block.splitlines() if ln.strip()]
        lines = [ln for ln in lines if not _is_noise_line(ln)]
        if not lines:
            continue
        for sentence in split_sentences(collapse(to_plain(" ".join(lines)))):
            if len(sentence) > SUMMARY_MIN_SENTENCE and _LETTER.search(sentence):
                sentences.append(sentence)
        if len(sentences) >= 3:
            break
    summary = ""
    for sentence in sentences[:3]:
        candidate = f"{summary} {sentence}".strip()
        if len(candidate) > SUMMARY_MAX:
            summary = summary or truncate(sentence, SUMMARY_MAX)
            break
        summary = candidate
    return summary


# --------------------------------------------------------------------------- 8. chunks
def split_blocks(md: str) -> list[tuple[str | None, str]]:
    """Split on blank lines and before headings. Returns (current section heading, block)."""
    blocks: list[tuple[str | None, str]] = []
    heading: str | None = None
    for raw in re.split(r"\n\s*\n", md):
        buf: list[str] = []
        for line in raw.splitlines():
            if _HEADING_LINE.match(line.strip()):
                if "".join(buf).strip():
                    blocks.append((heading, "\n".join(buf).strip()))
                heading = collapse(to_plain(line))
                buf = [line.strip()]
            else:
                buf.append(line)
        if "".join(buf).strip():
            blocks.append((heading, "\n".join(buf).strip()))
    return blocks


def split_long(text: str, limit: int) -> list[str]:
    """Split a block longer than ``limit``: by sentences, then lines, then words."""
    if len(text) <= limit:
        return [text]
    for splitter in (split_sentences, lambda t: t.splitlines(), lambda t: t.split(" ")):
        units = [u for u in splitter(text) if u.strip()]
        if len(units) > 1:
            break
    else:  # one giant token: hard cut
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    parts, current = [], ""
    for unit in units:
        if len(unit) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.extend(split_long(unit, limit))
        elif not current:
            current = unit
        elif len(current) + 1 + len(unit) <= limit:
            current = f"{current} {unit}"
        else:
            parts.append(current)
            current = unit
    if current:
        parts.append(current)
    return parts


def overlap_tail(text: str, overlap: int) -> str:
    """The last ``overlap`` characters of ``text``, starting at a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return ""
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :].strip() if space != -1 else tail.strip()


def chunk_text(md: str, size: int, overlap: int) -> list[tuple[str | None, str]]:
    """Step 8: pack blocks into ~``size``-char chunks with ~``overlap`` chars of overlap.

    A chunk never ends on a lone heading line (the heading moves to the next chunk).
    Returns (section heading, chunk text) pairs in document order.
    """
    pieces = [(h, p) for h, block in split_blocks(md) for p in split_long(block, size - overlap - 2)]
    chunks: list[tuple[str | None, str]] = []
    current: list[str] = []
    current_heading: str | None = None
    has_new = False

    def length() -> int:
        return sum(len(p) for p in current) + 2 * max(len(current) - 1, 0)

    for heading, piece in pieces:
        if has_new and length() + 2 + len(piece) > size:
            carry = []
            if len(current) > 1 and _HEADING_LINE.match(current[-1]):
                carry = [current.pop()]
            body = "\n\n".join(current)
            chunks.append((current_heading, body))
            tail = overlap_tail(body, overlap)
            current = ([tail] if tail else []) + carry
            current_heading, has_new = (heading if carry else None), bool(carry)
        if not has_new:
            current_heading = heading
        current.append(piece)
        has_new = True
    if has_new:
        chunks.append((current_heading, "\n\n".join(current)))
    return chunks


# --------------------------------------------------------------------------- 9. write catalog
def write_catalog(docs: list[Doc], out_path: Path, build_meta: dict) -> int:
    """Step 9: write documents, chunks and both FTS5 indexes into a fresh catalog.sqlite."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = db.connect(tmp)
    db.init_catalog(conn)
    chunk_id = 0
    with conn:
        for doc in docs:
            conn.execute(
                """INSERT INTO documents (doc_id, title, title_source, genre, language, language_detected,
                   group_primary, groups_secondary, countries, keywords, summary, text_bytes, original_bytes,
                   original_ext, sha256, is_junk, duplicate_of, version, n_chunks)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (doc.doc_id, doc.title, doc.title_source, doc.genre, doc.language, doc.language_detected,
                 doc.group_primary,
                 json.dumps(doc.groups_secondary), json.dumps(doc.countries),
                 json.dumps(doc.keywords, ensure_ascii=False), doc.summary, len(doc.text.encode("utf-8")),
                 doc.original_bytes, doc.original_ext, doc.sha256, int(doc.is_junk), doc.duplicate_of,
                 len(doc.chunks)),
            )
            for ord_, (heading, text) in enumerate(doc.chunks):
                chunk_id += 1
                conn.execute(
                    "INSERT INTO chunks (chunk_id, doc_id, ord, heading, text) VALUES (?,?,?,?,?)",
                    (chunk_id, doc.doc_id, ord_, heading, text),
                )
            if doc.searchable:
                conn.execute(
                    "INSERT INTO cards_fts (doc_id, title, summary, keywords) VALUES (?,?,?,?)",
                    (doc.doc_id, doc.title, doc.summary, " ".join(doc.keywords)),
                )
        conn.execute("INSERT INTO chunks_fts(rowid, text) SELECT chunk_id, text FROM chunks")
        conn.executemany(
            "INSERT INTO catalog_meta (key, value) VALUES (?, ?)",
            [(k, json.dumps(v, ensure_ascii=False)) for k, v in build_meta.items()],
        )
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')")
    conn.commit()  # the INSERT above opens an implicit transaction; VACUUM needs none
    conn.execute("VACUUM")
    conn.close()
    os.replace(tmp, out_path)
    return chunk_id


# --------------------------------------------------------------------------- 11. cloud store
def copy_cloud_store(docs: list[Doc], cloud_store: Path) -> dict:
    """Step 11: copy every text (and original, if present) to what the cloud server serves."""
    text_dir, orig_dir = cloud_store / "text", cloud_store / "original"
    text_dir.mkdir(parents=True, exist_ok=True)
    n_orig = 0
    for doc in docs:
        shutil.copyfile(doc.md_path, text_dir / f"{doc.doc_id}.md")
        if doc.original_path:
            orig_dir.mkdir(parents=True, exist_ok=True)
            dest = orig_dir / f"{doc.doc_id}.{doc.original_ext}"
            if not dest.exists() or dest.stat().st_size != doc.original_bytes:
                shutil.copyfile(doc.original_path, dest)
            n_orig += 1
    return {"texts": len(docs), "originals": n_orig,
            "originals_mode": "real files" if n_orig else "placeholders of the real size (served by cloud/server.py)"}


# --------------------------------------------------------------------------- 12. report
def mb(n_bytes: float) -> float:
    return round(n_bytes / 1e6, 1)


def build_report(docs: list[Doc], dup_groups: list[list[str]], list_stats: dict, n_chunks: int,
                 catalog_path: Path, cloud: dict | None, seconds: float, cfg: dict) -> dict:
    searchable = [d for d in docs if d.searchable]
    non_junk = [d for d in docs if not d.is_junk]
    groups_all = Counter(d.group_primary or "UNMAPPED" for d in docs)
    return {
        "documents": len(docs),
        "junk": sum(d.is_junk for d in docs),
        "duplicates": sum(1 for d in docs if d.duplicate_of),
        "duplicate_groups": dup_groups,
        "searchable_documents": len(searchable),
        "csv_rows": list_stats["csv_rows"],
        "csv_rows_without_file_ignored": list_stats["csv_rows_without_file"],
        "md_files_without_metadata": list_stats["md_files_without_metadata"],
        "originals_source": list_stats["originals_source"],
        "docs_per_group": dict(groups_all.most_common()),
        "unmapped_genres": sorted({d.genre for d in docs if not d.group_primary}),
        "docs_per_group_searchable": dict(Counter(d.group_primary for d in searchable).most_common()),
        "docs_per_language": dict(Counter(d.language for d in docs).most_common()),
        "csv_language_disagreements": sorted(
            f"{d.doc_id}: csv={d.language} text={d.language_detected}"
            for d in non_junk if d.language_detected and d.language_detected != d.language
        ),
        "share_non_junk_with_country": round(sum(1 for d in non_junk if d.countries) / max(len(non_junk), 1), 3),
        "top_countries": dict(Counter(c for d in non_junk for c in d.countries).most_common(10)),
        "title_sources": dict(Counter(d.title_source for d in docs).most_common()),
        "chunks": n_chunks,
        "text_mb_all": mb(sum(len(d.text.encode("utf-8")) for d in docs)),
        "text_mb_non_junk": mb(sum(len(d.text.encode("utf-8")) for d in non_junk)),
        "originals_mb": mb(sum(d.original_bytes or 0 for d in docs)),
        "catalog_sqlite_mb": mb(catalog_path.stat().st_size),
        "embeddings": "disabled (search.use_embeddings: false)" if not cfg["search"].get("use_embeddings")
        else "not built yet (Task 10)",
        "cloud_store": cloud,
        "build_seconds": round(seconds, 1),
    }


def print_report(rep: dict) -> None:
    print("\n=================== CATALOG REPORT ===================")
    print(f"documents ............ {rep['documents']}  (CSV rows {rep['csv_rows']}, "
          f"{rep['csv_rows_without_file_ignored']} without a file ignored)")
    print(f"junk ................. {rep['junk']}")
    print(f"duplicates ........... {rep['duplicates']}  {rep['duplicate_groups']}")
    print(f"searchable ........... {rep['searchable_documents']}")
    print(f"groups (all docs) .... {rep['docs_per_group']}")
    print(f"groups (searchable) .. {rep['docs_per_group_searchable']}")
    if rep["unmapped_genres"]:
        print(f"UNMAPPED GENRES ...... {rep['unmapped_genres']}")
    print(f"languages ............ {rep['docs_per_language']}  (from documentation.csv)")
    print(f"CSV language vs text . {len(rep['csv_language_disagreements'])} disagree: "
          f"{rep['csv_language_disagreements']}")
    print(f"with a country ....... {rep['share_non_junk_with_country']:.0%} of non-junk docs; "
          f"top: {rep['top_countries']}")
    print(f"titles from .......... {rep['title_sources']}")
    print(f"chunks ............... {rep['chunks']}")
    print(f"text ................. {rep['text_mb_non_junk']} MB non-junk ({rep['text_mb_all']} MB all)")
    print(f"originals ............ {rep['originals_mb']} MB  (source: {rep['originals_source']})")
    print(f"catalog.sqlite ....... {rep['catalog_sqlite_mb']} MB  (documents + chunks + FTS5)")
    print(f"embeddings ........... {rep['embeddings']}")
    print(f"cloud store .......... {rep['cloud_store']}")
    print(f"build time ........... {rep['build_seconds']} s")
    print("======================================================")


# --------------------------------------------------------------------------- main
def build(cfg: dict, copy_store: bool = True) -> dict:
    started = time.time()
    missing = missing_inputs(cfg)
    if missing:
        raise SystemExit("Missing inputs:\n  " + "\n  ".join(missing))
    search_cfg = cfg["search"]

    docs, list_stats = list_documents(cfg)
    log.info("listed %d documents (%s for originals)", len(docs), list_stats["originals_source"])
    dup_groups = mark_junk_and_duplicates(docs)
    log.info("junk=%d duplicates=%d", sum(d.is_junk for d in docs), sum(1 for d in docs if d.duplicate_of))

    matcher = CountryMatcher()
    for doc in docs:
        pick_title(doc)
        assign_groups(doc, cfg)
        if doc.is_junk:
            continue
        clean = fix_ligatures(doc.text)
        doc.language_detected = detect_language(to_plain(clean))
        doc.countries = matcher.find(to_plain(clean[:COUNTRY_SCAN_CHARS]))
        doc.summary = extract_summary(clean)
        if doc.searchable:
            doc.chunks = chunk_text(clean, int(search_cfg["chunk_chars"]), int(search_cfg["chunk_overlap"]))
    log.info("titles, groups, countries, summaries and chunks done")

    extract_keywords(docs)
    log.info("keywords done")

    build_meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "catalog_version": 1,
        "chunk_chars": search_cfg["chunk_chars"],
        "chunk_overlap": search_cfg["chunk_overlap"],
        "fts_tokenizer": "unicode61 remove_diacritics 2",
        "countries_semantics": "mentioned in text (dictionary match), not verified applicability",
        "embedding_model": search_cfg.get("model") if search_cfg.get("use_embeddings") else None,
    }
    catalog_path = cfg["paths"]["catalog_db"]
    n_chunks = write_catalog(docs, catalog_path, build_meta)
    log.info("wrote %s (%d chunks)", catalog_path, n_chunks)

    if search_cfg.get("use_embeddings"):
        log.warning("search.use_embeddings is true but the embedding step is Task 10: skipped for now")

    cloud = copy_cloud_store(docs, cfg["paths"]["cloud_store"]) if copy_store else None
    report = build_report(docs, dup_groups, list_stats, n_chunks, catalog_path, cloud, time.time() - started, cfg)
    report_path = cfg["paths"]["work_dir"] / "catalog_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", help="path to config.yaml (default: repo root)")
    parser.add_argument("--no-copy", action="store_true", help="skip copying files to data/cloud_store")
    args = parser.parse_args()
    report = build(load(args.config), copy_store=not args.no_copy)
    print_report(report)


if __name__ == "__main__":
    main()
