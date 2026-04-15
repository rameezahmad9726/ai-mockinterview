# ML Workspace

This folder contains starter scaffolding for model training and evaluation.

## Structure

- `pipelines/train_behavior.py`: trains `behavior_fusion_model_v1`
- `pipelines/train_speech.py`: trains `speech_scorer_model_v1`
- `evaluation/evaluate_models.py`: aggregates latest metrics into `artifacts/model_eval_latest.json`
- `notebooks/`: reserved for exploratory work

## Quick Start

1. Build dataset (pseudo-label bootstrap) from backend report JSON files:

```bash
python ml/pipelines/build_dataset_from_reports.py --reports-dir backend/reports --out data/processed/interview_segments_v1.parquet
```

2. Or build dataset from live JSONL training-row logs (Phase 0 integration):

```bash
python ml/pipelines/build_dataset_from_training_rows.py --jsonl backend/training_rows/interview_segments.jsonl --out data/processed/interview_segments_v1.parquet
```

3. Optional sanity check before training:

```bash
python ml/pipelines/check_training_rows.py --jsonl backend/training_rows/interview_segments.jsonl --sample-size 200
```

4. Or bring your own processed parquet matching `docs/ml/data_schema.json`.
5. Train models:

```bash
python ml/pipelines/train_behavior.py --data data/processed/interview_segments_v1.parquet
python ml/pipelines/train_speech.py --data data/processed/interview_segments_v1.parquet
python ml/evaluation/evaluate_models.py
```

## Phase Go/No-Go Gates

Run all gates:

```bash
python ml/evaluation/check_phase_gates.py
```

Run a specific gate:

```bash
python ml/evaluation/check_phase_gates.py --phase phase0_to_phase1
python ml/evaluation/check_phase_gates.py --phase phase1_to_phase2
python ml/evaluation/check_phase_gates.py --phase phase2_to_phase3
```

Windows helper:

```cmd
run_phase_gate.cmd
run_phase_gate.cmd phase0_to_phase1
```

## Output Artifacts

- `models/behavior/v1/behavior_model.joblib`
- `models/behavior/v1/metrics.json`
- `models/speech/v1/speech_model.joblib`
- `models/speech/v1/metrics.json`
- `artifacts/model_eval_latest.json`

