# Epic FHIR Setup Scripts

## Overview

These scripts set up Epic FHIR integration with two OAuth 2.0 flows:

1. **Backend Services (M2M)** - System-to-system authentication
2. **User Federation (3LO)** - User-authorized access

## Which Setup Do I Need?

### Backend Services (M2M)

✅ **Use for:**
- Background monitoring
- Scheduled batch jobs
- System-wide patient access
- No user interaction

❌ **Not for:**
- User-initiated queries
- Need user consent/authorization

### User Federation (3LO)

✅ **Use for:**
- Interactive applications
- User-initiated queries
- User-scoped patient access
- Compliance requirements for user consent

❌ **Not for:**
- Background jobs
- System-wide monitoring

---

## Backend Services (M2M) Setup

### What It Does

Creates JWK Set URL infrastructure for JWT-based authentication.

### Prerequisites

- AWS credentials configured (`quicksuite` profile)
- OpenSSL installed
- Node.js and npm

### Setup Steps

**1. Generate RSA keypair:**

Already done! Keys are in `.epic-credentials/`
- Private key: `.epic-credentials/epic_private_key.pem`
- Public key: `.epic-credentials/epic_public_key.pem`

**2. Deploy JWK Set infrastructure:**

```bash
cd epic-jwks-hosting-cdk
npm install
npm run deploy -- --profile quicksuite
```

Save the CloudFront URL from output:
```
https://d3ff1uoye1c365.cloudfront.net/jwks.json
```

**3. Register in Epic app:**

- Go to https://fhir.epic.com/Developer/Apps
- Edit your app
- **Non-Production JWK Set URL**: Paste CloudFront URL
- **SMART Scopes**: `system/Patient.read`, `system/MedicationRequest.read`, etc.
- Save

**4. Test authentication:**

```bash
python3 scripts/test_epic_auth.py
```

### Files Created

- CloudFront distribution (JWK Set URL)
- S3 bucket with `jwks.json`
- Private key in Secrets Manager

---

## User Federation (3LO) Setup

### What It Does

Creates AgentCore Identity OAuth2 Credential Provider for user-authorized access.

### Prerequisites

- AWS credentials configured (`quicksuite` profile)
- Epic app NOT YET created (or ready to update)

### Setup Steps

**Step 1: Create OAuth2 Credential Provider**

```bash
./scripts/setup-epic-3lo.sh --profile quicksuite
```

This creates the credential provider and gives you the callback URL:
```
https://bedrock-agentcore.us-east-1.amazonaws.com/identities/oauth2/callback
```

**Step 2: Register Epic App**

Go to https://fhir.epic.com/Developer/Apps and create app:

```
Application Name: MCP Connector - 3LO
Application Audience: ☑ Backend Systems
Public Documentation URL: http://www.example.com
Incoming APIs: FHIR
Endpoint URI: <PASTE CALLBACK URL FROM STEP 1>
Can Register Dynamic Clients: ☐ UNCHECKED
Is Confidential Client: ☑ CHECKED
SMART Scopes: user/Patient.read, user/MedicationRequest.read, etc.
```

Save and get:
- Client ID
- Client Secret (click to reveal)

**Step 3: Update Credential Provider**

```bash
./scripts/update-epic-3lo-credentials.sh \
  --client-id "your-client-id-from-epic" \
  --client-secret "your-client-secret-from-epic" \
  --profile quicksuite
```

**Step 4: Deploy Agent**

```bash
cd infra-cdk
npm run deploy -- --profile quicksuite
```

**Step 5: Test User Federation**

```bash
agentcore invoke '{"patientId": "test-id"}' \
  --agent your-agent \
  --user-id test-user \
  --session-id "unique-session-id-min-33-chars-long"
```

You'll receive an authorization URL. Open in browser, log in, authorize.

### Files Created

- OAuth2 Credential Provider in AgentCore Identity
- `.epic-3lo-callback-url` (saved locally for reference)
- `.epic-3lo-client-id` (saved locally for reference)

---

## Script Reference

### M2M Scripts

| Script | Purpose |
|--------|---------|
| `test_epic_auth.py` | Test M2M JWT authentication |

### 3LO Scripts

| Script | Purpose |
|--------|---------|
| `setup-epic-3lo.sh` | Create OAuth2 Credential Provider (one-time) |
| `update-epic-3lo-credentials.sh` | Update with Epic app credentials |

---

## Script Usage Examples

### setup-epic-3lo.sh

**Basic usage:**
```bash
./scripts/setup-epic-3lo.sh
```

**With custom profile/region:**
```bash
./scripts/setup-epic-3lo.sh --profile myprofile --region us-west-2
```

**Help:**
```bash
./scripts/setup-epic-3lo.sh --help
```

### update-epic-3lo-credentials.sh

**Basic usage:**
```bash
./scripts/update-epic-3lo-credentials.sh \
  --client-id "f6e6a266-31e2-43e0-afec-358de041181a" \
  --client-secret "your-secret-here"
```

**With custom profile:**
```bash
./scripts/update-epic-3lo-credentials.sh \
  --client-id "your-id" \
  --client-secret "your-secret" \
  --profile quicksuite
```

**Help:**
```bash
./scripts/update-epic-3lo-credentials.sh --help
```

---

## Comparison Table

| Aspect | M2M Setup | 3LO Setup |
|--------|-----------|-----------|
| **One-time setup** | Deploy JWK Set CDK | Run `setup-epic-3lo.sh` |
| **Epic app config** | JWK Set URL | Callback URL + Client Secret |
| **AWS resources** | CloudFront, S3, Secrets Manager | AgentCore Identity Provider |
| **Testing** | `test_epic_auth.py` | `agentcore invoke` |
| **Cost** | ~$0.50/month | Included in AgentCore |

---

## Troubleshooting

### M2M: "JWT signature verification failed"

```bash
# Verify JWK Set URL is accessible
curl https://d3ff1uoye1c365.cloudfront.net/jwks.json

# Verify kid matches
cat epic-jwks-hosting-cdk/jwks.json | jq '.keys[].kid'
grep kid gateway/tools/epic_fhir_tools.py
```

### 3LO: "Provider already exists"

```bash
# Option 1: Use existing (recommended)
./scripts/update-epic-3lo-credentials.sh --client-id <ID> --client-secret <SECRET>

# Option 2: Delete and recreate
aws bedrock-agentcore-control delete-oauth2-credential-provider \
  --name EpicFHIRProvider \
  --profile quicksuite

./scripts/setup-epic-3lo.sh --profile quicksuite
```

### 3LO: "Callback URL mismatch"

```bash
# Get callback URL from provider
aws bedrock-agentcore-control get-oauth2-credential-provider \
  --name EpicFHIRProvider \
  --profile quicksuite \
  | jq -r '.callbackUrl'

# Update Epic app with this exact URL
```

---

## Documentation

- **Quick Reference**: `docs/epic/EPIC_QUICK_REFERENCE.md`
- **OAuth Flow Guide**: `docs/epic/EPIC_FHIR_OAUTH_FLOWS.md`
- **M2M Infrastructure**: `docs/epic/EPIC_JWKS_CUSTOMER_DEPLOYMENT.md`
- **Epic App Setup**: `docs/epic/EPIC_FHIR_SETUP.md`

---

## Support

**M2M Issues:**
- Check `docs/epic/EPIC_JWKS_CUSTOMER_DEPLOYMENT.md`
- Verify JWK Set infrastructure is deployed

**3LO Issues:**
- Check `docs/epic/EPIC_FHIR_OAUTH_FLOWS.md`
- Verify AgentCore Identity permissions
- Check CloudWatch logs for agent

**Epic App Issues:**
- https://fhir.epic.com
- https://apporchard.epic.com
