---
name: medical-coding
description: Use when a provider needs to find ICD-10-CM, CPT, or SNOMED CT codes for diagnoses and procedures, extract medical entities from clinical text using Comprehend Medical, or validate code accuracy against clinical documentation.
---

# Medical Coding

## When to use this skill
- Find the correct ICD-10-CM code for a diagnosis
- Look up CPT/HCPCS codes for procedures and services
- Search SNOMED CT codes for clinical concepts
- Extract medical entities from clinical notes (NLP)
- Validate that assigned codes match clinical documentation
- Determine code specificity (3rd, 4th, 5th, 6th, 7th character requirements)

## MCP Servers Used
- **AgentCore Gateway** — for Amazon Comprehend Medical tools (entity extraction, ICD-10-CM/RxNorm inference)
- **Bedrock Knowledge Base** — for medical code lookup (ICD-10-CM, CPT, SNOMED CT code descriptions and relationships)

## Workflow: Code Clinical Documentation

### Step 1: Extract medical entities from clinical text
Use Gateway Comprehend Medical tools:
- `detect_entities_v2` — extract conditions, medications, procedures, anatomy, and test/treatment/procedure entities
- `infer_icd10cm` — get ICD-10-CM code suggestions with confidence scores
- `infer_rx_norm` — map medication mentions to RxNorm concepts

Output per entity:
- Entity text, category, type
- Confidence score (0.0 - 1.0)
- Suggested codes with scores
- Traits (negation, diagnosis, sign/symptom)

### Step 2: Search knowledge base for code verification
Tool: `search_medical_codes`
- Input: query (description of condition/procedure), code_type (icd10 | cpt | snomed | all)
- Output: matching codes with descriptions and relevance scores
- Use to verify Comprehend Medical suggestions and find more specific codes

### Step 3: Determine code specificity
ICD-10-CM specificity rules:
- Codes must be assigned to the highest level of specificity
- Check if additional characters are required (4th, 5th, 6th, 7th)
- 7th character extensions: A (initial encounter), D (subsequent), S (sequela)
- Placeholder "X" required when 7th character applies but code is fewer than 7 characters

### Step 4: Validate code selection
Cross-reference:
- Does the code description match the clinical documentation?
- Is laterality specified where required (right/left/bilateral)?
- Are combination codes used where applicable?
- Are manifestation codes sequenced correctly (etiology first)?
- Are "code first" and "use additional code" notes followed?

### Step 5: Present coding results
For each code assignment:
- Code and official description
- Clinical documentation supporting the assignment
- Confidence level (from Comprehend Medical or knowledge base relevance)
- Any coding notes or sequencing requirements
- Alternative codes considered and why primary was selected

## Code Format Reference

| Code System | Format | Example | Description |
|-------------|--------|---------|-------------|
| ICD-10-CM | A00-Z99.xxx | M54.5 | Low back pain |
| ICD-10-CM (7th char) | S00-T88.xxxA/D/S | S72.001A | Fracture, initial encounter |
| CPT Category I | 5 digits | 99213 | Office visit, established |
| CPT Category II | 4 digits + F | 2022F | Dilated eye exam |
| CPT Category III | 4 digits + T | 0042T | Cerebral perfusion analysis |
| HCPCS Level II | Letter + 4 digits | J1745 | Infliximab injection |
| SNOMED CT | Numeric (6-18 digits) | 195967001 | Asthma |

## Key Conventions
- Always code to the highest specificity supported by documentation
- Never assign a code without supporting clinical documentation
- Comprehend Medical confidence scores below 0.5 should be verified manually
- "Excludes1" means the two codes CANNOT be used together
- "Excludes2" means the condition is not included but CAN be coded additionally if documented
- Use the knowledge base to verify unfamiliar codes — Comprehend Medical can suggest outdated codes
- Sequencing matters: principal diagnosis first, then secondary diagnoses in clinical significance order
