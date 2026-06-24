# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Prior Auth Run (Option 2) — headless agent invocation over public API Gateway.

Lets a CDS Hooks card trigger the full Prior Authorization Agent end-to-end with
NO browser login and NO multi-step UI.

Why async: the agent takes ~60-100s, which exceeds API Gateway's 29s integration
timeout, and this account blocks public Lambda Function URLs. So the flow is:

  GET /prior-auth-run?patientId=&code=&desc=&payor=&exp=&sig=   (start)
    -> verify short-lived HMAC token
    -> create a jobId, store RUNNING in DynamoDB
    -> async self-invoke a worker that runs the agent (up to 5 min)
    -> return a self-refreshing HTML "working…" page that polls ?jobId=<id>

  GET /prior-auth-run?jobId=<id>                                (poll)
    -> read DynamoDB; RUNNING -> refresh; DONE -> decision page

  async worker invocation ({"_worker": true, ...})
    -> mint M2M token, invoke the agent, write the decision to DynamoDB

Only the Python standard library is used for HTTP (urllib).
"""

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import time
import urllib.parse
import urllib.request
import uuid

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
STACK_NAME = os.getenv("STACK_NAME", "healthcare-agents-stack")
RUN_SECRET_ARN = os.getenv("RUN_SECRET_ARN", "")
JOBS_TABLE = os.getenv("JOBS_TABLE", "")

_ssm = boto3.client("ssm", region_name=REGION)
_sm = boto3.client("secretsmanager", region_name=REGION)
_lambda = boto3.client("lambda", region_name=REGION)
_ddb = boto3.resource("dynamodb", region_name=REGION)

_cache: dict = {}


def _ssm_param(name: str) -> str:
    if name not in _cache:
        _cache[name] = _ssm.get_parameter(Name=name)["Parameter"]["Value"]
    return _cache[name]


def _run_secret() -> str:
    if "_run_secret" not in _cache:
        _cache["_run_secret"] = _sm.get_secret_value(SecretId=RUN_SECRET_ARN)["SecretString"]
    return _cache["_run_secret"]


def _table():
    return _ddb.Table(JOBS_TABLE)


def sign(patient_id: str, exp: str) -> str:
    msg = f"{patient_id}|{exp}".encode("utf-8")
    return hmac.new(_run_secret().encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_token(patient_id: str, exp: str, sig: str) -> tuple[bool, str]:
    if not patient_id or not exp or not sig:
        return False, "Missing token parameters"
    try:
        if int(exp) < int(time.time()):
            return False, "Link expired — generate a fresh card"
    except ValueError:
        return False, "Invalid expiry"
    if not hmac.compare_digest(sign(patient_id, exp), sig):
        return False, "Invalid signature"
    return True, ""


def _get_m2m_token() -> str:
    domain = _ssm_param(f"/{STACK_NAME}/cognito_provider")
    client_id = _ssm_param(f"/{STACK_NAME}/machine_client_id")
    client_secret = _sm.get_secret_value(SecretId=f"/{STACK_NAME}/machine_client_secret")["SecretString"]
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": f"{STACK_NAME}-api/invoke",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://{domain}/oauth2/token",
        data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def _invoke_agent(prompt: str) -> str:
    token = _get_m2m_token()
    arn = _ssm_param(f"/{STACK_NAME}/prior-authorization-agent/runtime-arn")
    url = (
        f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/"
        f"{urllib.parse.quote(arn, safe='')}/invocations?qualifier=DEFAULT"
    )
    session_id = str(uuid.uuid4())
    payload = json.dumps({
        "prompt": prompt,
        "userId": "cds-hooks-run",
        "runtimeSessionId": session_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
            "X-Amzn-Bedrock-AgentCore-Runtime-User-Id": "cds-hooks-run",
        },
        method="POST",
    )
    completion = ""
    with urllib.request.urlopen(req, timeout=290) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            try:
                evt = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(evt, dict):
                continue
            text = (
                evt.get("event", {})
                .get("contentBlockDelta", {})
                .get("delta", {})
                .get("text")
            )
            if text:
                completion += text
    return completion.strip()


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
_STYLE = """<style>
 body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
   background:#f1f5f9;margin:0;padding:24px;color:#0f172a}
 .card{max-width:860px;margin:0 auto;background:#fff;border-radius:14px;
   box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden}
 .hd{padding:18px 24px;border-bottom:1px solid #e2e8f0}
 .hd h1{font-size:18px;margin:0}
 .content{padding:24px}
 pre{white-space:pre-wrap;word-wrap:break-word;font:13px/1.55 ui-monospace,Menlo,monospace;
   background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin:16px 0 0}
 .badge{display:inline-block;color:#fff;border-radius:999px;padding:6px 14px;font-weight:600;font-size:14px}
 .src{color:#64748b;font-size:12px;margin-top:8px}
 .spin{width:42px;height:42px;border:4px solid #dbeafe;border-top-color:#2563eb;
   border-radius:50%;animation:s 1s linear infinite;margin:8px 0 16px}
 @keyframes s{to{transform:rotate(360deg)}}
</style>"""


def _html(title: str, inner: str, status: int = 200, refresh_to: str | None = None) -> dict:
    head_refresh = (
        f'<meta http-equiv="refresh" content="3;url={html.escape(refresh_to)}">'
        if refresh_to else ""
    )
    page = (
        f'<!doctype html><html><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{head_refresh}<title>{html.escape(title)}</title>{_STYLE}</head>"
        f'<body><div class="card">{inner}</div></body></html>'
    )
    return {
        "statusCode": status,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "body": page,
    }


def _decision_banner(text: str) -> tuple[str, str]:
    low = text.lower()
    if "authorization is recommended" in low:
        return "Authorization Recommended", "#16a34a"
    if "authorization is denied" in low:
        return "Authorization Denied", "#dc2626"
    if "additional documentation required" in low:
        return "Additional Documentation Required", "#d97706"
    return "Assessment Complete", "#2563eb"


def _decision_page(order: str, patient_id: str, payor: str, result: str) -> dict:
    label, color = _decision_banner(result)
    inner = (
        '<div class="hd">'
        f"<h1>Prior Authorization — {html.escape(order)}</h1>"
        f'<div class="src">Patient {html.escape(patient_id)}'
        f'{" · " + html.escape(payor) if payor else ""} · AI Prior Auth Agent</div>'
        "</div>"
        '<div class="content">'
        f'<span class="badge" style="background:{color}">{html.escape(label)}</span>'
        f"<pre>{html.escape(result)}</pre>"
        "</div>"
    )
    return _html(f"Prior Authorization — {order}", inner)


def _working_page(order: str, poll_url: str) -> dict:
    inner = (
        '<div class="hd"><h1>Prior Authorization — '
        f"{html.escape(order)}</h1></div>"
        '<div class="content"><div class="spin"></div>'
        "<p><strong>The AI Prior Authorization agent is working…</strong></p>"
        "<p class=\"src\">Retrieving patient data from HealthLake, checking payer "
        "policy, and assessing medical necessity. This page refreshes "
        "automatically (typically 60–100 seconds).</p></div>"
    )
    return _html(f"Working — {order}", inner, refresh_to=poll_url)


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
def _run_worker(job_id: str, patient_id: str, code: str, desc: str, payor: str):
    order = desc or code or "the selected order"
    prompt = (
        f"Process a prior authorization for patient {patient_id} for "
        f"medication/procedure: {order}. "
        f"{'Payer: ' + payor + '. ' if payor else ''}"
        f"{'Order code: ' + code + '. ' if code else ''}"
        "Determine if prior authorization is required, gather clinical evidence "
        "from HealthLake, check payer policy, assess medical necessity, make a "
        "final authorization decision, and generate the FHIR PAS Bundle and "
        "ClaimResponse."
    )
    try:
        result = _invoke_agent(prompt) or "The agent returned no assessment text."
        _table().update_item(
            Key={"jobId": job_id},
            UpdateExpression="SET #s=:s, #r=:r",
            ExpressionAttributeNames={"#s": "status", "#r": "result"},
            ExpressionAttributeValues={":s": "DONE", ":r": result},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("worker_agent_failed job=%s", job_id)
        _table().update_item(
            Key={"jobId": job_id},
            UpdateExpression="SET #s=:s, #e=:e",
            ExpressionAttributeNames={"#s": "status", "#e": "error"},
            ExpressionAttributeValues={":s": "FAILED", ":e": str(e)},
        )


def _api_base(event) -> str:
    """Reconstruct the public request path for self-refresh poll links."""
    rc = event.get("requestContext", {})
    stage = rc.get("stage", "")
    path = event.get("path", "/prior-auth-run")
    host = (event.get("headers") or {}).get("Host") or (event.get("headers") or {}).get("host")
    if host:
        return f"https://{host}/{stage}{path}".replace(f"/{stage}/{stage}", f"/{stage}")
    return path


def handler(event, context):
    # 1) Async worker invocation
    if isinstance(event, dict) and event.get("_worker"):
        _run_worker(
            event["jobId"], event.get("patientId", ""), event.get("code", ""),
            event.get("desc", ""), event.get("payor", ""),
        )
        return {"ok": True}

    # 2) API Gateway (GET) — start or poll
    qs = event.get("queryStringParameters") or {}
    job_id = qs.get("jobId")
    order_for_title = qs.get("desc") or qs.get("code") or "the selected order"

    # --- poll ---
    if job_id:
        try:
            item = _table().get_item(Key={"jobId": job_id}).get("Item")
        except Exception:
            logger.exception("ddb_get_failed")
            item = None
        if not item:
            return _html(
                "Not found",
                '<div class="hd"><h1>Prior Authorization</h1></div>'
                '<div class="content"><p>This request was not found or has '
                "expired. Re-open the card link to start a new assessment.</p></div>",
                status=404,
            )
        status = item.get("status")
        if status == "DONE":
            return _decision_page(
                item.get("desc") or item.get("code") or "the selected order",
                item.get("patientId", ""), item.get("payor", ""), item.get("result", ""),
            )
        if status == "FAILED":
            return _html(
                "Prior authorization — error",
                '<div class="hd"><h1>Prior Authorization</h1></div>'
                '<div class="content"><p>The agent could not complete the '
                f'assessment.</p><pre>{html.escape(item.get("error", "unknown error"))}</pre></div>',
                status=502,
            )
        # still running
        poll_url = f"{_api_base(event)}?jobId={urllib.parse.quote(job_id)}"
        return _working_page(order_for_title, poll_url)

    # --- start ---
    patient_id = qs.get("patientId", "")
    code = qs.get("code", "")
    desc = qs.get("desc", "")
    payor = qs.get("payor", "")
    exp = qs.get("exp", "")
    sig = qs.get("sig", "")

    ok, err = verify_token(patient_id, exp, sig)
    if not ok:
        return _html(
            "Access denied",
            '<div class="hd"><h1>Access denied</h1></div>'
            f'<div class="content"><p>{html.escape(err)}</p></div>',
            status=403,
        )

    new_job = str(uuid.uuid4())
    ttl = int(time.time()) + 86400  # 1 day
    _table().put_item(Item={
        "jobId": new_job, "status": "RUNNING", "patientId": patient_id,
        "code": code, "desc": desc, "payor": payor, "ttl": ttl,
    })
    _lambda.invoke(
        FunctionName=context.function_name,
        InvocationType="Event",
        Payload=json.dumps({
            "_worker": True, "jobId": new_job, "patientId": patient_id,
            "code": code, "desc": desc, "payor": payor,
        }).encode("utf-8"),
    )
    poll_url = f"{_api_base(event)}?jobId={urllib.parse.quote(new_job)}"
    return _working_page(desc or code or "the selected order", poll_url)
