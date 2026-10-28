---
inclusion: always
---
# Tech rules

- Python 3.11+, FastAPI + Uvicorn, SQLite with FTS5 (built-in sqlite3), NumPy, PyYAML, httpx, scikit-learn, BeautifulSoup, pypdf. Optional: sentence-transformers with model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- Front end: plain HTML + vanilla JS + CSS in hub/static/. No build step, no CDN at runtime (the demo must work offline). Copy any JS library into static/.
- OS is Windows: use pathlib everywhere; paths contain spaces ("D4GC data"). Give PowerShell commands, not bash.
- Every path, weight, budget and port comes from config.yaml (loaded by common/config.py). Env vars D4GC_DATA_ROOT and D4GC_METADATA_CSV override the data paths.
- NEVER copy MSF documents, the CSV, generated .sqlite/.npy files or the data/ folder into git. Generated files go in ./data (gitignored).
- SQLite gotcha: bm25() cannot be used directly with GROUP BY; rank chunks in a subquery first (see PROJECT_SPEC 8.1). Lower bm25() = better.
- Escape user queries before FTS5 MATCH (quote each term) so punctuation never crashes search.
- Small, documented functions; log every state change with a timestamp. The jury reads the code.
- After each task, run the task's "check" and show the output before marking it done.
