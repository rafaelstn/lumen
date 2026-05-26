import { useState } from "react";
import { ShieldAlert, TrendingDown, HelpCircle } from "lucide-react";
import { moeda, numero } from "../utils/format.js";

// Painel de destaque dos fornecedores em risco ALTO para 2027 (grupo A/B com
// débito ativo na Receita). Só aparece quando há CND consultada e risco alto.
export default function AlertasRisco({ fornecedores }) {
  const [ajuda, setAjuda] = useState(false);
  const emRisco = fornecedores
    .filter((f) => f.risco_2027 === "ALTO")
    .sort((a, b) => (b.impacto_financeiro_anual ?? 0) - (a.impacto_financeiro_anual ?? 0));

  if (emRisco.length === 0) return null;

  const impactoTotal = emRisco.reduce((s, f) => s + (Number(f.impacto_financeiro_anual) || 0), 0);

  return (
    <section className="overflow-hidden rounded-2xl border border-signal-200 bg-gradient-to-br from-signal-50 to-white shadow-panel">
      <div className="flex items-start gap-3 border-b border-signal-100 p-5">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-signal-600 text-white animate-pulse-ring">
          <ShieldAlert className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h2 className="font-display text-lg font-600 text-signal-700">Risco de crédito em 2027</h2>
          <p className="mt-0.5 text-sm text-signal-700/80">
            {numero(emRisco.length)} fornecedor(es) com débito ativo na Receita podem perder o aproveitamento do crédito de ICMS.
          </p>
        </div>
        {impactoTotal > 0 && (
          <div className="relative ml-auto hidden shrink-0 text-right sm:block">
            <p className="flex items-center justify-end gap-1 text-[0.65rem] font-600 uppercase tracking-wider text-signal-600">
              <TrendingDown className="h-3.5 w-3.5" /> Impacto anual
              <button
                type="button"
                onClick={() => setAjuda((v) => !v)}
                aria-label="Como o impacto anual é calculado"
                className="ml-0.5 grid h-4 w-4 place-items-center rounded-full border border-signal-300 text-signal-600 transition-colors hover:bg-signal-100"
              >
                <HelpCircle className="h-3 w-3" />
              </button>
            </p>
            <p className="tnum font-display text-2xl font-600 text-signal-700">{moeda(impactoTotal)}</p>
            {ajuda && (
              <div className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-slate-200 bg-white p-3 text-left text-xs font-400 leading-relaxed text-slate-600 shadow-panel">
                <p className="mb-1 font-600 normal-case tracking-normal text-ink-800">Como calculamos o impacto</p>
                <p>
                  É a soma do <strong>ICMS efetivamente aproveitado</strong> (o crédito real destacado
                  nas notas) dos fornecedores de <strong>risco alto</strong>: Grupo A com débito ativo
                  na Receita.
                </p>
                <p className="mt-1.5">
                  Esse é o crédito que o cliente perde se o fornecedor, inadimplente, não puder
                  transferi-lo a partir de 2027. Por isso o valor de cada fornecedor é igual ao da
                  coluna <strong>ICMS aproveitado</strong> da tabela.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      <ul className="divide-y divide-signal-100">
        {emRisco.slice(0, 5).map((f) => (
          <li key={f.cod_forn} className="flex items-center gap-3 px-5 py-3">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-signal-600 text-xs font-600 text-white">
              {f.grupo}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-500 text-ink-800">{f.nome_forn}</p>
              {f.motivo_risco && <p className="truncate text-xs text-slate-500">{f.motivo_risco}</p>}
            </div>
            {f.impacto_financeiro_anual != null && (
              <span className="tnum shrink-0 text-sm font-600 text-signal-700">
                {moeda(f.impacto_financeiro_anual)}
              </span>
            )}
          </li>
        ))}
        {emRisco.length > 5 && (
          <li className="px-5 py-2.5 text-center text-xs text-signal-600">
            + {emRisco.length - 5} outros na tabela abaixo
          </li>
        )}
      </ul>
    </section>
  );
}
