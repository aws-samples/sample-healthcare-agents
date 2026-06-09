FROM python:3.13-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY patterns/medical-coding-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY patterns/medical-coding-agent/ .

# Copy shared utilities
COPY gateway/ gateway/
COPY tools/ tools/

# Create non-root user for security
RUN useradd -m -u 1000 bedrock_agentcore && \
    chown -R bedrock_agentcore:bedrock_agentcore /app
USER bedrock_agentcore

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/ping', timeout=3)" || exit 1

CMD ["python", "medical_coding_agent.py"]
