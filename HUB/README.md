# D4GC_Buffet_Destroyers: MSF Field Knowledge Hub

Data 4 Good Challenge 2026 (Emergent × Doctors Without Borders).

An offline-first document retrieval system for MSF missions:
- a **hub** at the mission base holds the full index, the text of every document, and a subset of the originals chosen by a cost model under a storage budget;
- **staff devices** on the local network keep only what their group needs, but can still find every document;
- missing files come from the **central server** when internet is available, or a tiny query goes over a **volunteer LoRa relay** network to neighbouring hubs.

Full design: [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md). Build tasks: [`.kiro/specs/field-knowledge-hub/tasks.md`](.kiro/specs/field-knowledge-hub/tasks.md).

## Data (not in this repo)

The MSF documents are **not committed** (the repo is public). Put the data pack in `./data_raw/` (gitignored):

```
data_raw/Parsed/*.md              # text of the 582 documents
data_raw/documentation.csv        # id, genre, language
data_raw/originals_manifest.csv   # id, original_ext, original_bytes, original_title
```
The original PDFs/HTML (403 MB) are not needed: sizes and titles come from the manifest. If you have them, put them in `data_raw/Original/` and they are used instead.

## Demo quick start (proof of concept)

```bash
source .venv/bin/activate                 # Windows: .venv\Scripts\Activate.ps1
python preprocess/build_catalog.py        # ~10 s, builds data/catalog.sqlite from data_raw/
python run_all.py                         # hub + simulated devices/cloud/LoRa on http://127.0.0.1:8000
```
In Kiro, open port 8000 from the PORTS tab.

What the demo shows (one process; devices, cloud downloads and the LoRa relay are simulated):
- **Search**: BM25 on chunks + doc cards, Reciprocal Rank Fusion, group/intent boosts, same-language bonus, confidence filter ("no confident match"), per-result "Why this rank?" and honest metadata warnings. Role selector = the 4 staff devices.
- **Access control**: out-of-group opens are logged; Financial Reports need hub-operator approval (Requests tab).
- **Emergency Mode**: extractive only. Shows the exact source passage and citation, always labelled UNVERIFIED (the dataset has no validation records), with the safe fallback message.
- **Hub storage**: budget slider (20–450 MB) runs the cost model; core/reserve tiers with a one-line reason per document.
- **Requests & LoRa relay**: internet ON → simulated download with progress; internet OFF → text still readable, 15-byte WHO_HAS flooded over the relay, options with ETA and cost.

Not built yet: embeddings (cross-language search), separate device processes, login/JWT, voice, evaluation scripts.

## Setup (Kiro / Linux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python preprocess/build_catalog.py   # builds data/catalog.sqlite (once)
python run_all.py                    # cloud :9000, hub :8000, devices :8101-8104
```
Windows: `py -m venv .venv` then `.venv\Scripts\Activate.ps1`.

Hub dashboard: http://localhost:8000. Devices: http://localhost:8101 to 8104 (in Kiro, open them from the PORTS tab).
