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

// Variante "suave" para fundos de tabela e chips claros.
export const CORES_GRUPO = {
  A: "bg-jade-50 text-jade-700 border-jade-200",
  B: "bg-amber-50 text-amber-700 border-amber-200",
  C: "bg-signal-50 text-signal-700 border-signal-200",
  INDEFINIDO: "bg-slate-100 text-slate-600 border-slate-300",
};

// Variante "sólida" para badges de destaque (header de grupo, legendas do gráfico).
export const CORES_GRUPO_SOLIDA = {
  A: "bg-jade-600 text-white",
  B: "bg-amber-500 text-white",
  C: "bg-signal-600 text-white",
  INDEFINIDO: "bg-slate-400 text-white",
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
