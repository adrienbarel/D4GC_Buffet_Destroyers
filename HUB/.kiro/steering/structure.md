---
inclusion: always
---
# Project structure (see docs/PROJECT_SPEC.md section 4)

```
config.yaml, requirements.txt, run_all.py
common/   config.py, search.py, lora_codec.py
preprocess/ build_catalog.py, countries.json
cloud/    server.py                     (port 9000)
hub/      app.py, db.py, planner.py, manifests.py, upstream.py, relay_sim.py, access.py, static/
device/   agent.py                      (ports 8101-8104)
eval/     eval_search.py, simulate_cache.py
data/     generated, gitignored
docs/     PROJECT_SPEC.md
```
Do not create other top-level folders without a reason.
