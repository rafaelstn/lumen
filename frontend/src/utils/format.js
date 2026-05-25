const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const brlCompacto = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

export function moeda(valor) {
  return brl.format(Number(valor) || 0);
}

// Versão compacta para KPIs (ex.: R$ 1,2 mi) — evita estourar o card.
export function moedaCompacta(valor) {
  return brlCompacto.format(Number(valor) || 0);
}

export function percentual(valor) {
  return `${(Number(valor) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export function numero(valor) {
  return (Number(valor) || 0).toLocaleString("pt-BR");
}

// Data/hora pt-BR (ex.: "22/05/2026, 14:30"). Aceita ISO string ou Date.
// Devolve "—" para valor ausente/inválido em vez de "Invalid Date".
const dataHoraBr = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function dataHora(valor) {
  if (!valor) return "—";
  const d = valor instanceof Date ? valor : new Date(valor);
  if (Number.isNaN(d.getTime())) return "—";
  return dataHoraBr.format(d);
}

// Variante "suave" para fundos de tabela e chips claros.
export const CORES_GRUPO = {
  A: "bg-jade-50 text-jade-700 border-jade-200",
  B: "bg-amber-50 text-amber-700 border-amber-200",
  C: "bg-signal-50 text-signal-700 border-signal-200",
  INDEFINIDO: "bg-slate-100 text-slate-600 border-slate-300",
};

// Cor base (hex) de cada grupo, usada no donut e barras do Recharts.
export const HEX_GRUPO = {
  A: "#059669",
  B: "#f59e0b",
  C: "#dc2626",
  INDEFINIDO: "#94a3b8",
};

export const ROTULO_GRUPO = {
  A: "Grupo A — crédito pleno",
  B: "Grupo B — crédito simbólico",
  C: "Grupo C — sem crédito",
  INDEFINIDO: "Indefinido",
};

// Metadados visuais por status de CND (regularidade fiscal).
export const STATUS_CND = {
  NEGATIVA: { rotulo: "Negativa", classe: "bg-jade-50 text-jade-700 border-jade-200", regular: true },
  POSITIVA_EFEITO_NEGATIVA: {
    rotulo: "Positiva c/ efeito negativo",
    classe: "bg-jade-50 text-jade-700 border-jade-200",
    regular: true,
  },
  POSITIVA: { rotulo: "Positiva (débito)", classe: "bg-signal-50 text-signal-700 border-signal-200", regular: false },
  FALHA: { rotulo: "Falha na consulta", classe: "bg-slate-100 text-slate-500 border-slate-300", regular: null },
};

export function statusCndMeta(status) {
  return STATUS_CND[status] ?? null;
}

// Metadados visuais por nível de risco 2027.
export const RISCO_2027 = {
  ALTO: { rotulo: "Risco alto", classe: "bg-signal-600 text-white", chip: "bg-signal-50 text-signal-700 border-signal-200" },
  MEDIO: { rotulo: "Risco médio", classe: "bg-amber-500 text-white", chip: "bg-amber-50 text-amber-700 border-amber-200" },
  BAIXO: { rotulo: "Risco baixo", classe: "bg-jade-600 text-white", chip: "bg-jade-50 text-jade-700 border-jade-200" },
};

export function riscoMeta(risco) {
  return RISCO_2027[risco] ?? null;
}

// Formata CNPJ (14 dígitos) no padrão 00.000.000/0000-00; se não bater, devolve cru.
export function formatarCnpj(valor) {
  const so = String(valor ?? "").replace(/\D/g, "");
  if (so.length !== 14) return valor ?? "—";
  return so.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

// ---- MÓDULO 02 — Score Fiscal -----------------------------------------
// Faixa de score do fornecedor: BAIXO <40 (signal), MEDIO 40-69 (âmbar),
// ALTO ≥70 (jade). "ALTO" = fornecedor saudável; "BAIXO" = crítico.
export const FAIXA_SCORE = {
  ALTO: {
    rotulo: "Saudável",
    texto: "text-jade-700",
    anel: "text-jade-500",
    chip: "bg-jade-50 text-jade-700 border-jade-200",
    solido: "bg-jade-600 text-white",
    hex: "#059669",
  },
  MEDIO: {
    rotulo: "Atenção",
    texto: "text-amber-700",
    anel: "text-amber-500",
    chip: "bg-amber-50 text-amber-700 border-amber-200",
    solido: "bg-amber-500 text-white",
    hex: "#d97706",
  },
  BAIXO: {
    rotulo: "Crítico",
    texto: "text-signal-700",
    anel: "text-signal-500",
    chip: "bg-signal-50 text-signal-700 border-signal-200",
    solido: "bg-signal-600 text-white",
    hex: "#dc2626",
  },
};

// Deriva a faixa a partir do score numérico quando o backend não a envia.
export function faixaPorScore(score) {
  const n = Number(score) || 0;
  if (n >= 70) return "ALTO";
  if (n >= 40) return "MEDIO";
  return "BAIXO";
}

export function faixaMeta(faixa, score) {
  return FAIXA_SCORE[faixa] ?? FAIXA_SCORE[faixaPorScore(score)];
}

// Rótulo legível dos componentes do score (dict {regime, situacao_cadastral, cnd, maturidade}).
export const ROTULO_COMPONENTE = {
  regime: "Regime",
  situacao_cadastral: "Situação cadastral",
  cnd: "Regularidade (CND)",
  maturidade: "Maturidade",
};

// Metadados visuais por tipo de alerta do M02.
export const TIPO_ALERTA = {
  MUDANCA_STATUS: {
    rotulo: "Mudança de status",
    classe: "bg-amber-50 text-amber-700 border-amber-200",
    ponto: "bg-amber-500",
  },
  SCORE_CRITICO: {
    rotulo: "Score crítico",
    classe: "bg-signal-50 text-signal-700 border-signal-200",
    ponto: "bg-signal-600",
  },
  DEVEDOR_CONTUMAZ: {
    rotulo: "Devedor contumaz",
    classe: "bg-signal-50 text-signal-700 border-signal-200",
    ponto: "bg-signal-600",
  },
};

export function alertaMeta(tipo) {
  return (
    TIPO_ALERTA[tipo] ?? {
      rotulo: tipo || "Alerta",
      classe: "bg-slate-100 text-slate-600 border-slate-300",
      ponto: "bg-slate-400",
    }
  );
}
