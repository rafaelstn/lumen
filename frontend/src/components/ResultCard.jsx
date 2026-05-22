// Card de KPI do dashboard. Suporta tom (neutro/positivo/atenção/risco),
// ícone, valor de destaque e uma legenda secundária.
const TONS = {
  neutro: {
    card: "border-slate-200 bg-white",
    icone: "bg-ink-900 text-white",
    valor: "text-ink-900",
  },
  positivo: {
    card: "border-jade-200 bg-gradient-to-br from-jade-50 to-white",
    icone: "bg-jade-600 text-white",
    valor: "text-jade-700",
  },
  atencao: {
    card: "border-amber-200 bg-gradient-to-br from-amber-50 to-white",
    icone: "bg-amber-500 text-white",
    valor: "text-amber-700",
  },
  risco: {
    card: "border-signal-200 bg-gradient-to-br from-signal-50 to-white",
    icone: "bg-signal-600 text-white",
    valor: "text-signal-700",
  },
};

export default function ResultCard({ titulo, valor, sublabel, tom = "neutro", Icone, alertaPulsante = false }) {
  const t = TONS[tom] ?? TONS.neutro;

  return (
    <div className={`group relative overflow-hidden rounded-2xl border p-5 shadow-panel transition-shadow hover:shadow-lift ${t.card}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[0.7rem] font-600 uppercase tracking-[0.12em] text-slate-500">{titulo}</p>
        {Icone && (
          <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg ${t.icone} ${alertaPulsante ? "animate-pulse-ring" : ""}`}>
            <Icone className="h-[1.1rem] w-[1.1rem]" strokeWidth={2.1} />
          </span>
        )}
      </div>
      <p className={`tnum mt-3 font-display text-3xl font-600 leading-none tracking-tight ${t.valor}`}>
        {valor}
      </p>
      {sublabel && <p className="mt-2 text-xs text-slate-500">{sublabel}</p>}
    </div>
  );
}
