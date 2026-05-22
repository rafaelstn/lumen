// Card de resumo exibido ao final do processamento. Preenchido na Fase 6.
export default function ResultCard({ titulo, valor, destaque = false }) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        destaque ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-xs uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className="text-2xl font-semibold text-slate-800 mt-1">{valor}</p>
    </div>
  );
}
