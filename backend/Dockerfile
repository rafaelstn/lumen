# Fixado em bookworm (Debian 12): a tag "slim" passou a apontar para o trixie
# (Debian 13), que o Playwright 1.44 ainda não reconhece no install-deps.
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .

# Libs de sistema do WeasyPrint (nomes do Debian bookworm) + dependências Python.
# A CND é consultada via API (Infosimples), então não há Playwright/Chromium aqui.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

COPY . .

# Sem --reload (modo debug). O dev local usa o docker-compose, que sobrescreve o
# comando com --reload; em produção o railway.toml define o startCommand.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
