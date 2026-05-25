import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { moeda } from "../utils/format.js";

// Painel de confirmação de custo antes de disparar uma consulta paga.
// Reutilizado pelos pontos pagos do M01 (CND, enriquecimento de CNPJ) e mantém o
// mesmo padrão visual da confirmação do M02. Cálculo em centavos inteiros.
export default function ConfirmacaoCusto({
  quantidade,
  custoUnitarioCent,
  descricao,
  aviso,
  processando = false,
  onConfirmar,
  onCancelar,
}) {
  const q = Math.max(0, Math.trunc(Number(quantidade) || 0));
  // O custo unitário pode chegar fracionário (preço derivado do backend, fração
  // de centavo): preserva a fração no total e arredonda (ROUND_HALF_UP) só na
  // exibição. O unitário mostrado também é arredondado para o centavo.
  const unitExato = Math.max(0, Number(custoUnitarioCent) || 0);
  const unit = Math.round(unitExato);
  const totalCent = Math.round(q * unitExato);

  return (
    <div
      className="rounded-xl border border-jade-200 bg-jade-50 p-4"
      role="alertdialog"
      aria-label="Confirmar custo da consulta"
    >
      {aviso && (
        <p className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
          <span>{aviso}</span>
        </p>
      )}
      <p className="flex items-start gap-2 text-sm text-ink-800">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-jade-600" />
        <span>
          {descricao} de <strong>{q}</strong> fornecedor{q > 1 ? "es" : ""}. Custo estimado:{" "}
          <strong className="tnum">{moeda(totalCent / 100)}</strong> ({q} × {moeda(unit / 100)}).
          Confirmar?
        </span>
      </p>
      <div className="mt-3.5 flex flex-wrap gap-2.5">
        <button
          type="button"
          onClick={onConfirmar}
          disabled={processando}
          className="inline-flex items-center gap-2 rounded-xl bg-jade-600 px-5 py-2.5 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:opacity-50"
        >
          {processando ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
          {processando ? "Consultando..." : "Confirmar"}
        </button>
        <button
          type="button"
          onClick={onCancelar}
          disabled={processando}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-500 text-ink-700 transition-colors hover:bg-white disabled:opacity-50"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}
