import { useState } from "react";
import { Loader2, Play, Search, CheckCircle2, Coins } from "lucide-react";
import { numero, moeda } from "../utils/format.js";
import { SERVICO } from "../utils/custos.js";
import ConfirmacaoCusto from "./ConfirmacaoCusto.jsx";

// Painel de enriquecimento de CNPJ via API CNPJá (PAGA): dispara a busca
// automática por razão social dos fornecedores pendentes. Consome créditos.
// A busca gratuita no banco e a correção manual ficam na tabela.
// Só aparece quando há pendentes.
export default function PainelCnpj({
  pendentes,
  resumoEnriquecimento,
  onEnriquecer,
  enriquecendo,
  erro,
  custoCadastroCent = 0,
}) {
  const [confirmando, setConfirmando] = useState(false);
  if (pendentes <= 0 && !resumoEnriquecimento) return null;

  // custoCadastroCent pode ser fracionário (preço derivado do backend): preserva
  // a fração na multiplicação e arredonda só no total exibido.
  const totalCent = Math.round(
    Math.max(0, Math.trunc(pendentes || 0)) * Math.max(0, Number(custoCadastroCent) || 0),
  );

  function confirmar() {
    setConfirmando(false);
    onEnriquecer();
  }

  return (
    <section className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-5 shadow-panel">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500 text-white">
            <Search className="h-5 w-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-lg font-600 text-amber-700">Enriquecimento automático</h2>
              <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[0.65rem] font-600 uppercase tracking-wide text-amber-700">
                <Coins className="h-3 w-3" /> consome créditos
              </span>
            </div>
            <p className="mt-0.5 text-sm text-amber-700/80">
              {pendentes > 0 ? (
                <>
                  <strong className="tnum font-600">{numero(pendentes)}</strong> fornecedor(es) sem CNPJ casado. Esta busca
                  consulta a base cadastral oficial por razão social e <strong className="font-600">consome créditos pagos</strong>{" "}
                  (≈ <strong className="tnum font-600">{moeda(totalCent / 100)}</strong> no total). Para
                  resolver sem custo, use a busca no banco (grátis) na tabela abaixo.
                </>
              ) : (
                "Todos os fornecedores pendentes foram processados."
              )}
            </p>
          </div>
        </div>

        {pendentes > 0 && !confirmando && (
          <button
            type="button"
            onClick={() => setConfirmando(true)}
            disabled={enriquecendo}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-600 text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
          >
            {enriquecendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {enriquecendo ? "Buscando..." : "Buscar (pago)"}
          </button>
        )}
      </div>

      {pendentes > 0 && confirmando && (
        <div className="mt-4">
          <ConfirmacaoCusto
            quantidade={pendentes}
            custoUnitarioCent={custoCadastroCent}
            descricao="Busca de CNPJ"
            servico={SERVICO.CADASTRO}
            processando={enriquecendo}
            onConfirmar={confirmar}
            onCancelar={() => setConfirmando(false)}
          />
        </div>
      )}

      {erro && (
        <p className="mt-3 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2 text-sm text-signal-700">{erro}</p>
      )}

      {resumoEnriquecimento && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-lg border border-jade-200 bg-jade-50 px-2.5 py-1 font-500 text-jade-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> {numero(resumoEnriquecimento.confirmados)} confirmados
          </span>
          <Chip>{numero(resumoEnriquecimento.baixa_confianca)} baixa confiança</Chip>
          <Chip>{numero(resumoEnriquecimento.ambiguos)} ambíguos</Chip>
          <Chip>{numero(resumoEnriquecimento.nao_encontrados)} não encontrados</Chip>
          <Chip>{numero(resumoEnriquecimento.pendentes_restantes)} ainda pendentes</Chip>
          {resumoEnriquecimento.creditos_esgotados && (
            <span className="rounded-lg border border-signal-200 bg-signal-50 px-2.5 py-1 font-500 text-signal-700">
              Créditos da API esgotados
            </span>
          )}
        </div>
      )}

      {resumoEnriquecimento && (
        <p className="mt-3 text-xs text-amber-700/70">
          Os CNPJ encontrados foram aplicados à análise. Recarregue uma nova análise para ver o casamento atualizado na tabela, ou ajuste os pendentes manualmente abaixo.
        </p>
      )}
    </section>
  );
}

function Chip({ children }) {
  return (
    <span className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-500 text-slate-600">{children}</span>
  );
}
