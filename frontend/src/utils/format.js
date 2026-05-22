const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function moeda(valor) {
  return brl.format(Number(valor) || 0);
}

export function percentual(valor) {
  return `${(Number(valor) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export const CORES_GRUPO = {
  A: "bg-emerald-50 text-emerald-700 border-emerald-200",
  B: "bg-amber-50 text-amber-700 border-amber-200",
  C: "bg-rose-50 text-rose-700 border-rose-200",
  INDEFINIDO: "bg-slate-100 text-slate-600 border-slate-300",
};
