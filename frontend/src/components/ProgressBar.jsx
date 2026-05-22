// Barra de progresso da consulta CND. Mostra percentual, "X de Y" e falhas.
// Efeito "scan" sobre o preenchimento sinaliza atividade em curso.
export default function ProgressBar({ percentual = 0, total, consultados, falhas = 0, ativo = true, label }) {
  const pct = Math.min(100, Math.max(0, Number(percentual) || 0));

  return (
    <div>
      <div className="mb-2 flex items-end justify-between gap-3">
        <p className="text-sm font-500 text-ink-800">{label ?? "Consultando regularidade fiscal"}</p>
        <p className="tnum text-sm font-600 text-jade-700">{pct.toFixed(1)}%</p>
      </div>

      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className="relative h-full rounded-full bg-gradient-to-r from-jade-500 to-jade-600 transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        >
          {ativo && pct < 100 && (
            <span className="absolute inset-0 animate-scan bg-gradient-to-r from-transparent via-white/40 to-transparent" />
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        {total != null && (
          <span className="tnum">
            Consultando <strong className="font-600 text-ink-700">{consultados ?? 0}</strong> de{" "}
            <strong className="font-600 text-ink-700">{total}</strong> fornecedores
          </span>
        )}
        {falhas > 0 && (
          <span className="tnum inline-flex items-center gap-1 text-amber-700">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
            {falhas} {falhas === 1 ? "falha" : "falhas"}
          </span>
        )}
      </div>
    </div>
  );
}
