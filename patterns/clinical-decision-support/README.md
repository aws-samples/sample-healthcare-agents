# Clinical Decision Support Agent

Real-time clinical decision support using Epic FHIR data with user authorization (3LO).

## Overview

This agent helps healthcare providers make safe medication decisions by:

1. **Retrieving patient data** from Epic FHIR (with user authorization via 3LO)
2. **Analyzing drug safety** - interactions, contraindications, allergies
3. **Providing recommendations** - safety ratings, alternatives, clinical guidance

## Use Case

**Scenario**: Doctor is prescribing a medication and needs to check safety

**Example**:
```
Doctor: "Check if Metformin is safe for patient 8MsEzCJO3BA3"

Agent (first time):
→ Requests Epic authorization
→ Doctor logs in to Epic, authorizes access
→ Agent retrieves patient data:
   - Current medications
   - Allergies
   - Recent labs (kidney function)

Agent analyzes:
⚠️  CONTRAINDICATED
   - Patient has Stage 3 CKD (eGFR 42)
   - Metformin contraindicated with eGFR <45
   - Risk: Lactic acidosis

Agent recommends:
✅ Alternative: Empagliflozin
   - Safer for kidney function
   - Added cardiovascular benefit
```

## Epic 3LO (User Federation) Integration

### How It Works

1. **First Invocation**: User receives Epic authorization URL
2. **User Authorization**: Opens URL, logs into Epic, grants permission
3. **Token Storage**: AgentCore Identity stores tokens
4. **Subsequent Calls**: Token used automatically (transparent to user)

### Required Configuration

- **OAuth2 Credential Provider**: `EpicFHIRProvider` (already configured)
- **Epic App**: Client ID `<YOUR_EPIC_CLIENT_ID>`
- **SMART Scopes**:
  - `user/Patient.read`
  - `user/MedicationRequest.read`
  - `user/AllergyIntolerance.read`
  - `user/Observation.read`

## Input Format

```json
{
  "patientId": "8MsEzCJO3BA3",
  "medication": "Metformin",
  "query": "Check if Metformin is safe for this patient"
}
```

**Parameters**:
- `patientId` (required): Epic patient ID
- `medication` (optional): Medication to analyze
- `query` (optional): Free-text clinical question

## Output Format

```json
{
  "status": "success",
  "patientId": "8MsEzCJO3BA3",
  "medication": "Metformin",
  "recommendation": {
    "safety_level": "CONTRAINDICATED",
    "summary": "Metformin contraindicated due to reduced kidney function",
    "interactions": [],
    "contraindications": [
      "Stage 3 CKD with eGFR 42 (Metformin requires eGFR ≥45)"
    ],
    "allergies_flagged": [],
    "alternatives": [
      "Empagliflozin (SGLT2 inhibitor) - safer for kidney function",
      "DPP-4 inhibitor (e.g., Linagliptin) - no dose adjustment needed"
    ],
    "clinical_notes": "Consider cardiology consult given cardiovascular comorbidities. Monitor kidney function quarterly."
  }
}
```

## Testing

### 1. First-Time Authorization Test

```bash
# This will trigger the OAuth flow
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/<RUNTIME_ID> \
  --runtime-session-id test-session-$(date +%s) \
  --runtime-user-id dr-test-user \
  --payload '{"patientId": "8MsEzCJO3BA3", "medication": "Metformin"}' \
  --profile quicksuite \
  output.json
```

**Expected Response** (first time):
```json
{
  "returnControl": {
    "invocationInputs": [{
      "authorizationUrl": "https://fhir.epic.com/interconnect-fhir-oauth/oauth2/authorize?..."
    }]
  }
}
```

**Action**: Open the authorization URL in browser, log in to Epic, authorize

### 2. Subsequent Test (After Authorization)

Re-run the same command with the same `runtime-session-id`. The agent will now have access to patient data and will analyze the medication.

## Test Scenarios

### Scenario 1: Drug-Drug Interaction
```json
{
  "patientId": "8MsEzCJO3BA3",
  "medication": "Warfarin",
  "query": "Check for drug interactions with Warfarin"
}
```

### Scenario 2: Allergy Check
```json
{
  "patientId": "8MsEzCJO3BA3",
  "medication": "Amoxicillin",
  "query": "Is patient allergic to Amoxicillin?"
}
```

### Scenario 3: Kidney Function Check
```json
{
  "patientId": "8MsEzCJO3BA3",
  "medication": "Gabapentin",
  "query": "Check if dose adjustment needed based on kidney function"
}
```

## Deployment

This pattern will be automatically deployed when you add it to `config.yaml` in `infra-cdk/`:

```yaml
patterns:
  - name: clinical-decision-support
    type: docker
    enabled: true
```

Then deploy:
```bash
cd infra-cdk
npm run deploy -- --profile quicksuite
```

## Security & Compliance

- **User Authorization**: Each clinician must authorize access
- **Patient Context**: Only patients the user has Epic access to
- **Token Security**: Encrypted storage in AgentCore Identity
- **Audit Trail**: All access logged with user_id and session_id
- **HIPAA Compliant**: Meets minimum necessary access requirements

## Clinical Safety Notes

⚠️ **This agent is for clinical decision support only**
- Not a replacement for clinical judgment
- Always verify recommendations with references
- Consult pharmacy for complex interactions
- Follow institutional protocols

## Architecture

```
Doctor
  ↓
AgentCore Runtime
  ↓
Clinical Decision Support Agent
  ↓
@requires_access_token (Epic 3LO)
  ↓
Epic FHIR API
  ↓
Patient Data
```

## Tools Used

1. **get_patient_with_user_auth**: Patient demographics
2. **get_medications_with_user_auth**: Current medications
3. **get_allergies_with_user_auth**: Allergy history
4. **get_observations_with_user_auth**: Lab results

All tools use `@requires_access_token` decorator for automatic OAuth handling.
