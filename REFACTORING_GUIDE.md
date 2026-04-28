# MMR Refactoring Guide (Data Engineering Layout)

`MMR 작업 소스.py` is a notebook JSON saved with a `.py` extension.
This project now splits the mixed notebook code into an English-named, data-engineering style folder architecture.

## Run

```bash
PYTHONPATH=src python scripts/prepare_refactor.py "MMR 작업 소스.py" -o refactored_sources
```

## Target Architecture

```text
refactored_sources/
  01_bronze_ingestion/
  02_silver_validation/
  02_silver_feature_prep/
  03_analytics_validation/
  03_gold_match_features/
  03_gold_mmr/
  03_gold_serving/
  04_analytics_reporting/
```

## Flow Explanation

1. **Bronze (Ingestion)**
   - Environment setup and raw CSV loading logic are isolated first.
2. **Silver (Validation / Feature Prep)**
   - Null/outlier checks, position weighting, and game impact transformations are separated.
3. **Analytics Validation**
   - Distribution checks and normalization verification are split for QA/EDA workflows.
4. **Gold (Serving-ready Metrics)**
   - Team contribution, ELO/MMR updates, and user summary tables are separated into serving layers.
5. **Analytics Reporting**
   - Player style and interpretation/report code is isolated for BI/reporting output.

## Recommended Next Steps

1. Remove duplicated imports and shared global state.
2. Convert each file into pure functions with explicit input/output schemas.
3. Build a single orchestrator pipeline (`main_pipeline.py`) that calls bronze → silver → gold → reporting.
