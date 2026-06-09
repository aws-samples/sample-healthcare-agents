# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

WORKDIR /app

# Copy requirements from clinical-decision-agent-langgraph pattern
COPY patterns/clinical-decision-agent-langgraph/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared gateway utilities and tools
COPY gateway/ gateway/
COPY tools/ tools/

# Copy agent code
COPY patterns/clinical-decision-agent-langgraph/clinical_decision_agent.py .
COPY patterns/clinical-decision-agent-langgraph/epic_fhir_direct.py .

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore && \
    chown -R bedrock_agentcore:bedrock_agentcore /app
USER bedrock_agentcore

EXPOSE 8080
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping', timeout=3)" || exit 1

# Run the agent
CMD ["python", "clinical_decision_agent.py"]
