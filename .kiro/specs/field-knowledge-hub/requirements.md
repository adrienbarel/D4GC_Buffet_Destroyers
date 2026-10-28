# Requirements: Field Knowledge Hub

Source of truth: docs/PROJECT_SPEC.md. This file restates the requirements in Kiro format.

## 1. Catalog and preprocessing
**User story:** As the team, we want one clean catalog of the 582 MSF documents so that search and caching work on reliable data.
1.1 WHEN build_catalog.py runs THEN it SHALL read Parsed/*.md, Original/*.pdf|html and documentation.csv, and ignore CSV rows with no file.
1.2 The system SHALL mark the 18 identical scraped-menu files as is_junk and the 3 exact duplicate pairs with duplicate_of.
1.3 The system SHALL store per doc: title, genre, language, primary/secondary group, countries (ISO-2), 10 keywords, a ≤300-char extractive summary, text and original sizes, sha256.
1.4 The system SHALL build FTS5 indexes on chunks and on doc cards, and optionally multilingual embeddings.
1.5 It SHALL print a report (counts per group/language, junk, duplicates, index sizes in MB).

## 2. Hub search
**User story:** As a doctor, I want to type a question and get the right documents, in any of the 4 languages, with few wrong results.
2.1 WHEN a query is sent to /search THEN the hub SHALL combine BM25 and (if enabled) vector results with Reciprocal Rank Fusion.
2.2 The hub SHALL boost the requester's group and clinical guidelines for clinical-intent queries, and demote financial/legal docs for them.
2.3 IF no result passes min_confidence THEN the hub SHALL return no_confident_match = true.
2.4 Each result SHALL show availability (device / hub / text-only / cloud) and access status.

## 3. Cache planning on the hub
**User story:** As a mission logistician, I want the hub to keep the most useful originals within a storage budget, and to explain why.
3.1 The hub SHALL always keep the index and the text of all non-junk documents.
3.2 The hub SHALL fill a core tier by value per MB and a reserve tier by total value (expensive-to-fetch docs), per PROJECT_SPEC 7.3.
3.3 WHEN the budget slider changes THEN the plan SHALL be recomputed and each document SHALL show a one-line reason.

## 4. Devices
**User story:** As a staff member, I want my device to hold only my group's documents, but still find everything.
4.1 Each device SHALL sync a manifest from the hub: all cards, its group's texts, then its group's originals within its budget.
4.2 Restricted genres SHALL never be stored on devices of other groups.
4.3 IF the hub is unreachable THEN the device SHALL search its local cards and texts with BM25 and show an offline banner.

## 5. Getting missing documents
**User story:** As a doctor, if the original is not available, I want to read the text now and get the original as fast and cheaply as possible.
5.1 IF internet is ON THEN the hub SHALL download the original from the cloud server with visible progress.
5.2 IF internet is OFF THEN the hub SHALL serve the text immediately and show the options (wait, satellite, neighbour hub, courier) with ETA and cost.
5.3 IF the relay is ON THEN the hub SHALL send a WHO_HAS message (≤51 bytes) over the simulated LoRa network and show the replies.

## 6. Access and confidentiality
6.1 Every device SHALL see every card. Opening an out-of-group doc SHALL be logged, and restricted genres SHALL need approval in the hub UI.

## 7. Evaluation
7.1 eval_search.py SHALL report Recall@1, Recall@5, MRR (BM25 vs hybrid), the cross-language P21→P22 test and the false-positive rejection rate.
7.2 simulate_cache.py SHALL report the device/hub/upstream hit rates vs budget for our planner and 2 baselines, and save a PNG chart.
