import { useState } from "react";
import { Loader2, Play, Search, CheckCircle2, Coins, Clock, RotateCcw } from "lucide-react";
import { numero, moeda } from "../utils/format.js";
import ConfirmacaoCusto from "./ConfirmacaoCusto.jsx";
import ProgressBar from "./ProgressBar.jsx";

// Painel de enriquecimento de CNPJ via API CNPJá (PAGA): dispara a busca
// automática por razão social dos fornecedores pendentes. Consome créditos.
// A busca roda de forma assíncrona no servidor; este painel é o MOSTRADOR:
// enquanto roda exibe uma barra de progresso com parciais; ao concluir, o resumo.
// A busca gratuita no banco e a correção manual ficam na tabela.
// Só aparece quando há pendentes ou quando já houve uma busca (progresso presente).
//
// Os pendentes vêm separados em NOVOS (nunca pesquisados) e JÁ TENTADOS (já
// consultados sem sucesso). Por padrão só os NOVOS são buscados; os já-tentados
// só com a ação secundária (forçar), porque re-consultar gasta crédito à toa a
// menos que a base tenha mudado (ex: subiu um arquivo novo).
export default function PainelCnpj({
  pendentes,
  pendentesDetalhe,
  carregandoPendentes = false,
  progresso,
  onEnriquecer,
  enriquecendo,
  erro,
  custoCadastroCent = 0,
}) {
  // confirmando: null | "novos" | "forcar". Define qual confirmação está aberta.
  const [confirmando, setConfirmando] = useState(null);
  if (pendentes <= 0 && !progresso) return null;

  const rodando = progresso?.status === "em_andamento";
  const concluido = progresso?.status === "concluido";

  // Quebra dos pendentes. Enquanto o detalhe não chegou, cai no total agregado
  // (tudo conta como "novo") para não travar o fluxo nem o custo.
  const detalheOk = !carregandoPendentes && pendentesDetalhe != null;
  const novos = detalheOk ? Math.max(0, Math.trunc(pendentesDetalhe.novos || 0)) : Math.max(0, Math.trunc(pendentes || 0));
  const jaTentados = detalheOk ? Math.max(0, Math.trunc(pendentesDetalhe.ja_tentados || 0)) : 0;

  const unitExato = Math.max(0, Number(custoCadastroCent) || 0);
  // Custo do botão principal: só os NOVOS. Custo do forçar: novos + já-tentados
  // (o forçar re-inclui os já-tentados sem deixar os novos de fora).
  const totalNovosCent = Math.round(novos * unitExato);
  const qtdForcar = novos + jaTentados;

  const semNovos = detalheOk && novos === 0;
  const temJaTentados = detalheOk && jaTentados > 0;

  function confirmarNovos() {
    setConfirmando(null);
    onEnriquecer({ forcar: false });
  }

  function confirmarForcar() {
    setConfirmando(null);
    onEnriquecer({ forcar: true });
  }

  return (
    <section className="rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 to-white p-5 shadow-panel">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500 text-white">
            {rodando ? <Loader2 className="h-5 w-5 animate-spin" /> : <Search className="h-5 w-5" />}
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-lg font-600 text-amber-700">Enriquecimento automático</h2>
              <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[0.65rem] font-600 uppercase tracking-wide text-amber-700">
                <Coins className="h-3 w-3" /> consome créditos
              </span>
            </div>
            <p className="mt-0.5 text-sm text-amber-700/80">
              {rodando ? (
                "Buscando os CNPJ pendentes na base cadastral oficial. Você pode acompanhar o andamento abaixo."
              ) : pendentes > 0 ? (
                <DescricaoPendentes
                  carregando={carregandoPendentes && pendentesDetalhe == null}
                  detalheOk={detalheOk}
                  pendentes={pendentes}
                  novos={novos}
                  jaTentados={jaTentados}
                  totalNovosCent={totalNovosCent}
                  semNovos={semNovos}
                />
              ) : (
                "Todos os fornecedores pendentes foram processados."
              )}
            </p>
          </div>
        </div>

        {/* Ação principal no header. Se ainda há novos a pesquisar: "Buscar (pago)".
            Se já pesquisou tudo (só restam já-tentados): o principal vira "Tentar de novo",
            sem o botão desabilitado confundindo. */}
        {pendentes > 0 && !confirmando && !rodando && (
          semNovos && temJaTentados ? (
            <button
              type="button"
              onClick={() => setConfirmando("forcar")}
              disabled={enriquecendo}
              className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-600 text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
            >
              <RotateCcw className="h-4 w-4" />
              Tentar de novo ({numero(jaTentados)})
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmando("novos")}
              disabled={enriquecendo || carregandoPendentes || semNovos}
              className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-600 text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
              title={semNovos ? "Todos os pendentes já foram pesquisados sem sucesso" : undefined}
            >
              {carregandoPendentes ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Buscar (pago)
            </button>
          )
        )}

        {rodando && (
          <span className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-amber-100 px-4 py-2.5 text-sm font-600 text-amber-700">
            <Loader2 className="h-4 w-4 animate-spin" /> Buscando...
          </span>
        )}
      </div>

      {/* Confirmação do fluxo principal: custo sobre os NOVOS apenas */}
      {pendentes > 0 && confirmando === "novos" && !rodando && (
        <div className="mt-4">
          <ConfirmacaoCusto
            quantidade={novos}
            custoUnitarioCent={custoCadastroCent}
            descricao="Busca de CNPJ"
            processando={enriquecendo}
            onConfirmar={confirmarNovos}
            onCancelar={() => setConfirmando(null)}
          />
        </div>
      )}

      {/* Confirmação do forçar: aviso explícito de re-consulta dos já-tentados */}
      {pendentes > 0 && confirmando === "forcar" && !rodando && (
        <div className="mt-4">
          <ConfirmacaoCusto
            quantidade={qtdForcar}
            custoUnitarioCent={custoCadastroCent}
            descricao="Nova tentativa de busca de CNPJ"
            aviso={
              `${numero(jaTentados)} desses fornecedores já foram pesquisados antes e não foram encontrados. ` +
              `Refazer consome crédito de novo e só vale a pena se a base mudou (ex: você subiu um arquivo novo). ` +
              (novos > 0
                ? `Esta ação busca os ${numero(jaTentados)} já-pesquisados mais os ${numero(novos)} novos.`
                : `Esta ação re-busca os ${numero(jaTentados)} já-pesquisados.`)
            }
            processando={enriquecendo}
            onConfirmar={confirmarForcar}
            onCancelar={() => setConfirmando(null)}
          />
        </div>
      )}

      {/* Ação secundária: só quando há NOVOS e também já-tentados (opção de forçar
          incluindo os já-tentados). Se só restam já-tentados, o botão principal no
          header já é o "Tentar de novo", então não duplica aqui. */}
      {temJaTentados && !semNovos && !confirmando && !rodando && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setConfirmando("forcar")}
            disabled={enriquecendo}
            className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-sm font-600 text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50"
          >
            <RotateCcw className="h-4 w-4" />
            Tentar de novo os {numero(jaTentados)} já pesquisados
          </button>
        </div>
      )}

      {/* MOSTRADOR: barra de progresso animada enquanto a busca roda */}
      {rodando && (
        <div
          className="mt-4 rounded-xl border border-amber-200 bg-white/70 p-4"
          role="status"
          aria-live="polite"
        >
          <ProgressBar
            percentual={progresso?.percentual ?? 0}
            total={progresso?.total}
            consultados={progresso?.processados}
            falhas={progresso?.erros_pontuais}
            ativo
            label="Buscando CNPJ na base cadastral"
          />
          {/* Parciais em tempo real para deixar claro que está rodando */}
          {(progresso?.confirmados != null || progresso?.nao_encontrados != null) && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1 rounded-lg border border-jade-200 bg-jade-50 px-2.5 py-1 font-500 text-jade-700">
                <CheckCircle2 className="h-3.5 w-3.5" /> {numero(progresso?.confirmados || 0)} confirmados
              </span>
              <Chip>{numero(progresso?.nao_encontrados || 0)} não encontrados</Chip>
            </div>
          )}
        </div>
      )}

      {erro && (
        <p className="mt-3 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2 text-sm text-signal-700">{erro}</p>
      )}

      {/* RESUMO FINAL: ao concluir a busca */}
      {concluido && (
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-lg border border-jade-200 bg-jade-50 px-2.5 py-1 font-500 text-jade-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> {numero(progresso.confirmados)} confirmados
          </span>
          <Chip>{numero(progresso.baixa_confianca)} baixa confiança</Chip>
          <Chip>{numero(progresso.ambiguos)} ambíguos</Chip>
          <Chip>{numero(progresso.nao_encontrados)} não encontrados</Chip>
          {pendentes > 0 && <Chip>{numero(pendentes)} ainda pendentes</Chip>}
        </div>
      )}

      {/* Avisos de limite (ao concluir): créditos, rate limit, teto diário */}
      {concluido && progresso.creditos_esgotados && (
        <p className="mt-3 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2 text-sm text-signal-700">
          Créditos esgotados. Recarregue para concluir os fornecedores ainda pendentes.
        </p>
      )}

      {concluido && progresso.teto_diario_atingido && (
        <p className="mt-3 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2 text-sm text-signal-700">
          Teto diário de consultas atingido. Tente novamente amanhã para concluir os pendentes.
        </p>
      )}

      {/* Rate limit (transitório): orienta aguardar e continuar, sem confundir com crédito */}
      {concluido && progresso.limite_taxa_atingido && (
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
          <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Muitas consultas em pouco tempo. Aguarde cerca de 1 minuto e clique em "Buscar" de novo
            para continuar de onde parou ({numero(pendentes)} ainda pendente(s)). Seu saldo de
            créditos não acabou.
          </span>
        </p>
      )}

      {concluido && (
        <p className="mt-3 text-xs text-amber-700/70">
          Os CNPJ encontrados foram aplicados à análise e já aparecem na tabela abaixo. Ajuste os pendentes manualmente se necessário.
        </p>
      )}
    </section>
  );
}

// Texto descritivo dos pendentes, sensível ao estado: carregando, com já-tentados,
// sem novos (tudo já tentado) ou caso simples (só novos).
function DescricaoPendentes({ carregando, detalheOk, pendentes, novos, jaTentados, totalNovosCent, semNovos }) {
  if (carregando) {
    return (
      <>
        <strong className="tnum font-600">{numero(pendentes)}</strong> fornecedor(es) sem CNPJ casado. Verificando quais
        ainda não foram pesquisados...
      </>
    );
  }

  if (detalheOk && semNovos) {
    return (
      <>
        Os <strong className="tnum font-600">{numero(jaTentados)}</strong> fornecedores pendentes já foram pesquisados e não
        foram encontrados na base, então não serão buscados de novo automaticamente. Se você subiu um arquivo novo, use o
        botão "Tentar de novo" abaixo. Você também pode corrigir o CNPJ manualmente na tabela.
      </>
    );
  }

  if (detalheOk && jaTentados > 0) {
    return (
      <>
        <strong className="tnum font-600">{numero(pendentes)}</strong> sem CNPJ:{" "}
        <strong className="tnum font-600">{numero(novos)}</strong> novos e{" "}
        <strong className="tnum font-600">{numero(jaTentados)}</strong> já pesquisados antes sem sucesso (não serão buscados
        de novo). A busca consulta a base cadastral oficial por razão social e{" "}
        <strong className="font-600">consome créditos pagos</strong> (≈{" "}
        <strong className="tnum font-600">{moeda(totalNovosCent / 100)}</strong> pelos {numero(novos)} novos).
      </>
    );
  }

  // Caso simples: todos os pendentes são novos (sem já-tentados).
  return (
    <>
      <strong className="tnum font-600">{numero(novos)}</strong> fornecedor(es) sem CNPJ casado. Esta busca consulta a base
      cadastral oficial por razão social e <strong className="font-600">consome créditos pagos</strong> (≈{" "}
      <strong className="tnum font-600">{moeda(totalNovosCent / 100)}</strong> no total). Para resolver sem custo, use a
      busca no banco (grátis) na tabela abaixo.
    </>
  );
}

function Chip({ children }) {
  return (
    <span className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-500 text-slate-600">{children}</span>
  );
}
