# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

WORKDIR /app

COPY patterns/appeals-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ gateway/
COPY tools/ tools/

COPY patterns/appeals-agent/appeals_agent.py .
COPY patterns/appeals-agent/appeal_letter_builder.py .
COPY patterns/appeals-agent/deadline_tracker.py .

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore && \
    chown -R bedrock_agentcore:bedrock_agentcore /app
USER bedrock_agentcore

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping', timeout=3)" || exit 1

CMD ["python", "appeals_agent.py"]
