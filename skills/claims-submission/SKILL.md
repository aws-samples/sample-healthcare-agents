---
name: claims-submission
description: Use when a provider needs to submit an assembled EDI 837P claim to a payer via AWS B2B Data Interchange, track submission status, or check for acknowledgment responses (997/999 and 277CA).
---

# Claims Submission

## When to use this skill
- Submit an assembled 837P claim to a payer electronically
- Track the status of a previously submitted claim
- Check for functional acknowledgments (997/999)
- Retrieve claim status responses (277CA)
- Manage B2B trading partner connections

## MCP Servers Used
- **AgentCore Gateway** — for AWS B2B Data Interchange tools (EDI submission, acknowledgment retrieval, status tracking)

## Workflow: Submit Claim via B2B Data Interchange

### Step 1: Verify submission readiness
Before submitting, confirm:
- Claim has been validated and assembled (837P structure exists)
- Payer trading partner is configured in B2B Data Interchange
- Correct payer_id and submission endpoint are available
- The claim has not already been submitted (avoid duplicates)

### Step 2: Submit claim
Use Gateway B2B tools to:
- Package the 837P EDI transaction
- Route to the correct payer trading partner
- Capture the submission transaction ID for tracking

### Step 3: Monitor acknowledgments
Track two levels of acknowledgment:
1. **997/999 Functional Acknowledgment** — confirms EDI envelope was received and syntactically valid
   - TA1: Interchange acknowledgment (envelope level)
   - 999: Implementation acknowledgment (transaction set level)
   - Watch for: AK9 segment with accept/reject status
2. **277CA Claim Acknowledgment** — confirms claim was accepted for adjudication
   - Per-claim acceptance/rejection status
   - Rejection reasons with specific error codes

### Step 4: Handle rejections
If rejected at any level:
- Parse rejection reason codes
- Map to specific claim fields that need correction
- Report actionable errors to provider
- Claims rejected at 997/999 level need EDI structure fixes
- Claims rejected at 277CA level typically need data corrections

### Step 5: Report submission status
Provide clear summary:
- Submission timestamp and transaction ID
- Current status (submitted, acknowledged, accepted, rejected)
- Any pending acknowledgments
- Next steps for the provider

## Submission Status Flow
```
Submitted → 997/999 Received → 277CA Received → In Adjudication
    ↓              ↓                  ↓
 Timeout    999 Rejected       277CA Rejected
```

## Key Conventions
- Never submit the same claim twice without confirming the first was rejected
- Always wait for 997/999 before reporting success — submission alone doesn't mean acceptance
- B2B Data Interchange handles EDI envelope wrapping (ISA/GS/ST segments)
- Payer-specific submission windows may apply (some reject claims outside business hours)
- Timely filing limits vary by payer — check before submission if claim is near deadline
- Keep submission transaction IDs for audit trail and follow-up queries
