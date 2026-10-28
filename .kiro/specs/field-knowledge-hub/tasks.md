# Implementation Plan

Do the tasks in order. Each task ends with a check: run it and show the output before marking the task done. P0 = must have for the demo, P1 = should have, P2 = nice to have.

- [ ] 1. Project setup (P0, ~10 min)
  - Create the folders from structure.md with empty `__init__.py` files.
  - Write common/config.py: load config.yaml, apply env overrides D4GC_DATA_ROOT / D4GC_METADATA_CSV, and resolve paths with pathlib.
  - Check: `python -c "from common.config import load; c=load(); print(c['paths'])"` prints existing paths.
  - _Requirements: all_

- [ ] 2. Preprocessing and catalog (P0, ~25 min)
  - Implement preprocess/build_catalog.py per PROJECT_SPEC section 6, with `search.use_embeddings` respected (start with false).
  - Create preprocess/countries.json (about 40 countries, en/fr/es/ar aliases, word boundaries, longest names first).
  - Use the SQLite schema of PROJECT_SPEC 7.1 (hub/db.py).
  - Check: the report shows 582 docs, 18 junk, 3 duplicates, and medical 300 / field_ops 130 / communications 132 / admin_legal 20.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 3. Search module and hub API core (P0, ~20 min)
  - common/search.py: BM25 on chunks + cards (subquery for bm25 + GROUP BY), query escaping, RRF, boosts, confidence, filters.
  - hub/app.py: /status, /search, /catalog/cards, /catalog/doc/{id}, /docs/{id}/text, /docs/{id}/original.
  - Check (PROJECT_SPEC 8.1): from group medical, "treatment of pulmonary tuberculosis" has P21 in the top 3; "child malaria treatment" has no Financial Report in the top 5; "paramedics killed in Lebanon" returns D17e499ac0a first.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ] 4. Cache planner and hub dashboard (P0, ~20 min)
  - hub/planner.py per PROJECT_SPEC 7.3 (p_need, cost_missing, value, priority, core and reserve passes, reasons).
  - POST /admin/budget, GET /admin/plan; hub/static/hub.html with the budget slider (20–450 MB), the stacked storage bar and the plan table.
  - Check: at 150 MB the clinical guidelines that fit are in core; moving to 50 MB visibly changes the tiers.
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 5. Device agents and device UI (P0, ~20 min)
  - hub/manifests.py per 7.4; device/agent.py (own SQLite + files folder, sync loop, local BM25 search, "disconnect from hub" toggle); device.html with availability badges; run_all.py starting cloud, hub and 4 devices.
  - Check: medical-1 holds the medical texts + guideline originals; disconnecting the hub still returns results with the offline banner.
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 6. Cloud server and request flow (P1, ~15 min)
  - cloud/server.py (throttled, Range support); hub/upstream.py state machine (PROJECT_SPEC 10.2); requests panel in hub.html; Internet ON/OFF toggle.
  - Check: internet ON → an uncached original downloads with a progress bar; internet OFF → the text opens and options with ETA and cost appear.
  - _Requirements: 5.1, 5.2_

- [ ] 7. Access control (P1, ~10 min)
  - hub/access.py: log_and_allow + needs_approval for restricted genres, access_log, approve/reject buttons.
  - Check: comms-1 opening a Financial Report → AWAITING_APPROVAL in the hub UI.
  - _Requirements: 6.1_

- [ ] 8. Evaluation (P1, ~15 min)
  - eval/eval_search.py and eval/simulate_cache.py per PROJECT_SPEC 13; save results to data/eval/*.csv and the chart PNG.
  - Check: the metrics table and the chart file are produced.
  - _Requirements: 7.1, 7.2_

- [ ] 9. LoRa relay simulation (P2, ~15 min)
  - common/lora_codec.py (struct formats, 51-byte limit) and hub/relay_sim.py (nodes A, R1, R2, R3, B, C; TTL 3; beacons); relay panel with byte log.
  - Check: with internet OFF and relay ON, a 15-byte WHO_HAS goes A→R1→R2→B and an I_HAVE comes back.
  - _Requirements: 5.3_

- [ ] 10. Embeddings on (P2, ~10 min)
  - Set use_embeddings: true, rebuild, re-run eval.
  - Check: the cross-language test finds P22 for the English P21 query; report hybrid vs BM25.
  - _Requirements: 1.4, 2.1, 7.1_
