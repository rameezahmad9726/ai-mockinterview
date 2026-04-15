# Model Training and Integration Plan

This document is the implementation playbook for evolving from rule-based scoring to trained models without breaking production behavior.

## Scope

- Train and integrate two custom models first:
  - `behavior_fusion_model_v1` (confidence/trend/recommendation)
  - `speech_scorer_model_v1` (clarity/confidence from speech features + transcript)
- Keep current rule-based logic as fallback until gates are met.
- Roll out behind feature flags for safe staged adoption.

## Success Metrics

- **Confidence regression:** MAE improves by at least 15% from baseline.
- **Recommendation classification:** F1 improves by at least 10% from baseline.
- **Trend classification:** macro-F1 improves by at least 10% from baseline.
- **Latency:** inference adds at most 150ms per request for aggregate scoring.
- **Safety:** no subgroup regression for at least: recording quality, accent tags, lighting.

## Phase 0 - Baseline and Data Readiness

### Goal
Create repeatable baselines and reliable labeled data before training.

### Steps
1. Freeze current heuristics as baseline behavior.
2. Add feature logging pipeline for every analyzed interview:
   - emotion, posture, eye-contact, speech metadata, transcript, final heuristic outputs.
3. Export training rows conforming to `docs/ml/data_schema.json`.
4. Create baseline report script (MAE, F1, confusion matrix, calibration).
5. Build a labeling rubric with examples for 1-10 confidence/clarity.
6. Label at least 600 segments with at least 2 raters each.

### Integration Output
- New reproducible artifact: `artifacts/baseline_v1_metrics.json`.
- Dataset snapshot: `data/processed/interview_segments_v1.parquet`.

## Phase 1 - Behavior Fusion Model

### Goal
Replace weighted heuristics in behavior analysis with a learned model while preserving API contracts.

### Model
- Start with LightGBM/XGBoost on aggregated + temporal features.
- Targets:
  - `label_confidence_1_10` (regression)
  - `label_trend` (3-class classification)
  - optional `label_recommendation` (binary classification)

### Steps
1. Feature engineering:
   - aggregate emotion histograms, switch count
   - posture mean/variance, movement
   - eye-contact mean/std/trend
   - speech metadata (wpm, filler_count, pause_ratio)
2. Train baseline tabular models with fixed random seeds.
3. Evaluate against Phase 0 baselines.
4. Package model + preprocessing pipeline.
5. Add model-serving module (read-only first).
6. Add feature flag in backend:
   - `USE_LEARNED_BEHAVIOR_MODEL=false` by default.
7. Dual-run mode:
   - compute both heuristic and model outputs
   - log deltas for offline comparison.

### Integration Output
- `backend/modules/model_inference/behavior_fusion.py`
- Model artifact versioned under `models/behavior/v1/`
- Config flag wired in runtime settings.

## Phase 2 - Speech Scorer Model

### Goal
Improve speech clarity/confidence consistency using learned scoring.

### Model
- Keep Whisper transcription as upstream.
- Train a compact model using:
  - transcript embeddings (or engineered lexical features)
  - prosody/tempo/filler features from audio pipeline

### Steps
1. Define speech-only features and leakage checks.
2. Train clarity/confidence regressors.
3. Validate on held-out test split and subgroup slices.
4. Package model with deterministic preprocessing.
5. Add inference module and feature flag:
   - `USE_LEARNED_SPEECH_MODEL=false` initially.
6. Run dual-mode logging in production-like traffic.

### Integration Output
- `backend/modules/model_inference/speech_scorer.py`
- Model artifact versioned under `models/speech/v1/`

## Phase 3 - Progressive Rollout

### Goal
Enable trained models gradually and safely.

### Steps
1. Staging rollout with both flags disabled by default.
2. Enable behavior model for internal users only.
3. Monitor quality and drift for 1-2 weeks.
4. Enable speech model for internal users only.
5. Expand to 10%, 25%, 50%, 100% cohorts if gates hold.
6. Keep fallback path available for rollback at all times.

### Rollback Rules
- Automatic rollback if:
  - MAE/F1 degrades beyond threshold for 24h window
  - latency SLO breached
  - severe subgroup regression detected.

## Phase 4 - Optional Domain Fine-Tuning

### Goal
Address remaining error clusters after two-model rollout.

### Candidate Work
- Emotion calibration for interview-specific camera setups.
- Eye-contact threshold tuning per camera framing profile.
- Multimodal temporal model (GRU/TCN) only if tabular plateau is reached.

## Required Repository Structure

```text
docs/ml/
  data_schema.json
  training_plan.md
ml/
  notebooks/
  pipelines/
  evaluation/
models/
  behavior/v1/
  speech/v1/
artifacts/
  baseline_v1_metrics.json
```

## Backend Integration Checklist (Step-by-Step)

1. Add model loading and inference modules without changing current API schema.
2. Keep heuristic functions as default behavior.
3. Add environment flags:
   - `USE_LEARNED_BEHAVIOR_MODEL`
   - `USE_LEARNED_SPEECH_MODEL`
4. Implement dual-run mode and log both outputs.
5. Add model metadata to report payload:
   - `model_version`, `inference_mode` (`heuristic|learned|dual`)
6. Add health checks for model artifact presence and load status.
7. Add robust error handling:
   - fallback to heuristics if model load/inference fails.
8. Add regression tests that assert API output fields are unchanged.
9. Add benchmark test for inference latency.
10. Promote flags only after evaluation gates pass.

## MLOps and Governance

- Version every dataset snapshot, model artifact, and evaluation report.
- Track experiment metadata (seed, features, params, commit hash).
- Keep an immutable holdout test set for release decisions.
- Require sign-off on fairness and drift checks before production rollout.

## Milestone Timeline (Suggested)

- Week 1: Phase 0
- Weeks 2-3: Phase 1
- Weeks 4-5: Phase 2
- Weeks 6-7: Phase 3 rollout
- Week 8+: Phase 4 only if needed

## Notes for Future Implementation

- Do not delete heuristic paths until learned models have passed at least one full release cycle.
- Any schema changes to training data must increment `schema_version` in `data_schema.json`.
- Keep model outputs interpretable: include top contributing features for debugging.
