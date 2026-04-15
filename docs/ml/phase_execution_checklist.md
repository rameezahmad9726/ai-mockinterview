# Phase Execution Checklist (Go / No-Go)

Use this checklist before moving from one phase to the next.  
If any **required** item fails, phase status is **NO-GO**.

## Phase 0 -> Phase 1 Gate

### Required
- [ ] Training row log exists (`backend/training_rows/interview_segments.jsonl`)
- [ ] Schema sanity is clean (`invalid_rows == 0`, no missing required fields)
- [ ] Dataset parquet exists (`data/processed/interview_segments_v1.parquet`)
- [ ] Minimum data volume reached:
  - [ ] `row_count >= 200` (absolute minimum for first meaningful pass)
- [ ] Baseline metrics artifact exists (`artifacts/baseline_v1_metrics.json`)

### Recommended
- [ ] At least 2 raters for a subset of samples
- [ ] Label rubric finalized and versioned
- [ ] Segment-level error examples documented

## Phase 1 -> Phase 2 Gate

### Required
- [ ] `artifacts/model_eval_latest.json` exists
- [ ] Behavior model validation set non-trivial (`rows_val >= 50`)
- [ ] Behavior MAE improvement vs baseline >= 15%
- [ ] Dual-run logging enabled (`USE_DUAL_RUN_MODE=true`)
- [ ] No API contract regressions in report payload

### Recommended
- [ ] Feature importance report generated
- [ ] Drift monitor baseline snapshot saved

## Phase 2 -> Phase 3 Gate

### Required
- [ ] Speech model validation set non-trivial (`rows_val >= 50`)
- [ ] Speech clarity MAE improvement vs baseline >= 10%
- [ ] Internal pilot run completed (at least 1 week)
- [ ] Fallback path tested (flag toggle rollback verified)

### Recommended
- [ ] Subgroup checks on accent/quality buckets
- [ ] Latency budget report captured

## Phase 3 Rollout Gate (10% -> 25% -> 50% -> 100%)

### Required (each rollout step)
- [ ] Previous cohort stable for 24h+
- [ ] No severe quality regression
- [ ] No latency SLO breach
- [ ] Rollback command tested before expansion

### Rollback Triggers
- [ ] MAE/F1 degradation beyond threshold
- [ ] Error rate increase > 2x baseline
- [ ] Inference failures from model loading/prediction

## Phase 4 Entry Gate

### Required
- [ ] Tabular model improvements plateaued across 2+ iterations
- [ ] Error taxonomy points to domain-specific blind spots
- [ ] Enough labeled data for targeted fine-tuning experiments

---

## Fast Gate Command

Run:

```bash
python ml/evaluation/check_phase_gates.py
```

Optional:

```bash
python ml/evaluation/check_phase_gates.py --phase phase0_to_phase1
python ml/evaluation/check_phase_gates.py --metrics artifacts/model_eval_latest.json --baseline artifacts/baseline_v1_metrics.json
```

