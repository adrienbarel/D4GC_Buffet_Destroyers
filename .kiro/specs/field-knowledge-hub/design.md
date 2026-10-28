# Design: Field Knowledge Hub

The full design is in **docs/PROJECT_SPEC.md**. Read the matching section before each task:

| Topic | PROJECT_SPEC section |
|---|---|
| Architecture diagram, what makes it different | 2 |
| Data facts (582 docs, junk, duplicates, groups, measured search problems) | 3 |
| File layout and stack | 4 |
| config.yaml | 5 (already in repo root) |
| Preprocessing steps | 6 |
| SQLite schema, storage tiers, cost model and planner, device manifests, access | 7 |
| Hub API endpoints and search algorithm | 8 |
| LoRa relay simulation and binary message formats | 9 |
| Cloud server and request state machine | 10 |
| Hub and device UIs | 11 |
| Evaluation | 13 |
| Demo script | 14 |

## Key decisions
- The index is separated from the content: every device knows every document exists.
- All text (21 MB) always stays on the hub; only originals (403 MB) are rationed.
- Two cache tiers: core = value per MB, reserve = total value (insurance for expensive misses).
- Hybrid search (FTS5 BM25 + multilingual MiniLM) fused with RRF, group/intent boosts, and a confidence cut-off for false positives.
- Devices are separate processes (device/agent.py) reusing common/search.py, so offline device search is real, not faked.
- LoRa is simulated in-process with real byte-level message encoding (≤51 bytes).
