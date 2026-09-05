# Correctness foundation verification

Date: 2026-09-05. Runtime: 0.1.0.dev27. Machine schema: 3.27.0-draft1.
Scope: first implementation slice of the 14-item Web-ready checklist.

## Implementation and acceptance

- R01: attribution rejects multiple distinct fact occurrences as ambiguous_fact_binding; duplicate evidence windows at the same occurrence and owner remain valid. Other unambiguous facts survive.
- R02 partial: negated containment remains unclassified; original facts remain intact. Full semantic conflict handling is pending.
- R05 partial: M1/M2 saved requests have credential-free fingerprints; incompatible resume is rejected before new provider calls. Compatible resume rebinds and regrounds saved model output. Explicit offline M2 replay verifies task association and records immutable source lineage; N3 rejects outdated grounding policy.
- R12 partial: declared pytest/jsonschema development dependencies and documented full pytest entry. Clean environment installation and CI remain pending.
- R06 preparation: annotation protocol draft exists; human gold, evaluator and quality thresholds remain pending.

## Verification observed

- Initial targeted regression run: 11 failed / 22 passed; after grounding and semantic fixes: 33 passed.
- Cache regression run: 30 passed. Offline replay regression run after nested target-reference correction: 2 passed.
- Full suite with E:/BaiduNetdiskDownload/miniconda/conda/python.exe -m pytest -q: 209 passed and 13 subtests passed (2.36 seconds).
- Final contract assertion verification: 19 passed (0.23 seconds).
- python -m compileall -q src tests: exit 0.
- JSON Schema Draft202012 meta-schema and 32 replayed M2 grounded packets validated.
- git diff --check: exit 0; line-ending normalization warnings only.
- Project-to-Act validation: valid=true, issues=[]. Lifecycle validation: valid=true, stage=6, revision=4.

## Real saved-output replay

Command: PYTHONPATH=src python -m novel_character_generator replay-m2-grounding --input-file tests/小说/斗罗大陆前20章.txt --source-m1-run-dir runs/douluo-20ch-e2e-dev13-20260831/m1 --source-m2-run-dir runs/douluo-20ch-e2e-dev13-20260831/m2 --output-dir runs/douluo-20ch-e2e-dev13-20260831/m2-grounding-dev27

Completed 32/32 M2 tasks across 17 chunks. Of 84 model facts, 83 grounded (82 exact, 1 describe); 1 ambiguous_fact_binding. No new model-provider calls. The ambiguous quote was 唐昊 / 邋遢 with three chunk-local spans: [1510,1512), [1652,1654), [2079,2081). These are candidate occurrences for review, not a forced earliest binding.

Original run inputs were preserved. Existing downstream dev26 profiles and render artifacts have not been regenerated from these 83 facts. Unit regressions and offline replay do not establish human extraction/identity/snapshot quality. Stage 6 remains in progress; no overall quality Gate passed. Source-before/source-after and validation artifact SHA256 values are recorded in CONTEXT.json.
