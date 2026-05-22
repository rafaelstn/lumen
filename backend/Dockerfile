FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema do WeasyPrint. Nomes de pacote do Debian bookworm
# (base do python:3.11-slim): libgdk-pixbuf-2.0-0 tem hífen extra vs. bullseye.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
