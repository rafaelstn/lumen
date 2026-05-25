import axios from "axios";

// Em dev, VITE_API_URL fica vazio e o Vite faz proxy de /api e /health.
// Em produção (Railway), VITE_API_URL aponta para a URL pública do backend.
const API_BASE = import.meta.env.VITE_API_URL ?? "";

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

// ---- SESSÃO / TOKEN -----------------------------------------------------
// O token vive em localStorage. Quando há token (modo auth ligado), todo
// request leva Authorization: Bearer. Quando não há (modo anônimo atual),
// nada muda no comportamento de hoje.
const TOKEN_KEY = "lumen.token";

export function lerToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || null;
  } catch {
    return null;
  }
}

export function gravarToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage indisponível: segue sem persistir */
  }
}

// Callback registrado pelo AuthProvider para reagir a um 401 (sessão expirada
// ou inválida) em modo auth ligado: limpa sessão e devolve à tela de login.
let onSessaoExpirada = null;
export function registrarHandlerSessaoExpirada(fn) {
  onSessaoExpirada = fn;
}

// Injeta o Bearer em toda request quando existe token.
api.interceptors.request.use((config) => {
  const token = lerToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Em 401, só reage se havia token (sessão de fato expirada). Em modo anônimo
// não existe token, então um eventual 401 não dispara logout.
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401 && lerToken()) {
      gravarToken(null);
      if (typeof onSessaoExpirada === "function") onSessaoExpirada();
    }
    return Promise.reject(error);
  }
);

// /health: { status, version, auth_enabled }. Define o modo de operação do app.
export async function getHealth() {
  const { data } = await axios.get(`${API_BASE}/health`);
  return data;
}

// ---- AUTENTICAÇÃO (prefixo /api/auth) ----------------------------------
// Cadastro já loga: devolve { usuario, token:{ access_token, ... } }.
export async function signup({ nome_escritorio, email, senha }) {
  const { data } = await api.post("/auth/signup", { nome_escritorio, email, senha });
  return data;
}

// Login: { access_token, token_type, expira_em_min }. 401 genérico se inválido.
export async function login({ email, senha }) {
  const { data } = await api.post("/auth/login", { email, senha });
  return data;
}

// Dados do usuário logado: { id, email, escritorio_id, role, ativo, ... }.
export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

// ---- ADMIN (prefixo /api/admin, exige token de admin; 403 se não-admin) -
export async function getAdminResumo() {
  const { data } = await api.get("/admin/resumo");
  return data;
}

export async function getAdminEscritorios() {
  const { data } = await api.get("/admin/escritorios");
  return data;
}

export async function getAdminConsumoPorEscritorio({ inicio, fim } = {}) {
  const params = {};
  if (inicio) params.inicio = inicio;
  if (fim) params.fim = fim;
  const { data } = await api.get("/admin/consumo-por-escritorio", { params });
  return data;
}

export async function getAdminEscritorioDetalhe(id) {
  const { data } = await api.get(`/admin/escritorio/${id}`);
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

// Pendentes do enriquecimento de CNPJ, separados por estado de tentativa.
// { total_pendentes, novos, ja_tentados }. "novos" nunca foram pesquisados;
// "ja_tentados" já foram consultados sem sucesso (não_encontrado/ambíguo) e,
// por padrão, NÃO são re-pesquisados (economia de crédito). Não consome crédito.
export async function consultarPendentesEnriquecimento(jobId) {
  const { data } = await api.get(`/modulo01/enriquecimento-pendentes/${jobId}`);
  return data;
}

// Dispara o enriquecimento automático de CNPJ a partir da razão social. Roda no
// servidor de forma assíncrona; retorna na hora { job_id, status, total, forcar }.
// Por padrão (forcar=false) processa só os NOVOS. Com forcar=true re-inclui os
// já-tentados sem sucesso. O progresso é acompanhado via
// consultarProgressoEnriquecimento (polling).
export async function enriquecerCnpj(jobId, { forcar = false, limite } = {}) {
  const params = {};
  if (forcar) params.forcar = true;
  if (limite) params.limite = limite;
  const { data } = await api.post(`/modulo01/enriquecer-cnpj/${jobId}`, null, {
    params: Object.keys(params).length ? params : undefined,
  });
  return data;
}

// Snapshot do progresso do enriquecimento de CNPJ:
// { total, processados, confirmados, baixa_confianca, ambiguos, nao_encontrados,
//   erros_pontuais, percentual, status ("nao_iniciado" | "em_andamento" | "concluido"),
//   creditos_esgotados, limite_taxa_atingido, teto_diario_atingido }.
export async function consultarProgressoEnriquecimento(jobId) {
  const { data } = await api.get(`/modulo01/enriquecimento-progresso/${jobId}`);
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

// ---- HISTÓRICO DE ANÁLISES — reabrir sem re-subir ----------------------
// Análises já processadas, mais recente primeiro. Não consome créditos.
// { analises: [{ id, cliente, cnpj_cliente, periodo, total_fornecedores,
//   criado_em, atualizado_em }] }.
export async function listarAnalises() {
  const { data } = await api.get("/modulo01/analises");
  return data.analises;
}

// Reabre uma análise salva: re-hidrata o job no servidor e devolve o MESMO
// shape de /resultado/{job_id} ({ job_id, status, metadados, resumo,
// fornecedores }). O job_id retornado serve para continuar enriquecimento,
// CND e PDF normalmente.
export async function abrirAnalise(id) {
  const { data } = await api.get(`/modulo01/analise/${id}`);
  return data;
}

// Remove uma análise do histórico. { id, status: "removida" }.
export async function apagarAnalise(id) {
  const { data } = await api.delete(`/modulo01/analise/${id}`);
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

// ---- CONSUMO & CUSTOS — histórico de consultas pagas -------------------
// O controle de saldo/recarga foi removido da UI (o saldo real é acompanhado no
// painel do provedor). Aqui ficou só o histórico de consumo, que o sistema
// registra de forma confiável a cada consulta paga.

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
