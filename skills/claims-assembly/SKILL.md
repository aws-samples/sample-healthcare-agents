---
name: claims-assembly
description: Use when a provider needs to validate claim data and assemble an EDI 837P professional claim, check payer-specific validation rules, or verify HIPAA 5010 compliance before submission.
---

# Claims Assembly

## When to use this skill
- Provider needs to assemble a professional claim (837P) for submission
- Validate claim data against HIPAA 5010 requirements
- Look up payer-specific validation rules before assembly
- Check EDI schema requirements for specific fields
- Verify NPI, ICD-10-CM, CPT/HCPCS code formats

## MCP Servers Used
- **Bedrock Knowledge Base** — for payer-specific validation rules, HIPAA compliance rules, and EDI schema requirements

## Workflow: Assemble EDI 837P Claim

### Step 1: Gather claim data from provider
Required components:
- **Billing Provider**: name, NPI, tax_id, taxonomy_code, address, contact_phone
- **Subscriber**: first_name, last_name, member_id, date_of_birth (CCYYMMDD), gender (M/F/U), group_number
- **Payer**: name, payer_id, address
- **Diagnosis Codes**: 1-12 ICD-10-CM codes with descriptions
- **Service Lines**: procedure_code (CPT/HCPCS), charge_amount, units, date_of_service (CCYYMMDD), place_of_service, modifiers, diagnosis_pointers

Optional:
- total_charge, prior_auth_number, referral_number, rendering_provider, facility_npi/name

### Step 2: Query validation rules knowledge base
Tool: `query_validation_rules`
- Input: query (e.g., "Medicare modifier requirements"), rule_type (payer | compliance | schema | all)
- Output: relevant validation rules with relevance scores
- Check payer-specific requirements BEFORE assembly (referral numbers, specific modifiers, timely filing limits)

### Step 3: Validate and assemble
Tool: `validate_and_assemble_claim`
- Input: claim_json (JSON string following the schema)
- Performs deterministic validation:
  - NPI format (10 digits, Luhn check)
  - ICD-10-CM code format (letter + digits, valid range)
  - CPT/HCPCS code format (5-digit numeric or alpha-numeric)
  - Date format (CCYYMMDD, valid calendar date)
  - Charge consistency (total_charge = sum of line charges)
  - Cross-field rules (diagnosis_pointers reference valid indices)
  - Required field presence
- Output: `valid` (bool), `issues` (list with severity/field/message), `edi_837p` (if valid)

### Step 4: Review and correct
- If validation fails, present issues to provider grouped by severity (error vs warning)
- Errors block assembly; warnings are advisory
- After corrections, re-validate until clean

## Validation Rules Reference

| Field | Format | Example |
|-------|--------|---------|
| NPI | 10 digits | 1234567890 |
| ICD-10-CM | A00-Z99.x format | M54.5, E11.65 |
| CPT | 5-digit numeric | 99213, 72148 |
| HCPCS | Alpha + 4 digits | J1745, G0127 |
| Date | CCYYMMDD | 20260115 |
| Gender | M, F, or U | M |
| Place of Service | 2-digit code | 11 (office), 21 (hospital) |

## Key Conventions
- Always query the validation KB for payer rules BEFORE assembling
- Total charge must equal the sum of all service line charges
- Diagnosis pointers are 1-based indices into the diagnosis_codes array
- Maximum 12 diagnosis codes per claim
- At least one service line is required
- Relationship code defaults to "18" (self) if not specified
- Modifiers are ordered (primary, secondary, tertiary, quaternary)
