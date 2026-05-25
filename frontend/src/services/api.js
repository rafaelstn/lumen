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

// ---- CONSUMO & CUSTOS — controle de saldo das APIs pagas ---------------
// Saldo por controle interno: o usuário informa quanto comprou (recarga) e o
// servidor desconta o consumo real. Sempre devolve os dois serviços (cnpj e cnd).
// Aritmética monetária no backend é em centavos inteiros.

// Saldo atual: { itens: [{ servico, creditos_comprados, creditos_consumidos,
//   creditos_restantes, valor_total_pago_centavos, preco_por_credito (string
//   decimal em centavos, ex "2.499"), custo_restante_centavos }] }.
export async function getSaldo() {
  const { data } = await api.get("/consultas/saldo");
  return data;
}

// Registra uma compra de créditos (acumula, não substitui). A recarga é por
// VALOR TOTAL PAGO pelo pacote, não por preço unitário: o crédito custa fração
// de centavo (R$ 0,024990) e não cabe em centavo inteiro; o valor do pacote é exato.
// { servico, creditos, valor_total_centavos } -> { servico, creditos_comprados,
//   valor_total_pago_centavos, preco_por_credito (string), atualizado_em }.
export async function recarregar({ servico, creditos, valor_total_centavos }) {
  const { data } = await api.post("/consultas/recarga", {
    servico,
    creditos,
    valor_total_centavos,
  });
  return data;
}

// Histórico de consultas no período (datas opcionais YYYY-MM-DD):
// { itens: [...], totais: {creditos_consumidos, custo_centavos}, por_dia: [...], por_mes: [...] }.
export async function getHistorico({ inicio, fim } = {}) {
  const params = {};
  if (inicio) params.inicio = inicio;
  if (fim) params.fim = fim;
  const { data } = await api.get("/consultas/historico", { params });
  return data;
}

export default api;
