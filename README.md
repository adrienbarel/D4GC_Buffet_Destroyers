# D4GC_Buffet_Destroyers: MSF Field Knowledge Hub

Data 4 Good Challenge 2026 (Emergent × Doctors Without Borders).

An offline-first document retrieval system for MSF missions:
- a **hub** at the mission base holds the full index, the text of every document, and a subset of the originals chosen by a cost model under a storage budget;
- **staff devices** on the local network keep only what their group needs, but can still find every document;
- missing files come from the **central server** when internet is available, or a tiny query goes over a **volunteer LoRa relay** network to neighbouring hubs.

Full design: [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md). Build tasks: [`.kiro/specs/field-knowledge-hub/tasks.md`](.kiro/specs/field-knowledge-hub/tasks.md).

## Data (not in this repo)

The MSF documents are **not committed** (the repo is public, and the files are 400+ MB). Each teammate keeps them locally and points to them:

- either edit `paths` in `config.yaml`,
- or set environment variables (PowerShell):
  ```powershell
  $env:D4GC_DATA_ROOT = "C:\path\to\D4GC data\D4GC data"   # folder with Original\ and Parsed\
  $env:D4GC_METADATA_CSV = "C:\path\to\documentation.csv"
  ```

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python preprocess/build_catalog.py   # builds data/catalog.sqlite (once)
python run_all.py                    # cloud :9000, hub :8000, devices :8101-8104
```

Hub dashboard: http://localhost:8000. Devices: http://localhost:8101 to 8104.
