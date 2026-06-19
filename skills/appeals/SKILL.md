---
name: appeals
description: Use when a provider needs to generate an appeal letter for a denied insurance claim, check filing deadlines, validate appeal components, or save completed appeal letters to S3 with presigned download URLs.
---

# Appeals

## When to use this skill
- Provider needs to appeal a denied claim
- Check if the filing deadline for an appeal is still open
- Generate a compliant appeal letter with clinical rationale
- Validate appeal components (NPI, CARC/RARC codes, required fields)
- Save a finalized appeal letter and get a download link

## MCP Servers Used
- **AgentCore Gateway** — for payer rules knowledge base (denial codes, filing requirements, medical necessity evidence)

## Workflow: Generate Appeal Letter

### Step 1: Check filing deadline
Tool: `check_appeal_deadline`
- Input: payer_name, denial_date (YYYY-MM-DD), appeal_level (first_level | second_level | external_review | peer_to_peer)
- Output: deadline date, days remaining, urgency classification
- **STOP** if deadline has passed — inform provider of options (external review, state insurance commissioner)

### Step 2: Gather denial details
Retrieve from provider or system:
- Claim ID, denial date, denial reason code (CARC), remark codes (RARC)
- Payer name, authorization number (if applicable)
- Patient demographics (name, DOB, member ID)
- Provider info (name, NPI, contact)

### Step 3: Research payer rules via Gateway KB
Use Gateway knowledge base tools to look up:
- Payer-specific appeal requirements for the denial reason code
- Medical necessity criteria for the denied service
- Required supporting documentation

### Step 4: Draft appeal narrative
Generate the letter body (HTML) including:
- Clinical rationale addressing the specific denial reason
- Evidence of medical necessity
- References to payer policy and clinical guidelines
- Specific remedy requested

### Step 5: Validate and assemble
Tool: `validate_and_assemble_appeal`
- Validates all required fields, NPI format (10 digits), CARC code validity
- Checks clinical rationale completeness
- Assembles compliant HTML letter if all validations pass
- Returns validation errors if any component is missing or malformed

### Step 6: Save and deliver
Tool: `save_appeal_letter`
- Saves validated HTML to S3 (`appeals/{claim_id}/{timestamp}-appeal.html`)
- Returns presigned URL (1-hour expiry) for download

## Key Conventions
- Always check deadline BEFORE generating the letter
- Appeal levels: First Level, Second Level, External Review
- NPI must be exactly 10 digits
- CARC codes must be valid numeric codes (e.g., "50", "197")
- Clinical rationale must specifically address the denial reason — generic statements will fail validation
- Letter body must be HTML format
- Presigned download URLs expire after 1 hour
