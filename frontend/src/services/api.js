import axios from "axios";

// Em dev, VITE_API_URL fica vazio e o Vite faz proxy de /api e /health.
// Em produção (Railway), VITE_API_URL aponta para a URL pública do backend.
const API_BASE = import.meta.env.VITE_API_URL ?? "";

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

export async function getHealth() {
  const { data } = await axios.get(`${API_BASE}/health`);
  return data;
}

export async function getModulo01Status() {
  const { data } = await api.get("/modulo01/status");
  return data;
}

export async function processarArquivos({ entradas }) {
  const form = new FormData();
  form.append("entradas", entradas);
  const { data } = await api.post("/modulo01/processar", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

// Busca gratuita no banco de fornecedores (cache local CNPJ ↔ razão social).
// Não consome créditos da API paga. Retorna [{ cnpj, razao_social, origem }].
export async function buscarFornecedores(q) {
  const { data } = await api.get("/modulo01/fornecedores/buscar", { params: { q } });
  return data.resultados;
}

export function urlRelatorio(jobId) {
  return `${API_BASE}/api/modulo01/relatorio/${jobId}`;
}

export async function definirCnpjManual(jobId, { cod_forn, cnpj, razao_social }) {
  const { data } = await api.post(`/modulo01/cnpj-manual/${jobId}`, {
    cod_forn,
    cnpj,
    razao_social,
  });
  return data;
}

// Enriquecimento automático de CNPJ a partir da razão social (assíncrono/sob demanda).
export async function enriquecerCnpj(jobId, limite) {
  const params = limite ? { limite } : undefined;
  const { data } = await api.post(`/modulo01/enriquecer-cnpj/${jobId}`, null, { params });
  return data;
}

// Dispara a consulta de CND (regularidade fiscal). Roda no servidor de forma
// assíncrona; o progresso é acompanhado via consultarProgresso (polling).
export async function consultarCnd(jobId, limite) {
  const params = limite ? { limite } : undefined;
  const { data } = await api.post(`/modulo01/consultar-cnd/${jobId}`, null, { params });
  return data;
}

// Snapshot do progresso da consulta CND: { total, consultados, falhas, percentual, status }.
export async function consultarProgresso(jobId) {
  const { data } = await api.get(`/modulo01/progresso/${jobId}`);
  return data;
}

// Estado atual do job (fornecedores atualizados após enriquecimento de CNPJ e CND).
export async function consultarResultado(jobId) {
  const { data } = await api.get(`/modulo01/resultado/${jobId}`);
  return data;
}

// ---- MÓDULO 02 — Score Fiscal de Fornecedores --------------------------
// Consultas que tocam due-diligence/monitorar/reavaliar consomem créditos da
// API paga (InfoSimples). O servidor pode retornar 400 com detalhe
// "INFOSIMPLES_TOKEN ausente" quando o token não está configurado.

// Due diligence em lote: avalia uma lista de CNPJs e devolve o ranking
// (pior score primeiro). { resultados, avaliados, teto_atingido }.
export async function dueDiligence(cnpjs) {
  const { data } = await api.post("/modulo02/due-diligence", { cnpjs });
  return data;
}

// Avalia um CNPJ e o adiciona à carteira monitorada.
export async function monitorarCnpj(cnpj) {
  const { data } = await api.post("/modulo02/monitorar", { cnpj });
  return data;
}

// Carteira monitorada atual.
export async function listarMonitorados() {
  const { data } = await api.get("/modulo02/monitorados");
  return data;
}

// Re-consulta toda a carteira (pode demorar). { reavaliados, alertas_gerados, teto_atingido }.
export async function reavaliarCarteira() {
  const { data } = await api.post("/modulo02/reavaliar");
  return data;
}

// Alertas gerados pela carteira.
export async function listarAlertas() {
  const { data } = await api.get("/modulo02/alertas");
  return data;
}

export default api;
