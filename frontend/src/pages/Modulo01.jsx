import { useEffect, useRef, useState, lazy, Suspense } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Users,
  Coins,
  Ban,
  ShieldAlert,
  TrendingDown,
  FileDown,
  RotateCcw,
  Play,
  Loader2,
  AlertCircle,
  ScanLine,
  Sparkles,
  EyeOff,
  History,
  ServerCrash,
  HelpCircle,
} from "lucide-react";
import {
  processarArquivos,
  definirCnpjManual,
  enriquecerCnpj,
  consultarPendentesEnriquecimento,
  consultarCnd,
  consultarProgresso,
  consultarProgressoEnriquecimento,
  consultarResultado,
  abrirAnalise,
  urlRelatorio,
} from "../services/api.js";
import HistoricoAnalises from "../components/HistoricoAnalises.jsx";
import { moeda, moedaCompacta, numero } from "../utils/format.js";
import { useCustosEfetivos } from "../utils/custos.js";
import FileUpload from "../components/FileUpload.jsx";
import ResultCard from "../components/ResultCard.jsx";
import FornecedoresTable from "../components/FornecedoresTable.jsx";
import ClienteHeader from "../components/ClienteHeader.jsx";
import AlertasRisco from "../components/AlertasRisco.jsx";
import PainelCnpj from "../components/PainelCnpj.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import ConfirmacaoCusto from "../components/ConfirmacaoCusto.jsx";
import ExplicacaoMetodologia from "../components/ExplicacaoMetodologia.jsx";

// Recharts é pesado; carregado sob demanda só quando o dashboard aparece.
const DistribuicaoGrupos = lazy(() => import("../components/DistribuicaoGrupos.jsx"));

// Preferência local (não-auth) para ocultar a seção de histórico. Vira controle
// por papel quando o login entrar. Lida de forma tolerante a localStorage indisponível.
const CHAVE_HISTORICO_OCULTO = "lumen:historico-oculto";
function lerHistoricoOculto() {
  try {
    return localStorage.getItem(CHAVE_HISTORICO_OCULTO) === "1";
  } catch {
    return false;
  }
}

// Última análise aberta: re-hidratada ao recarregar a página, para não cair na tela
// de upload. Tolerante a localStorage indisponível.
const CHAVE_ULTIMA_ANALISE = "lumen:m01:ultima-analise";
function lerUltimaAnalise() {
  try {
    return localStorage.getItem(CHAVE_ULTIMA_ANALISE);
  } catch {
    return null;
  }
}
function gravarUltimaAnalise(id) {
  try {
    if (id) localStorage.setItem(CHAVE_ULTIMA_ANALISE, id);
    else localStorage.removeItem(CHAVE_ULTIMA_ANALISE);
  } catch {
    /* localStorage indisponível: segue sem persistir */
  }
}

// Orquestra o fluxo do Módulo 01:
// upload → classificação → (CNPJ manual) → consulta CND assíncrona com polling → dashboard final → PDF.
export default function Modulo01() {
  const [entradas, setEntradas] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [erroCnpj, setErroCnpj] = useState(null);

  // Preferência local: seção de histórico oculta. Persistida em localStorage.
  const [historicoOculto, setHistoricoOculto] = useState(lerHistoricoOculto);

  // Estado da consulta CND: progresso vindo do polling + erro de disparo.
  const [progresso, setProgresso] = useState(null); // {total, consultados, falhas, percentual, status}
  const [erroCnd, setErroCnd] = useState(null);
  const pollRef = useRef(null);

  // Estado do enriquecimento automático de CNPJ: progresso vindo do polling + erro de disparo.
  // progressoEnriquecimento: {total, processados, confirmados, baixa_confianca, ambiguos,
  //   nao_encontrados, erros_pontuais, percentual, status, creditos_esgotados,
  //   limite_taxa_atingido, teto_diario_atingido}.
  const [progressoEnriquecimento, setProgressoEnriquecimento] = useState(null);
  const [erroEnriquecimento, setErroEnriquecimento] = useState(null);
  const pollEnriqRef = useRef(null);

  // Quebra dos pendentes do enriquecimento: { total_pendentes, novos, ja_tentados }.
  // novos = nunca pesquisados; ja_tentados = já consultados sem sucesso (não
  // re-pesquisados por padrão). Não consome crédito. Usado pelo PainelCnpj para
  // dimensionar custo (só os novos no fluxo normal) e liberar a ação de forçar.
  const [pendentesEnriq, setPendentesEnriq] = useState(null);
  const [carregandoPendentesEnriq, setCarregandoPendentesEnriq] = useState(false);

  // Custos unitários efetivos: preço do backend (recarga) quando há saldo
  // configurado, senão o do localStorage. Fonte da verdade do preço = backend.
  const custos = useCustosEfetivos();

  const processar = useMutation({
    mutationFn: processarArquivos,
    onSuccess: (data) => setResultado(data),
  });

  // Reabrir análise salva: o backend re-hidrata o job e devolve o MESMO shape
  // de /resultado/{job_id}. Tratamos exatamente como o processar.onSuccess —
  // setResultado leva direto ao dashboard com o job_id ativo, então enriquecimento,
  // CND e PDF seguem funcionando sobre a análise reaberta.
  const abrir = useMutation({
    mutationFn: abrirAnalise,
    onSuccess: (data) => setResultado(data),
    // Reabrir falhou (ex.: análise apagada): não insistir nessa no próximo reload.
    onError: () => gravarUltimaAnalise(null),
  });

  // Painel de ajuda explicando a metodologia da análise.
  const [mostrarMetodologia, setMostrarMetodologia] = useState(false);

  function alternarHistorico(oculto) {
    setHistoricoOculto(oculto);
    try {
      if (oculto) localStorage.setItem(CHAVE_HISTORICO_OCULTO, "1");
      else localStorage.removeItem(CHAVE_HISTORICO_OCULTO);
    } catch {
      /* preferência some se o storage estiver indisponível; sem impacto no fluxo */
    }
  }

  const salvarCnpj = useMutation({
    mutationFn: ({ codForn, cnpj, razaoSocial }) =>
      definirCnpjManual(resultado.job_id, { cod_forn: codForn, cnpj, razao_social: razaoSocial }),
    onSuccess: (fornAtualizado) => {
      setErroCnpj(null);
      setResultado((r) => ({
        ...r,
        fornecedores: r.fornecedores.map((f) =>
          f.cod_forn === fornAtualizado.cod_forn ? fornAtualizado : f
        ),
      }));
      // Re-fetch para recalcular o resumo (pendentes, casados) e os KPIs.
      recarregarResultado(resultado.job_id);
    },
    onError: (e) => setErroCnpj(e?.response?.data?.detail ?? "Não foi possível salvar o CNPJ."),
  });

  const enriquecer = useMutation({
    mutationFn: ({ forcar = false } = {}) => enriquecerCnpj(resultado.job_id, { forcar }),
    onMutate: () => {
      setErroEnriquecimento(null);
      // Estado inicial otimista para a barra aparecer já no disparo.
      setProgressoEnriquecimento((p) => p ?? { status: "em_andamento", percentual: 0 });
    },
    onSuccess: (inicio) => {
      // Disparo assíncrono: NÃO há resumo aqui. O backend devolve { job_id, status, total }.
      // O acompanhamento passa a ser pelo polling do enriquecimento-progresso.
      setProgressoEnriquecimento({
        status: "em_andamento",
        percentual: 0,
        total: inicio?.total ?? null,
        processados: 0,
      });
    },
    onError: (e) => {
      setErroEnriquecimento(
        e?.response?.data?.detail ?? "Não foi possível buscar os CNPJ automaticamente.",
      );
      setProgressoEnriquecimento(null);
      pararPollingEnriquecimento();
    },
  });

  const dispararCnd = useMutation({
    mutationFn: () => consultarCnd(resultado.job_id),
    onMutate: () => {
      setErroCnd(null);
      setProgresso((p) => p ?? { status: "em_andamento", percentual: 0, total: null, consultados: 0, falhas: 0 });
    },
    onSuccess: (data) => {
      // Confirma o estado com o total que o backend devolveu, garantindo "em_andamento"
      // mesmo que o primeiro tick do polling tenha visto "nao_iniciado" (race do disparo).
      setProgresso((p) => ({
        status: "em_andamento",
        percentual: p?.percentual ?? 0,
        total: data?.total ?? p?.total ?? null,
        consultados: p?.consultados ?? 0,
        falhas: p?.falhas ?? 0,
      }));
    },
    onError: (e) => {
      // 409 = já existe uma CND em andamento no servidor. Não é erro: ativa a barra
      // e o polling em vez de mostrar mensagem vermelha.
      if (e?.response?.status === 409) {
        setErroCnd(null);
        setProgresso((p) => p ?? { status: "em_andamento", percentual: 0, total: null, consultados: 0, falhas: 0 });
        return;
      }
      setErroCnd(e?.response?.data?.detail ?? "Não foi possível iniciar a consulta de CND.");
      pararPolling();
    },
  });

  function pararPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function pararPollingEnriquecimento() {
    if (pollEnriqRef.current) {
      clearInterval(pollEnriqRef.current);
      pollEnriqRef.current = null;
    }
  }

  // Rebusca o job atualizado (fornecedores com CNPJ/CND/risco) preservando o resumo.
  async function recarregarResultado(jobId) {
    try {
      const atualizado = await consultarResultado(jobId);
      setResultado(atualizado);
    } catch {
      /* mantém o estado atual se a releitura falhar */
    }
  }

  // Rebusca a quebra dos pendentes (novos vs já-tentados). Gratuito. Tolera falha:
  // se o endpoint não responder, o painel cai no comportamento agregado (tudo novo).
  async function recarregarPendentesEnriq(jobId) {
    setCarregandoPendentesEnriq(true);
    try {
      const d = await consultarPendentesEnriquecimento(jobId);
      setPendentesEnriq(d);
    } catch {
      setPendentesEnriq(null);
    } finally {
      setCarregandoPendentesEnriq(false);
    }
  }

  // Polling do progresso a cada 3s enquanto a consulta CND estiver em andamento.
  useEffect(() => {
    if (!resultado?.job_id || progresso?.status !== "em_andamento" || pollRef.current) return;

    async function tick() {
      try {
        const p = await consultarProgresso(resultado.job_id);
        // Race do disparo: o POST que inicia a CND pode ainda estar em voo no primeiro
        // tick; ignorar "nao_iniciado" evita resetar a barra ao botão inicial.
        if (p.status === "nao_iniciado") return;
        setProgresso(p);
        if (p.status === "concluido") {
          pararPolling();
          recarregarResultado(resultado.job_id); // traz status_cnd e risco_2027 para a tabela
        }
      } catch {
        /* tolera falha pontual de polling; tenta de novo no próximo tick */
      }
    }

    tick();
    pollRef.current = setInterval(tick, 3000);
    return pararPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultado?.job_id, progresso?.status]);

  // Polling do progresso do enriquecimento de CNPJ a cada 3s. Ref própria
  // (pollEnriqRef) para coexistir com o polling da CND sem conflito de intervalos.
  useEffect(() => {
    if (
      !resultado?.job_id ||
      progressoEnriquecimento?.status !== "em_andamento" ||
      pollEnriqRef.current
    )
      return;

    async function tick() {
      try {
        const p = await consultarProgressoEnriquecimento(resultado.job_id);
        // Mesma race do disparo: ignora "nao_iniciado" pra não resetar a barra.
        if (p.status === "nao_iniciado") return;
        setProgressoEnriquecimento(p);
        if (p.status === "concluido") {
          pararPollingEnriquecimento();
          recarregarResultado(resultado.job_id); // reflete os CNPJ casados na tabela
        } else {
          // Atualização incremental: os fornecedores casam ao longo da busca.
          recarregarResultado(resultado.job_id);
        }
      } catch {
        /* tolera falha pontual de polling; tenta de novo no próximo tick */
      }
    }

    tick();
    pollEnriqRef.current = setInterval(tick, 3000);
    return pararPollingEnriquecimento;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultado?.job_id, progressoEnriquecimento?.status]);

  useEffect(() => pararPolling, []);
  useEffect(() => pararPollingEnriquecimento, []);

  // Persiste a última análise aberta e a re-hidrata ao carregar a página, para que recarregar
  // não jogue o usuário de volta na tela de upload.
  useEffect(() => {
    if (resultado?.job_id) gravarUltimaAnalise(resultado.job_id);
  }, [resultado?.job_id]);

  const restaurouRef = useRef(false);
  useEffect(() => {
    if (restaurouRef.current || resultado) return;
    restaurouRef.current = true;
    const id = lerUltimaAnalise();
    if (id) abrir.mutate(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ao carregar/reabrir uma análise, re-hidrata o progresso de CND e de enriquecimento
  // a partir do servidor. Sem isso, a barra some ao reabrir uma análise cuja consulta
  // ainda está rodando (o estado local começa zerado).
  useEffect(() => {
    const jobId = resultado?.job_id;
    if (!jobId) return;
    let cancelado = false;
    (async () => {
      try {
        const pc = await consultarProgresso(jobId);
        if (!cancelado && (pc?.status === "em_andamento" || pc?.status === "concluido")) {
          setProgresso(pc);
        }
      } catch {
        /* sem progresso de CND para este job */
      }
      try {
        const pe = await consultarProgressoEnriquecimento(jobId);
        if (!cancelado && (pe?.status === "em_andamento" || pe?.status === "concluido")) {
          setProgressoEnriquecimento(pe);
        }
      } catch {
        /* sem progresso de enriquecimento para este job */
      }
    })();
    return () => {
      cancelado = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultado?.job_id]);

  // Rebusca a quebra novos/já-tentados sempre que o número de pendentes mudar e
  // nada estiver em andamento. Reage ao casamento manual (que reduz pendentes) e
  // ao fim do enriquecimento (status passa a "concluido"). Sem pendentes, zera.
  const pendentesCount = resultado?.resumo?.cnpj_pendentes ?? 0;
  useEffect(() => {
    const jobId = resultado?.job_id;
    if (!jobId) return;
    if (pendentesCount <= 0) {
      setPendentesEnriq(null);
      return;
    }
    if (progressoEnriquecimento?.status === "em_andamento") return;
    recarregarPendentesEnriq(jobId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resultado?.job_id, pendentesCount, progressoEnriquecimento?.status]);

  const detalheErro =
    processar.error?.response?.data?.detail ??
    processar.error?.message ??
    "Falha ao processar os arquivos.";

  function reiniciar() {
    pararPolling();
    pararPollingEnriquecimento();
    gravarUltimaAnalise(null); // "Nova análise" não deve re-hidratar a anterior no reload
    setResultado(null);
    processar.reset();
    dispararCnd.reset();
    setEntradas(null);
    setProgresso(null);
    setErroCnd(null);
    setErroCnpj(null);
    enriquecer.reset();
    setProgressoEnriquecimento(null);
    setErroEnriquecimento(null);
  }

  // ---- ESTADO 1: UPLOAD --------------------------------------------------
  if (!resultado) {
    return (
      <div className="mx-auto max-w-xl animate-fade-up">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex flex-col items-center text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-ink-900 text-jade-400">
              <ScanLine className="h-6 w-6" />
            </span>
            <h1 className="mt-4 font-display text-2xl font-600 tracking-tight text-ink-900">Nova análise</h1>
            <p className="mt-1 max-w-sm text-sm text-slate-500">
              Envie o Livro de Entradas para classificar os fornecedores por crédito de ICMS.
            </p>
          </div>

          <div className="mt-7">
            <FileUpload
              label="Livro de Entradas"
              hint="Documento obrigatório com os lançamentos de entrada."
              obrigatorio
              file={entradas}
              onChange={setEntradas}
            />
          </div>

          {/* O casamento de CNPJ agora é automático pelo banco de fornecedores. */}
          <p className="mt-3 flex items-start gap-2 text-xs text-slate-400">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-jade-500" />
            <span>
              Os CNPJ conhecidos são casados automaticamente pelo banco de fornecedores, sem custo. Os pendentes podem ser
              resolvidos após o processamento.
            </span>
          </p>

          {processar.error && (
            <Alerta tom="erro" className="mt-5">
              {detalheErro}
            </Alerta>
          )}

          <div className="mt-6 flex flex-col items-center gap-2">
            <button
              type="button"
              onClick={() => entradas && processar.mutate({ entradas })}
              disabled={!entradas || processar.isPending}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-3 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
            >
              {processar.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Processando...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" /> Processar análise
                </>
              )}
            </button>
            {processar.isPending && (
              <p className="text-sm text-slate-500">Lendo e classificando fornecedores...</p>
            )}
            {!entradas && !processar.isPending && (
              <p className="text-sm text-slate-400">Selecione o Livro de Entradas para continuar.</p>
            )}
          </div>
        </div>

        {abrir.isError && (
          <Alerta tom="erro" className="mt-4">
            {abrir.error?.response?.data?.detail ?? "Não foi possível reabrir a análise."}
          </Alerta>
        )}

        {/* Histórico de acesso rápido: reabrir análises sem subir a planilha de novo.
            Ocultável por preferência local (vira controle por papel com o login). */}
        {historicoOculto ? (
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={() => alternarHistorico(false)}
              className="inline-flex items-center gap-1.5 text-xs font-500 text-slate-400 transition-colors hover:text-ink-700"
            >
              <History className="h-3.5 w-3.5" /> Mostrar histórico
            </button>
          </div>
        ) : (
          <div className="mt-2">
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => alternarHistorico(true)}
                className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-500 text-slate-400 transition-colors hover:text-ink-700"
                aria-label="Ocultar histórico de análises"
              >
                <EyeOff className="h-3.5 w-3.5" /> Ocultar
              </button>
            </div>
            <HistoricoAnalises onAbrir={(id) => abrir.mutate(id)} abrindoId={abrir.isPending ? abrir.variables : null} />
          </div>
        )}
      </div>
    );
  }

  // ---- ESTADO 2-5: DASHBOARD --------------------------------------------
  const r = resultado.resumo;
  const cndConcluida = progresso?.status === "concluido";
  const cndRodando = progresso?.status === "em_andamento";
  const totalRiscoAlto = resultado.fornecedores.filter((f) => f.risco_2027 === "ALTO").length;
  // Quantos fornecedores AINDA serão consultados (e cobrados): tem CNPJ e não tem resultado
  // válido (sem status ou status FALHA). Espelha _precisa_consultar do backend, para o número
  // e o custo do card não ficarem no total cheio depois que alguns já voltaram negativa/positiva.
  const cndPorConsultar = resultado.fornecedores.filter(
    (f) => f.cnpj && (!f.status_cnd || f.status_cnd === "FALHA")
  ).length;
  // A CND já foi consultada nesta análise se algum fornecedor tem status ou risco calculado.
  // Baseia-se nos DADOS (persistem no histórico), não no progresso da sessão: assim o KPI de
  // risco e o impacto continuam aparecendo após recarregar/reabrir.
  const temResultadoCnd = resultado.fornecedores.some((f) => f.status_cnd || f.risco_2027);
  const impactoTotal = resultado.fornecedores.reduce(
    (s, f) => s + (Number(f.impacto_financeiro_anual) || 0),
    0
  );

  return (
    <div className="space-y-6 animate-fade-up">
      <ClienteHeader metadados={resultado.metadados} />
      <ExplicacaoMetodologia aberto={mostrarMetodologia} onFechar={() => setMostrarMetodologia(false)} />

      <div className="-mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => setMostrarMetodologia(true)}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-500 text-slate-500 transition-colors hover:bg-slate-100 hover:text-jade-700"
        >
          <HelpCircle className="h-3.5 w-3.5" /> Como esta análise é feita?
        </button>
      </div>

      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ResultCard titulo="Fornecedores" valor={numero(r.total_fornecedores)} Icone={Users} tom="neutro" sublabel={`${r.cnpj_casados} com CNPJ · ${r.cnpj_pendentes} pendente(s)`} />
        <ResultCard titulo="Crédito ICMS aproveitado" valor={moedaCompacta(r.total_credito_aproveitado)} Icone={Coins} tom="positivo" sublabel={moeda(r.total_credito_aproveitado)} />
        <ResultCard titulo="Compras sem crédito" valor={moedaCompacta(r.total_compras_sem_credito)} Icone={Ban} tom="atencao" sublabel={moeda(r.total_compras_sem_credito)} />
        {temResultadoCnd ? (
          <ResultCard titulo="Risco 2027" valor={numero(totalRiscoAlto)} Icone={ShieldAlert} tom={totalRiscoAlto > 0 ? "risco" : "positivo"} alertaPulsante={totalRiscoAlto > 0} sublabel={totalRiscoAlto > 0 ? "fornecedores em risco alto" : "nenhum risco alto"} />
        ) : (
          <ResultCard titulo="Verificação manual (ST)" valor={numero(r.caso_especial)} Icone={Sparkles} tom={r.caso_especial > 0 ? "atencao" : "neutro"} sublabel="possível Substituição Tributária" />
        )}
      </div>

      {temResultadoCnd && impactoTotal > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <ResultCard titulo="Impacto estimado anual" valor={moeda(impactoTotal)} Icone={TrendingDown} tom="risco" sublabel="crédito de ICMS sob risco em 2027" />
        </div>
      )}

      {/* Gráfico + bloco CND lado a lado */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Suspense
          fallback={
            <div className="grid h-72 place-items-center rounded-2xl border border-slate-200 bg-white shadow-panel">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          }
        >
          <DistribuicaoGrupos resumo={r} />
        </Suspense>
        <BlocoCnd
          progresso={progresso}
          cndRodando={cndRodando}
          cndConcluida={cndConcluida}
          erroCnd={erroCnd}
          disparando={dispararCnd.isPending}
          onDisparar={() => dispararCnd.mutate()}
          qtdComCnpj={cndPorConsultar}
          custoCndCent={custos.cndCent}
        />
      </div>

      {/* Alertas de risco (só com CND) */}
      {/* O painel se baseia nos dados (risco_2027, que persistem no histórico), não no estado
          efêmero da consulta: assim continua aparecendo após recarregar. Ele mesmo se oculta
          quando não há fornecedor em risco alto. */}
      <AlertasRisco fornecedores={resultado.fornecedores} />

      <PainelCnpj
        pendentes={r.cnpj_pendentes}
        pendentesDetalhe={pendentesEnriq}
        carregandoPendentes={carregandoPendentesEnriq}
        progresso={progressoEnriquecimento}
        onEnriquecer={({ forcar } = {}) => enriquecer.mutate({ forcar })}
        enriquecendo={enriquecer.isPending || progressoEnriquecimento?.status === "em_andamento"}
        erro={erroEnriquecimento}
        custoCadastroCent={custos.cadastroCent}
      />

      {erroCnpj && <Alerta tom="erro">{erroCnpj}</Alerta>}

      <FornecedoresTable
        fornecedores={resultado.fornecedores}
        onSalvarCnpj={(codForn, dados) => salvarCnpj.mutate({ codForn, ...dados })}
        salvando={salvarCnpj.isPending}
      />

      {/* Ações finais */}
      <div className="flex flex-wrap items-center gap-3">
        <a
          href={urlRelatorio(resultado.job_id)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-xl bg-ink-900 px-5 py-3 text-sm font-600 text-white shadow-lift transition-colors hover:bg-ink-800"
        >
          <FileDown className="h-4 w-4" /> Baixar relatório PDF
        </a>
        <button
          type="button"
          onClick={reiniciar}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-3 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50"
        >
          <RotateCcw className="h-4 w-4" /> Nova análise
        </button>
      </div>
    </div>
  );
}

// Bloco da consulta de regularidade fiscal (CND): inicial, em andamento, concluída ou erro.
function BlocoCnd({ progresso, cndRodando, cndConcluida, erroCnd, disparando, onDisparar, qtdComCnpj, custoCndCent }) {
  const [confirmando, setConfirmando] = useState(false);
  // custoCndCent pode ser fracionário (preço derivado do backend): preserva a
  // fração na multiplicação e arredonda só no total exibido.
  const totalCent = Math.round(
    Math.max(0, Math.trunc(qtdComCnpj || 0)) * Math.max(0, Number(custoCndCent) || 0),
  );

  function confirmar() {
    setConfirmando(false);
    onDisparar();
  }

  return (
    <section className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
      <div className="flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
          <ScanLine className="h-4 w-4" />
        </span>
        <h2 className="font-display text-lg font-600 text-ink-900">Regularidade fiscal (CND)</h2>
      </div>

      <div className="mt-4 flex flex-1 flex-col justify-center">
        {erroCnd && <Alerta tom="erro" className="mb-4">{erroCnd}</Alerta>}

        {cndRodando ? (
          <ProgressBar
            percentual={progresso?.percentual ?? 0}
            total={progresso?.total}
            consultados={progresso?.consultados}
            falhas={progresso?.falhas}
            termoFalha="pendente"
            termoFalhas="pendentes"
            ativo
          />
        ) : confirmando ? (
          // Confirmação tem prioridade sobre o estado concluído: permite re-disparar
          // a CND (re-tenta as que falharam) quando a Receita volta ao ar.
          <ConfirmacaoCusto
            quantidade={qtdComCnpj}
            custoUnitarioCent={custoCndCent}
            descricao="Consulta de CND"
            processando={disparando}
            onConfirmar={confirmar}
            onCancelar={() => setConfirmando(false)}
          />
        ) : cndConcluida ? (
          <div className="space-y-3">
            <ProgressBar
              percentual={100}
              total={progresso?.total}
              consultados={progresso?.consultados}
              falhas={progresso?.falhas}
              termoFalha="pendente"
              termoFalhas="pendentes"
              ativo={false}
              label="Consulta concluída"
            />
            {(progresso?.origem_indisponivel ?? 0) > 0 && (
              <div className="space-y-3">
                <AvisoReceitaForaDoAr quantidade={progresso.origem_indisponivel} />
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={() => setConfirmando(true)}
                    disabled={disparando || !qtdComCnpj}
                    className="inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-sm font-600 text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50"
                  >
                    {disparando ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                    {disparando ? "Iniciando..." : "Consultar regularidade de novo"}
                  </button>
                </div>
              </div>
            )}
            <p className="text-xs text-slate-500">
              Resultados de CND e risco aplicados à análise. O detalhamento completo por fornecedor consta no relatório PDF.
            </p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm text-slate-500">
              Consulte a Certidão Negativa de Débitos de cada fornecedor para avaliar o risco de perda de crédito em 2027.
            </p>
            <p className="mt-2 flex flex-wrap items-center justify-center gap-1.5 text-xs text-slate-500">
              <Coins className="h-3.5 w-3.5 text-amber-500" />
              Consulta paga · {numero(qtdComCnpj || 0)} a consultar ≈{" "}
              <strong className="tnum text-ink-700">{moeda(totalCent / 100)}</strong>
            </p>
            <div className="mt-4 flex justify-center">
              <button
                type="button"
                onClick={() => setConfirmando(true)}
                disabled={disparando || !qtdComCnpj}
                className="inline-flex items-center gap-2 rounded-xl bg-jade-600 px-5 py-2.5 text-sm font-600 text-white transition-colors hover:bg-jade-700 disabled:opacity-50"
              >
                {disparando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {disparando ? "Iniciando..." : "Consultar regularidade"}
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// Origem oficial (Receita Federal/PGFN) fora do ar: parte das CND falhou por
// causa da fonte, não por defeito do sistema. Distinto de erro do sistema:
// basta re-tentar em alguns minutos clicando em "Consultar regularidade" de
// novo, que o backend refaz só as que falharam.
function AvisoReceitaForaDoAr({ quantidade, className = "" }) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-700 ${className}`}
      role="status"
    >
      <ServerCrash className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        A Receita Federal/PGFN está instável (fora do ar ou devolvendo certidão incompleta).{" "}
        <strong>
          {quantidade} consulta{quantidade > 1 ? "s" : ""}
        </strong>{" "}
        ficou pendente por isso, não por defeito do sistema. Em alguns minutos, clique em{" "}
        <strong>Consultar regularidade</strong> de novo para re-tentar apenas as pendentes.
      </span>
    </div>
  );
}

function Alerta({ tom = "erro", children, className = "" }) {
  const tons = {
    erro: "border-signal-200 bg-signal-50 text-signal-700",
    atencao: "border-amber-200 bg-amber-50 text-amber-700",
  };
  return (
    <div className={`flex items-start gap-2.5 rounded-xl border p-3.5 text-sm ${tons[tom]} ${className}`} role="alert">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}
