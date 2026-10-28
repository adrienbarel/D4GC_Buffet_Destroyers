---
inclusion: always
---
# Tech rules

- Python 3.11+, FastAPI + Uvicorn, SQLite with FTS5 (built-in sqlite3), NumPy, PyYAML, httpx, scikit-learn, BeautifulSoup, pypdf. Optional: sentence-transformers with model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Front end: plain HTML + vanilla JS + CSS in hub/static/. No build step, no CDN at runtime (the demo must work offline). Copy any JS library into static/.
- The dev machine is Kiro's Linux workspace: give bash commands. Still use pathlib so the code also runs on Windows laptops.
- Data lives in ./data_raw (gitignored): Parsed/*.md, documentation.csv, originals_manifest.csv. The Original/ PDFs/HTML are NOT available: take original sizes and titles from originals_manifest.csv, and let the cloud server serve a placeholder file of the real size.
- Every path, weight, budget and port comes from config.yaml (loaded by common/config.py). Env vars D4GC_DATA_ROOT and D4GC_METADATA_CSV override the data paths.
- NEVER commit MSF documents, data_raw/, the CSV, generated .sqlite/.npy files or the data/ folder (the repo is public). Generated files go in ./data (gitignored).
- SQLite gotcha: bm25() cannot be used directly with GROUP BY; rank chunks in a subquery first (see PROJECT_SPEC 8.1). Lower bm25() = better.
- Escape user queries before FTS5 MATCH (quote each term) so punctuation never crashes search.
- Small, documented functions; log every state change with a timestamp. The jury reads the code.
- After each task, run the task's "check" and show the output before marking it done.
