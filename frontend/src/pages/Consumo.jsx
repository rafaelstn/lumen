import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Wallet,
  Receipt,
  Loader2,
  AlertCircle,
  Inbox,
  CalendarRange,
} from "lucide-react";
import { getHistorico } from "../services/api.js";
import { moeda, numero } from "../utils/format.js";
import { SERVICO } from "../utils/custos.js";

const NOME_SERVICO = {
  [SERVICO.CADASTRO]: "Consulta cadastral",
  [SERVICO.CND]: "Certidão de regularidade (CND)",
};

const ROTULO_OPERACAO = {
  enriquecimento: "Enriquecimento de CNPJ",
  cnd_lote: "CND em lote",
  due_diligence: "Due diligence",
  avaliacao_individual: "Avaliação individual",
  reavaliacao: "Reavaliação da carteira",
};

const ROTULO_MODULO = { modulo01: "Módulo 01", modulo02: "Módulo 02" };

// Histórico de consumo e custos: visão transversal do gasto real nas APIs pagas
// (CNPJá, Infosimples) por pesquisa. O controle de saldo/recarga foi removido (o
// saldo real é acompanhado direto no painel do provedor); aqui fica só o que o
// sistema registra de forma confiável: cada consulta paga, com data, custo e
// quantidade, agregada por período e por mês.
export default function Consumo() {
  return (
    <div className="space-y-6 animate-fade-up">
      <Cabecalho />
      <SecaoHistorico />
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
          Histórico de consumo &amp; custos
        </h1>
        <p className="mt-1 max-w-xl text-sm text-slate-500">
          Acompanhe o gasto real nas APIs pagas por pesquisa. Cada consulta feita no Módulo 01 ou 02
          é registrada aqui com data, custo e quantidade, com totais por período e por mês.
        </p>
      </div>
    </div>
  );
}

// ---- HISTÓRICO --------------------------------------------------------
function SecaoHistorico() {
  // Filtro de período opcional (datas YYYY-MM-DD do <input type=date>).
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");

  const historico = useQuery({
    queryKey: ["consultas", "historico", inicio || null, fim || null],
    queryFn: () => getHistorico({ inicio: inicio || undefined, fim: fim || undefined }),
    keepPreviousData: true,
  });

  const dados = historico.data;
  const itens = dados?.itens ?? [];
  const totais = dados?.totais ?? { creditos_consumidos: 0, custo_centavos: 0 };
  const porMes = dados?.por_mes ?? [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
            <Receipt className="h-4 w-4" />
          </span>
          <h2 className="font-display text-lg font-600 text-ink-900">Histórico de consultas</h2>
        </div>
        <FiltroPeriodo
          inicio={inicio}
          fim={fim}
          onInicio={setInicio}
          onFim={setFim}
          onLimpar={() => {
            setInicio("");
            setFim("");
          }}
        />
      </div>

      {/* Totais acumulados */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <CardTotal
          rotulo="Gasto no período"
          valor={moeda(Math.max(0, Math.trunc(Number(totais.custo_centavos) || 0)) / 100)}
          sublabel={`${numero(totais.creditos_consumidos)} créditos consumidos`}
          destaque
        />
        <CardTotal
          rotulo="Consultas registradas"
          valor={numero(itens.length)}
          sublabel="lançamentos no período"
        />
        {porMes.length > 0 && (
          <CardTotal
            rotulo="Mês mais recente"
            valor={moeda(
              Math.max(0, Math.trunc(Number(porMes[porMes.length - 1]?.custo_centavos) || 0)) / 100
            )}
            sublabel={porMes[porMes.length - 1]?.periodo ?? "—"}
          />
        )}
      </div>

      {porMes.length > 0 && <ResumoPorMes porMes={porMes} />}

      {historico.isError ? (
        <ErroConsulta error={historico.error} />
      ) : historico.isLoading ? (
        <EstadoCarregando texto="Carregando histórico de consultas..." />
      ) : itens.length === 0 ? (
        <EstadoVazio
          Icone={Inbox}
          titulo="Nenhuma consulta no período"
          descricao={
            inicio || fim
              ? "Não há consultas pagas registradas nesse intervalo. Ajuste o período ou limpe o filtro."
              : "Assim que você fizer pesquisas pagas no Módulo 01 ou 02, elas aparecem aqui com data, custo e quantidade."
          }
        />
      ) : (
        <TabelaHistorico itens={itens} />
      )}
    </section>
  );
}

function FiltroPeriodo({ inicio, fim, onInicio, onFim, onLimpar }) {
  return (
    <div className="flex flex-wrap items-end gap-2.5">
      <div>
        <label htmlFor="hist-inicio" className="mb-1 block text-[0.7rem] font-500 text-slate-500">
          De
        </label>
        <input
          id="hist-inicio"
          type="date"
          value={inicio}
          max={fim || undefined}
          onChange={(e) => onInicio(e.target.value)}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900 transition-colors focus:border-jade-500"
        />
      </div>
      <div>
        <label htmlFor="hist-fim" className="mb-1 block text-[0.7rem] font-500 text-slate-500">
          Até
        </label>
        <input
          id="hist-fim"
          type="date"
          value={fim}
          min={inicio || undefined}
          onChange={(e) => onFim(e.target.value)}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-ink-900 transition-colors focus:border-jade-500"
        />
      </div>
      {(inicio || fim) && (
        <button
          type="button"
          onClick={onLimpar}
          className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-500 text-ink-700 transition-colors hover:bg-slate-50"
        >
          Limpar
        </button>
      )}
    </div>
  );
}

function CardTotal({ rotulo, valor, sublabel, destaque = false }) {
  return (
    <div
      className={[
        "rounded-2xl border px-5 py-4 shadow-panel",
        destaque ? "border-jade-200 bg-jade-50" : "border-slate-200 bg-white",
      ].join(" ")}
    >
      <p className="text-[0.7rem] font-600 uppercase tracking-wide text-slate-500">{rotulo}</p>
      <p
        className={[
          "tnum mt-1 font-display text-2xl font-600",
          destaque ? "text-jade-700" : "text-ink-900",
        ].join(" ")}
      >
        {valor}
      </p>
      <p className="mt-0.5 text-xs text-slate-400">{sublabel}</p>
    </div>
  );
}

function ResumoPorMes({ porMes }) {
  const maxCent = Math.max(
    1,
    ...porMes.map((m) => Math.max(0, Math.trunc(Number(m.custo_centavos) || 0)))
  );
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
      <div className="flex items-center gap-2.5">
        <CalendarRange className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-600 text-ink-900">Gasto por mês</h3>
      </div>
      <ul className="mt-3.5 space-y-2.5">
        {porMes.map((m) => {
          const cent = Math.max(0, Math.trunc(Number(m.custo_centavos) || 0));
          const pct = Math.round((cent / maxCent) * 100);
          return (
            <li key={m.periodo} className="flex items-center gap-3">
              <span className="tnum w-20 shrink-0 text-xs text-slate-500">{m.periodo}</span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                <span
                  className="block h-full rounded-full bg-jade-500"
                  style={{ width: `${pct}%` }}
                />
              </span>
              <span className="tnum w-24 shrink-0 text-right text-sm font-500 text-ink-900">
                {moeda(cent / 100)}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function TabelaHistorico({ itens }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="border-b border-slate-100 px-5 py-3.5">
        <h3 className="text-sm font-600 text-ink-900">
          {numero(itens.length)} consulta{itens.length === 1 ? "" : "s"} no período
        </h3>
      </div>
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-500">Data</th>
              <th className="px-5 py-3 font-500">Módulo</th>
              <th className="px-5 py-3 font-500">Serviço</th>
              <th className="px-5 py-3 font-500">Operação</th>
              <th className="px-5 py-3 text-right font-500">Qtd.</th>
              <th className="px-5 py-3 text-right font-500">Créditos</th>
              <th className="px-5 py-3 text-right font-500">Custo</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((it) => (
              <tr
                key={it.id}
                className="border-b border-slate-50 last:border-0 transition-colors hover:bg-slate-50/60"
              >
                <td className="whitespace-nowrap px-5 py-3.5 text-slate-600">
                  {formatarDataHora(it.criado_em)}
                </td>
                <td className="px-5 py-3.5 text-slate-600">
                  {ROTULO_MODULO[it.modulo] ?? it.modulo ?? "—"}
                </td>
                <td className="px-5 py-3.5 text-slate-600">
                  {NOME_SERVICO[it.servico] ?? it.servico ?? "—"}
                </td>
                <td className="px-5 py-3.5">
                  <span className="inline-flex items-center gap-2">
                    <span className="text-ink-800">
                      {ROTULO_OPERACAO[it.operacao] ?? it.operacao ?? "—"}
                    </span>
                    {it.consumo_estimado && (
                      <span
                        className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[0.65rem] font-600 uppercase tracking-wide text-amber-700"
                        title="Consumo estimado: o custo real pode variar conforme cache ou resposta da API"
                      >
                        <AlertCircle className="h-3 w-3" /> estimado
                      </span>
                    )}
                  </span>
                </td>
                <td className="tnum px-5 py-3.5 text-right text-slate-600">
                  {numero(it.quantidade)}
                </td>
                <td className="tnum px-5 py-3.5 text-right text-slate-600">
                  {numero(it.creditos_consumidos)}
                </td>
                <td className="tnum px-5 py-3.5 text-right font-500 text-ink-900">
                  {moeda(Math.max(0, Math.trunc(Number(it.custo_centavos) || 0)) / 100)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---- AUXILIARES -------------------------------------------------------
function mensagemErro(error) {
  const detalhe = error?.response?.data?.detail ?? error?.message ?? "";
  return (
    (typeof detalhe === "string" && detalhe) ||
    "Não foi possível concluir a operação. Tente novamente."
  );
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

function formatarDataHora(valor) {
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
