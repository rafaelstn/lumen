// Barra de progresso da consulta CND. Alimentada pelo polling na Fase 6.
export default function ProgressBar({ percentual = 0, label }) {
  const pct = Math.min(100, Math.max(0, percentual));
  return (
    <div>
      {label && <p className="text-sm text-slate-600 mb-1">{label}</p>}
      <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
        <div
          className="bg-emerald-500 h-3 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-500 mt-1">{pct.toFixed(1)}%</p>
    </div>
  );
}
