import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Wallet,
  ScanSearch,
  ListChecks,
  BellRing,
  Play,
  Loader2,
  AlertCircle,
  Plus,
  RotateCcw,
  ShieldAlert,
  Building2,
  Clock,
  Inbox,
} from "lucide-react";
import {
  dueDiligence,
  monitorarCnpj,
  listarMonitorados,
  reavaliarCarteira,
  listarAlertas,
} from "../services/api.js";
import {
  formatarCnpj,
  faixaMeta,
  statusCndMeta,
  alertaMeta,
  ROTULO_COMPONENTE,
} from "../utils/format.js";
import ScoreGauge from "../components/ScoreGauge.jsx";

const ABAS = [
  { id: "due", rotulo: "Due diligence", Icone: ScanSearch },
  { id: "carteira", rotulo: "Carteira monitorada", Icone: ListChecks },
  { id: "alertas", rotulo: "Alertas", Icone: BellRing },
];

// Módulo 02 — Score Fiscal de Fornecedores.
// Avalia fornecedores (0-100), monitora a carteira e gera alertas.
// Três seções navegáveis por abas internas (mantém o foco e o custo de render baixo).
export default function Modulo02() {
  const [aba, setAba] = useState("due");

  return (
    <div className="space-y-6 animate-fade-up">
      <Cabecalho />

      {/* Abas internas */}
      <div
        role="tablist"
        aria-label="Seções do Score Fiscal"
        className="flex flex-wrap gap-1.5 rounded-2xl border border-slate-200 bg-white p-1.5 shadow-panel"
      >
        {ABAS.map((a) => {
          const ativa = aba === a.id;
          return (
            <button
              key={a.id}
              type="button"
              role="tab"
              aria-selected={ativa}
              onClick={() => setAba(a.id)}
              className={[
                "inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-500 transition-colors sm:flex-none",
                ativa
                  ? "bg-ink-900 text-white shadow-lift"
                  : "text-ink-700 hover:bg-slate-50",
              ].join(" ")}
            >
              <a.Icone className="h-4 w-4 shrink-0" strokeWidth={2.1} />
              {a.rotulo}
            </button>
          );
        })}
      </div>

      {aba === "due" && <DueDiligence />}
      {aba === "carteira" && <Carteira />}
      {aba === "alertas" && <Alertas />}
    </div>
  );
}

function Cabecalho() {
  return (
    <div className="flex items-start gap-3.5">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-ink-900 text-jade-400">
        <Wallet className="h-5 w-5" />
      </span>
      <div>
        <h1 className="font-display text-2xl font-600 tracking-tight text-ink-900">
          Score Fiscal de Fornecedores
        </h1>
        <p className="mt-1 max-w-xl text-sm text-slate-500">
          Avalie fornecedores de 0 a 100 pela saúde fiscal, monitore a carteira e receba alertas de
          mudança de status. As avaliações consultam dados oficiais e consomem créditos da API paga.
        </p>
      </div>
    </div>
  );
}

// ---- SEÇÃO 1: DUE DILIGENCE EM LOTE -----------------------------------
function DueDiligence() {
  const [texto, setTexto] = useState("");

  const avaliar = useMutation({ mutationFn: dueDiligence });
  const resposta = avaliar.data;

  const cnpjs = texto
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  function submeter() {
    if (cnpjs.length === 0) return;
    avaliar.mutate(cnpjs);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
            <ScanSearch className="h-4 w-4" />
          </span>
          <h2 className="font-display text-lg font-600 text-ink-900">Due diligence em lote</h2>
        </div>

        <label htmlFor="cnpjs-lote" className="mt-4 block text-sm font-500 text-ink-800">
          CNPJs (um por linha)
        </label>
        <textarea
          id="cnpjs-lote"
          rows={6}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={"12.345.678/0001-90\n98.765.432/0001-10"}
          className="mt-2 w-full resize-y rounded-xl border border-slate-300 bg-white p-3.5 font-mono text-sm tnum text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500"
        />

        <p className="mt-2 flex items-start gap-2 text-xs text-slate-400">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span>
            Cada CNPJ avaliado consome uma consulta paga. O ranking abaixo lista do pior ao melhor
            score.
          </span>
        </p>

        <ErroConsulta error={avaliar.error} className="mt-4" />

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={submeter}
            disabled={cnpjs.length === 0 || avaliar.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-3 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
          >
            {avaliar.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Avaliando...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" /> Avaliar
              </>
            )}
          </button>
          {cnpjs.length > 0 && !avaliar.isPending && (
            <span className="text-sm text-slate-500">
              {cnpjs.length} CNPJ{cnpjs.length > 1 ? "s" : ""} na fila
            </span>
          )}
        </div>
      </section>

      {avaliar.isPending && (
        <EstadoCarregando texto="Consultando dados oficiais de cada fornecedor..." />
      )}

      {resposta && !avaliar.isPending && (
        <RankingDueDiligence
          resultados={resposta.resultados ?? []}
          avaliados={resposta.avaliados}
          tetoAtingido={resposta.teto_atingido}
        />
      )}
    </div>
  );
}

function RankingDueDiligence({ resultados, avaliados, tetoAtingido }) {
  if (resultados.length === 0) {
    return (
      <EstadoVazio
        Icone={ScanSearch}
        titulo="Nenhum fornecedor avaliado"
        descricao="Nenhum dos CNPJs informados pôde ser avaliado. Verifique os números e tente novamente."
      />
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-600 text-ink-900">
          Ranking de risco — {avaliados ?? resultados.length} avaliado
          {(avaliados ?? resultados.length) > 1 ? "s" : ""}
        </h3>
        <span className="text-xs text-slate-400">Do pior ao melhor score</span>
      </div>

      {tetoAtingido && <AvisoTeto />}

      <div className="grid gap-4">
        {resultados.map((f, i) => (
          <CardFornecedor key={`${f.cnpj}-${i}`} f={f} />
        ))}
      </div>
    </section>
  );
}

function CardFornecedor({ f }) {
  const faixa = faixaMeta(f.faixa, f.score);
  const cnd = statusCndMeta(f.status_cnd);
  const componentes = f.componentes ?? {};

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-panel transition-shadow hover:shadow-lift">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        {/* Score em destaque */}
        <div className="flex items-center gap-4 sm:flex-col sm:items-center sm:gap-1.5">
          <ScoreGauge score={f.score} faixa={f.faixa} />
          <span
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500 ${faixa.chip}`}
          >
            {faixa.rotulo}
          </span>
        </div>

        {/* Identificação */}
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-lg font-600 text-ink-900">
            {f.razao_social || "Razão social não informada"}
          </p>
          <p className="mt-0.5 font-mono tnum text-sm text-slate-500">{formatarCnpj(f.cnpj)}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {cnd && (
              <span
                className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500 ${cnd.classe}`}
              >
                CND: {cnd.rotulo}
              </span>
            )}
            {f.situacao_cadastral && (
              <span className="inline-flex items-center rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-xs font-500 text-slate-600">
                {f.situacao_cadastral}
              </span>
            )}
            {f.simples_optante != null && (
              <span className="inline-flex items-center rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-xs font-500 text-slate-600">
                {f.simples_optante ? "Optante do Simples" : "Não optante do Simples"}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Breakdown dos componentes do score */}
      {Object.keys(componentes).length > 0 && (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="text-[0.7rem] font-600 uppercase tracking-[0.12em] text-slate-400">
            Composição do score
          </p>
          <dl className="mt-2.5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {Object.entries(componentes).map(([chave, valor]) => (
              <div
                key={chave}
                className="rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2.5"
              >
                <dt className="truncate text-xs text-slate-500">
                  {ROTULO_COMPONENTE[chave] ?? chave}
                </dt>
                <dd className="tnum mt-0.5 font-display text-base font-600 text-ink-900">
                  {typeof valor === "number" ? `+${valor}` : String(valor)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </article>
  );
}

// ---- SEÇÃO 2: CARTEIRA MONITORADA -------------------------------------
function Carteira() {
  const queryClient = useQueryClient();
  const [novoCnpj, setNovoCnpj] = useState("");
  const [mostrarForm, setMostrarForm] = useState(false);

  const carteira = useQuery({ queryKey: ["m02", "monitorados"], queryFn: listarMonitorados });

  const adicionar = useMutation({
    mutationFn: () => monitorarCnpj(novoCnpj.trim()),
    onSuccess: () => {
      setNovoCnpj("");
      setMostrarForm(false);
      queryClient.invalidateQueries({ queryKey: ["m02", "monitorados"] });
    },
  });

  const reavaliar = useMutation({
    mutationFn: reavaliarCarteira,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["m02", "monitorados"] });
      queryClient.invalidateQueries({ queryKey: ["m02", "alertas"] });
    },
  });

  const monitorados = carteira.data ?? [];

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
              <ListChecks className="h-4 w-4" />
            </span>
            <h2 className="font-display text-lg font-600 text-ink-900">Carteira monitorada</h2>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => setMostrarForm((v) => !v)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50"
            >
              <Plus className="h-4 w-4" /> Adicionar CNPJ
            </button>
            <button
              type="button"
              onClick={() => reavaliar.mutate()}
              disabled={reavaliar.isPending || monitorados.length === 0}
              className="inline-flex items-center gap-2 rounded-xl bg-jade-600 px-4 py-2.5 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
            >
              {reavaliar.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Reavaliando...
                </>
              ) : (
                <>
                  <RotateCcw className="h-4 w-4" /> Reavaliar agora
                </>
              )}
            </button>
          </div>
        </div>

        {mostrarForm && (
          <div className="mt-4 flex flex-col gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label htmlFor="novo-cnpj" className="mb-1.5 block text-sm font-500 text-ink-800">
                CNPJ a monitorar
              </label>
              <input
                id="novo-cnpj"
                type="text"
                value={novoCnpj}
                onChange={(e) => setNovoCnpj(e.target.value)}
                placeholder="12.345.678/0001-90"
                className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 font-mono text-sm tnum text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500"
              />
            </div>
            <button
              type="button"
              onClick={() => adicionar.mutate()}
              disabled={!novoCnpj.trim() || adicionar.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink-900 px-5 py-2.5 text-sm font-600 text-white transition-colors hover:bg-ink-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {adicionar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {adicionar.isPending ? "Avaliando..." : "Adicionar e avaliar"}
            </button>
          </div>
        )}

        <p className="mt-3 flex items-start gap-2 text-xs text-slate-400">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
          <span>
            Adicionar e reavaliar consomem consultas pagas. A reavaliação re-consulta toda a carteira
            e pode demorar.
          </span>
        </p>

        <ErroConsulta error={adicionar.error} className="mt-4" />
        <ErroConsulta error={reavaliar.error} className="mt-4" />
        {reavaliar.data?.teto_atingido && <AvisoTeto className="mt-4" />}
      </section>

      {carteira.isError ? (
        <ErroConsulta error={carteira.error} />
      ) : carteira.isLoading ? (
        <EstadoCarregando texto="Carregando a carteira monitorada..." />
      ) : monitorados.length === 0 ? (
        <EstadoVazio
          Icone={Building2}
          titulo="Nenhum fornecedor monitorado ainda"
          descricao="Adicione um CNPJ para começar a acompanhar a saúde fiscal ao longo do tempo. A cada reavaliação, o sistema atualiza o score e gera alertas de mudança."
        />
      ) : (
        <TabelaCarteira monitorados={monitorados} />
      )}
    </div>
  );
}

function TabelaCarteira({ monitorados }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="border-b border-slate-100 px-5 py-3.5">
        <h3 className="text-sm font-600 text-ink-900">
          {monitorados.length} fornecedor{monitorados.length > 1 ? "es" : ""} na carteira
        </h3>
      </div>
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-500">Score</th>
              <th className="px-5 py-3 font-500">Fornecedor</th>
              <th className="px-5 py-3 font-500">CND</th>
              <th className="px-5 py-3 font-500">Última consulta</th>
            </tr>
          </thead>
          <tbody>
            {monitorados.map((m) => {
              const cnd = statusCndMeta(m.status_cnd_atual);
              return (
                <tr
                  key={m.id}
                  className="border-b border-slate-50 last:border-0 transition-colors hover:bg-slate-50/60"
                >
                  <td className="px-5 py-3.5">
                    <ScoreGauge score={m.score_atual} tamanho="sm" />
                  </td>
                  <td className="px-5 py-3.5">
                    <p className="font-500 text-ink-900">{m.razao_social || "—"}</p>
                    <p className="font-mono tnum text-xs text-slate-500">{formatarCnpj(m.cnpj)}</p>
                  </td>
                  <td className="px-5 py-3.5">
                    {cnd ? (
                      <span
                        className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500 ${cnd.classe}`}
                      >
                        {cnd.rotulo}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-slate-500">
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-slate-400" />
                      {formatarData(m.ultima_consulta)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---- SEÇÃO 3: ALERTAS -------------------------------------------------
function Alertas() {
  const alertas = useQuery({ queryKey: ["m02", "alertas"], queryFn: listarAlertas });
  const lista = alertas.data ?? [];

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
            <BellRing className="h-4 w-4" />
          </span>
          <h2 className="font-display text-lg font-600 text-ink-900">Alertas da carteira</h2>
        </div>
        <p className="mt-2 text-sm text-slate-500">
          Mudanças de status fiscal, scores críticos e indícios de devedor contumaz detectados nas
          reavaliações.
        </p>
      </section>

      {alertas.isError ? (
        <ErroConsulta error={alertas.error} />
      ) : alertas.isLoading ? (
        <EstadoCarregando texto="Carregando alertas..." />
      ) : lista.length === 0 ? (
        <EstadoVazio
          Icone={Inbox}
          titulo="Nenhum alerta no momento"
          descricao="Quando uma reavaliação detectar mudança de status, score crítico ou devedor contumaz, o alerta aparece aqui."
        />
      ) : (
        <ul className="space-y-3">
          {lista.map((a) => (
            <CardAlerta key={a.id} a={a} />
          ))}
        </ul>
      )}
    </div>
  );
}

function CardAlerta({ a }) {
  const meta = alertaMeta(a.tipo);
  return (
    <li
      className={[
        "flex items-start gap-3.5 rounded-2xl border bg-white p-4 shadow-panel transition-shadow hover:shadow-lift",
        a.lido ? "border-slate-200" : "border-slate-300",
      ].join(" ")}
    >
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-50 text-ink-700">
        <ShieldAlert className="h-[1.1rem] w-[1.1rem]" strokeWidth={2.1} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-500 ${meta.classe}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${meta.ponto}`} />
            {meta.rotulo}
          </span>
          {!a.lido && (
            <span className="inline-flex items-center rounded-full bg-jade-500/10 px-2 py-0.5 text-[0.65rem] font-600 uppercase tracking-wide text-jade-700">
              Novo
            </span>
          )}
        </div>
        <p className="mt-1.5 text-sm text-ink-800">{a.mensagem}</p>
        <p className="mt-1 text-xs text-slate-400">{formatarData(a.criado_em)}</p>
      </div>
    </li>
  );
}

// ---- AUXILIARES COMPARTILHADOS ----------------------------------------

// Extrai a mensagem amigável de erro. Trata o caso do token da API paga ausente.
function mensagemErro(error) {
  const detalhe = error?.response?.data?.detail ?? error?.message ?? "";
  if (typeof detalhe === "string" && detalhe.toUpperCase().includes("INFOSIMPLES_TOKEN")) {
    return "A consulta paga não está configurada no servidor. Avise o responsável técnico para habilitar o acesso à fonte de dados oficial.";
  }
  return detalhe || "Não foi possível concluir a operação. Tente novamente.";
}

function ErroConsulta({ error, className = "" }) {
  if (!error) return null;
  return (
    <div
      className={`flex items-start gap-2.5 rounded-xl border border-signal-200 bg-signal-50 p-3.5 text-sm text-signal-700 ${className}`}
      role="alert"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{mensagemErro(error)}</span>
    </div>
  );
}

function AvisoTeto({ className = "" }) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-700 ${className}`}
      role="status"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>
        O teto de consultas pagas foi atingido. Parte dos fornecedores pode não ter sido avaliada
        nesta rodada.
      </span>
    </div>
  );
}

function EstadoCarregando({ texto }) {
  return (
    <div className="grid place-items-center rounded-2xl border border-slate-200 bg-white py-16 shadow-panel">
      <Loader2 className="h-7 w-7 animate-spin text-slate-300" />
      <p className="mt-3 text-sm text-slate-500">{texto}</p>
    </div>
  );
}

function EstadoVazio({ Icone, titulo, descricao }) {
  return (
    <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white/60 py-16 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Icone className="h-6 w-6" />
      </span>
      <p className="mt-4 text-sm font-500 text-ink-800">{titulo}</p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">{descricao}</p>
    </div>
  );
}

// Data legível em pt-BR; tolera valor ausente ou inválido.
function formatarData(valor) {
  if (!valor) return "—";
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return String(valor);
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
