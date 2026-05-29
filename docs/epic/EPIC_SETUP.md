# Epic FHIR Sandbox Setup Guide

## App Registration

### 1. Go to Epic FHIR Sandbox
Visit: https://fhir.epic.com/Developer/Apps

**First time?** You'll need to create a developer account:
- Click "Sign Up"
- Use your work email
- Verify email and log in

### 2. Create New App
Click **"Create"** (top right) and select **"Backend System (Recommended)"**

This opens the app registration form with multiple sections.

### 3. App Configuration

**Application Details:**

- **Application Name**: `Healthcare Safety Agent` or `Epic FHIR Connector`
- **Application Type**: Backend System
- **FHIR Version**: R4
- **Redirect URI**: Leave blank (not needed for backend service)
- **Public Documentation URL**:
  - **Options:**
    - Your company website: `https://www.yourcompany.com`
    - GitHub repo: `https://github.com/your-org/healthcare-agents`
    - Internal wiki: `https://wiki.yourcompany.com/healthcare-agents`
    - Placeholder: `https://example.com` (for sandbox only)
  - **Note:** For sandbox, this is just informational. For production App Orchard, you'll need real public documentation.

**Incoming APIs:**
- **Search for**: Type "FHIR" and select **"Available"**
- This indicates your app will call Epic's FHIR API (not expose APIs)
- The dropdown will show "FHIR R4" or similar - select it

**SMART Scopes (select these):**
- `system/Patient.read` - Read patient demographics
- `system/MedicationRequest.read` - Read medication orders
- `system/AllergyIntolerance.read` - Read allergies
- `system/Observation.read` - Read vitals and labs

**Authentication Settings:**
- **Token Endpoint Auth Method**: `private_key_jwt` (most secure)
- **Public Key**: Upload your public key (we'll generate this in step 4)

### 4. Understanding the Fields

**Public Documentation URL - What is this?**
- Epic wants to know where users/hospitals can learn about your app
- For sandbox testing, this is NOT strictly enforced
- For production (App Orchard), you'll need real public documentation
- **Recommendation:** Use your company website or GitHub repo URL

**Incoming APIs - What does this mean?**
- "Incoming" = APIs your app will CALL (consume)
- "Outgoing" = APIs your app will EXPOSE (provide)
- Since you're calling Epic's FHIR API, select "Incoming APIs"
- Search for "FHIR" and select it from the dropdown

**Token Endpoint Auth Method - Why private_key_jwt?**
- Most secure option for backend services
- Uses asymmetric keys (public/private keypair)
- No shared secrets over the network
- Industry standard for server-to-server authentication

### 5. Generate Public/Private Key Pair

Run this command to generate keys:
```bash
# Generate private key
openssl genrsa -out epic_private_key.pem 2048

# Generate public key from private key
openssl rsa -in epic_private_key.pem -pubout -out epic_public_key.pem

# View public key to copy into Epic
cat epic_public_key.pem
```

**IMPORTANT**:
- Keep `epic_private_key.pem` secure (add to .gitignore)
- Upload `epic_public_key.pem` content to Epic app registration

### 6. Complete Registration Form - Step by Step

Fill out the Epic app registration form exactly as shown:

**Application Name**
```
Healthcare Safety Agent
```

**Application Audience**
```
Select: Backend Systems ✓
```
(Not "Patients" or "Clinicians" - this is a server-to-server integration)

**Use Case**
```
Select: General ✓
```
(Not CMS-specific unless you're building for CMS requirements)

**Public Documentation URL**
```
http://www.yourcompany.com

OR

https://github.com/your-org/healthcare-agents
```
**What to put here:**
- ✓ Your company website
- ✓ GitHub repository URL
- ✓ `http://www.example.com` (placeholder for sandbox only)
- ✗ Leave blank (field is required)

**Incoming APIs**
```
1. Click "Search available service list"
2. Search for: "FHIR" or just click "Available"
3. Click to move it to "Selected"
4. You should see it appear in the "Selected" box
```
This means your app will CALL Epic's FHIR API

**Outgoing APIs**
```
Leave empty (no selection)
```
We're not exposing APIs to Epic, only consuming them

**Non-Production JWK Set URL**
```
Leave default: http://fhir.epic.com
OR
Leave blank
```
For sandbox with private_key_jwt, this may not be used

**Production JWK Set URL**
```
Leave default: https://fhir.epic.com
OR
Leave blank
```
For production, you'll configure this if using JWK Set instead of direct key upload

**Next:** After basic info, you'll see SMART Scopes section (click "Next" or scroll down)

### 7. Save App Credentials

After registration, Epic will provide:
- **Client ID**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- **Audience URL**: `https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4`

## Epic Sandbox Endpoints

### Authentication Endpoint
```
POST https://fhir.epic.com/interconnect-fhir-oauth/oauth2/token
```

### FHIR API Base URL
```
https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4/
```

## Test Patients

Epic provides test patients in the sandbox:

| Patient Name | FHIR ID | Use Case |
|--------------|---------|----------|
| Derrick Lin | Tbt3KuCY0B5PSrJvCu2j-PlK.aiHsu2xUjUM8bWpetXoB | Adult with medications |
| Camila Lopez | eq081-VQEgP8drUUqCWzHfw3 | Pediatric with allergies |
| Desiree Powell | erXuFYUfucBZaryVksYEcMg3 | Adult with chronic conditions |

## Next Steps

1. Generate keys with commands above
2. Register app at https://fhir.epic.com/Developer/Apps
3. Save Client ID and private key securely
4. Test authentication with provided test patients
