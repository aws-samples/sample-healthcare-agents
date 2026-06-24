# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
CDS Hooks Lambda handler for EHR integration.

Implements the CDS Hooks specification (https://cds-hooks.hl7.org/) to enable
seamless integration with EHR systems. Supports:
- Service discovery (GET /cds-services)
- patient-view hook: Retrieves patient conditions from HealthLake
- order-select hook: Determines if prior authorization is required using
  payor rules and clinical data from HealthLake

Based on: https://github.com/aws-samples/aws-crd-hooks-with-awshealthlake-api
"""

import json
import logging
import os
from pathlib import Path

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session
import urllib.parse

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
aws_region = os.getenv("HEALTHLAKE_REGION", "us-east-1")
HEALTHLAKE_DATASTORE_ID = os.getenv("HEALTHLAKE_DATASTORE_ID")
HEALTHLAKE_ENDPOINT = f"https://healthlake.{aws_region}.amazonaws.com"

session = boto3.Session()
credentials = session.get_credentials()
http_session = URLLib3Session()

# Single-source-of-truth prior-auth requirement rule lives in the payor-policy
# Lambda (lookup_prior_auth_requirements). CDS order-select delegates to it so
# the EHR card and the Prior Auth Agent share one rule source. The local
# keyword heuristic below is kept only as a resilience fallback if the
# payor-policy Lambda is unavailable.
PAYOR_POLICY_LAMBDA_NAME = os.getenv("PAYOR_POLICY_LAMBDA_NAME")
# App URL used to deep-link the EHR card to the agent-backed prior-auth flow.
APP_URL = os.getenv("APP_URL", "").rstrip("/")
# Option 2: headless agent Function URL + HMAC secret to sign card links so a
# click runs the full Prior Auth Agent with no browser login / multi-step UI.
PRIOR_AUTH_RUN_URL = os.getenv("PRIOR_AUTH_RUN_URL", "").rstrip("/")
RUN_SECRET_ARN = os.getenv("RUN_SECRET_ARN", "")
_lambda_client = boto3.client("lambda", region_name=aws_region)
_sm_client = boto3.client("secretsmanager", region_name=aws_region)
_run_secret_cache = {}


def _get_run_secret():
    """Fetch (and cache) the HMAC secret used to sign Option 2 run links."""
    if not RUN_SECRET_ARN:
        return None
    if "v" not in _run_secret_cache:
        try:
            _run_secret_cache["v"] = _sm_client.get_secret_value(
                SecretId=RUN_SECRET_ARN
            )["SecretString"]
        except Exception:
            logger.warning("run_secret_fetch_failed", exc_info=False)
            _run_secret_cache["v"] = None
    return _run_secret_cache["v"]


def _prior_auth_run_link(patient_id, code, desc, payor):
    """Build a short-lived HMAC-signed link to the headless agent Function URL.

    Returns None if Option 2 isn't configured, so the caller can fall back to
    the in-app deep link.
    """
    import hashlib
    import hmac
    import time

    secret = _get_run_secret()
    if not PRIOR_AUTH_RUN_URL or not secret or not patient_id:
        return None
    exp = str(int(time.time()) + 1800)  # 30-minute validity
    sig = hmac.new(
        secret.encode("utf-8"), f"{patient_id}|{exp}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    qs = "&".join([
        f"patientId={urllib.parse.quote(patient_id)}",
        f"code={urllib.parse.quote(code or '')}",
        f"desc={urllib.parse.quote(desc or '')}",
        f"payor={urllib.parse.quote(payor or '')}",
        f"exp={exp}",
        f"sig={sig}",
    ])
    return f"{PRIOR_AUTH_RUN_URL}?{qs}"


def _requirement_from_policy(procedure_code, payer_name, description=None):
    """Query the canonical payor-policy requirement rule (single source of truth).

    Invokes the payor-policy Lambda's lookup_prior_auth_requirements tool, passing
    both the code and the medication/procedure description (EHRs send product-level
    RxNorm codes that vary, so name matching is the reliable signal for drugs).
    Returns True/False when determinable, or None if it could not be resolved.
    """
    if not PAYOR_POLICY_LAMBDA_NAME or (not procedure_code and not description):
        return None
    try:
        resp = _lambda_client.invoke(
            FunctionName=PAYOR_POLICY_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps({
                "action_name": "lookup_prior_auth_requirements",
                "procedure_code": procedure_code,
                "payor_name": payer_name,
                "description": description,
            }).encode("utf-8"),
        )
        payload = json.loads(resp["Payload"].read() or b"{}")
        text = (payload.get("content") or [{}])[0].get("text", "{}")
        data = json.loads(text)
        val = data.get("typically_requires_prior_auth")
        return val if isinstance(val, bool) else None
    except Exception:
        logger.warning("payor_policy_lookup_failed", exc_info=False)
        return None

# DTR config path for payer questionnaire lookup
DTR_CONFIG_PATH = os.getenv(
    "DTR_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "dtr-config", "payer-questionnaires.json"),
)

_dtr_config_cache = None


def _load_dtr_config():
    """Load and cache the payer DTR questionnaire configuration."""
    global _dtr_config_cache
    if _dtr_config_cache is not None:
        return _dtr_config_cache

    config_path = Path(DTR_CONFIG_PATH).resolve()
    if not config_path.exists():
        _dtr_config_cache = {"payers": []}
        return _dtr_config_cache

    with open(config_path, "r", encoding="utf-8") as f:
        _dtr_config_cache = json.load(f)
    return _dtr_config_cache


def _get_dtr_questionnaire_url(payer_name, procedure_code):
    """Look up DTR Questionnaire URL for a payer/procedure combination."""
    if not payer_name or not procedure_code:
        return None

    config = _load_dtr_config()
    payer_name_lower = payer_name.strip().lower()

    for payer in config.get("payers", []):
        names = [payer["payer_name"].lower()] + [a.lower() for a in payer.get("aliases", [])]
        if payer_name_lower not in names:
            continue
        for q in payer.get("questionnaires", []):
            if q.get("procedure_code") == procedure_code:
                return q["questionnaire_url"]
    return None


def fhir_search(resource_type, params):
    """Execute FHIR search query with SigV4 authentication."""
    if not HEALTHLAKE_DATASTORE_ID:
        raise Exception("HEALTHLAKE_DATASTORE_ID environment variable not set")

    query_string = urllib.parse.urlencode(params)
    url = f"{HEALTHLAKE_ENDPOINT}/datastore/{HEALTHLAKE_DATASTORE_ID}/r4/{resource_type}?{query_string}"

    request = AWSRequest(method="GET", url=url)
    SigV4Auth(credentials, "healthlake", aws_region).add_auth(request)

    response = http_session.send(request.prepare())
    if response.status_code != 200:
        raise Exception(
            f"HealthLake API error: {response.status_code} - {response.text}"
        )

    return json.loads(response.content)


def _codeable_label(cc):
    """Best-effort human label from a FHIR CodeableConcept.

    EHRs/CDS clients populate the ordered item inconsistently — sometimes in
    ``text``, sometimes only in ``coding[].display``, sometimes only a code.
    Try them in order so the prior-auth keyword/code logic has something to work
    with (fixes 'Unknown medication' when the sandbox omits .text).
    """
    if not isinstance(cc, dict):
        return None
    if cc.get("text"):
        return cc["text"]
    for c in cc.get("coding") or []:
        if c.get("display"):
            return c["display"]
    for c in cc.get("coding") or []:
        if c.get("code"):
            return c["code"]
    return None


def _first_code(cc):
    """Return the first coding code from a CodeableConcept, or None."""
    if not isinstance(cc, dict):
        return None
    for c in cc.get("coding") or []:
        if c.get("code"):
            return c["code"]
    return None


def get_cds_services(*, public: bool = False):
    """
    CDS Hooks service discovery endpoint.

    Returns the list of CDS services available, following the CDS Hooks spec.
    EHR systems call this to discover what hooks are supported.

    Threat T9 mitigation:
        ``public=True`` returns a *minimal* discovery payload (id, hook, name,
        description only) — no prefetch templates, no parameter examples.
        Removing prefetch from the public payload prevents unauthenticated
        callers from learning the parameter shape and lowers the
        reconnaissance value of the endpoint.

        Authenticated callers (``public=False``) get the full payload
        including prefetch templates that the EHR needs to invoke hooks.
    """
    full_services = [
        {
            "hook": "patient-view",
            "name": "prior-auth-patient-view",
            "description": "Retrieves patient conditions and flags procedures that may require prior authorization.",
            "id": "prior-auth-patient-view",
            "prefetch": {
                "patient": "Patient/{{context.patientId}}",
                "conditions": "Condition?patient={{context.patientId}}",
            },
        },
        {
            "hook": "order-select",
            "name": "prior-auth-order-select",
            "description": "Evaluates whether prior authorization is required for the selected order based on payor rules and patient clinical data.",
            "id": "prior-auth-order-select",
            "prefetch": {
                "patient": "Patient/{{context.patientId}}",
                "conditions": "Condition?patient={{context.patientId}}",
                "coverage": "Coverage?patient={{context.patientId}}",
            },
        },
    ]

    if not public:
        return {"services": full_services}

    # Minimized payload for unauthenticated callers — no prefetch templates.
    return {
        "services": [
            {k: v for k, v in s.items() if k != "prefetch"}
            for s in full_services
        ]
    }


def handle_patient_view(event):
    """
    patient-view CDS Hook handler.

    Triggered when a provider opens a patient chart. Retrieves patient
    conditions from HealthLake and returns informational cards about
    conditions that may require prior authorization for future orders.
    """
    context = event.get("context", {})
    patient_id = context.get("patientId")

    if not patient_id:
        return {"cards": []}

    # Retrieve patient conditions from HealthLake
    try:
        conditions_bundle = fhir_search(
            "Condition", {"patient": patient_id, "_sort": "-onset-date"}
        )
    except Exception as e:
        return {
            "cards": [
                {
                    "summary": "Unable to retrieve patient conditions",
                    "indicator": "warning",
                    "detail": str(e),
                    "source": {"label": "Prior Auth Agent"},
                }
            ]
        }

    conditions = []
    for entry in conditions_bundle.get("entry", []):
        resource = entry.get("resource", {})
        code_text = resource.get("code", {}).get("text", "Unknown")
        clinical_status = (
            resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "")
        )
        if clinical_status == "active":
            conditions.append(code_text)

    if not conditions:
        return {"cards": []}

    return {
        "cards": [
            {
                "summary": f"Patient has {len(conditions)} active condition(s)",
                "indicator": "info",
                "detail": f"Active conditions: {', '.join(conditions)}. "
                "Review these when ordering procedures — some may require prior authorization.",
                "source": {"label": "Prior Auth Agent"},
            }
        ]
    }


def handle_order_select(event):
    """
    order-select CDS Hook handler.

    Triggered when a provider selects an order (medication, procedure, etc.).
    Evaluates whether prior authorization is required based on:
    - Patient's insurance coverage from HealthLake
    - The ordered procedure/medication code
    - Payor-specific prior authorization rules

    Returns CDS cards indicating whether prior auth is needed.
    When prior auth is required and a DTR Questionnaire is configured for the
    payer/procedure, includes a SMART link to the DTR Questionnaire.
    """
    context = event.get("context", {})
    patient_id = context.get("patientId")
    draft_orders = context.get("draftOrders", {})

    if not patient_id or not draft_orders:
        return {"cards": []}

    # Extract order details
    orders = draft_orders.get("entry", [])
    if not orders:
        return {"cards": []}

    # Retrieve coverage to determine payer name and coverage ID
    payer_name = None
    coverage_id = None
    try:
        coverage_bundle = fhir_search("Coverage", {"patient": patient_id, "status": "active"})
        coverage_entries = coverage_bundle.get("entry", [])
        has_coverage = len(coverage_entries) > 0
        if has_coverage:
            cov_resource = coverage_entries[0].get("resource", {})
            coverage_id = cov_resource.get("id")
            # Extract payer name from payor reference display or organization
            payors = cov_resource.get("payor", [])
            if payors:
                payer_name = payors[0].get("display")
    except Exception:
        has_coverage = False

    cards = []

    for order_entry in orders:
        resource = order_entry.get("resource", {})
        resource_type = resource.get("resourceType", "")

        # Extract the ordered item description and code. EHR/CDS clients vary in
        # where they put the label (text vs coding.display vs medicationReference),
        # so parse defensively.
        procedure_code = None
        if resource_type == "MedicationRequest":
            order_type = "medication"
            cc = resource.get("medicationCodeableConcept", {})
            order_desc = _codeable_label(cc)
            procedure_code = _first_code(cc)
            if not order_desc:
                # Some clients send a medicationReference instead of a concept
                order_desc = (resource.get("medicationReference") or {}).get("display")
            order_desc = order_desc or "Unknown medication"
        elif resource_type == "ServiceRequest":
            order_type = "procedure"
            cc = resource.get("code", {})
            order_desc = _codeable_label(cc) or "Unknown procedure"
            procedure_code = _first_code(cc)
        else:
            order_desc = "Unknown order"
            order_type = "other"

        # Diagnostic: log the order item shape (synthetic order data, not PHI) so
        # we can see how the calling EHR/sandbox structured the medication/code.
        logger.info(
            "order_select_item type=%s resolved_desc=%r code=%s raw=%s",
            resource_type,
            order_desc,
            procedure_code,
            json.dumps(resource.get("medicationCodeableConcept")
                       or resource.get("medicationReference")
                       or resource.get("code") or {})[:500],
        )

        # Check patient claims history for this type of order
        try:
            claims_bundle = fhir_search("Claim", {"patient": f"Patient/{patient_id}"})
            has_prior_claims = len(claims_bundle.get("entry", [])) > 0
        except Exception:
            has_prior_claims = False

        # Determine if prior auth is required. The canonical payor-policy rule
        # (shared with the Prior Auth Agent) is the single source of truth and
        # is fully dynamic — it model-assesses the actual submitted order. There
        # is intentionally NO hardcoded keyword/code fallback here: asserting a
        # negative from a keyword miss caused false "No Prior Auth Required"
        # results. If the canonical rule cannot be resolved we surface an
        # explicit "could not determine" card rather than guessing.
        prior_auth_required = _requirement_from_policy(procedure_code, payer_name, order_desc)

        if prior_auth_required is None:
            cards.append(
                {
                    "summary": f"Unable to determine prior authorization for {order_desc}",
                    "indicator": "warning",
                    "detail": (
                        f"The prior-authorization rule service was unavailable for this "
                        f"{order_type}: {order_desc}. Verify requirements directly with the "
                        "payer before proceeding."
                    ),
                    "source": {"label": "Prior Auth Agent"},
                }
            )
            continue

        if prior_auth_required:
            card = {
                "summary": f"Prior Authorization Required for {order_desc}",
                "indicator": "critical",
                "detail": (
                    f"Prior authorization is required for this {order_type}: {order_desc}. "
                    "Use the Prior Authorization Agent to submit the request automatically."
                ),
                "source": {"label": "Prior Auth Agent"},
                "suggestions": [
                    {
                        "label": "Submit Prior Authorization",
                        "actions": [
                            {
                                "type": "create",
                                "description": f"Create prior auth request for {order_desc}",
                                "resource": {
                                    "resourceType": "Task",
                                    "status": "requested",
                                    "intent": "order",
                                    "code": {
                                        "text": "prior-authorization-request"
                                    },
                                    "for": {"reference": f"Patient/{patient_id}"},
                                    "description": f"Prior authorization for {order_desc}",
                                },
                            }
                        ],
                    }
                ],
            }

            # Add DTR Questionnaire link if configured for this payer/procedure
            dtr_url = _get_dtr_questionnaire_url(payer_name, procedure_code) if payer_name and procedure_code else None
            if dtr_url:
                card["links"] = [
                    {
                        "label": "Complete DTR Questionnaire",
                        "url": dtr_url,
                        "type": "smart",
                        "appContext": json.dumps({
                            "patientId": patient_id,
                            "coverageId": coverage_id,
                            "serviceCode": procedure_code,
                        }),
                    }
                ]
            elif payer_name and procedure_code:
                # No DTR config — set warning indicator with manual documentation note
                card["indicator"] = "warning"
                card["detail"] += (
                    " No DTR questionnaire is configured for this payer/procedure combination. "
                    "Manual documentation may be required."
                )

            # Route the card's submit link to the full Amplify prior-auth UI,
            # carrying the order context so the app auto-populates it. The app
            # resolves patient demographics/coverage and runs the agent-backed
            # workflow (which makes the decision and persists the ClaimResponse).
            if APP_URL:
                qs = "&".join([
                    f"patientId={urllib.parse.quote(patient_id)}",
                    f"code={urllib.parse.quote(procedure_code or '')}",
                    f"desc={urllib.parse.quote(order_desc or '')}",
                    f"payor={urllib.parse.quote(payer_name or '')}",
                ])
                card.setdefault("links", []).append({
                    "label": "Submit Prior Authorization (AI agent)",
                    "url": f"{APP_URL}/orders/prior-auth?{qs}",
                    "type": "absolute",
                })

            cards.append(card)
        else:
            cards.append(
                {
                    "summary": f"No Prior Authorization Required for {order_desc}",
                    "indicator": "info",
                    "detail": f"Based on available coverage data, prior authorization does not appear to be required for this {order_type}.",
                    "source": {"label": "Prior Auth Agent"},
                }
            )

    return {"cards": cards}


def _allowed_cors_origin(event):
    """Return the request Origin if it's on the allowlist, else the first
    allowlisted origin. Set CDS_HOOKS_ALLOWED_ORIGINS env var to a
    comma-separated list. Mitigates Threat T9 by replacing wildcard
    CORS with an explicit allowlist."""
    raw = os.getenv("CDS_HOOKS_ALLOWED_ORIGINS", "")
    allowed = [o.strip() for o in raw.split(",") if o.strip()]
    if not allowed:
        return None  # CORS off if not configured
    headers = event.get("headers") or {}
    origin = headers.get("Origin") or headers.get("origin") or ""
    return origin if origin in allowed else allowed[0]


def _verify_bearer_token(event):
    """Verify the EHR's bearer token on CDS Hooks requests.

    Threat T9 mitigation. Returns ``(ok, error_message)``.

    The expected token issuer / audience is configured via env vars:
    - ``CDS_HOOKS_REQUIRED_ISS``: token ``iss`` claim must match
    - ``CDS_HOOKS_REQUIRED_AUD``: token ``aud`` claim must match
    - ``CDS_HOOKS_JWKS_URL``: JWKS endpoint for the EHR's signing keys

    If none of these env vars are set the lambda is in *dev mode* — it
    requires the ``Authorization: Bearer <token>`` header to be present
    but does not verify the signature. Production deployments MUST set
    all three.
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    auth_header = headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return False, "Missing Authorization: Bearer <token> header"

    token = auth_header[7:].strip()
    if not token:
        return False, "Empty bearer token"

    required_iss = os.getenv("CDS_HOOKS_REQUIRED_ISS", "")
    required_aud = os.getenv("CDS_HOOKS_REQUIRED_AUD", "")
    jwks_url = os.getenv("CDS_HOOKS_JWKS_URL", "")

    if not required_iss or not required_aud or not jwks_url:
        # Dev mode — token presence checked but signature not validated.
        # Production deployments must configure all three env vars.
        logger.warning(
            "cds_hooks_auth=dev_mode_token_unverified iss_set=%s aud_set=%s jwks_set=%s",
            bool(required_iss), bool(required_aud), bool(jwks_url),
        )
        return True, None

    # Production mode: verify against JWKS.
    try:
        import jwt  # PyJWT, must be in lambda layer
        from jwt import PyJWKClient
        jwks = PyJWKClient(jwks_url, cache_keys=True, lifespan=300)
        signing_key = jwks.get_signing_key_from_jwt(token).key
        jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            issuer=required_iss,
            audience=required_aud,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
        return True, None
    except ImportError:
        logger.error("PyJWT not available; cannot verify token signature")
        return False, "Token verification unavailable"
    except Exception as e:
        logger.warning("cds_hooks_auth=token_verification_failed reason=%s", type(e).__name__)
        return False, "Invalid bearer token"


def handle_rest_request(event):
    """
    Route API Gateway HTTP events to the correct CDS Hooks handler.

    Supports:
      GET  /cds-services                              → get_cds_services()
      POST /cds-services/prior-auth-patient-view       → handle_patient_view()
      POST /cds-services/prior-auth-order-select       → handle_order_select()

    Threat T9 mitigation:
        - Discovery endpoint: returns minimized payload (no prefetch templates)
          to unauthenticated callers; full payload only with valid bearer token.
        - Hook invocation endpoints: require valid bearer token.
        - CORS: tightened to the configured allowlist instead of '*'.
    """
    http_method = event.get("httpMethod", "GET")
    path = event.get("path", "")

    cors_origin = _allowed_cors_origin(event) or ""
    cors_headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Content-Type": "application/json",
    }
    if cors_origin:
        cors_headers["Access-Control-Allow-Origin"] = cors_origin
        cors_headers["Vary"] = "Origin"

    # Handle CORS preflight
    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers, "body": ""}

    # Authenticate (T9). Discovery: token optional → minimized payload.
    # Hook invocation: token REQUIRED.
    is_discovery = path.endswith("/cds-services") and http_method == "GET"
    auth_ok, auth_err = _verify_bearer_token(event)

    if not auth_ok and not is_discovery:
        return {
            "statusCode": 401,
            "headers": {**cors_headers, "WWW-Authenticate": 'Bearer realm="cds-hooks"'},
            "body": json.dumps({"error": auth_err or "Unauthorized"}),
        }

    try:
        if is_discovery:
            # Authenticated discovery → full prefetch templates.
            # Unauthenticated discovery → minimized payload (no schemas).
            result = get_cds_services(public=not auth_ok)
        elif path.endswith("/prior-auth-patient-view") and http_method == "POST":
            body = json.loads(event.get("body", "{}"))
            result = handle_patient_view(body)
        elif path.endswith("/prior-auth-order-select") and http_method == "POST":
            body = json.loads(event.get("body", "{}"))
            result = handle_order_select(body)
        else:
            return {
                "statusCode": 404,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Unknown route: {http_method} {path}"}),
            }

        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps(result),
        }
    except Exception as e:
        logger.exception("CDS Hooks request failed")
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": "Internal error"}),
        }


def handler(event, context):
    """Main Lambda handler for CDS Hooks endpoints.

    Supports dual invocation:
    - API Gateway REST (external EHR): detected by 'httpMethod' in event
    - AgentCore Gateway MCP (agent): detected by tool name in context/event
    """
    try:
        # PHI-safe event logging (mitigates Threat T11).
        # Log only structural metadata, never the event payload itself.
        logger.info(
            "event_summary=%s",
            json.dumps({
                "top_level_keys": sorted(event.keys()) if isinstance(event, dict) else [],
                "size_bytes": len(json.dumps(event, default=str)) if event else 0,
                "invocation": "api_gateway" if isinstance(event, dict) and "httpMethod" in event else "mcp",
                "httpMethod": event.get("httpMethod") if isinstance(event, dict) else None,
                "path": event.get("path") if isinstance(event, dict) else None,
            }, default=str),
        )

        # Dual-invocation detection: REST vs MCP
        if "httpMethod" in event:
            return handle_rest_request(event)

        # MCP invocation path — determine which hook/endpoint was called
        tool_name = None
        if context and hasattr(context, "client_context") and context.client_context:
            custom = getattr(context.client_context, "custom", None)
            if custom and isinstance(custom, dict):
                tool_name = custom.get("bedrockAgentCoreToolName")

        if not tool_name:
            tool_name = event.get("action_name")

        if tool_name and "___" in tool_name:
            tool_name = tool_name.split("___")[-1]

        if not tool_name:
            # Default: service discovery
            tool_name = "get_cds_services"

        print(f"Tool name: {tool_name}")

        if tool_name == "get_cds_services":
            result = get_cds_services()
        elif tool_name == "handle_patient_view":
            result = handle_patient_view(event)
        elif tool_name == "handle_order_select":
            result = handle_order_select(event)
        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            }

        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "isError": True}
