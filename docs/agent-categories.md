# Healthcare Agent Categories

## Providers (Hospitals, Clinics, Health Systems)

### Clinical Operations

#### Patient Safety & Risk Management
| Agent | What it does | Status |
|---|---|---|
| `hospital-safety-agent` | Incident reporting, classification, specialist routing (falls, medication errors, infection control) — reactive | Done |
| Sepsis Early Warning | Real-time vitals/labs monitoring, alerts when Sepsis-3 criteria met — proactive | Planned |
| Near-Miss Reporting | Captures events that didn't cause harm but could; pattern detection to prevent recurrence | Planned |

**Why it matters:**
- Regulatory — CMS and Joint Commission require incident tracking and response
- Financial — Hospital-Acquired Conditions (HACs) trigger CMS payment penalties
- Liability — Documented incident response reduces malpractice exposure

**Reactive vs. Proactive:**
- Reactive: `hospital-safety-agent` handles incidents after they happen
- Proactive: Sepsis/deterioration monitoring catches risk before the adverse event

#### Clinical Decision Support
| Agent | What it does | Status |
|---|---|---|
| `clinical-decision-agent-langgraph` | Epic FHIR-integrated clinical recommendations | Done |
| `clinical-decision-support` | Clinical decision support (Strands) | Done |
| Discharge Planning | Post-acute care options, insurance coverage check, follow-up scheduling | Planned |
| Nurse Handoff | SBAR-format handoff summaries from EHR data | Planned |

### Revenue Cycle Management
| Agent | What it does | Status |
|---|---|---|
| `medical-coding-agent` | ICD-10/CPT code suggestions from clinical notes | Done |
| `claims-assembly-agent` | Assembles claims from clinical and patient data | Done |
| `claims-submission-agent` | Submits claims to payers, tracks status | Done |
| Prior Authorization | Submits PA requests, tracks status, drafts appeal letters | Planned |
| Denial Management | Analyzes denied claims, identifies root cause, drafts appeals | Planned |
| Charge Capture | Reviews notes vs. charges submitted, flags missed charges | Planned |
| Eligibility & Benefits | Real-time insurance verification before appointments | Planned |

### Patient Experience
| Agent | What it does | Status |
|---|---|---|
| Patient Intake | Pre-visit questionnaires, symptom collection, appointment prep | Planned |
| Post-Discharge Follow-up | Contacts patients after discharge, flags deterioration signs | Planned |

---

## Healthtechs (Payers, Startups, Digital Health)

### Payer / Insurance
| Agent | What it does | Status |
|---|---|---|
| Utilization Management | Reviews clinical criteria (InterQual/MCG) for inpatient admission authorization | Planned |
| Care Gap Closure | Identifies members missing preventive care, outreaches them (HEDIS/Stars) | Planned |
| Fraud, Waste & Abuse (FWA) | Flags anomalous billing patterns and outlier providers | Planned |

### Digital Health / Infrastructure
| Agent | What it does | Status |
|---|---|---|
| FHIR Data Extraction | Queries records across EHRs via FHIR APIs, normalizes data | Planned |
| Clinical Trial Matching | Matches patients to eligible trials based on EHR criteria | Planned |
| Population Health | Stratifies patient panels by risk score, surfaces high-risk patients | Planned |
| RCM Automation | End-to-end claim lifecycle — build, scrub, submit, track, post ERA | Planned |

---

## Priority Gaps (highest value not yet built)

1. **Prior Authorization** — #1 admin burden for providers, well-defined multi-agent workflow
2. **Denial Management** — pairs with existing claims patterns, 60% of denials are recoverable
3. **Sepsis Early Warning** — high clinical impact, real-time streaming fits AgentCore well
4. **Care Gap Closure** — payer-side, FHIR integration already exists via Epic
