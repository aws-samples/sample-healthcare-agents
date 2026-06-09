# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Clinical Decision Support Agent - Docker Image
# Real-time clinical decision support using Epic FHIR with user authorization

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Copy project metadata and shared packages
COPY pyproject.toml .
COPY gateway/ gateway/
COPY tools/ tools/

# Copy agent requirements
COPY patterns/clinical-decision-support/requirements.txt requirements.txt

# Install dependencies using uv for fast installation
RUN uv pip install --system --no-cache -r requirements.txt && \
    uv pip install --system --no-cache aws-opentelemetry-distro==0.10.1

# Install FAST package (provides gateway and tools modules)
RUN uv pip install --system --no-cache -e . --no-deps && \
    uv pip install --system --no-cache requests>=2.31.0

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore

# Copy clinical decision support agent code
COPY patterns/clinical-decision-support/orchestrator.py .

# Fix file ownership for bedrock_agentcore user
RUN chown -R bedrock_agentcore:bedrock_agentcore /app

# Set user
USER bedrock_agentcore

# Expose port for AgentCore Runtime
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping', timeout=3)" || exit 1

# Run the orchestrator agent
CMD ["python", "orchestrator.py"]
