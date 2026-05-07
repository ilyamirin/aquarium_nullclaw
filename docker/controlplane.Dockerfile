FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY orchestrator /app/orchestrator
COPY controlplane /app/controlplane
COPY manage.py /app/manage.py
COPY knowledge /app/knowledge
COPY scripts /app/scripts

RUN pip install --no-cache-dir -e .[dev]

CMD ["sh", "/app/scripts/controlplane-container-start.sh"]
