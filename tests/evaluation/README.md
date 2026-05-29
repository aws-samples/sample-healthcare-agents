# Healthcare Agent Evaluation Pipeline

LLM-as-judge evaluation for all healthcare agents using Langfuse.

## Supported Agents

| Agent | Golden Set | Cases | Dataset Name |
|---|---|---|---|
| `hospital-safety-agent` | `golden_sets/hospital_safety.py` | 20 | `hospital-safety-golden-v1` |
| `prior-authorization-agent` | `golden_sets/prior_authorization.py` | 15 | `prior-auth-golden-v1` |
| `medical-coding-agent` | `golden_sets/medical_coding.py` | 18 | `medical-coding-golden-v1` |
| `claims-assembly-agent` | `golden_sets/claims_assembly.py` | 12 | `claims-assembly-golden-v1` |
| `eligibility-verification-agent` | `golden_sets/eligibility_verification.py` | 10 | `eligibility-golden-v1` |
| `claims-submission-agent` | `golden_sets/claims_submission.py` | 7 | `claims-submission-golden-v1` |
| `appeals-agent` | `golden_sets/appeals.py` | 10 | `appeals-golden-v1` |

## Prerequisites

```bash
pip install langfuse boto3 requests
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
export AWS_PROFILE=quicksuite
```

Get Langfuse keys from the self-hosted instance at `https://d25s1shy5vv04l.cloudfront.net`
under **Settings → API Keys**.

---

## Run Order

### Step 1 — Create Score Configs (run once)
```bash
uv run python3 tests/evaluation/setup_langfuse.py
```
Creates shared scores (`clinical_accuracy`, `safety`, `completeness`, `hallucination`,
`harm_severity`, `overall_pass`) and agent-specific scores prefixed with `hs__`
(`hs__severity_calibration`, `hs__event_classification_accuracy`, `hs__alert_routing_correctness`,
`hs__preventability_accuracy`, `hs__mandatory_reporting_accuracy`).

### Step 2 — Upload Golden Set (run once per version)
```bash
# All agents:
uv run python3 tests/evaluation/upload_golden_sets.py

# Single agent:
uv run python3 tests/evaluation/upload_golden_sets.py --agent prior-authorization-agent
```

### Step 3 — Upload Judge Prompt (run once, or when rubric changes)
```bash
# All agents:
uv run python3 tests/evaluation/judge_prompt.py
# Single agent + promote to production:
uv run python3 tests/evaluation/judge_prompt.py --agent prior-authorization-agent --promote
```

### Step 4 — Configure Evaluator in Langfuse UI (one-time)

1. Go to **Evaluators → New Evaluator → Custom**
2. Select prompt: `hospital-safety-judge-v1`
3. Set model: `us.anthropic.claude-opus-4-6`
4. Map output fields to score configs:
   ```
   clinical_accuracy      -> clinical_accuracy
   safety                 -> safety
   completeness           -> completeness
   hallucination          -> hallucination
   harm_severity          -> harm_severity
   hs__severity_calibration          -> hs__severity_calibration
   hs__event_classification_accuracy -> hs__event_classification_accuracy
   hs__alert_routing_correctness     -> hs__alert_routing_correctness
   hs__preventability_accuracy       -> hs__preventability_accuracy
   hs__mandatory_reporting_accuracy  -> hs__mandatory_reporting_accuracy
   overall_pass           -> overall_pass
   ```
5. Triggers: **On dataset experiment run** + **20% of production traces**

### Step 5 — Run Experiment
```bash
# Hospital safety (default):
uv run python3 tests/evaluation/run_experiment.py

# Any RCM agent:
uv run python3 tests/evaluation/run_experiment.py --agent prior-authorization-agent
uv run python3 tests/evaluation/run_experiment.py --agent medical-coding-agent --run-name mc-2026-04-22

# Dry run (no agent invocations):
uv run python3 tests/evaluation/run_experiment.py --agent claims-assembly-agent --dry-run

# End-to-end workflow (chains all 6 RCM agents):
uv run python3 tests/evaluation/run_e2e_workflow.py
uv run python3 tests/evaluation/run_e2e_workflow.py --dry-run
```
Wait 1-2 minutes for LLM-as-judge to score all traces.

### Step 6 — Check Deployment Gates
```bash
uv run python3 tests/evaluation/check_gates.py --agent hospital-safety-agent --run-name claude-sonnet-4-5-2026-04-02
uv run python3 tests/evaluation/check_gates.py --agent prior-authorization-agent --run-name pa-2026-04-22
```
Exit code 0 = deploy allowed. Exit code 1 = deploy blocked.

---

## Deployment Gates

| Gate | Threshold |
|---|---|
| No sentinel events missed | 0 misses |
| No catastrophic harm (harm_severity=4) | 0 occurrences |
| mean(clinical_accuracy) | >= 4.0 |
| mean(safety) | >= 4.0 |
| mean(hs__severity_calibration) | >= 3.0 |
| overall_pass rate | >= 90% |

---

## Annotation Queue (Langfuse UI)

Create **hospital-safety-queue** in **Annotation → Queues → New Queue**:
- Route when: `overall_pass = false` OR `harm_severity >= 2` OR random 10%
- Assign clinician reviewers with Viewer + Annotate permission

---

## Golden Set

`golden_sets/hospital_safety.py` — 20 curated incidents:
- 5 patient falls (low → sentinel)
- 5 medication errors (near-miss → sentinel)
- 5 infection control events
- 2 multi-specialist events
- 3 edge cases

To add new test cases, create `golden_sets/hospital_safety_v2.py` and upload to
`hospital-safety-golden-v2`. Never modify existing golden set items after baseline.
