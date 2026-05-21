FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

COPY portfolio.yaml.example portfolio.yaml

CMD ["stock-agent", "--config", "portfolio.yaml"]
