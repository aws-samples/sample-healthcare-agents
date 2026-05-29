# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY patterns/claims-submission-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared packages (gateway and tools)
COPY gateway/ gateway/
COPY tools/ tools/

# Copy agent code
COPY patterns/claims-submission-agent/claims_submission_agent.py .

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore && \
    chown -R bedrock_agentcore:bedrock_agentcore /app
USER bedrock_agentcore

# Expose port for AgentCore Runtime
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping', timeout=3)" || exit 1

CMD ["python", "claims_submission_agent.py"]
