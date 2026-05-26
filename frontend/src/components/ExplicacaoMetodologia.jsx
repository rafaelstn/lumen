import { X, HelpCircle } from "lucide-react";

// Explica, para o usuário, como a análise é construída. Fiel à lógica do backend
// (classifier.py: grupos A/B/C; risk.py: risco 2027 e impacto). Modal sobreposto.
export default function ExplicacaoMetodologia({ aberto, onFechar }) {
  if (!aberto) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Como esta análise é feita"
    >
      <div className="absolute inset-0 bg-ink-900/40 backdrop-blur-sm" onClick={onFechar} />
      <div className="relative z-10 max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-jade-600 text-white">
              <HelpCircle className="h-5 w-5" />
            </span>
            <h2 className="font-display text-lg font-600 text-ink-800">Como esta análise é feita</h2>
          </div>
          <button
            type="button"
            onClick={onFechar}
            aria-label="Fechar"
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-5 text-sm leading-relaxed text-ink-700">
          <section>
            <h3 className="font-600 text-ink-800">1. Classificação por crédito de ICMS (A / B / C)</h3>
            <p className="mt-1 text-slate-600">
              Cada fornecedor é classificado pela alíquota máxima de ICMS das notas de entrada:
            </p>
            <ul className="mt-2 space-y-1.5">
              <li>
                <strong className="text-jade-700">Grupo A — Bom:</strong> alíquota ≥ 12%. Fornecedor de
                Lucro Real/Presumido, gera crédito pleno de ICMS.
              </li>
              <li>
                <strong className="text-amber-700">Grupo B — Crédito podre:</strong> alíquota entre 0% e
                10%. Simples Nacional, crédito simbólico.
              </li>
              <li>
                <strong className="text-slate-600">Grupo C — Sem crédito:</strong> alíquota 0%. Simples
                Nacional sem destaque. Estimamos o crédito que você deixou de aproveitar aplicando a
                alíquota interna de referência de SP (18%) sobre as compras.
              </li>
              <li>
                <strong>Faixa 10%–12%:</strong> indefinida; sinalizada para revisão manual, sem
                distorcer o resultado.
              </li>
              <li>
                <strong className="text-amber-700">Atenção ST:</strong> Grupo A com ICMS zerado pode ser
                Substituição Tributária ou erro de lançamento, então é marcado para verificação.
              </li>
            </ul>
          </section>

          <section>
            <h3 className="font-600 text-ink-800">2. Risco de perder crédito em 2027</h3>
            <p className="mt-1 text-slate-600">
              A partir de 2027, empresa inadimplente não poderá transferir crédito de ICMS. Cruzamos o
              grupo do fornecedor com a regularidade fiscal (CND da Receita Federal/PGFN):
            </p>
            <ul className="mt-2 space-y-1.5">
              <li>
                <strong className="text-signal-700">Risco ALTO:</strong> Grupo A com débito ativo na
                Receita (CND positiva). Oferece crédito hoje, mas pode perder em 2027.
              </li>
              <li>
                <strong className="text-amber-700">Risco MÉDIO:</strong> Grupo A com regularidade ainda
                não verificada (CND pendente).
              </li>
              <li>
                <strong className="text-jade-700">Risco BAIXO:</strong> demais casos.
              </li>
            </ul>
          </section>

          <section>
            <h3 className="font-600 text-ink-800">3. Impacto financeiro anual</h3>
            <p className="mt-1 text-slate-600">
              Estimativa do crédito de ICMS em risco por fornecedor:{" "}
              <strong>total de compras × alíquota ÷ 100</strong>. O painel de risco soma o impacto dos
              fornecedores de risco alto.
            </p>
          </section>

          <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
            A regularidade fiscal (CND) é consultada na Receita Federal/PGFN. Quando a Receita não
            retorna a certidão, o fornecedor fica como <strong>pendente</strong>, o que não significa que
            ele tem débito: apenas que a consulta ainda não foi concluída.
          </p>
        </div>
      </div>
    </div>
  );
}
