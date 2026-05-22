# Sistema de Análise Fiscal de Fornecedores — Lumen

Plataforma web modular que recebe relatórios XLS de um ERP contábil, processa dados fiscais de ICMS por fornecedor, consulta a regularidade fiscal (CND) de cada CNPJ na Receita Federal e gera um relatório PDF formal pronto para entrega.

Cliente: IDESAN COMERCIAL LTDA. Escopo atual: **Módulo 01 — Análise de Crédito ICMS e Regularidade Fiscal**.

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.11, FastAPI, pandas + xlrd, Playwright, WeasyPrint + Jinja2, SQLAlchemy + asyncpg |
| Frontend | React 18 + Vite, TailwindCSS, Axios, React Query |
| Infra | Docker Compose, PostgreSQL 15, Nginx (produção) |

## Como subir (desenvolvimento)

```bash
docker-compose up --build
```

| Serviço | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend (API) | http://localhost:8000 |
| Health check | http://localhost:8000/health |
| Docs da API | http://localhost:8000/docs |

## Produção

```bash
docker-compose -f docker-compose.prod.yml up --build
```

Sobe atrás do Nginx na porta 80. Exige `POSTGRES_PASSWORD` e demais variáveis definidas no ambiente / `backend/.env`.

## Configuração

Copie `backend/.env.example` para `backend/.env` e preencha. **Nunca** commite `.env` nem a `CAPTCHA_API_KEY`.

A consulta de CND no portal da Receita exige resolução de captcha. O sistema usa um solver externo (2Captcha/Anti-Captcha) parametrizado por `CAPTCHA_API_KEY`.

## Testes

```bash
cd backend && pytest
```

## Estrutura modular

O sistema é desenhado para receber os módulos 02 a 05 (gestão de fornecedores, monitoramento contínuo, relatórios gerenciais, multi-cliente) sem refatoração estrutural. Cada módulo vive em `backend/app/modules/moduloXX/` com responsabilidade isolada.

## Status das fases (Módulo 01)

- [x] Fase 1 — Fundação (Docker, FastAPI, React, health check)
- [ ] Fase 2 — Parser + Classificação
- [ ] Fase 3 — Consulta CND
- [ ] Fase 4 — Engine de Risco 2027
- [ ] Fase 5 — Gerador de PDF
- [ ] Fase 6 — Interface Web
