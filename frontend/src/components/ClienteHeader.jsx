import { Building2, Calendar, Hash } from "lucide-react";

// Faixa de identificação do cliente analisado: nome, CNPJ e período.
export default function ClienteHeader({ metadados }) {
  if (!metadados) return null;
  const { cliente, cnpj_cliente, periodo } = metadados;

  return (
    <section className="rounded-2xl border border-ink-800 bg-ink-900 p-5 text-white shadow-panel sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white/10 ring-1 ring-white/10">
            <Building2 className="h-6 w-6 text-jade-400" strokeWidth={1.8} />
          </span>
          <div className="min-w-0">
            <p className="text-[0.65rem] font-500 uppercase tracking-[0.16em] text-jade-400">Cliente analisado</p>
            <h2 className="truncate font-display text-xl font-600 leading-tight">{cliente ?? "—"}</h2>
          </div>
        </div>

        <dl className="flex flex-wrap gap-x-7 gap-y-3 text-sm">
          <Meta Icone={Hash} rotulo="CNPJ" valor={cnpj_cliente} />
          <Meta Icone={Calendar} rotulo="Período" valor={periodo} />
        </dl>
      </div>
    </section>
  );
}

function Meta({ Icone, rotulo, valor }) {
  return (
    <div className="flex items-center gap-2.5">
      <Icone className="h-4 w-4 text-ink-600" strokeWidth={1.8} />
      <div>
        <dt className="text-[0.65rem] uppercase tracking-wider text-ink-600">{rotulo}</dt>
        <dd className="tnum text-sm font-500 text-white">{valor ?? "—"}</dd>
      </div>
    </div>
  );
}
