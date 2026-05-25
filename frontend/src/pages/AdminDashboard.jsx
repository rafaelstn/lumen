import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
} from "lucide-react";
import {
  getAdminResumo,
  getAdminEscritorios,
  getAdminConsumoPorEscritorio,
  getAdminEscritorioDetalhe,
} from "../services/api.js";
import { moeda, numero, dataHora } from "../utils/format.js";

const QK_RESUMO = ["admin", "resumo"];
const QK_ESCRITORIOS = ["admin", "escritorios"];
const QK_CONSUMO = ["admin", "consumo-por-escritorio"];
const QK_DETALHE = (id) => ["admin", "escritorio", id];

// Centavos (inteiro) -> R$. Tudo que é dinheiro no contrato vem em *_centavos.
function reais(centavos) {
  return moeda((Number(centavos) || 0) / 100);
}

// Dashboard administrativo: visão global da operação (todos os escritórios).
// Só é montado para usuários com role === "admin" (gate no App/Sidebar).
export default function AdminDashboard() {
  const [escritorioId, setEscritorioId] = useState(null);

  const resumo = useQuery({ queryKey: QK_RESUMO, queryFn: getAdminResumo });
  const escritorios = useQuery({ queryKey: QK_ESCRITORIOS, queryFn: getAdminEscritorios });
  const consumo = useQuery({
    queryKey: QK_CONSUMO,
    queryFn: () => getAdminConsumoPorEscritorio(),
  });

  return (
    <div className="space-y-7 animate-fade-up">
      <Cabecalho />

      <SecaoMetricas query={resumo} />
      <SecaoEscritorios query={escritorios} onAbrir={setEscritorioId} />
      <SecaoConsumo query={consumo} />

      {escritorioId != null && (
        <DetalheEscritorio id={escritorioId} onFechar={() => setEscritorioId(null)} />
      )}
    </div>
  );
}

function Cabecalho() {
  return (
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

function SecaoEscritorios({ query, onAbrir }) {
  const { data, isLoading, isError, refetch } = query;

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
                <CardEscritorioMobile escritorio={e} onAbrir={() => onAbrir(e.id)} />
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
                  <th className="px-5 py-3" aria-label="Abrir" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((e) => (
                  <tr
                    key={e.id}
                    onClick={() => onAbrir(e.id)}
                    className="cursor-pointer transition-colors hover:bg-slate-50"
                  >
                    <td className="px-5 py-3 font-500 text-ink-900">{e.nome}</td>
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
                    <td className="px-5 py-3 text-right">
                      <ChevronRight className="ml-auto h-4 w-4 text-slate-400" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function CardEscritorioMobile({ escritorio: e, onAbrir }) {
  return (
    <button
      type="button"
      onClick={onAbrir}
      className="flex w-full items-center justify-between gap-3 px-5 py-4 text-left transition-colors hover:bg-slate-50"
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
  );
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

function DetalheEscritorio({ id, onFechar }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: QK_DETALHE(id),
    queryFn: () => getAdminEscritorioDetalhe(id),
  });

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
          {!isLoading && !isError && data && <CorpoDetalhe d={data} />}
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
