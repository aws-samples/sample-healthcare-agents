# Epic FHIR JWKS Hosting Infrastructure

Separate CDK stack for hosting Epic FHIR JSON Web Key Set (JWKS) endpoint.

## Overview

This infrastructure hosts a public HTTPS endpoint that serves your Epic FHIR public key in JWK Set format, required by Epic for Backend OAuth 2.0 authentication since November 2025 (static key uploads no longer supported).

## Architecture

```
S3 Bucket (jwks.json) → CloudFront (HTTPS + Caching) → Public HTTPS URL
```

## What Gets Deployed

- **S3 Bucket**: Stores `jwks.json` file
- **CloudFront Distribution**: Global CDN with HTTPS, 29-hour cache (Epic default)
- **Origin Access Identity (OAI)**: Secure S3 access (bucket remains private)

## Prerequisites

1. AWS credentials configured (`quicksuite` profile)
2. Node.js 18+ and npm
3. AWS CDK CLI: `npm install -g aws-cdk`

## Setup

```bash
# Install dependencies
npm install

# Bootstrap CDK (first time only)
cdk bootstrap --profile quicksuite

# Deploy
npm run deploy -- --profile quicksuite
```

## Deployment Output

After deployment, you'll get:
```
Outputs:
EpicJwksStack.JwksUrl = https://d1234567890abc.cloudfront.net/jwks.json
```

## Register in Epic App

1. Copy the `JwksUrl` from deployment output
2. Go to https://fhir.epic.com/Developer/Apps
3. Edit your app *(Client ID comes from your Epic app registration; not stored in this repo)*
4. In "Non-Production JWK Set URL", paste the CloudFront URL
5. Save

## Key Rotation

To rotate your public key:

1. Generate new keypair in parent project:
   ```bash
   cd ..
   openssl genrsa -out .epic-credentials/epic_private_key_new.pem 2048
   openssl rsa -in .epic-credentials/epic_private_key_new.pem -pubout -out .epic-credentials/epic_public_key_new.pem
   ```

2. Convert new public key to JWK:
   ```bash
   cd epic-jwks-hosting-cdk
   source venv/bin/activate
   python scripts/convert_pem_to_jwk.py ../.epic-credentials/epic_public_key_new.pem
   ```

3. Update `jwks.json` with multiple keys (old + new)

4. Redeploy:
   ```bash
   npm run deploy -- --profile quicksuite
   ```

5. Wait 5 minutes, then remove old key from `jwks.json` and redeploy

## Costs

Estimated: **~$0.50/month**
- S3: ~$0.02/month (1 object)
- CloudFront: ~$0.08/month for first 10TB (very minimal traffic)

## Stack Independence

This stack is **separate from healthcare-agents-stack**:
- Independent deployment lifecycle
- Can be destroyed without affecting healthcare agents
- Reusable for other Epic FHIR integrations

## Troubleshooting

**CloudFront not serving latest jwks.json:**
```bash
# Invalidate cache
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*" \
  --profile quicksuite
```

**Test endpoint:**
```bash
curl https://d1234567890abc.cloudfront.net/jwks.json
```

Should return:
```json
{
  "keys": [
    {
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "kid": "d6442e4fb9469893",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

## Security

- ✅ HTTPS-only (CloudFront enforced)
- ✅ S3 bucket private (CloudFront OAI for access)
- ✅ No authentication required (public endpoint, as Epic requires)
- ✅ Read-only (only GET/HEAD methods allowed)
- ✅ CORS enabled for Epic's requests

## CDK Commands

- `npm run build` - Compile TypeScript
- `npm run synth` - Synthesize CloudFormation template
- `npm run deploy` - Deploy stack
- `cdk destroy` - Delete stack (keeps S3 bucket)
