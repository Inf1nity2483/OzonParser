FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

RUN mkdir -p /app/data /app/data/checkpoints

ENV PYTHONUNBUFFERED=1
ENV DEMO_MODE=true
ENV LLM_MOCK=true
ENV CRM_MOCK=true
ENV PARSER_MOCK=true

CMD ["python", "-m", "src.main", "run"]
