FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Tudo num único layer, com as listas do apt disponíveis até o final:
# 1) libs de sistema do WeasyPrint (nomes do Debian bookworm)
# 2) dependências Python
# 3) Chromium do Playwright + suas dependências de SO (--with-deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
