# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Centralized observability module with PHI masking.

Supports any agent framework (Strands, LangGraph, Anthropic SDK, etc.) by
wiring into the global OpenTelemetry TracerProvider.  Agents call:

    from tools.observability import initialize_telemetry
    initialize_telemetry(service_name="my-agent")

PHI is masked via Amazon Bedrock Guardrails before export to Langfuse.
Regex patterns are used as a fallback if the guardrail is unavailable.
"""

import base64
import json
import logging
import os
import re
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

# ── PHI masking patterns ───────────────────────────────────────────────────────

_PHI_PATTERNS = [
    # ── Identifiers ────────────────────────────────────────────────────────────
    # Email addresses (HIPAA #6)
    (re.compile(r"\b[\w.+-]+?@[\w-]+?\.\w{2,}\b"), "[REDACTED EMAIL]"),
    # US phone / fax numbers (HIPAA #4, #5)
    (re.compile(r"\b(\+1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b"), "[REDACTED PHONE]"),
    # Fax label prefix
    (re.compile(r"\b(?:fax|facsimile)[:\s]+[\d()+. -]{7,}\b", re.IGNORECASE), "[REDACTED FAX]"),
    # SSN xxx-xx-xxxx (HIPAA #7)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED SSN]"),
    # IPv4 addresses (HIPAA #15)
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED IP]"),

    # ── Dates (HIPAA #3) ───────────────────────────────────────────────────────
    # DOB / admission / discharge / death with label
    (
        re.compile(
            r"\b(?:DOB|date of birth|birthdate|birth date|admission date|discharge date"
            r"|date of death|DOD|DOA)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
            re.IGNORECASE,
        ),
        "[REDACTED DATE]",
    ),
    # Bare mm/dd/yyyy or mm-dd-yyyy dates
    (
        re.compile(r"\b(0?[1-9]|1[0-2])[/\-](0?[1-9]|[12]\d|3[01])[/\-](\d{2}|\d{4})\b"),
        "[REDACTED DATE]",
    ),
    # Written month dd, yyyy  e.g. "January 15, 1952"
    (
        re.compile(
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
            r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+\d{1,2},?\s+\d{4}\b",
            re.IGNORECASE,
        ),
        "[REDACTED DATE]",
    ),
    # Ages over 89 (HIPAA #3)
    (re.compile(r"\b(?:age[d]?|aged)[:\s]+(?:9\d|1[0-9]\d)\b", re.IGNORECASE), "[REDACTED AGE 90+]"),
    (re.compile(r"\b(?:9\d|1[0-9]\d)[-\s]?year[-\s]?old\b", re.IGNORECASE), "[REDACTED AGE 90+]"),

    # ── Medical identifiers ────────────────────────────────────────────────────
    # MRN / Medical Record Number (HIPAA #8)
    (
        re.compile(r"\b(?:MRN|Medical Record(?:\s+Number)?|Chart\s+(?:Number|#))[:\s#]+[\w-]+\b", re.IGNORECASE),
        "[REDACTED MRN]",
    ),
    # Health plan beneficiary numbers (HIPAA #9)
    (
        re.compile(
            r"\b(?:beneficiary(?:\s+(?:number|#|id))?|member\s+(?:id|#)|plan\s+(?:id|#)"
            r"|policy\s+(?:number|#))[:\s#]+[\w-]+\b",
            re.IGNORECASE,
        ),
        "[REDACTED HEALTH_PLAN_ID]",
    ),
    # NPI (10-digit national provider identifier)
    (re.compile(r"\bNPI[:\s]+\d{10}\b", re.IGNORECASE), "[REDACTED NPI]"),
    # Device identifiers and serial numbers (HIPAA #13)
    (
        re.compile(
            r"\b(?:serial\s+(?:number|#|no\.?)|device\s+(?:id|#)|s/n)[:\s#]+[\w-]+\b",
            re.IGNORECASE,
        ),
        "[REDACTED DEVICE_ID]",
    ),
    # Certificate / license numbers (HIPAA #11)
    (
        re.compile(
            r"\b(?:license\s+(?:number|#|no\.?)|certificate\s+(?:number|#)|cert)[:\s#]+[\w-]+\b",
            re.IGNORECASE,
        ),
        "[REDACTED LICENSE]",
    ),
    # Account numbers (HIPAA #10)
    (
        re.compile(r"\b(?:account\s+(?:number|#|no\.?)|acct)[:\s#]+[\w-]+\b", re.IGNORECASE),
        "[REDACTED ACCOUNT]",
    ),

    # ── Geographic (HIPAA #2) ─────────────────────────────────────────────────
    # ZIP codes (5 or 9 digit) with keyword prefix
    (re.compile(r"\b(?:ZIP|zip|postal\s+code)[:\s]+\d{5}(?:-\d{4})?\b", re.IGNORECASE), "[REDACTED ZIP]"),
]


def mask_phi(value: object) -> object:
    """Apply all PHI masking patterns to a string value; non-strings pass through."""
    if not isinstance(value, str):
        return value
    for pattern, replacement in _PHI_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


# ── OTEL exporter wrapper ──────────────────────────────────────────────────────

try:
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class PHIMaskingExporter(SpanExporter):
        """Wraps any SpanExporter and redacts PHI from span data before export.

        Uses Amazon Bedrock Guardrails when guardrail_id is provided; falls back
        to regex patterns if the guardrail call fails or is not configured.
        """

        def __init__(
            self,
            wrapped: SpanExporter,
            guardrail_id: Optional[str] = None,
            guardrail_version: str = "DRAFT",
        ) -> None:
            self._wrapped = wrapped
            self._guardrail_id = guardrail_id
            self._guardrail_version = guardrail_version
            self._bedrock_client = None
            if guardrail_id:
                try:
                    import boto3
                    self._bedrock_client = boto3.client("bedrock-runtime")
                    logger.info("[TELEMETRY] Bedrock Guardrail PHI masking enabled (id=%s)", guardrail_id)
                except Exception as exc:
                    logger.warning("[TELEMETRY] Could not init bedrock-runtime client: %s", exc)

        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            for span in spans:
                self._sanitize(span)
            return self._wrapped.export(spans)

        def shutdown(self) -> None:
            self._wrapped.shutdown()

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            return self._wrapped.force_flush(timeout_millis)

        def _apply_guardrail(self, text: str) -> str:
            """Apply Bedrock Guardrail then regex to mask PHI (two-layer approach).

            Guardrail handles: names, addresses, SSN, phone, email, IP, URL, etc.
            Regex second pass handles: dates, MRN, health plan IDs, account numbers,
            device serials, license numbers, fax, ages 90+, and anything guardrail missed.
            """
            if self._bedrock_client and self._guardrail_id:
                try:
                    resp = self._bedrock_client.apply_guardrail(
                        guardrailIdentifier=self._guardrail_id,
                        guardrailVersion=self._guardrail_version,
                        source="OUTPUT",
                        content=[{"text": {"text": text}}],
                    )
                    outputs = resp.get("outputs", [])
                    if outputs:
                        text = outputs[0].get("text", text)
                except Exception as exc:
                    logger.debug("[TELEMETRY] Guardrail apply failed, using regex only: %s", exc)
            # Always run regex as second pass (catches dates, MRNs, etc. not in guardrail)
            return mask_phi(text)

        def _mask_value(self, value: object) -> object:
            if not isinstance(value, str):
                return value
            return self._apply_guardrail(value)

        # System identifiers — not PHI, skip masking to prevent false positives
        _SAFE_KEYS = frozenset({
            "user.id", "session.id", "agent.type", "service.name",
            "service.namespace", "deployment.environment",
        })

        def _sanitize(self, span: ReadableSpan) -> None:
            # Mask span attributes (BoundedAttributes supports item assignment)
            if span._attributes:
                for key in list(span._attributes.keys()):
                    if key in self._SAFE_KEYS:
                        continue
                    original = span._attributes[key]
                    masked = self._mask_value(original)
                    if masked is not original:
                        span._attributes[key] = masked

            # Mask span events
            if span._events:
                from opentelemetry.sdk.trace import Event as SDKEvent
                sanitized_events = []
                for event in span._events:
                    if event.attributes:
                        new_attrs = {k: self._mask_value(v) for k, v in event.attributes.items()}
                        try:
                            # NamedTuple-based Event (older OTEL versions)
                            sanitized_events.append(event._replace(attributes=new_attrs))
                        except AttributeError:
                            # Dataclass/object-based Event (Python 3.13+ / newer OTEL)
                            sanitized_events.append(
                                SDKEvent(
                                    name=event.name,
                                    attributes=new_attrs,
                                    timestamp=event.timestamp,
                                )
                            )
                    else:
                        sanitized_events.append(event)
                span._events = sanitized_events

except ImportError:
    PHIMaskingExporter = None  # type: ignore[assignment,misc]


# ── Public API ─────────────────────────────────────────────────────────────────

_initialized = False


def initialize_telemetry(service_name: str = "healthcare-agent") -> bool:
    """
    Initialize OTEL telemetry with PHI masking against the global TracerProvider.

    Works with any framework that instruments via OpenTelemetry:
      - Strands agents
      - LangGraph / LangChain agents
      - Anthropic SDK (with otel instrumentation)
      - Any other OTEL-instrumented library

    Credentials are fetched from AWS Secrets Manager at runtime (HIPAA-safe).
    Returns True if telemetry was successfully initialized.
    """
    global _initialized
    if _initialized:
        return True

    # nosemgrep: identical-is-comparison - PHIMaskingExporter is set to None when
    # the optional opentelemetry SDK import at module load time fails; this is a
    # legitimate `<symbol> is None` check, not an `x is x` comparison.
    if PHIMaskingExporter is None:
        logger.warning("[TELEMETRY] opentelemetry SDK not installed – skipping")
        return False

    secret_arn = os.environ.get("LANGFUSE_SECRET_ARN")
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not (secret_arn and otel_endpoint):
        logger.info("[TELEMETRY] Langfuse not configured – skipping observability")
        return False

    try:
        import boto3
        sm = boto3.client("secretsmanager")
        response = sm.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(response["SecretString"])

        public_key = secret_data.get("publicKey", "")
        secret_key = secret_data.get("secretKey", "")

        if not (public_key and secret_key):
            logger.warning("[TELEMETRY] Langfuse credentials empty – skipping")
            return False

        auth_token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        headers = {"Authorization": f"Basic {auth_token}"}

        # Fetch Bedrock Guardrail config from SSM (optional – regex fallback if absent)
        guardrail_id: Optional[str] = None
        guardrail_version: str = "DRAFT"
        ssm_base = os.environ.get("SSM_STACK_BASE", "healthcare-agents-stack")
        try:
            ssm = boto3.client("ssm")
            guardrail_id = ssm.get_parameter(
                Name=f"/{ssm_base}/phi-guardrail-id"
            )["Parameter"]["Value"]
            guardrail_version = ssm.get_parameter(
                Name=f"/{ssm_base}/phi-guardrail-version"
            )["Parameter"]["Value"]
            logger.info("[TELEMETRY] Loaded guardrail id=%s version=%s", guardrail_id, guardrail_version)
            print(f"[TELEMETRY] Bedrock Guardrail PHI masking enabled (id={guardrail_id})")
        except Exception as ssm_exc:
            logger.info("[TELEMETRY] Guardrail SSM params not found, using regex fallback: %s", ssm_exc)
            print(f"[TELEMETRY] Guardrail not found, using regex PHI fallback: {ssm_exc}")

        _setup_provider(otel_endpoint, headers, service_name, guardrail_id, guardrail_version)
        _initialized = True
        logger.info("[TELEMETRY] Initialized with PHI masking (service=%s)", service_name)
        print(f"[TELEMETRY] Langfuse observability initialized with PHI masking (service={service_name})")
        return True

    except Exception as exc:
        logger.error("[TELEMETRY] Failed to initialize: %s", exc)
        print(f"[TELEMETRY] Failed to initialize observability: {exc}")
        return False


def get_langfuse_callback(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_name: Optional[str] = None,
):
    """
    Create a Langfuse CallbackHandler for LangChain/LangGraph tracing.

    Fetches credentials from the same Secrets Manager secret used by OTEL.
    Returns None if Langfuse is not configured or the SDK is not installed.
    """
    secret_arn = os.environ.get("LANGFUSE_SECRET_ARN")
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not (secret_arn and otel_endpoint):
        return None

    try:
        from langfuse.callback import CallbackHandler
    except ImportError as e:
        print(f"[TELEMETRY] langfuse package not installed – callback unavailable: {e}")
        return None

    try:
        import boto3
        sm = boto3.client("secretsmanager")
        secret_data = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
        public_key = secret_data.get("publicKey", "")
        secret_key = secret_data.get("secretKey", "")
        if not (public_key and secret_key):
            print("[TELEMETRY] Langfuse credentials empty – callback unavailable")
            return None

        # Derive Langfuse host from OTEL endpoint (strip /api/public/otel suffix)
        host = otel_endpoint.replace("/api/public/otel/v1/traces", "")
        host = host.replace("/api/public/otel", "").rstrip("/")
        print(f"[TELEMETRY] Creating Langfuse callback (host={host}, session={session_id})")

        cb = CallbackHandler(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            session_id=session_id,
            user_id=user_id,
            trace_name=trace_name,
        )
        print("[TELEMETRY] Langfuse callback created successfully")
        return cb
    except Exception as exc:
        print(f"[TELEMETRY] Failed to create Langfuse callback: {exc}")
        return None


def _setup_provider(
    endpoint: str,
    headers: dict,
    service_name: str,
    guardrail_id: Optional[str] = None,
    guardrail_version: str = "DRAFT",
) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    environment = os.environ.get("LANGFUSE_TRACING_ENVIRONMENT", "production")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "healthcare-agents",
            "deployment.environment": environment,
        }
    )

    # OTLPSpanExporter uses the endpoint as-is; Langfuse requires /v1/traces suffix
    traces_endpoint = endpoint.rstrip("/") + "/v1/traces"
    raw_exporter = OTLPSpanExporter(endpoint=traces_endpoint, headers=headers)
    masked_exporter = PHIMaskingExporter(raw_exporter, guardrail_id=guardrail_id, guardrail_version=guardrail_version)
    processor = SimpleSpanProcessor(masked_exporter)

    # Replace (or configure) the global TracerProvider so all frameworks pick it up
    existing = trace.get_tracer_provider()
    if hasattr(existing, "add_span_processor"):
        # A SDK TracerProvider already exists (e.g. set by Strands) – just add our processor
        existing.add_span_processor(processor)
    else:
        # No SDK provider yet – create one and register it globally
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
