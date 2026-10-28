# MSF Field Knowledge Hub: Project Specification

**For:** the AI coding assistant in VS Code (and the team).
**Event:** Data 4 Good Challenge 2026 (Emergent × Doctors Without Borders), pitch at 18:30.
**Goal of this file:** describe everything needed to build a working demo of the **hub side** of an offline-first document retrieval system. Build in the order of Section 12, and stop after any step if time runs out. Each step ends with a check that tells you it works.

> **How to use this file with the coding AI.** Open this file in VS Code and tell the AI: *"Read PROJECT_SPEC.md. Implement Step N only (Section 12). Follow the file layout in Section 4 and the config in Section 5. When done, run the check for Step N and show me the output."* Do one step at a time.

---

## 1. The problem in one paragraph

MSF teams work in places with poor or no internet, limited storage and limited computing power. Doctors and staff still need to find the right document fast (a clinical guideline, a project report, a statement) with few false positives. No single vendor may be required. Preprocessing can happen off-site; retrieval must work on-site. (Source: the D4GC challenge document, sections 1, 6 and 7.)

## 2. Our solution in one paragraph

A **hub** (one laptop or mini-server at the mission base) holds a **search index of every document** in the collection, the **text of every document**, and a **chosen subset of the original files** (PDF/HTML), selected by a cost model under a storage budget. **Staff devices** on the mission's local network sync from the hub and keep only what their **staff group** needs. A device can still *find* any document through the index. If the file is not on the device, the hub serves it. If the hub doesn't have it either, the hub fetches it from the **central cloud server** when internet is available. When there is no internet, the hub sends a **tiny query over a volunteer LoRa relay network** to nearby hubs ("who has document X? who has internet?"). It then offers the cheapest way to get it: wait for internet, use the satellite data link, or send someone to drive and collect it.

```
                        ┌──────────────────────────┐
                        │  CENTRAL CLOUD SERVER     │  all originals, master catalog
                        │  (port 9000 in the demo)  │
                        └────────────▲─────────────┘
                     internet (when available) │  satellite data link (expensive)
                                     │
  ┌─────────────┐  LoRa relay   ┌────┴─────────────────────────────┐
  │ Neighbour   │◄─────────────►│  MISSION HUB  (port 8000)         │
  │ hub B / C   │  volunteer    │  • full index + all text (21 MB)  │
  │ (simulated) │  DIY relays   │  • originals chosen by cost model │
  └─────────────┘  ≤51-byte msgs│  • hybrid search (BM25+semantic)  │
                                │  • request queue + access control │
                                └────▲─────────▲─────────▲─────────┘
                                     │ local Wi-Fi / LAN (always on)
                         ┌───────────┴┐  ┌─────┴──────┐  ┌┴───────────┐ ...
                         │ Device     │  │ Device     │  │ Device     │
                         │ medical-1  │  │ field_ops-1│  │ comms-1    │
                         │ (8101)     │  │ (8102)     │  │ (8103)     │
                         └────────────┘  └────────────┘  └────────────┘
```

**What makes it different (for the "Creativity" score):**
1. **The index and the content are separate.** Nobody is ever blind, because every device can see that a document exists, even offline.
2. **A two-tier cache built from a cost model.** The *core* tier maximises hits per MB. The *reserve* tier keeps documents that are less likely to be needed but very expensive to fetch later ("just in case").
3. **Text first, original later.** The parsed text of the whole collection is only 21 MB, against 403 MB for the originals. So the hub always holds all text, and only the heavy originals are rationed. A missing original can still be read as text immediately.
4. **A volunteer LoRa relay network** for tiny "who has it?" messages, which turns neighbouring missions into a shared cache.

---

## 3. What the data looks like (measured on our folder)

Folder on Adrien's laptop: `C:\Users\adrie\Documents\D4FG\D4GC data\D4GC data\`

| Item | Value |
|---|---|
| Documents | **582** (each one has an original + a parsed `.md`, same ID) |
| Originals | `Original/` folder: `.pdf` (241) and `.html` (341). **403 MB** total, median 242 KB, largest 46 MB |
| Parsed text | `Parsed/` folder: `.md`. **21 MB** total, median 6.6 KB, largest 1.8 MB |
| Metadata | `documentation.csv` (one level up, in `D4FG\`): columns `id, genre, language`. It has 764 rows; **182 rows have no file** and must be ignored |
| Languages | en 470, ar 51, fr 44, es 17 |
| Genres | 25 genres in the files: Peer-reviewed Article 216, Clinical Guideline Chapter 70, Press Release 61, Project Update 38, Statement 38, Activity Report Chapter 34, Voices from the Field 25, Interview 12, Financial Report 11, … |
| Location | **No location column.** Countries must be extracted from the text; about 2/3 of documents name at least one country (most common: Sudan, DR Congo, Gaza/Palestine, South Sudan, Kenya, Lebanon, Nigeria, Haiti) |
| Titles | Only 128 of 582 `.md` files have a Markdown heading, so the title must come from the original (HTML `<title>`, PDF metadata) or the first text line |
| Dates | No date column |
| **Junk** | **18 files are identical** (a scraped web menu: "Latest News … Get Involved!"). Example: `D4d679068a9.md`. Mark them `is_junk` |
| **Duplicates** | 3 exact duplicate pairs: `P44`=`Dbd6e2ef149`, `P42`=`Da68d33c442`, `P16`=`D5da0aed2fd`. Keep one, mark the other `duplicate_of` |

**Things we measured that shape the design:**
- **Plain keyword search is not enough.** We tested BM25 (SQLite FTS5) on the raw chunks. For "treatment of pulmonary tuberculosis", four research articles rank above the clinical guideline `P21`. For "child malaria treatment", a **Financial Report** (`D3eb698da05`) ranks first, a clear false positive. This is why Section 8.1 adds a group/intent boost and a confidence threshold.
- **The same content exists in several languages.** `P22` is the French version of `P21` ("La tuberculose pulmonaire…"). An English query can only find `P22` with the multilingual model, so this pair is a perfect cross-language demo and test.
- **Exact keyword match works well for news.** "paramedics killed in Lebanon" finds `D17e499ac0a` first, with a score twice as high as the next result.

**Staff groups (decided).** Genre decides the primary group:

| Group | Genres | Docs | Text | Originals |
|---|---|---|---|---|
| `medical` | Clinical Guideline Chapter, Peer-reviewed Article, Study Protocol, Scientific Publication Notice, Scientific News, Field Study, Operational Research Essay, Research Policy, Research Governance Document, Evaluation Methodology Guide | 300 | ~7 MB | ~186 MB |
| `field_ops` | Project Update, Activity Report Chapter, Report, Evaluation Report, Timeline, Voices from the Field, First-person Field Account, Historical Case Study, Summary | 130 | ~9.5 MB | ~67 MB |
| `communications` | Press Release, Statement, Interview, Speech, Opinion, Op-Ed, Advocacy Brief, Critical Essay | 132 | ~1.7 MB | ~38 MB |
| `admin_legal` | Financial Report, Legal Encyclopedia Entry | 20 | ~2.9 MB | ~111 MB |

Note that `admin_legal` has only 20 documents but 111 MB of originals (big financial PDFs). This is a good example of why the **size cost** must be in the score.

**Secondary groups.** A document is also somewhat relevant (weight 0.3) to these groups:
- Clinical Guideline Chapter → `field_ops`
- Project Update, Activity Report Chapter → `communications`
- Press Release, Statement → `field_ops`
- Legal Encyclopedia Entry → `field_ops`, `communications`

---

## 4. File layout

Create this structure (repository root = `hub-project/`):

```
hub-project/
├── README.md                    # how to install and run (Windows PowerShell commands)
├── requirements.txt
├── config.yaml                  # ALL paths, budgets, weights, groups, mission profile (Section 5)
├── run_all.py                   # starts cloud (9000), hub (8000), 4 devices (8101-8104)
├── common/
│   ├── config.py                # loads config.yaml
│   ├── search.py                # BM25 (SQLite FTS5) + optional embeddings + fusion; used by hub AND devices
│   └── lora_codec.py            # pack/unpack of the tiny binary relay messages (Section 9)
├── preprocess/
│   ├── build_catalog.py         # Section 6: data/catalog.sqlite + data/embeddings.npy + data/cloud_store/
│   └── countries.json           # country aliases in en/fr/es/ar -> ISO code
├── cloud/
│   └── server.py                # Section 10: the "central server", serves catalog + files, throttled
├── hub/
│   ├── app.py                   # FastAPI app, all hub endpoints (Section 8)
│   ├── db.py                    # hub SQLite schema + helpers (Section 7)
│   ├── planner.py               # cost model + cache planner (Section 7.3)
│   ├── manifests.py             # what each device should hold (Section 7.4)
│   ├── upstream.py              # request queue, fetch from cloud, fallback options (Section 10)
│   ├── relay_sim.py             # simulated volunteer LoRa network (Section 9)
│   ├── access.py                # group-based access rules + access log
│   └── static/
│       ├── hub.html             # hub dashboard (Section 11.1)
│       ├── device.html          # device UI (Section 11.2), served by each device agent
│       ├── app.js
│       └── style.css
├── device/
│   └── agent.py                 # one device = one process with its own SQLite + files folder
├── eval/
│   ├── eval_search.py           # Section 13.1
│   └── simulate_cache.py        # Section 13.2
└── data/                        # generated; not committed
    ├── catalog.sqlite           # master catalog (built offline)
    ├── embeddings.npy           # chunk embeddings (int8 or float16)
    ├── cloud_store/             # copy of all originals + texts = what the cloud serves
    ├── hub_store/               # what the hub holds
    └── devices/<device_id>/     # what each device holds
```

**Stack:** Python 3.11+, FastAPI + Uvicorn, SQLite (built into Python) with FTS5, NumPy, PyYAML, httpx (HTTP client), scikit-learn (TF-IDF keywords), sentence-transformers (embeddings, optional). Front end: plain HTML + vanilla JS + CSS, no build step. Copy any JS library into `static/` so the demo works with no internet.

`requirements.txt`:
```
fastapi
uvicorn
httpx
pyyaml
numpy
scikit-learn
beautifulsoup4
pypdf
sentence-transformers   # optional: if install fails, set search.use_embeddings: false
```

---

## 5. `config.yaml` (single source of truth)

All weights below are **demo values, not MSF data**. Say so in the pitch. They are meant to be tuned with real usage logs.

```yaml
paths:
  data_root: "C:/Users/adrie/Documents/D4FG/D4GC data/D4GC data"   # contains Original/ and Parsed/
  metadata_csv: "C:/Users/adrie/Documents/D4FG/documentation.csv"
  work_dir: "./data"

ports: { cloud: 9000, hub: 8000, devices_start: 8101 }

mission:                      # mission profile = solves the "day one, no history" problem
  name: "Demo mission - Sudan / South Sudan"
  countries: ["SD", "SS"]
  languages: ["en", "ar"]
  staff: { medical: 6, field_ops: 3, communications: 1, admin_legal: 1 }

devices:                      # simulated devices started by run_all.py
  - { id: medical-1,  group: medical,        budget_mb: 25 }
  - { id: fieldops-1, group: field_ops,      budget_mb: 25 }
  - { id: comms-1,    group: communications, budget_mb: 25 }
  - { id: admin-1,    group: admin_legal,    budget_mb: 25 }

hub:
  budget_mb: 150              # changed live with the slider in the hub UI
  core_share: 0.7             # 70% of the originals budget = core tier, 30% = reserve tier
  reserve_min_p_need: 0.05    # reserve tier ignores near-irrelevant docs

groups:                       # genre -> primary group (Section 3); secondary listed separately
  medical: ["Clinical Guideline Chapter", "Peer-reviewed Article", "Study Protocol",
            "Scientific Publication Notice", "Scientific News", "Field Study",
            "Operational Research Essay", "Research Policy", "Research Governance Document",
            "Evaluation Methodology Guide"]
  field_ops: ["Project Update", "Activity Report Chapter", "Report", "Evaluation Report",
              "Timeline", "Voices from the Field", "First-person Field Account",
              "Historical Case Study", "Summary"]
  communications: ["Press Release", "Statement", "Interview", "Speech", "Opinion", "Op-Ed",
                   "Advocacy Brief", "Critical Essay"]
  admin_legal: ["Financial Report", "Legal Encyclopedia Entry"]
secondary:
  "Clinical Guideline Chapter": [field_ops]
  "Project Update": [communications]
  "Activity Report Chapter": [communications]
  "Press Release": [field_ops]
  "Statement": [field_ops]
  "Legal Encyclopedia Entry": [field_ops, communications]
relevance: { primary: 1.0, secondary: 0.3, other: 0.05 }

urgency:                      # how bad it is to NOT have the doc when needed (1 = normal)
  "Clinical Guideline Chapter": 3.0
  "Study Protocol": 1.5
  "Peer-reviewed Article": 1.2
  default: 1.0

boosts:
  mission_country: 1.0        # +100% if the doc mentions a mission country
  mission_language: 0.5       # +50% if the doc language is a mission language
  popularity_half_life_days: 14

links:                        # PLACEHOLDER costs, replace with real MSF numbers
  internet:  { available_probability: 0.3, cost_per_mb: 0.0, seconds_per_mb: 4 }
  satellite: { cost_per_mb: 5.0, seconds_per_mb: 20 }      # BGAN/VSAT-type data link
  courier:   { fixed_cost: 60.0, fixed_hours: 6 }          # someone drives to another hub
  relay:     { max_payload_bytes: 51, hop_delay_s: 2, ttl: 3 }

search:
  use_embeddings: true
  model: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
  chunk_chars: 1200
  chunk_overlap: 150
  max_embedded_chunks_per_doc: 40
  bm25_top_k: 50
  vector_top_k: 50
  rrf_k: 60
  min_confidence: 0.35        # below this, show "no confident match" (limits false positives)
  boosts:                     # Section 8.1 step 4
    same_group: 1.3
    secondary_group: 1.1
    guideline_clinical_intent: 1.5
    admin_clinical_intent: 0.5
  clinical_intent_words: [treatment, dose, dosage, diagnosis, management, protocol, symptoms,
                          child, adult, traitement, posologie, diagnostic, tratamiento, dosis, "علاج", "جرعة"]

access:
  out_of_group_policy: "log_and_allow"   # or "needs_approval"
  restricted_genres: ["Financial Report"] # always needs approval outside admin_legal
```

---

## 6. Preprocessing (`preprocess/build_catalog.py`), done once, off-site

Input: `Original/`, `Parsed/`, `documentation.csv`. Output: `data/catalog.sqlite`, `data/embeddings.npy`, `data/chunk_ids.npy`, and `data/cloud_store/` (a copy of every original + text = the cloud's content).

Step by step:

1. **List documents.** Take every `Parsed/*.md`. ID = file name without extension. Find the matching original (`.pdf` or `.html`) in `Original/`. Join with the CSV on `id` and ignore CSV rows with no file.
2. **Clean.** Compute the SHA-256 of each `.md`.
   - **Junk:** if 4 or more files share a hash, or the text is under 2,000 chars and contains "Get Involved", set `is_junk = 1`. Junk is kept in the catalog but never indexed, cached or shown.
   - **Duplicates:** for other identical hashes, keep the first ID and set `duplicate_of` on the others.
3. **Title.**
   - For HTML originals, use `<title>` from BeautifulSoup and strip " | MSF" style suffixes.
   - For PDFs, use the `pypdf` metadata title if it is longer than 5 chars.
   - Otherwise use the first Markdown heading, or else the first non-empty line with bullet marks removed. Cut to 120 chars.
4. **Group.** Map `genre` → primary group and secondary groups from config.
5. **Countries.** Search the text (first 20,000 chars) for the aliases in `countries.json`. Store a list of ISO-2 codes, ordered by count, at most 5.
   - `countries.json` holds about 40 countries where MSF often works, each with English, French and Spanish names plus Arabic names for the Middle East / North Africa ones. Include common aliases: "DRC", "DR Congo", "RDC", "Gaza", "Palestine", "Territoires palestiniens", "السودان", "غزة", "لبنان", "اليمن", "سوريا".
   - Watch out: "Niger" must not match inside "Nigeria", and "Sudan" must not match inside "South Sudan". Use word boundaries, and match the longer names first and remove them from the text before matching the shorter ones.
6. **Keywords.** Run TF-IDF (scikit-learn, one vectorizer per language, using the built-in English stop words and small stop-word lists for fr/es) and keep the top 10 terms per document.
7. **Summary (extractive).** Take the first 2–3 sentences of the text that are longer than 40 chars, skipping lines that are only bullets, links or citations. Limit to 300 chars.
8. **Chunks.** Split the text on blank lines and headings, then pack the pieces into chunks of about 1,200 chars with 150 chars of overlap. Keep the chunk order number. (Expect about 17,000 chunks in total.)
9. **Full-text index.** Create the SQLite FTS5 tables (schema in 7.1) with `tokenize = 'unicode61 remove_diacritics 2'`, which works for en/fr/es and for space-separated Arabic words.
10. **Embeddings (if enabled).** Embed the title plus summary as one "doc card" vector, and up to 40 chunks per document. That gives about 7,500 vectors of dimension 384. Normalise them and save as float16 (about 6 MB). This takes a few minutes on a laptop CPU, so print progress.
11. **Copy to the cloud store:** `data/cloud_store/original/<id>.<ext>` and `data/cloud_store/text/<id>.md`.
12. **Print a report:** document count, junk and duplicate counts, docs per group, docs per language, and the share of docs with countries. Also print the index sizes (FTS DB, embeddings) in MB. These numbers go on a pitch slide.

**Check:** `python preprocess/build_catalog.py` prints 582 docs, 18 junk, 3 duplicates, and 4 groups with the counts in Section 3, without errors.

---

## 7. Hub data model and logic

### 7.1 SQLite schema (`hub/db.py`, also used for `catalog.sqlite`)

```sql
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY, title TEXT, genre TEXT, language TEXT,
  group_primary TEXT, groups_secondary TEXT,      -- JSON list
  countries TEXT, keywords TEXT, summary TEXT,    -- JSON lists / text
  text_bytes INTEGER, original_bytes INTEGER, original_ext TEXT,
  sha256 TEXT, is_junk INTEGER DEFAULT 0, duplicate_of TEXT, version INTEGER DEFAULT 1
);
CREATE TABLE chunks (chunk_id INTEGER PRIMARY KEY, doc_id TEXT, ord INTEGER, text TEXT);
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='chunk_id',
  tokenize='unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE cards_fts USING fts5(doc_id UNINDEXED, title, summary, keywords,
  tokenize='unicode61 remove_diacritics 2');      -- "index-only" search, tiny, copied to devices

-- hub-only tables
CREATE TABLE hub_store (doc_id TEXT PRIMARY KEY, has_text INTEGER, has_original INTEGER,
  tier TEXT,                                      -- 'text_only' | 'core' | 'reserve'
  score_p_need REAL, score_cost_missing REAL, score_priority REAL, updated_at TEXT);
CREATE TABLE devices (device_id TEXT PRIMARY KEY, grp TEXT, budget_mb REAL, url TEXT,
  last_seen TEXT, manifest_version INTEGER);
CREATE TABLE device_holdings (device_id TEXT, doc_id TEXT, has_text INTEGER, has_original INTEGER,
  PRIMARY KEY (device_id, doc_id));
CREATE TABLE views (doc_id TEXT, device_id TEXT, ts TEXT);
CREATE TABLE requests (req_id INTEGER PRIMARY KEY, doc_id TEXT, device_id TEXT, want TEXT,
  reason TEXT, status TEXT, path TEXT, eta_s REAL, cost_estimate REAL,
  created_at TEXT, updated_at TEXT, log TEXT);    -- log = JSON list of {ts, msg}
CREATE TABLE access_log (ts TEXT, device_id TEXT, doc_id TEXT, action TEXT, allowed INTEGER, reason TEXT);
CREATE TABLE relay_log (ts TEXT, msg_id INTEGER, src TEXT, dst TEXT, type TEXT, bytes INTEGER, hex TEXT, note TEXT);
```

### 7.2 Storage tiers on the hub

| Tier | Contents | Size |
|---|---|---|
| Always | `catalog.sqlite` (index, cards, chunks, FTS) + embeddings + **text of all non-junk docs** | about 21 MB of text + about 15 MB of index |
| `core` | Originals with the best **priority per MB** | `core_share` × (budget − always) |
| `reserve` | Originals with the highest **expected cost if missing**, from the docs not chosen for core | the rest of the budget |
| not cached | Everything else: the original is fetched from the cloud on request | 0 |

If the budget is smaller than the "always" tier, show a warning in the UI and keep only the index + the text of the highest-priority docs.

### 7.3 Cost model and planner (`hub/planner.py`)

For every non-junk, non-duplicate document *d*:

**1. Probability it will be needed at this mission**

```
relevance(d, g) = 1.0 if g is d's primary group, 0.3 if secondary, 0.05 otherwise
share(g)        = staff[g] / total_staff                     (from mission profile)
base(d)         = Σ_g share(g) × relevance(d, g)
mission(d)      = 1 + 1.0 × [d mentions a mission country] + 0.5 × [d.language in mission languages]
popularity(d)   = 1 + ln(1 + decayed_views(d))     decayed_views = Σ 0.5^(age_days / 14) over views
p_need(d)       = base(d) × mission(d) × popularity(d)        then rescale so max = 1
```

**2. Cost if it is missing when needed** (expected cost of fetching the original later)

```
size_mb         = original_bytes / 1e6
fetch(d)        = p_inet × (inet.seconds_per_mb × size_mb / 3600 × hour_value)
                + (1 − p_inet) × min( satellite.cost_per_mb × size_mb ,  courier.fixed_cost )
cost_missing(d) = urgency(genre) × fetch(d)       (hour_value: config, default 10)
```

**3. Value and priority**

```
value(d)    = p_need(d) × cost_missing(d)            # expected loss avoided by caching d
priority(d) = value(d) / size_mb                      # value per MB (knapsack density)
```

**4. Filling the budget (greedy knapsack, two passes)**

1. `B = budget_mb − always_tier_mb`. `B_core = core_share × B`. `B_reserve = B − B_core`.
2. **Core pass:** sort by `priority` (highest first) and add originals while they fit in `B_core`. Skip any doc that doesn't fit and try the next one.
3. **Reserve pass:** from the remaining docs with `p_need ≥ reserve_min_p_need`, sort by `value` (not per MB). This favours big, important, expensive-to-fetch files. Add them while they fit in `B_core leftover + B_reserve`.
4. Write the results to `hub_store` with the tier and the three scores, so the UI can explain every decision. **Every row must say why it is there.**
5. Return a summary: MB per tier, docs per tier, docs per group, and the top 10 of each tier.

**Re-planning** happens when the slider changes, the mission profile changes, or once every N new views. The planner only *decides*. `upstream.py` then downloads any newly chosen originals (when internet is available) and deletes the ones that were dropped.

### 7.4 Device manifests (`hub/manifests.py`)

Each device has a group and a budget (default 25 MB). The hub computes its manifest:

1. **Always:** the **cards index** (title + summary + keywords + availability of every non-junk doc, about 0.5 MB). The device can search the whole collection by title and summary even if the hub goes down.
2. **Text** of the documents where `relevance(d, group) = 1.0`, in order of `p_need` (computed with `share = 1` for this group only), until 40% of the budget is used. For example, all ~7 MB of medical text fits in a 25 MB medical device.
3. **Originals** of the group's docs in order of `priority`, until the budget is full. For the medical group, clinical guidelines come first because of their urgency.
4. **Never** put documents from `restricted_genres` on a device of another group.

The device polls `GET /manifest/{device_id}` every 30 s (or when the user clicks "Sync"). It downloads what is missing, deletes what was dropped, and reports its holdings with `POST /devices/{id}/holdings`.

### 7.5 Access control (`hub/access.py`), for confidentiality

- **Everyone can see the card** of every non-junk document: title, summary, genre, language, size, and where it is available.
- **Opening a document** of the device's own group (primary or secondary) is allowed.
- **Opening a document outside the group:**
  - With `log_and_allow`, it opens and a row is written in `access_log`, shown in the hub UI.
  - With `needs_approval`, a request with status `AWAITING_APPROVAL` is created, and the hub operator approves or rejects it in the hub UI.
- **`restricted_genres`** always need approval outside their group.
- Every open, request, approval and denial goes in `access_log`.

---

## 8. Hub API (`hub/app.py`, port 8000)

All JSON. The device agents and the two web pages use only these endpoints.

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | redirect to `/static/hub.html` |
| GET | `/status` | hub state: internet on/off, relay on/off, budget, MB used per tier, counts, pending requests |
| POST | `/admin/connectivity` | `{internet: bool, relay: bool}`: the demo toggles |
| POST | `/admin/budget` | `{budget_mb}`: runs the planner, returns its summary |
| GET | `/admin/plan` | current plan: every doc with its tier, scores and reason |
| POST | `/admin/mission` | change mission countries/languages/staff, then re-plan |
| GET | `/catalog/cards?since_version=` | the cards index (for device sync) |
| GET | `/catalog/doc/{id}` | the full card of one doc + availability (`device?/hub_text/hub_original/cloud_only`) |
| POST | `/search` | `{q, device_id, filters:{language, group, country, genre}, k:10}` → results (Section 8.1) |
| GET | `/docs/{id}/text?device_id=` | the text, after the access check |
| GET | `/docs/{id}/original?device_id=` | the original file (FileResponse), after the access check; 404 + `{"fetchable": true}` if not on the hub |
| POST | `/requests` | `{doc_id, device_id, want: "original"\|"text", reason}` → creates a request (Section 10) |
| GET | `/requests` / `/requests/{id}` | list / one request with its log |
| POST | `/requests/{id}/choose` | `{path: "wait_internet"\|"satellite"\|"courier"\|"neighbour_hub"}` when offline |
| POST | `/requests/{id}/approve` / `/reject` | for access approval |
| POST | `/devices/register` | `{device_id, group, budget_mb, url}` |
| GET | `/manifest/{device_id}` | list of `{doc_id, want_text, want_original, version}` |
| POST | `/devices/{id}/holdings` | what the device holds now |
| POST | `/events/view` | `{doc_id, device_id}`: feeds popularity |
| GET | `/relay/log` | the last relay messages (for the animation) |
| POST | `/relay/query` | manually ask the network "who has doc X?" (demo button) |

### 8.1 Search algorithm (`common/search.py`)

1. **BM25** on `chunks_fts` with `bm25(chunks_fts)` → top 50 chunks. Also run it on `cards_fts` → top 50 docs. Escape the user's query (quote each term) so punctuation can't break the FTS syntax.
2. **Vector** (if enabled): embed the query with the same multilingual model, take the cosine against the doc-card and chunk vectors, and keep the top 50. Because the model is multilingual, **an English query can find French, Spanish and Arabic documents.**
3. Collapse chunks to **document level** (best chunk per doc), then combine the rankings with **Reciprocal Rank Fusion**: `score(d) = Σ_lists 1 / (60 + rank_list(d))`.
   - **SQLite gotcha:** `bm25()` cannot be used directly with `GROUP BY`. Rank the chunks in a subquery first: `SELECT doc_id, MIN(s) FROM (SELECT c.doc_id, bm25(chunks_fts) AS s FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.rowid WHERE chunks_fts MATCH ? ORDER BY s LIMIT 200) GROUP BY doc_id ORDER BY MIN(s)`. Note that a lower `bm25()` value is better.
4. **Group and intent boost** (fixes the false positives measured in Section 3). Multiply the fused score:
   - by **1.3** if the doc's primary group equals the requesting device's group (by 1.1 if secondary);
   - by **1.5** for genre `Clinical Guideline Chapter` when the query has a clinical-intent word (`treatment, dose, dosage, diagnosis, management, protocol, symptoms, child, adult, traitement, posologie, diagnostic, tratamiento, dosis, علاج, جرعة`);
   - by **0.5** for `Financial Report` and `Legal Encyclopedia Entry` when the query has a clinical-intent word.
   Put these numbers in `config.yaml` under `search.boosts`, and show the applied boost in the result's debug info.
5. **Confidence** = the best cosine for that doc (or a normalised BM25 if embeddings are off). Drop results below `min_confidence`. If nothing is left, return `"no_confident_match": true` and the top 3 as "maybe". **This is how we limit false positives.**
6. Apply the filters, exclude junk and duplicates, and return the top k with: `doc_id, title, genre, language, countries, snippet` (the best chunk with the query terms in bold), `score, confidence, availability`, and `access` (`allowed` | `log` | `needs_approval`).
7. On a **device with no hub**, the same module runs BM25 only, on the local `cards_fts` + the chunks of the docs it holds.

**Checks** (from the medical device):
- `"treatment of pulmonary tuberculosis"` → `P21` in the **top 3** (without the boost it is only 5th).
- With embeddings on, the same query also returns **`P22`** (the French version) in the top 10.
- `"child malaria treatment"` → **no** Financial Report in the top 5.
- `"paramedics killed in Lebanon"` → `D17e499ac0a` first.

---

## 9. Volunteer LoRa relay (`hub/relay_sim.py` + `common/lora_codec.py`), simulated

**Idea.** Volunteers build cheap DIY LoRa relay nodes (for example an ESP32 with a LoRa radio and an antenna on a roof or a hill). The relays forward tiny messages between mission hubs. A relay never carries documents, only "who has it?" and "who has internet?".

**Simulated network** (in config or hard-coded for the demo):

```
HUB_A (us) ── R1 ── R2 ── HUB_B (neighbour mission, has a cache: a random 40% of originals)
                    └──── R3 ── HUB_C (has internet now and then: toggle in the UI)
```
Each hop adds `hop_delay_s` (2 s). Messages are **flooded with a TTL of 3** and duplicates are dropped by `msg_id`. Each node is an object in memory with its own clock (asyncio tasks). A message is refused if it is larger than **51 bytes**, the maximum application payload at the slowest, longest-range LoRaWAN data rate (DR0 = SF12/125 kHz) in the EU 868 MHz band. Our relay protocol is not LoRaWAN, but this is a safe, sourced limit to design for.

**Message formats** (`lora_codec.py`, big-endian, `struct`):

| Type | Byte layout | Size |
|---|---|---|
| `0x01 WHO_HAS` | type(1) src(2) msg_id(2) ttl(1) doc_hash(8) want(1: 0=text, 1=original) | 15 B |
| `0x02 I_HAVE` | type(1) src(2) reply_to(2) flags(1: bit0 text, bit1 original, bit2 internet) size_kb(2) | 8 B |
| `0x03 BEACON` | type(1) src(2) seq(2) flags(1: bit0 internet, bit1 accepts_courier) index_version(4) | 10 B |
| `0x04 FETCH_FOR_ME` | type(1) src(2) msg_id(2) doc_hash(8) deliver_via(1: 0=satellite, 1=internet-mirror) | 14 B |

`doc_hash` = the first 8 bytes of SHA-256(doc_id). Hub IDs are 2-byte integers. Every hub sends a `BEACON` every 30 s (simulated), so "does hub C have internet right now?" is usually already known **without any query**.

The hub UI shows each message as a line: time, from → to, type, **byte count**, hex. This shows the jury how small the messages are.

---

## 10. Getting a document the hub doesn't have (`hub/upstream.py` + `cloud/server.py`)

### 10.1 Cloud server (port 9000)
- `GET /catalog/version`, `GET /catalog/delta?since=`: for catalog updates (in the demo, the version is fixed at 1).
- `GET /files/{doc_id}/text` and `/files/{doc_id}/original`, with HTTP **Range** support (resumable downloads) and a **throttle** (default 300 KB/s, so download progress is visible in the demo).

### 10.2 Request lifecycle (state machine)

```
NEW
 ├─ access check fails ──────────────► AWAITING_APPROVAL ─► (approve) NEW | (reject) REJECTED
 ├─ hub has it ──────────────────────► DELIVERED  (the device downloads from the hub)
 └─ hub lacks it
     ├─ internet ON ─────────────────► DOWNLOADING (progress %) ─► ON_HUB ─► DELIVERED
     └─ internet OFF
         ├─ text missing? never: the hub always holds all text, so it is served immediately
         ├─ relay ON  ─► RELAY_QUERY (WHO_HAS sent) ─► RELAY_ANSWERED (who has it / who has internet)
         └─ relay OFF or no answer ─► OPTIONS_READY
                                      operator/device picks a path:
                                        wait_internet  → QUEUED (auto-starts when internet returns)
                                        satellite      → DOWNLOADING (slow, cost shown)
                                        neighbour_hub  → COURIER_TICKET (who, where, file list, SHA-256)
                                        courier        → COURIER_TICKET
```

For **OPTIONS_READY**, compute for each path an **ETA** and a **cost** from `links` in the config and the file size, and show them side by side. For example, for a 12 MB PDF:
- wait for internet: unknown ETA, free
- satellite: about 4 min, cost 60
- courier from Hub B: about 6 h, cost 60

Then recommend one: the lowest cost whose ETA fits the urgency. Clinical guidelines get a shorter allowed ETA.

**Key point to show:** while the original is missing, **the text version is already readable** from the hub, because the hub always holds all text.

A **courier ticket** is a small JSON record (and printable page): `{ticket_id, from_hub, to_hub, docs:[{doc_id, sha256, size}], created_at}`. At the other hub, the files are copied to a USB key. On return, the hub checks the SHA-256 of each file before accepting it.

---

## 11. User interfaces (plain HTML + JS, polling `/status` every 2 s)

### 11.1 Hub dashboard (`/static/hub.html`)
1. **Top bar:** the mission name, plus big toggles **Internet ON/OFF** and **LoRa relay ON/OFF**, and a toggle for "Hub C has internet".
2. **Storage panel:** a **budget slider (20–450 MB)** that calls `/admin/budget` and shows a stacked bar: always (index + text) / core / reserve / free. Below it, a small table of MB and doc counts per group and per tier.
3. **Plan table:** search box + filter by tier. Each row shows the title, group, size, `p_need`, `cost_missing`, `priority`, the tier, and a one-line **"why"**. Examples: "Clinical guideline, mission country SD, urgency 3", or "Reserve: 22 MB, expensive by satellite".
4. **Devices panel:** one card per device, showing its group, MB used out of its budget, last sync time, and how many docs it holds.
5. **Requests panel:** live list with status, a progress bar, the options with ETA and cost when offline, and approve/reject buttons.
6. **Relay panel:** a simple node diagram (SVG: A–R1–R2–B, R2–R3–C) where nodes flash when a message passes, plus the message log with byte sizes.
7. **Metrics strip:** queries today, and the share answered on the device / hub / upstream. Also the MB downloaded from the cloud and the estimated link cost.

### 11.2 Device page (`device.html`, served by each device agent on 8101–8104)
1. Header: device ID, group, storage used / budget, a hub connection dot, and a **"Disconnect from hub"** toggle (simulates the LAN going down).
2. Search box + language/country filters. The results show a badge:
   - 🟢 **On this device**
   - 🔵 **On hub**
   - 🟠 **Text on hub, original in the cloud**
   - 🔒 **Outside your group** (logged or needs approval)
3. Clicking a result opens the text in a reader panel, with a button to open the original if it is available. Otherwise a **"Request original"** button shows the request status live.
4. When disconnected from the hub, search falls back to the local index (BM25 on cards + local texts), and a banner says "Offline: searching this device only (582 titles, N full texts)".

---

## 12. Build plan, step by step (with time boxes)

Priorities: **P0 = must have for the demo**, **P1 = should have**, **P2 = nice to have**. If you are late, skip P2.

| Step | Time | Priority | What to build | Done when (check) |
|---|---|---|---|---|
| 0 | 10 min | P0 | Create the folders, `requirements.txt`, `config.yaml`, venv. Windows: `py -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt` | `python -c "import fastapi, sqlite3; print(sqlite3.sqlite_version)"` works |
| 1 | 25 min | P0 | `preprocess/build_catalog.py` (Section 6). Start with `use_embeddings: false` and add embeddings after step 2 works | The report prints 582 docs / 18 junk / 3 duplicates / 4 groups |
| 2 | 20 min | P0 | `common/search.py` + `hub/app.py` with `/status`, `/search`, `/catalog/*`, `/docs/*` | The two search checks in 8.1 pass |
| 3 | 20 min | P0 | `hub/planner.py` + `/admin/budget` + `hub.html` storage panel and plan table | Moving the slider changes the core/reserve contents. At 150 MB, all clinical guidelines that fit are in core |
| 4 | 20 min | P0 | `device/agent.py` + `manifests.py` + `device.html` + `run_all.py` | 4 devices sync. The medical device holds medical text + guideline originals. Search badges are correct |
| 5 | 15 min | P1 | `cloud/server.py` + `upstream.py` request flow + requests panel | Request an uncached original with internet ON → progress bar → opens. With internet OFF → options with ETA/cost appear |
| 6 | 15 min | P1 | `access.py` (log + approval) | A comms device opening a Financial Report → AWAITING_APPROVAL in the hub UI |
| 7 | 15 min | P2 | `relay_sim.py` + `lora_codec.py` + relay panel | With internet OFF and relay ON: WHO_HAS (15 B) goes A→R1→R2→B and I_HAVE comes back; the log shows byte sizes |
| 8 | 15 min | P1 | `eval/eval_search.py` + `eval/simulate_cache.py` (Section 13) | The numbers for the pitch slide are printed (and saved as CSV/PNG) |
| 9 | 10 min | P2 | Turn embeddings on and re-run step 1 + eval | Hybrid beats BM25 on the eval, or we report honestly that it doesn't |

**Rules for the coding AI**
- Keep every function small and documented. The jury scores "modular, well-documented codebase".
- No hard-coded paths: everything comes from `config.yaml`.
- No internet access at runtime except hub → cloud on localhost. Vendor any JS library into `static/`.
- Handle Windows paths (`pathlib`) and file names with spaces (`D4GC data`).
- Log every state change to the console with a timestamp.

---

## 13. Evaluation (numbers for the pitch)

### 13.1 Search quality (`eval/eval_search.py`)
There are no labelled queries, so generate them from the documents themselves (the "known-item" method):
- For each non-junk document, make 2 queries:
  - (a) its keywords joined (top 4)
  - (b) a 6–10 word phrase from a random middle sentence, with stop words removed.
- Run the search and record whether the source doc is in the top 1 / top 5. Also record the **reciprocal rank**.
- Report **Recall@1, Recall@5 and MRR** for: BM25 only vs hybrid, and per language.
- **False positives:** also run 50 off-topic queries (for example "football transfer news", "stock price of Apple") and report the **share that correctly returns "no confident match"** at the chosen `min_confidence`.
- **Cross-language test:** query the English first sentence of `P21`. Does the French twin `P22` appear in the top 10? Report this for BM25 vs hybrid. It is a one-line, very visual result for the pitch.
- **Boost test:** report Recall@5 for clinical-guideline docs with and without the group/intent boost.
- Be honest in the pitch: these queries are built from the documents, so the numbers are optimistic compared with real doctor questions.

### 13.2 Cache simulation (`eval/simulate_cache.py`)
- Generate 2,000 synthetic requests: pick a group by staff share, then a document with probability ∝ `relevance × mission boost`. Make **30% of requests uniformly random**, so the test isn't just the planner grading itself.
- For each hub budget in [25, 50, 100, 150, 250, 400] MB, compute the share of original-file requests served **on the device / on the hub / needing upstream**, and the **MB that must be fetched**.
- Compare our planner with two simple baselines: **random fill** and **smallest files first**.
- Save a line chart (`hit rate vs budget`, 3 lines) as a PNG for the slides.

---

## 14. Five-minute demo script

1. **(30 s) The problem:** offline missions, limited storage, need the right document fast.
2. **(60 s) Architecture slide** (diagram from Section 2): index everywhere, text always, originals rationed by a cost model.
3. **(90 s) Live demo:**
   1. On the **medical device**, search "treatment of pulmonary tuberculosis" → the guideline `P21` is on the device 🟢, and its French version `P22` appears too (cross-language).
   2. Search something from field ops → it is on the hub 🔵 and opens in 1 s.
   3. Request a large uncached PDF → with internet ON it downloads with a progress bar.
   4. Turn **internet OFF** and request another → the text opens right away. The relay panel shows a 15-byte WHO_HAS going to Hub B and an I_HAVE coming back, and the options appear with ETA and cost.
   5. Move the **budget slider** from 150 to 50 MB → the plan recomputes and each row explains why it stays.
4. **(45 s) Numbers:** index size in MB, Recall@5 / MRR, false-positive rejection rate, and the hit-rate chart against the baselines.
5. **(15 s) Why it is implementable:** open source only (SQLite, FastAPI, an open model), runs on one laptop, costs almost nothing per query, and LoRa relays are cheap volunteer hardware.

---

## 15. Limits and honest notes (say them before the jury does)

- **Weights and link costs are placeholders.** The cost model is the contribution, and the numbers must be tuned with MSF data.
- **The LoRa relay is simulated.** Real range depends a lot on terrain and antenna height: typically 2–5 km in cities and 5–15 km in rural areas, more with line of sight and hilltop relays.
- **LoRa carries no documents.** In the EU 868 MHz band, each sub-band has a duty-cycle limit: 0.1% or 1% in most sub-bands, which is 86 s or 864 s of transmit time per day. So even "only text" over LoRa would be very slow. One sub-band (869.4–869.65 MHz) allows 10% and up to 500 mW, a good fit for fixed volunteer relays. Other regions have other rules. Documents go over internet, a satellite data link or a courier.
- **Iridium SBD** (340-byte messages) could carry the same tiny queries by satellite where no relay exists, but not files.
- **The multilingual model adds about 450 MB** to the hub install. If that is too much for a site, set `use_embeddings: false` and keyword search still works.
- **Country extraction is a simple dictionary match** and will make some mistakes.

---

## 16. Sources

- Challenge brief: *D4GC Challenge Document – 2026* (sections 1, 3, 6, 7). Local file.
- SQLite FTS5 (full-text search, `bm25()` ranking, `unicode61` tokenizer): https://www.sqlite.org/fts5.html
- Multilingual embedding model (50+ languages, 384 dimensions): https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, SIGIR 2009): https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- FastAPI: https://fastapi.tiangolo.com/
- LoRa range and data rates: https://lora.readthedocs.io/ and https://en.wikipedia.org/wiki/LoRa
- LoRaWAN duty cycle per EU868 sub-band (ETSI EN 300 220-2): https://www.thethingsnetwork.org/docs/lorawan/duty-cycle/
- LoRaWAN EU868 regional parameters (51-byte max payload at DR0, 1% / 10% sub-bands, 500 mW in sub-band P): https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/
- Meshtastic (open-source LoRa mesh, the volunteer-relay model): https://meshtastic.org/ and https://en.wikipedia.org/wiki/Meshtastic
- Iridium SBD message sizes (340 B up / 270 B down): https://patents.justia.com/patent/8676122
- MSF field telecom (HF/VHF radio, BGAN, VSAT, Thuraya in use): https://impactpool.org/jobs/1194346
