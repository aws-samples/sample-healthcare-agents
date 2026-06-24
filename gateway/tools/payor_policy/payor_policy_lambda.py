# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Payor Policy Lambda handler for prior authorization rules.

Provides tools for:
1. Searching payor prior authorization policy documents via Bedrock Knowledge Base
2. Uploading new policy documents to S3 for indexing
3. Scraping payor websites for current prior auth requirements
4. Looking up procedure-specific prior auth rules by CPT/HCPCS code

Policy documents are stored in S3 and indexed by Amazon Bedrock Knowledge Base
(backed by Amazon S3 Vectors or OpenSearch Serverless) for semantic search.
"""

import json
import logging
import os
import re
import traceback
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment configuration
aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
POLICY_KB_ID = os.getenv("POLICY_KB_ID")
POLICY_BUCKET = os.getenv("POLICY_BUCKET")
POLICY_DATA_SOURCE_ID = os.getenv("POLICY_DATA_SOURCE_ID")
# Fast model used to dynamically assess prior-auth requirement for a submitted
# medication/procedure (no hardcoded drug allow-list).
PRIOR_AUTH_MODEL_ID = os.getenv(
    "PRIOR_AUTH_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)


def _dynamic_requirement(procedure_code, description, payor_name, kb_data):
    """Dynamically decide if a submitted order requires prior authorization.

    Reasons about the *actual* medication/procedure (drug class, cost, advanced
    imaging/surgery) for the given payer using Bedrock, grounded with any payer
    policy KB excerpts. This is intentionally NOT a hardcoded allow-list.

    Returns (requires: bool|None, name: str|None, source: str|None). Returns
    (None, None, None) when the model call is unavailable so the caller can fall
    back to the offline reference table.
    """
    label = (description or "").strip() or (procedure_code or "").strip()
    if not label:
        return None, None, None
    try:
        client = boto3.client("bedrock-runtime", region_name=aws_region)
        excerpts = ""
        results = (kb_data or {}).get("policy_results") or []
        if results:
            excerpts = "\n\nPayer policy excerpts:\n" + "\n---\n".join(
                (r.get("content", "") or "")[:600] for r in results[:3]
            )
        payer_txt = f" for payer '{payor_name}'" if payor_name else ""
        prompt = (
            "You are a prior-authorization rules engine for US health insurance. "
            f"Decide whether this order typically requires prior authorization{payer_txt}.\n"
            f"Order description: {label}\n"
            f"Code: {procedure_code or 'n/a'}{excerpts}\n\n"
            "Base the decision on standard utilization management: specialty/biologic/"
            "high-cost injectable or infused drugs, oncology agents, advanced imaging "
            "(MRI/CT/PET), and major surgical procedures generally require prior auth; "
            "routine generics, office visits, and basic labs generally do not. "
            "If payer policy excerpts are provided, prefer them.\n"
            'Respond with ONLY compact JSON: '
            '{"requires": true|false, "name": "<short order name>", "reason": "<short>"}'
        )
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 150,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = client.invoke_model(modelId=PRIOR_AUTH_MODEL_ID, body=json.dumps(body))
        payload = json.loads(resp["body"].read())
        text = "".join(b.get("text", "") for b in payload.get("content", []))
        match = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(match.group(0)) if match else {}
        val = data.get("requires")
        if isinstance(val, bool):
            return val, (data.get("name") or label), "model"
    except Exception:
        logger.warning("dynamic_requirement_unavailable", exc_info=False)
    return None, None, None


def search_payor_policies(query, payor_name=None, procedure_code=None, max_results=5):
    """
    Search payor policy documents using Bedrock Knowledge Base.

    Performs semantic search across uploaded payor policy documents to find
    relevant prior authorization rules, coverage criteria, and documentation
    requirements.

    Args:
        query: Natural language search query (e.g., "MRI lumbar spine prior auth requirements")
        payor_name: Optional filter by payor name (e.g., "UnitedHealthcare", "Aetna")
        procedure_code: Optional CPT/HCPCS code to search for
        max_results: Maximum number of results to return

    Returns:
        JSON with matching policy excerpts and metadata
    """
    if not POLICY_KB_ID:
        return json.dumps({
            "error": "POLICY_KB_ID not configured. Deploy the payor policy knowledge base first.",
            "suggestion": "Upload payor policy documents to S3 and configure the knowledge base."
        })

    bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=aws_region)

    # Enhance query with payor and procedure context
    enhanced_query = query
    if payor_name:
        enhanced_query = f"{payor_name} {enhanced_query}"
    if procedure_code:
        enhanced_query = f"{enhanced_query} CPT code {procedure_code}"

    try:
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=POLICY_KB_ID,
            retrievalQuery={"text": enhanced_query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = []
        for result in response.get("retrievalResults", []):
            results.append({
                "content": result.get("content", {}).get("text", ""),
                "score": result.get("score", 0.0),
                "source": result.get("location", {}).get("s3Location", {}).get("uri", ""),
                "metadata": result.get("metadata", {}),
            })

        return json.dumps({
            "query": query,
            "payor_filter": payor_name,
            "procedure_code": procedure_code,
            "results_count": len(results),
            "policy_results": results,
        }, indent=2)

    except Exception as e:
        print(f"[KB ERROR] Error searching policy KB: {e}")
        traceback.print_exc()
        return json.dumps({"error": str(e), "query": query})


def upload_policy_document(document_content, payor_name, document_type, filename=None):
    """
    Upload a payor policy document to S3 for indexing.

    Stores the document in the policy S3 bucket organized by payor name
    and document type. After upload, triggers a knowledge base sync to
    make the document searchable.

    Args:
        document_content: The document content (text or base64-encoded binary)
        payor_name: Name of the insurance payor (e.g., "UnitedHealthcare")
        document_type: Type of document (e.g., "prior_auth_policy", "coverage_criteria",
                       "medical_necessity", "formulary")
        filename: Optional filename. Auto-generated if not provided.

    Returns:
        JSON with upload status and S3 location
    """
    if not POLICY_BUCKET:
        return json.dumps({
            "error": "POLICY_BUCKET not configured. Deploy the policy storage infrastructure first."
        })

    # Threat T4 / T17 — pre-ingestion content scan for prompt-injection
    # markers. Documents that match are quarantined for manual review rather
    # than ingested into the RAG index.
    text_for_scan = (
        document_content if isinstance(document_content, str) else ""
    )
    injection_markers = (
        "ignore previous instructions", "ignore all previous", "you are now",
        "system:", "</prompt>", "approve regardless of policy",
        "<|im_start|>", "<|im_end|>", "[[admin override]]",
    )
    flagged = [m for m in injection_markers if m.lower() in text_for_scan.lower()]
    if flagged:
        # Write to a quarantine prefix instead of the live KB-indexed path.
        try:
            s3_client = boto3.client("s3", region_name=aws_region)
            quarantine_key = (
                f"quarantine/{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-"
                f"{(filename or 'unnamed').replace('/', '_')}"
            )
            s3_client.put_object(
                Bucket=POLICY_BUCKET,
                Key=quarantine_key,
                Body=text_for_scan.encode("utf-8"),
                ContentType="text/plain",
                Metadata={
                    "rejection_reason": "prompt_injection_markers",
                    "markers_matched": ",".join(flagged)[:512],
                },
            )
        except Exception as quarantine_err:
            logger.warning("Failed to write quarantine copy: %s", quarantine_err)
        logger.warning(
            "kb_ingestion_blocked reason=prompt_injection markers=%s payor=%s",
            flagged, payor_name,
        )
        return json.dumps({
            "status": "rejected",
            "reason": "Document contains prompt-injection markers and was quarantined",
            "markers_matched": flagged,
            "payor_name": payor_name,
        })

    s3_client = boto3.client("s3", region_name=aws_region)

    # Sanitize payor name for S3 key
    safe_payor = payor_name.lower().replace(" ", "-").replace("/", "-")
    safe_type = document_type.lower().replace(" ", "-")

    if not filename:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"{safe_payor}-{safe_type}-{timestamp}.txt"

    s3_key = f"payor-policies/{safe_payor}/{safe_type}/{filename}"

    # T4 — compute SHA-256 hash for the manifest. Logged at INFO so
    # downstream auditors can compare against an out-of-band approved-hashes
    # file before promoting a KB version.
    import hashlib
    body_bytes = (
        document_content.encode("utf-8") if isinstance(document_content, str) else document_content
    )
    content_hash = hashlib.sha256(body_bytes).hexdigest()
    logger.info(
        "kb_ingestion=accepted s3_key=%s sha256=%s payor=%s doc_type=%s",
        s3_key, content_hash, payor_name, document_type,
    )

    try:
        s3_client.put_object(
            Bucket=POLICY_BUCKET,
            Key=s3_key,
            Body=body_bytes,
            ContentType="text/plain",
            Metadata={
                "payor_name": payor_name,
                "document_type": document_type,
                "upload_date": datetime.utcnow().isoformat(),
                "content_sha256": content_hash,
            },
        )

        # Trigger KB sync if data source ID is configured
        sync_status = "not_triggered"
        if POLICY_DATA_SOURCE_ID and POLICY_KB_ID:
            try:
                bedrock_agent = boto3.client("bedrock-agent", region_name=aws_region)
                bedrock_agent.start_ingestion_job(
                    knowledgeBaseId=POLICY_KB_ID,
                    dataSourceId=POLICY_DATA_SOURCE_ID,
                )
                sync_status = "sync_started"
            except Exception as sync_err:
                print(f"[SYNC WARNING] KB sync failed: {sync_err}")
                sync_status = f"sync_failed: {str(sync_err)}"

        return json.dumps({
            "status": "uploaded",
            "s3_uri": f"s3://{POLICY_BUCKET}/{s3_key}",
            "payor_name": payor_name,
            "document_type": document_type,
            "filename": filename,
            "kb_sync_status": sync_status,
        })

    except Exception as e:
        print(f"[UPLOAD ERROR] Error uploading policy document: {e}")
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def list_policy_documents(payor_name=None):
    """
    List uploaded payor policy documents.

    Args:
        payor_name: Optional filter by payor name

    Returns:
        JSON with list of policy documents and metadata
    """
    if not POLICY_BUCKET:
        return json.dumps({"error": "POLICY_BUCKET not configured."})

    s3_client = boto3.client("s3", region_name=aws_region)

    prefix = "payor-policies/"
    if payor_name:
        safe_payor = payor_name.lower().replace(" ", "-").replace("/", "-")
        prefix = f"payor-policies/{safe_payor}/"

    try:
        response = s3_client.list_objects_v2(Bucket=POLICY_BUCKET, Prefix=prefix)

        documents = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            parts = key.replace("payor-policies/", "").split("/")
            if len(parts) >= 2:
                documents.append({
                    "s3_key": key,
                    "payor": parts[0],
                    "document_type": parts[1] if len(parts) > 1 else "unknown",
                    "filename": parts[-1],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })

        return json.dumps({
            "payor_filter": payor_name,
            "document_count": len(documents),
            "documents": documents,
        }, indent=2)

    except Exception as e:
        print(f"[LIST ERROR] Error listing policy documents: {e}")
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def lookup_prior_auth_requirements(procedure_code, payor_name=None, description=None):
    """
    Look up prior authorization requirements for a specific procedure code.

    Combines knowledge base search with structured lookup to determine:
    - Whether prior auth is required for this procedure
    - What documentation is needed
    - Payor-specific submission requirements

    Args:
        procedure_code: CPT or HCPCS procedure code
        payor_name: Optional payor name for payor-specific rules

    Returns:
        JSON with prior auth requirements and documentation needs
    """
    # Search the policy knowledge base for this procedure
    query = f"prior authorization requirements for procedure code {procedure_code}"
    if payor_name:
        query = f"{payor_name} {query}"

    kb_results = search_payor_policies(query, payor_name, procedure_code, max_results=3)
    kb_data = json.loads(kb_results)

    # Offline fallback reference — used ONLY if the dynamic model assessment is
    # unavailable. This is not the primary decision path.
    fallback_procedures = {
        "77065": {"name": "Diagnostic Mammography", "requires": True},
        "77066": {"name": "Diagnostic Mammography bilateral", "requires": True},
        "72148": {"name": "MRI Lumbar Spine without contrast", "requires": True},
        "72149": {"name": "MRI Lumbar Spine with contrast", "requires": True},
        "70553": {"name": "MRI Brain with and without contrast", "requires": True},
        "27447": {"name": "Total Knee Replacement", "requires": True},
        "27130": {"name": "Total Hip Replacement", "requires": True},
        "99213": {"name": "Office Visit Level 3", "requires": False},
        "99214": {"name": "Office Visit Level 4", "requires": False},
    }

    # Primary: dynamically assess the actual submitted order (medication/procedure),
    # grounded with any payer-policy KB excerpts. No hardcoded drug allow-list.
    requires, name, source = _dynamic_requirement(procedure_code, description, payor_name, kb_data)

    # Fallback: offline reference table only if the dynamic assessment was unavailable.
    if requires is None:
        info = fallback_procedures.get(procedure_code, {})
        requires = info.get("requires", "unknown")
        name = info.get("name") or description or "Unknown — check policy documents"
        source = "reference-table"

    return json.dumps({
        "procedure_code": procedure_code,
        "payor": payor_name,
        "procedure_name": name,
        "typically_requires_prior_auth": requires,
        "determination_source": source,
        "policy_kb_results": kb_data.get("policy_results", []),
        "note": "Determination is dynamic (model-assessed for the submitted order, grounded "
                "in payer policy when a knowledge base is configured). Always verify with the "
                "specific payor for the most current requirements.",
    }, indent=2)


def handler(event, context):
    """Main Lambda handler for payor policy tools."""
    try:
        # PHI-safe event logging (mitigates Threat T11).
        logger.info(
            "event_summary=%s",
            json.dumps({
                "top_level_keys": sorted(event.keys()) if isinstance(event, dict) else [],
                "size_bytes": len(json.dumps(event, default=str)) if event else 0,
                "invocation": "mcp",
                "action_name": (event.get("action_name") or event.get("actionName")) if isinstance(event, dict) else None,
            }, default=str),
        )

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
            return {
                "content": [{"type": "text", "text": "Error: Tool name not provided"}],
                "isError": True,
            }

        print(f"Tool name: {tool_name}")

        if tool_name == "search_payor_policies":
            result = search_payor_policies(
                query=event.get("query", ""),
                payor_name=event.get("payor_name"),
                procedure_code=event.get("procedure_code"),
                max_results=event.get("max_results", 5),
            )
        elif tool_name == "upload_policy_document":
            result = upload_policy_document(
                document_content=event.get("document_content", ""),
                payor_name=event.get("payor_name", ""),
                document_type=event.get("document_type", "general"),
                filename=event.get("filename"),
            )
        elif tool_name == "list_policy_documents":
            result = list_policy_documents(payor_name=event.get("payor_name"))
        elif tool_name == "lookup_prior_auth_requirements":
            result = lookup_prior_auth_requirements(
                procedure_code=event.get("procedure_code", ""),
                payor_name=event.get("payor_name"),
                description=event.get("description"),
            )
        else:
            return {
                "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                "isError": True,
            }

        return {"content": [{"type": "text", "text": result}]}

    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return {
            "content": [{"type": "text", "text": f"Error: {str(e)}"}],
            "isError": True,
        }
