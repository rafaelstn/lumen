import { useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import {
  ShieldCheck,
  Building2,
  Users,
  FileText,
  Database,
  CheckCircle2,
  Coins,
  CircleDollarSign,
  Loader2,
  AlertCircle,
  Inbox,
  ChevronRight,
  ArrowLeft,
  X,
  Plus,
  Trash2,
  Search,
  MapPin,
  Phone,
  Mail,
  Briefcase,
} from "lucide-react";
import {
  getAdminResumo,
  getAdminEscritorios,
  getAdminConsumoPorEscritorio,
  getAdminEscritorioDetalhe,
  criarEscritorio,
  deletarEscritorio,
  listarFornecedoresAdmin,
  detalheFornecedor,
} from "../services/api.js";
import { moeda, numero, dataHora, formatarCnpj, statusCndMeta } from "../utils/format.js";

const QK_RESUMO = ["admin", "resumo"];
const QK_ESCRITORIOS = ["admin", "escritorios"];
const QK_CONSUMO = ["admin", "consumo-por-escritorio"];
const QK_DETALHE = (id) => ["admin", "escritorio", id];
const QK_FORNECEDORES = (offset, limit, q) => ["admin", "fornecedores", offset, limit, q];
const QK_FORNECEDOR_DETALHE = (cnpj) => ["admin", "fornecedor", cnpj];

// Centavos (inteiro) -> R$. Tudo que é dinheiro no contrato vem em *_centavos.
function reais(centavos) {
  return moeda((Number(centavos) || 0) / 100);
}

// Dashboard administrativo: visão global da operação (todos os escritórios).
// Só é montado para usuários com role === "admin" (gate no App/Sidebar).
export default function AdminDashboard() {
  const [aba, setAba] = useState("operacao");
  const [escritorioId, setEscritorioId] = useState(null);
  const [cnpjAberto, setCnpjAberto] = useState(null);
  const [criando, setCriando] = useState(false);
  const queryClient = useQueryClient();

  const resumo = useQuery({ queryKey: QK_RESUMO, queryFn: getAdminResumo });
  const escritorios = useQuery({ queryKey: QK_ESCRITORIOS, queryFn: getAdminEscritorios });
  const consumo = useQuery({
    queryKey: QK_CONSUMO,
    queryFn: () => getAdminConsumoPorEscritorio(),
  });

  // Reúne as invalidações que tocam a foto da operação após cadastrar/excluir.
  function invalidarOperacao() {
    queryClient.invalidateQueries({ queryKey: QK_RESUMO });
    queryClient.invalidateQueries({ queryKey: QK_ESCRITORIOS });
    queryClient.invalidateQueries({ queryKey: QK_CONSUMO });
  }

  return (
    <div className="space-y-7 animate-fade-up">
      <Cabecalho aoCadastrar={() => setCriando(true)} />
      <Abas aba={aba} onTrocar={setAba} />

      {aba === "operacao" ? (
        <>
          <SecaoMetricas query={resumo} />
          <SecaoEscritorios
            query={escritorios}
            onAbrir={setEscritorioId}
            aoExcluir={invalidarOperacao}
          />
          <SecaoConsumo query={consumo} />
        </>
      ) : (
        <SecaoEmpresas onAbrir={setCnpjAberto} />
      )}

      {escritorioId != null && (
        <DetalheEscritorio
          id={escritorioId}
          onFechar={() => setEscritorioId(null)}
          aoExcluir={() => {
            invalidarOperacao();
            setEscritorioId(null);
          }}
        />
      )}

      {cnpjAberto != null && (
        <DetalheFornecedor cnpj={cnpjAberto} onFechar={() => setCnpjAberto(null)} />
      )}

      {criando && (
        <ModalCadastro
          onFechar={() => setCriando(false)}
          aoCriar={() => {
            invalidarOperacao();
            setCriando(false);
          }}
        />
      )}
    </div>
  );
}

function Abas({ aba, onTrocar }) {
  const itens = [
    { id: "operacao", rotulo: "Operação", Icone: Building2 },
    { id: "empresas", rotulo: "Empresas cadastradas", Icone: Database },
  ];
  return (
    <div
      role="tablist"
      aria-label="Seções do painel administrativo"
      className="flex gap-1 rounded-xl border border-slate-200 bg-white p-1 shadow-panel sm:w-fit"
    >
      {itens.map(({ id, rotulo, Icone }) => {
        const ativo = aba === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={ativo}
            onClick={() => onTrocar(id)}
            className={[
              "inline-flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-500 transition-colors sm:flex-none",
              ativo ? "bg-ink-900 text-white shadow-lift" : "text-slate-500 hover:bg-slate-50 hover:text-ink-800",
            ].join(" ")}
          >
            <Icone className="h-4 w-4" />
            {rotulo}
          </button>
        );
      })}
    </div>
  );
}

function Cabecalho({ aoCadastrar }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-start gap-3.5">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-ink-900 text-jade-400">
          <ShieldCheck className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-600 tracking-tight text-ink-900">
            Painel administrativo
          </h1>
          <p className="mt-1 max-w-xl text-sm text-slate-500">
            Visão global da operação: escritórios cadastrados, uso das APIs pagas e custo total
            acumulado. Valores monetários consolidados em reais.
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={aoCadastrar}
        className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-jade-600 px-4 py-2.5 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700"
      >
        <Plus className="h-4 w-4" /> Cadastrar escritório
      </button>
    </div>
  );
}

// ---- MÉTRICAS GLOBAIS ---------------------------------------------------

function SecaoMetricas({ query }) {
  const { data, isLoading, isError, refetch } = query;

  if (isLoading) return <GradeCardsSkeleton />;
  if (isError) return <ErroBloco aoTentar={refetch}>Não foi possível carregar as métricas.</ErroBloco>;

  const m = data ?? {};
  const cards = [
    { rotulo: "Escritórios", valor: numero(m.total_escritorios), Icone: Building2 },
    { rotulo: "Usuários", valor: numero(m.total_usuarios), Icone: Users },
    { rotulo: "Análises", valor: numero(m.total_analises), Icone: FileText },
    { rotulo: "Fornecedores no cache", valor: numero(m.fornecedores_cache_global), Icone: Database },
    {
      rotulo: "Cadastro completo",
      valor: numero(m.fornecedores_cadastro_completo),
      Icone: CheckCircle2,
    },
    { rotulo: "Consultas pagas", valor: numero(m.consultas_pagas), Icone: Coins },
    { rotulo: "Créditos consumidos", valor: numero(m.creditos_consumidos), Icone: Coins },
    {
      rotulo: "Custo total",
      valor: reais(m.custo_total_centavos),
      Icone: CircleDollarSign,
      destaque: true,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {cards.map((c) => (
        <CardMetrica key={c.rotulo} {...c} />
      ))}
    </div>
  );
}

function CardMetrica({ rotulo, valor, Icone, destaque }) {
  return (
    <div
      className={[
        "rounded-xl border p-4 shadow-panel",
        destaque ? "border-jade-200 bg-jade-50" : "border-slate-200 bg-white",
      ].join(" ")}
    >
      <div className="flex items-center gap-2 text-slate-500">
        <Icone className={`h-4 w-4 ${destaque ? "text-jade-600" : "text-slate-400"}`} />
        <span className="text-xs font-500">{rotulo}</span>
      </div>
      <p
        className={[
          "mt-2 font-display text-2xl font-600 tnum tracking-tight",
          destaque ? "text-jade-700" : "text-ink-900",
        ].join(" ")}
      >
        {valor}
      </p>
    </div>
  );
}

// ---- TABELA DE ESCRITÓRIOS ---------------------------------------------

function SecaoEscritorios({ query, onAbrir, aoExcluir }) {
  const { data, isLoading, isError, refetch } = query;
  // id do escritório com a confirmação de exclusão aberta (uma por vez).
  const [confirmandoId, setConfirmandoId] = useState(null);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-4">
        <Building2 className="h-4 w-4 text-jade-600" />
        <h2 className="font-display text-base font-600 tracking-tight text-ink-900">Escritórios</h2>
      </div>

      {isLoading && <BlocoCentral><Loader2 className="h-5 w-5 animate-spin text-slate-400" /> Carregando escritórios...</BlocoCentral>}
      {isError && <div className="p-5"><ErroBloco aoTentar={refetch}>Não foi possível carregar os escritórios.</ErroBloco></div>}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <BlocoVazio>Nenhum escritório cadastrado ainda.</BlocoVazio>
      )}

      {!isLoading && !isError && data && data.length > 0 && (
        <>
          {/* Mobile: cards. Desktop: tabela. */}
          <ul className="divide-y divide-slate-100 lg:hidden">
            {data.map((e) => (
              <li key={e.id}>
                <CardEscritorioMobile
                  escritorio={e}
                  onAbrir={() => onAbrir(e.id)}
                  confirmando={confirmandoId === e.id}
                  onPedirExcluir={() => setConfirmandoId(e.id)}
                  onCancelar={() => setConfirmandoId(null)}
                  aoExcluir={() => {
                    setConfirmandoId(null);
                    aoExcluir();
                  }}
                />
              </li>
            ))}
          </ul>

          <div className="hidden overflow-x-auto lg:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-500 uppercase tracking-wide text-slate-500">
                  <th className="px-5 py-3">Escritório</th>
                  <th className="px-5 py-3 text-right">Usuários</th>
                  <th className="px-5 py-3 text-right">Análises</th>
                  <th className="px-5 py-3 text-right">Fornecedores</th>
                  <th className="px-5 py-3 text-right">Créditos</th>
                  <th className="px-5 py-3 text-right">Custo</th>
                  <th className="px-5 py-3">Última atividade</th>
                  <th className="px-5 py-3 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((e) =>
                  confirmandoId === e.id ? (
                    <tr key={e.id} className="bg-signal-50/60">
                      <td colSpan={8} className="px-5 py-4">
                        <ConfirmExclusao
                          escritorio={e}
                          onCancelar={() => setConfirmandoId(null)}
                          aoExcluir={() => {
                            setConfirmandoId(null);
                            aoExcluir();
                          }}
                        />
                      </td>
                    </tr>
                  ) : (
                    <tr key={e.id} className="transition-colors hover:bg-slate-50">
                      <td
                        className="cursor-pointer px-5 py-3 font-500 text-ink-900"
                        onClick={() => onAbrir(e.id)}
                      >
                        {e.nome}
                      </td>
                      <td className="px-5 py-3 text-right tnum text-ink-700">{numero(e.total_usuarios)}</td>
                      <td className="px-5 py-3 text-right tnum text-ink-700">{numero(e.total_analises)}</td>
                      <td className="px-5 py-3 text-right tnum text-ink-700">
                        {numero(e.total_fornecedores_pesquisados)}
                      </td>
                      <td className="px-5 py-3 text-right tnum text-ink-700">
                        {numero(e.consumo?.creditos_consumidos)}
                      </td>
                      <td className="px-5 py-3 text-right tnum font-500 text-ink-900">
                        {reais(e.consumo?.custo_centavos)}
                      </td>
                      <td className="px-5 py-3 text-slate-500">{dataHora(e.ultima_atividade)}</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => onAbrir(e.id)}
                            aria-label={`Abrir detalhe de ${e.nome}`}
                            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-800"
                          >
                            <ChevronRight className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmandoId(e.id)}
                            aria-label={`Excluir ${e.nome}`}
                            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-signal-50 hover:text-signal-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function CardEscritorioMobile({
  escritorio: e,
  onAbrir,
  confirmando,
  onPedirExcluir,
  onCancelar,
  aoExcluir,
}) {
  if (confirmando) {
    return (
      <div className="bg-signal-50/60 px-5 py-4">
        <ConfirmExclusao escritorio={e} onCancelar={onCancelar} aoExcluir={aoExcluir} />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-5 py-4">
      <button
        type="button"
        onClick={onAbrir}
        className="flex min-w-0 flex-1 items-center justify-between gap-3 text-left"
      >
        <div className="min-w-0">
          <p className="truncate font-500 text-ink-900">{e.nome}</p>
          <p className="mt-1 text-xs text-slate-500">
            {numero(e.total_usuarios)} usuário(s) · {numero(e.total_analises)} análise(s)
          </p>
          <p className="mt-0.5 text-xs text-slate-400">Atividade: {dataHora(e.ultima_atividade)}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="tnum font-600 text-ink-900">{reais(e.consumo?.custo_centavos)}</p>
          <p className="mt-0.5 text-xs tnum text-slate-500">
            {numero(e.consumo?.creditos_consumidos)} créd.
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={onPedirExcluir}
        aria-label={`Excluir ${e.nome}`}
        className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-signal-50 hover:text-signal-600"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

// Confirmação inline de exclusão de escritório. Avisa o que é apagado e o que
// é preservado, e trata as proteções do backend (400 default/admin) e 404.
function ConfirmExclusao({ escritorio: e, onCancelar, aoExcluir, compacto }) {
  const mutacao = useMutation({
    mutationFn: () => deletarEscritorio(e.id),
    onSuccess: () => aoExcluir(),
  });

  const erro = mutacao.isError ? mensagemErroExclusao(mutacao.error) : null;

  return (
    <div className="space-y-3 text-left">
      <div className="flex items-start gap-2.5">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-signal-600" />
        <div className="text-sm text-ink-800">
          <p className="font-600">Excluir o escritório “{e.nome}”?</p>
          <p className="mt-1 text-slate-600">
            Remove em definitivo os usuários, as análises e o histórico deste escritório. O cadastro
            global de CNPJ (empresas) é preservado.
          </p>
        </div>
      </div>

      {erro && (
        <div
          className="flex items-start gap-2 rounded-lg border border-signal-200 bg-white px-3 py-2 text-sm text-signal-700"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{erro}</span>
        </div>
      )}

      <div className={`flex gap-2 ${compacto ? "flex-col" : "flex-col sm:flex-row"}`}>
        <button
          type="button"
          onClick={() => mutacao.mutate()}
          disabled={mutacao.isPending}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-signal-600 px-4 py-2 text-sm font-600 text-white transition-colors hover:bg-signal-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {mutacao.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Excluindo...
            </>
          ) : (
            <>
              <Trash2 className="h-4 w-4" /> Sim, excluir
            </>
          )}
        </button>
        <button
          type="button"
          onClick={onCancelar}
          disabled={mutacao.isPending}
          className="inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

// Traduz o erro do DELETE para mensagem clara. 400 = proteção (default/admin),
// 404 = já removido; usa o detail do backend quando vier.
function mensagemErroExclusao(error) {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  if (status === 400) {
    return (
      detail ??
      "Este escritório não pode ser excluído: o escritório padrão e os que contêm um administrador são protegidos."
    );
  }
  if (status === 404) return "Escritório não encontrado. Ele pode já ter sido removido.";
  return detail ?? "Não foi possível excluir o escritório. Tente novamente.";
}

// ---- CONSUMO POR ESCRITÓRIO (barras) -----------------------------------

function SecaoConsumo({ query }) {
  const { data, isLoading, isError, refetch } = query;

  let conteudo;
  if (isLoading) {
    conteudo = <BlocoCentral><Loader2 className="h-5 w-5 animate-spin text-slate-400" /> Carregando consumo...</BlocoCentral>;
  } else if (isError) {
    conteudo = <div className="p-5"><ErroBloco aoTentar={refetch}>Não foi possível carregar o consumo.</ErroBloco></div>;
  } else if (!data || data.length === 0) {
    conteudo = <BlocoVazio>Sem consumo registrado no período.</BlocoVazio>;
  } else {
    const maxCusto = Math.max(...data.map((d) => Number(d.custo_centavos) || 0), 1);
    const ordenado = [...data].sort(
      (a, b) => (Number(b.custo_centavos) || 0) - (Number(a.custo_centavos) || 0)
    );
    conteudo = (
      <ul className="space-y-3 px-5 py-5">
        {ordenado.map((d) => {
          const custo = Number(d.custo_centavos) || 0;
          const pct = Math.max(2, Math.round((custo / maxCusto) * 100));
          return (
            <li key={d.escritorio_id}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate font-500 text-ink-800">{d.nome}</span>
                <span className="shrink-0 tnum text-ink-700">{reais(custo)}</span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-jade-500"
                  style={{ width: `${pct}%` }}
                  role="img"
                  aria-label={`${d.nome}: ${reais(custo)}`}
                />
              </div>
              <p className="mt-1 text-xs tnum text-slate-400">
                {numero(d.creditos_consumidos)} crédito(s) consumido(s)
              </p>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-4">
        <Coins className="h-4 w-4 text-jade-600" />
        <h2 className="font-display text-base font-600 tracking-tight text-ink-900">
          Consumo por escritório
        </h2>
      </div>
      {conteudo}
    </section>
  );
}

// ---- DETALHE DO ESCRITÓRIO (drawer) ------------------------------------

function DetalheEscritorio({ id, onFechar, aoExcluir }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: QK_DETALHE(id),
    queryFn: () => getAdminEscritorioDetalhe(id),
  });
  const [confirmando, setConfirmando] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-ink-950/50 backdrop-blur-sm"
        onClick={onFechar}
        aria-hidden="true"
      />
      <aside
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-lift animate-fade-up"
        role="dialog"
        aria-modal="true"
        aria-label="Detalhe do escritório"
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-slate-100 bg-white px-5 py-4">
          <button
            type="button"
            onClick={onFechar}
            className="inline-flex items-center gap-1.5 text-sm font-500 text-slate-500 transition-colors hover:text-ink-800 lg:hidden"
          >
            <ArrowLeft className="h-4 w-4" /> Voltar
          </button>
          <h2 className="hidden font-display text-base font-600 tracking-tight text-ink-900 lg:block">
            Detalhe do escritório
          </h2>
          <button
            type="button"
            onClick={onFechar}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-800"
            aria-label="Fechar"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </div>

        <div className="flex-1 px-5 py-5">
          {isLoading && (
            <BlocoCentral><Loader2 className="h-5 w-5 animate-spin text-slate-400" /> Carregando detalhe...</BlocoCentral>
          )}
          {isError && (
            <ErroBloco aoTentar={refetch}>
              Não foi possível carregar o escritório. Ele pode ter sido removido.
            </ErroBloco>
          )}
          {!isLoading && !isError && data && (
            <>
              <CorpoDetalhe d={data} />
              <div className="mt-6 border-t border-slate-100 pt-5">
                {confirmando ? (
                  <ConfirmExclusao
                    escritorio={data}
                    compacto
                    onCancelar={() => setConfirmando(false)}
                    aoExcluir={aoExcluir}
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmando(true)}
                    className="inline-flex items-center gap-2 rounded-lg border border-signal-200 bg-signal-50 px-4 py-2 text-sm font-500 text-signal-700 transition-colors hover:bg-signal-100"
                  >
                    <Trash2 className="h-4 w-4" /> Excluir escritório
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function CorpoDetalhe({ d }) {
  const porServico = d?.consumo?.por_servico ?? {};
  const servicos = Object.entries(porServico);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-display text-lg font-600 tracking-tight text-ink-900">{d.nome}</h3>
        <p className="mt-1 text-xs text-slate-400">Criado em {dataHora(d.criado_em)}</p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <MiniCard rotulo="Análises" valor={numero(d.total_analises)} />
        <MiniCard rotulo="Fornecedores" valor={numero(d.total_fornecedores_pesquisados)} />
        <MiniCard rotulo="Custo" valor={reais(d.consumo?.custo_centavos)} destaque />
      </div>

      <div>
        <h4 className="mb-2 text-xs font-600 uppercase tracking-wide text-slate-500">Usuários</h4>
        {!d.usuarios || d.usuarios.length === 0 ? (
          <p className="text-sm text-slate-400">Nenhum usuário neste escritório.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {d.usuarios.map((u) => (
              <li key={u.id} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate text-ink-800">{u.email}</p>
                  <p className="mt-0.5 text-xs text-slate-400">{dataHora(u.criado_em)}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <ChipPapel role={u.role} />
                  {!u.ativo && (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[0.65rem] font-500 text-slate-500">
                      Inativo
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {servicos.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-600 uppercase tracking-wide text-slate-500">
            Consumo por serviço
          </h4>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {servicos.map(([nome, s]) => (
              <li key={nome} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                <span className="font-500 capitalize text-ink-800">{nome}</span>
                <span className="text-right text-xs text-slate-500">
                  <span className="tnum">{numero(s.consultas)}</span> consultas ·{" "}
                  <span className="tnum">{numero(s.creditos_consumidos)}</span> créd. ·{" "}
                  <span className="tnum font-500 text-ink-800">{reais(s.custo_centavos)}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ChipPapel({ role }) {
  const admin = role === "admin";
  return (
    <span
      className={[
        "rounded-full px-2 py-0.5 text-[0.65rem] font-500",
        admin ? "bg-ink-900 text-jade-400" : "bg-jade-50 text-jade-700",
      ].join(" ")}
    >
      {admin ? "Admin" : "Escritório"}
    </span>
  );
}

function MiniCard({ rotulo, valor, destaque }) {
  return (
    <div className={`rounded-lg border p-3 ${destaque ? "border-jade-200 bg-jade-50" : "border-slate-200 bg-slate-50"}`}>
      <p className="text-[0.65rem] font-500 uppercase tracking-wide text-slate-500">{rotulo}</p>
      <p className={`mt-1 tnum font-600 ${destaque ? "text-jade-700" : "text-ink-900"}`}>{valor}</p>
    </div>
  );
}

// ---- CADASTRO DE ESCRITÓRIO (modal) ------------------------------------

function ModalCadastro({ onFechar, aoCriar }) {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erros, setErros] = useState({});

  const mutacao = useMutation({
    mutationFn: () => criarEscritorio({ nome: nome.trim(), email: email.trim(), senha }),
    onSuccess: () => aoCriar(),
  });

  // Validação client-side: nome obrigatório, e-mail simples, senha >= 8.
  function validar() {
    const e = {};
    if (!nome.trim()) e.nome = "Informe o nome do escritório.";
    if (!email.trim()) e.email = "Informe o e-mail do dono.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) e.email = "E-mail inválido.";
    if (senha.length < 8) e.senha = "A senha deve ter ao menos 8 caracteres.";
    setErros(e);
    return Object.keys(e).length === 0;
  }

  function submeter(ev) {
    ev.preventDefault();
    if (!validar()) return;
    mutacao.mutate();
  }

  // Erro do servidor mapeado para o campo certo (409 e-mail, 422 senha).
  const erroServidor = mutacao.isError ? interpretarErroCadastro(mutacao.error) : null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-ink-950/50 backdrop-blur-sm" onClick={onFechar} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-cadastro"
        className="relative w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-lift animate-fade-up"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <h2 id="titulo-cadastro" className="font-display text-base font-600 tracking-tight text-ink-900">
            Cadastrar escritório
          </h2>
          <button
            type="button"
            onClick={onFechar}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-800"
            aria-label="Fechar"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </div>

        <form onSubmit={submeter} noValidate className="space-y-4 px-5 py-5">
          <p className="text-sm text-slate-500">
            Cria o escritório e o usuário dono em uma só etapa. O dono entra com o e-mail e a senha
            definidos aqui.
          </p>

          <CampoTexto
            id="cad-nome"
            rotulo="Nome do escritório"
            valor={nome}
            onChange={setNome}
            erro={erros.nome}
            placeholder="Ex.: Escritório Aurora Contabilidade"
            autoFocus
          />
          <CampoTexto
            id="cad-email"
            rotulo="E-mail do dono"
            tipo="email"
            valor={email}
            onChange={setEmail}
            erro={erros.email}
            placeholder="dono@escritorio.com.br"
          />
          <CampoTexto
            id="cad-senha"
            rotulo="Senha do dono"
            tipo="password"
            valor={senha}
            onChange={setSenha}
            erro={erros.senha}
            placeholder="Mínimo de 8 caracteres"
            ajuda="A senha precisa ter ao menos 8 caracteres."
          />

          {erroServidor && (
            <div
              className="flex items-start gap-2 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2.5 text-sm text-signal-700"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{erroServidor}</span>
            </div>
          )}

          <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onFechar}
              disabled={mutacao.isPending}
              className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50 disabled:opacity-60"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={mutacao.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-2.5 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
            >
              {mutacao.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Cadastrando...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" /> Cadastrar
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function interpretarErroCadastro(error) {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  if (status === 409) return "Este e-mail já está em uso por outro usuário.";
  if (status === 422) {
    if (typeof detail === "string") return detail;
    return "Dados inválidos. Verifique o e-mail e a senha (mínimo de 8 caracteres).";
  }
  return (typeof detail === "string" && detail) || "Não foi possível cadastrar o escritório. Tente novamente.";
}

function CampoTexto({ id, rotulo, valor, onChange, erro, tipo = "text", placeholder, ajuda, autoFocus }) {
  const idErro = `${id}-erro`;
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-500 text-ink-800">
        {rotulo}
      </label>
      <input
        id={id}
        type={tipo}
        value={valor}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-invalid={erro ? "true" : undefined}
        aria-describedby={erro ? idErro : undefined}
        className={[
          "w-full rounded-xl border bg-white px-3.5 py-2.5 text-sm text-ink-900 placeholder:text-slate-400 transition-colors focus:outline-none",
          erro ? "border-signal-400 focus:border-signal-500" : "border-slate-300 focus:border-jade-500",
        ].join(" ")}
      />
      {erro ? (
        <p id={idErro} className="mt-1 text-xs font-500 text-signal-600">
          {erro}
        </p>
      ) : ajuda ? (
        <p className="mt-1 text-xs text-slate-400">{ajuda}</p>
      ) : null}
    </div>
  );
}

// ---- EMPRESAS CADASTRADAS (cadastro global de CNPJ) --------------------

const TAM_PAGINA = 50;

function SecaoEmpresas({ onAbrir }) {
  const [termo, setTermo] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);

  const query = useQuery({
    queryKey: QK_FORNECEDORES(offset, TAM_PAGINA, busca),
    queryFn: () => listarFornecedoresAdmin({ offset, limit: TAM_PAGINA, q: busca }),
    placeholderData: keepPreviousData,
  });

  function submeter(e) {
    e.preventDefault();
    setOffset(0);
    setBusca(termo.trim());
  }

  function limpar() {
    setTermo("");
    setBusca("");
    setOffset(0);
  }

  const { data, isLoading, isError, refetch, isFetching } = query;
  const total = data?.total ?? 0;
  const resultados = data?.resultados ?? [];
  const inicio = total === 0 ? 0 : offset + 1;
  const fim = Math.min(offset + TAM_PAGINA, total);

  return (
    <section className="space-y-4">
      <form
        onSubmit={submeter}
        className="rounded-2xl border border-slate-200 bg-white p-4 shadow-panel sm:p-5"
      >
        <label htmlFor="busca-empresas" className="mb-2 block text-sm font-500 text-ink-800">
          Buscar empresa por CNPJ ou razão social
        </label>
        <div className="flex flex-col gap-2.5 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="busca-empresas"
              type="text"
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              placeholder="Ex.: 12.345.678/0001-90 ou Comercial Aurora"
              className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-3 text-sm text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-3 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700"
          >
            <Search className="h-4 w-4" /> Buscar
          </button>
          {busca && (
            <button
              type="button"
              onClick={limpar}
              className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50"
            >
              Limpar
            </button>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Lista o cadastro global de empresas. A busca é gratuita e não consome créditos.
        </p>
      </form>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <Database className="h-4 w-4 text-jade-600" />
            <h2 className="text-sm font-600 text-ink-900">
              {busca ? "Resultados" : "Empresas cadastradas"}
            </h2>
          </div>
          {!isLoading && !isError && total > 0 && (
            <span className="flex items-center gap-2 text-xs text-slate-500">
              {isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
              <span className="tnum">
                {numero(inicio)}–{numero(fim)} de {numero(total)}
              </span>
            </span>
          )}
        </div>

        {isLoading && (
          <BlocoCentral>
            <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> Carregando empresas...
          </BlocoCentral>
        )}
        {isError && (
          <div className="p-5">
            <ErroBloco aoTentar={refetch}>Não foi possível carregar as empresas cadastradas.</ErroBloco>
          </div>
        )}
        {!isLoading && !isError && resultados.length === 0 && (
          <BlocoVazio>
            {busca
              ? "Nenhuma empresa encontrada para essa busca."
              : "Nenhuma empresa cadastrada ainda. O cadastro cresce conforme as análises resolvem os CNPJ."}
          </BlocoVazio>
        )}

        {!isLoading && !isError && resultados.length > 0 && (
          <>
            {/* Mobile: cards. Desktop: tabela. */}
            <ul className="divide-y divide-slate-100 lg:hidden">
              {resultados.map((f) => (
                <li key={f.cnpj}>
                  <CardEmpresaMobile f={f} onAbrir={() => onAbrir(f.cnpj)} />
                </li>
              ))}
            </ul>

            <div className="hidden overflow-x-auto lg:block">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs font-500 uppercase tracking-wide text-slate-500">
                    <th className="px-5 py-3">Razão social</th>
                    <th className="px-5 py-3">CNPJ</th>
                    <th className="px-5 py-3">Município / UF</th>
                    <th className="px-5 py-3">Situação</th>
                    <th className="px-5 py-3" aria-label="Abrir" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {resultados.map((f) => (
                    <tr
                      key={f.cnpj}
                      onClick={() => onAbrir(f.cnpj)}
                      className="cursor-pointer transition-colors hover:bg-slate-50"
                    >
                      <td className="px-5 py-3.5">
                        <p className="font-500 text-ink-900">{f.razao_social || "—"}</p>
                        {f.nome_fantasia && (
                          <p className="mt-0.5 text-xs text-slate-400">{f.nome_fantasia}</p>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-5 py-3.5 font-mono tnum text-ink-800">
                        {formatarCnpj(f.cnpj)}
                      </td>
                      <td className="px-5 py-3.5 text-ink-700">
                        {[f.municipio, f.uf].filter(Boolean).join(" / ") || "—"}
                      </td>
                      <td className="px-5 py-3.5">
                        <ChipSituacao situacao={f.situacao_cadastral} />
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <ChevronRight className="ml-auto h-4 w-4 text-slate-400" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Paginacao
              offset={offset}
              total={total}
              tam={TAM_PAGINA}
              ocupado={isFetching}
              onAnterior={() => setOffset((o) => Math.max(0, o - TAM_PAGINA))}
              onProximo={() => setOffset((o) => o + TAM_PAGINA)}
            />
          </>
        )}
      </div>
    </section>
  );
}

function CardEmpresaMobile({ f, onAbrir }) {
  return (
    <button
      type="button"
      onClick={onAbrir}
      className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50"
    >
      <div className="min-w-0">
        <p className="truncate font-500 text-ink-900">{f.razao_social || "—"}</p>
        <p className="mt-1 font-mono text-xs tnum text-slate-500">{formatarCnpj(f.cnpj)}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          {(f.municipio || f.uf) && (
            <span className="text-xs text-slate-400">
              {[f.municipio, f.uf].filter(Boolean).join(" / ")}
            </span>
          )}
          <ChipSituacao situacao={f.situacao_cadastral} />
        </div>
      </div>
      <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
    </button>
  );
}

function ChipSituacao({ situacao }) {
  if (!situacao) return <span className="text-xs text-slate-400">—</span>;
  const ativa = /ativ/i.test(situacao);
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500",
        ativa
          ? "border-jade-200 bg-jade-50 text-jade-700"
          : "border-slate-300 bg-slate-100 text-slate-600",
      ].join(" ")}
    >
      {situacao}
    </span>
  );
}

function Paginacao({ offset, total, tam, ocupado, onAnterior, onProximo }) {
  const pagina = Math.floor(offset / tam) + 1;
  const totalPaginas = Math.max(1, Math.ceil(total / tam));
  const temAnterior = offset > 0;
  const temProximo = offset + tam < total;
  if (!temAnterior && !temProximo) return null;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3.5">
      <span className="text-xs text-slate-500">
        Página <span className="tnum">{pagina}</span> de <span className="tnum">{totalPaginas}</span>
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onAnterior}
          disabled={!temAnterior || ocupado}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Anterior
        </button>
        <button
          type="button"
          onClick={onProximo}
          disabled={!temProximo || ocupado}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Próximo
        </button>
      </div>
    </div>
  );
}

// ---- DETALHE DA EMPRESA (drawer com sócios) ----------------------------

function DetalheFornecedor({ cnpj, onFechar }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: QK_FORNECEDOR_DETALHE(cnpj),
    queryFn: () => detalheFornecedor(cnpj),
  });

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink-950/50 backdrop-blur-sm" onClick={onFechar} aria-hidden="true" />
      <aside
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-lift animate-fade-up"
        role="dialog"
        aria-modal="true"
        aria-label="Detalhe da empresa"
      >
        <div className="sticky top-0 flex items-center justify-between gap-3 border-b border-slate-100 bg-white px-5 py-4">
          <button
            type="button"
            onClick={onFechar}
            className="inline-flex items-center gap-1.5 text-sm font-500 text-slate-500 transition-colors hover:text-ink-800 lg:hidden"
          >
            <ArrowLeft className="h-4 w-4" /> Voltar
          </button>
          <h2 className="hidden font-display text-base font-600 tracking-tight text-ink-900 lg:block">
            Detalhe da empresa
          </h2>
          <button
            type="button"
            onClick={onFechar}
            className="grid h-8 w-8 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-ink-800"
            aria-label="Fechar"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </div>

        <div className="flex-1 px-5 py-5">
          {isLoading && (
            <BlocoCentral>
              <Loader2 className="h-5 w-5 animate-spin text-slate-400" /> Carregando empresa...
            </BlocoCentral>
          )}
          {isError && (
            <ErroBloco aoTentar={refetch}>
              Não foi possível carregar a empresa. Ela pode não estar mais no cadastro.
            </ErroBloco>
          )}
          {!isLoading && !isError && data && <CorpoFornecedor d={data} />}
        </div>
      </aside>
    </div>
  );
}

function CorpoFornecedor({ d }) {
  const end = d?.endereco ?? {};
  const contato = d?.contato ?? {};
  const atividade = d?.atividade ?? {};
  const cnd = d?.cnd ?? {};
  const socios = d?.socios ?? [];

  const linhaEndereco = [
    end.logradouro,
    end.numero,
    end.bairro,
    [end.municipio, end.uf].filter(Boolean).join(" / "),
    end.cep,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-display text-lg font-600 tracking-tight text-ink-900">
          {d.razao_social || "—"}
        </h3>
        {d.nome_fantasia && <p className="mt-0.5 text-sm text-slate-500">{d.nome_fantasia}</p>}
        <p className="mt-1.5 font-mono text-sm tnum text-ink-700">{formatarCnpj(d.cnpj)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <ChipSituacao situacao={d.situacao_cadastral} />
          {cnd.status && <ChipCnd status={cnd.status} />}
        </div>
      </div>

      {atividade.cnae_principal_descricao && (
        <LinhaInfo Icone={Briefcase} rotulo="Atividade principal">
          {atividade.cnae_principal_descricao}
          {atividade.cnae_principal && (
            <span className="ml-1 text-xs tnum text-slate-400">({atividade.cnae_principal})</span>
          )}
        </LinhaInfo>
      )}

      {linhaEndereco && (
        <LinhaInfo Icone={MapPin} rotulo="Endereço">
          {linhaEndereco}
        </LinhaInfo>
      )}

      {(contato.telefone_principal || contato.telefone) && (
        <LinhaInfo Icone={Phone} rotulo="Telefone">
          {contato.telefone_principal || contato.telefone}
        </LinhaInfo>
      )}

      {(contato.email_principal || contato.email) && (
        <LinhaInfo Icone={Mail} rotulo="E-mail">
          {contato.email_principal || contato.email}
        </LinhaInfo>
      )}

      <div className="grid grid-cols-2 gap-3">
        <MiniCard rotulo="Cadastro atualizado" valor={dataHora(d.cadastro_atualizado_em)} />
        <MiniCard rotulo="CND consultada" valor={dataHora(cnd.ultima_consulta)} />
      </div>

      <div>
        <h4 className="mb-2 text-xs font-600 uppercase tracking-wide text-slate-500">
          Sócios e administradores
        </h4>
        {socios.length === 0 ? (
          <p className="text-sm text-slate-400">Nenhum sócio informado no cadastro.</p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {socios.map((s, i) => (
              <li key={`${s.nome}-${i}`} className="flex items-start justify-between gap-3 px-3 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="font-500 text-ink-800">{s.nome || "—"}</p>
                  {s.qualificacao && (
                    <p className="mt-0.5 text-xs text-slate-500">{s.qualificacao}</p>
                  )}
                </div>
                {s.desde && (
                  <span className="shrink-0 text-xs tnum text-slate-400">desde {s.desde}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function LinhaInfo({ Icone, rotulo, children }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-500">
        <Icone className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-[0.65rem] font-600 uppercase tracking-wide text-slate-400">{rotulo}</p>
        <p className="mt-0.5 text-sm text-ink-800">{children}</p>
      </div>
    </div>
  );
}

function ChipCnd({ status }) {
  const meta = statusCndMeta(status);
  const classe = meta?.classe ?? "bg-slate-100 text-slate-600 border-slate-300";
  const rotulo = meta?.rotulo ?? status;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500 ${classe}`}>
      CND: {rotulo}
    </span>
  );
}

// ---- Estados compartilhados --------------------------------------------

function GradeCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-[88px] animate-pulse rounded-xl border border-slate-200 bg-white" />
      ))}
    </div>
  );
}

function BlocoCentral({ children }) {
  return (
    <div className="flex items-center justify-center gap-2 px-5 py-12 text-sm text-slate-500">
      {children}
    </div>
  );
}

function BlocoVazio({ children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-5 py-12 text-center">
      <Inbox className="h-7 w-7 text-slate-300" />
      <p className="text-sm text-slate-500">{children}</p>
    </div>
  );
}

function ErroBloco({ children, aoTentar }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-signal-200 bg-signal-50 px-5 py-8 text-center">
      <AlertCircle className="h-6 w-6 text-signal-500" />
      <p className="text-sm text-signal-700">{children}</p>
      {aoTentar && (
        <button
          type="button"
          onClick={() => aoTentar()}
          className="rounded-lg border border-signal-300 bg-white px-3 py-1.5 text-sm font-500 text-signal-700 transition-colors hover:bg-signal-100"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}
