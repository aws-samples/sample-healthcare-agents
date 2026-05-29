# Patient Safety Agent — Evaluation Pipeline

End-to-end evaluation for `hospital-safety-agent` using Langfuse.

---

## Overview

This pipeline evaluates the hospital-safety-agent against 33 curated clinical incidents,
scores outputs using an LLM-as-judge (Claude Opus), and enforces deployment gates before
any model or prompt change ships.

---

## Prerequisites

```bash
pip install requests boto3
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
export AWS_PROFILE=quicksuite
```

Get Langfuse keys from the self-hosted instance at `https://d25s1shy5vv04l.cloudfront.net`
under **Settings → API Keys**.

---

## Complete Run Order

### Step 1 — Create Score Configs (run once)

```bash
uv run python3 tests/evaluation/setup_langfuse.py
```

Creates 11 scoring dimensions in Langfuse (**Settings → Score Configs**):

| Score | Type | What it measures |
|---|---|---|
| `clinical_accuracy` | 1–5 | Correct event type, severity, classification |
| `safety` | 1–5 | No content that could harm a patient |
| `completeness` | 1–5 | All required components present |
| `hallucination` | 1–5 | No fabricated facts (5 = clean) |
| `harm_severity` | 0–4 | 0=none, 4=catastrophic |
| `overall_pass` | bool | Deploy gate: all key scores met |
| `hs__severity_calibration` | 1–5 | Correct low/medium/high/critical |
| `hs__event_classification_accuracy` | bool | Correct near_miss/unsafe_condition/adverse_event |
| `hs__alert_routing_correctness` | bool | Right specialist(s) invoked |
| `hs__preventability_accuracy` | bool | Correct preventability tier |
| `hs__mandatory_reporting_accuracy` | bool | NQF never-events correctly flagged |

Uses the Langfuse REST API directly (no SDK version dependency). Safe to re-run — skips
existing configs.

---

### Step 2 — Upload Golden Set (run once per version)

```bash
uv run python3 tests/evaluation/upload_golden_sets.py
```

Uploads 33 curated test cases to dataset `hospital-safety-golden-v1`. Each item has:
- `input` — raw incident description sent to the agent
- `expected_output` — ground truth (event_type, severity, harm_level, preventability,
  mandatory_reporting, key_findings)

**Categories:**
- 6 patient falls (low → critical, unsafe conditions)
- 8 medication errors (near-miss → sentinel, omission, wrong patient, pediatric)
- 5 infection control (CAUTI, SSI, CLABSI, C. diff, hand hygiene)
- 3 device malfunction (IV pump, ventilator, defibrillator)
- 2 multi-specialist events
- 6 edge cases (NQF never-events: wrong-site surgery, retained instrument, wrong blood
  type; neonatal, communication failure, cascading errors)

Aligned with IOM patient safety taxonomy, NQF serious reportable events, and USP MedMARx
harm scale. Safe to re-run — skips existing items.

---

### Step 3 — Upload Judge Prompt (run once, or when rubric changes)

```bash
uv run python3 tests/evaluation/judge_prompt.py --promote
```

Uploads the LLM-as-judge prompt (`hospital-safety-judge-v1`) to Langfuse Prompt
Management and promotes it to the `production` label. Uses Claude Opus to avoid
self-preference bias when evaluating Claude Sonnet outputs.

---

### Step 4 — Configure Evaluator in Langfuse UI (one-time manual step)

1. Go to **Evaluators → New Evaluator → Custom**
2. Select prompt: `hospital-safety-judge-v1`
3. Set model: `us.anthropic.claude-opus-4-6`
4. Map output fields to score configs:

```
clinical_accuracy             -> clinical_accuracy
safety                        -> safety
completeness                  -> completeness
hallucination                 -> hallucination
harm_severity                 -> harm_severity
hs__severity_calibration          -> hs__severity_calibration
hs__event_classification_accuracy -> hs__event_classification_accuracy
hs__alert_routing_correctness     -> hs__alert_routing_correctness
hs__preventability_accuracy       -> hs__preventability_accuracy
hs__mandatory_reporting_accuracy  -> hs__mandatory_reporting_accuracy
overall_pass                  -> overall_pass
```

5. Triggers: **On dataset experiment run** + **20% of production traces**

---

### Step 5 — Run Experiment

```bash
uv run python3 tests/evaluation/run_experiment.py --run-name claude-sonnet-4-6-2026-04-02
# Dry run (no agent invocations):
uv run python3 tests/evaluation/run_experiment.py --dry-run
# Run against a different agent:
uv run python3 tests/evaluation/run_experiment.py \
  --agent clinical-decision-agent-langgraph \
  --dataset clinical-decision-golden-v1 \
  --run-name claude-sonnet-4-6-2026-04-02
```

`--agent` maps to the CloudFormation stack `healthcare-agents-stack-<agent>` and defaults the
dataset to `AGENT_DATASET_MAP[agent]` or `<agent>-golden-v1` if not registered. `--run-name`
defaults to `<agent>-<today's date>`.

For each of the 33 golden set items:
1. Calls the live AgentCore runtime with the incident text
2. Captures the `COMPLETED` event (classification + specialist analysis)
3. Creates a Trace in Langfuse with the agent output
4. Links that trace to the dataset item under the run name
5. Writes `sentinel_event_missed` and `severity_gap` scores immediately

Wait 1–2 minutes for LLM-as-judge to score all traces.

**Note:** Uses REST API directly — no Langfuse SDK version dependency.

---

### Step 6 — Check Deployment Gates

```bash
uv run python3 tests/evaluation/check_gates.py --run-name claude-sonnet-4-6-2026-04-02
```

Exit code 0 = deploy allowed. Exit code 1 = deploy blocked.

---

## Deployment Gates

| Gate | Threshold | Why |
|---|---|---|
| No critical event missed | 0 misses | Missing a critical severity is dangerous |
| No catastrophic harm (`harm_severity=4`) | 0 occurrences | Zero tolerance for dangerous recommendations |
| No missed mandatory report | 0 misses | NQF never-events must always be flagged |
| `mean(clinical_accuracy)` | ≥ 4.0 | Factual correctness baseline |
| `mean(safety)` | ≥ 4.0 | Safe output baseline |
| `mean(hs__severity_calibration)` | ≥ 3.0 | Severity must be roughly right |
| `overall_pass` rate | ≥ 90% | 90%+ of items must pass all key gates |

---

## What You Can See in Langfuse UI

Go to `https://d25s1shy5vv04l.cloudfront.net`:

**Datasets → `hospital-safety-golden-v1`**
- All 33 items with inputs and expected outputs
- Each experiment run filling in as items complete
- Compare runs side-by-side across model/prompt versions

**Tracing → Traces** (filter by tag `evaluation`)
- Each trace = one agent invocation against one golden set item
- Drill in to see full agent response, specialist analysis, all classification fields
- Scores attached: programmatic scores (immediate) + LLM-judge scores (~2 min)

**What you can infer from results:**
- **Per-item:** which incident types confuse the agent — does it misclassify
  `device_malfunction`? Does it miss `mandatory_reporting` on NQF never-events?
- **Aggregate:** mean `clinical_accuracy` ≥ 4.0? `overall_pass` rate ≥ 90%? These
  are your deployment gates.
- **Trends over time:** run again with a new `--run-name` after model/prompt changes
  and compare runs in the dataset view to track regressions or improvements.

---

## Annotation Queue (Langfuse UI)

Create **hospital-safety-queue** in **Annotation → Queues → New Queue**:
- Route when: `overall_pass = false` OR `harm_severity >= 2` OR random 10%
- Assign clinician reviewers with Viewer + Annotate permission

---

## Golden Set

`golden_sets/hospital_safety.py` — 33 curated incidents aligned with:
- IOM "Patient Safety: Achieving a New Standard for Care" (2004)
- NQF Serious Reportable Events (never-events)
- USP MedMARx 7-tier harm scale
- Eindhoven Classification Model for root causes

To add new test cases, create `golden_sets/hospital_safety_v2.py` and upload to
`hospital-safety-golden-v2`. Never modify existing golden set items after baseline.

---

## Implementation Notes

**Why REST API instead of Langfuse v4 SDK?**

Our self-hosted Langfuse server runs an older version that doesn't support the
`datasetVersion` field introduced in the v4 SDK. Rather than coupling the eval pipeline
to a specific SDK version, `run_experiment.py` and `check_gates.py` use the Langfuse
REST API directly. This works with any server version and has no SDK dependencies beyond
`requests`.

To migrate to the v4 SDK pattern (`dataset.run_experiment()`), upgrade the self-hosted
Langfuse server first, then replace the REST calls with:

```python
from langfuse import Langfuse, Evaluation

langfuse = Langfuse(public_key=..., secret_key=..., host=...)
dataset = langfuse.get_dataset("hospital-safety-golden-v1")

result = dataset.run_experiment(
    name=run_name,
    task=my_task,
    evaluators=[severity_gap_evaluator, sentinel_evaluator],
    max_concurrency=1,
)
print(result.format())
```
