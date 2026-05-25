import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Wallet,
  Coins,
  PlusCircle,
  Receipt,
  Loader2,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Inbox,
  CalendarRange,
  Building2,
  FileText,
} from "lucide-react";
import { getSaldo, recarregar, getHistorico } from "../services/api.js";
import { moeda, moedaPreciso, numero } from "../utils/format.js";
import {
  QUERY_SALDO,
  SERVICO,
  reaisParaCentavos,
  precoPorCreditoParaCentavos,
} from "../utils/custos.js";

// Metadados de apresentação por serviço pago.
const SERVICOS = [
  {
    id: SERVICO.CADASTRO, // "cnpj"
    nome: "CNPJá",
    descricao: "Dados cadastrais e Simples Nacional",
    Icone: Building2,
  },
  {
    id: SERVICO.CND, // "cnd"
    nome: "Infosimples (CND)",
    descricao: "Certidão de regularidade fiscal",
    Icone: FileText,
  },
];

const NOME_SERVICO = { [SERVICO.CADASTRO]: "CNPJá", [SERVICO.CND]: "Infosimples (CND)" };

const ROTULO_OPERACAO = {
  enriquecimento: "Enriquecimento de CNPJ",
  cnd_lote: "CND em lote",
  due_diligence: "Due diligence",
  avaliacao_individual: "Avaliação individual",
  reavaliacao: "Reavaliação da carteira",
};

const ROTULO_MODULO = { modulo01: "Módulo 01", modulo02: "Módulo 02" };

// Consumo & custos: visão transversal do gasto nas APIs pagas.
// Saldo por controle interno (recarga manual) + histórico persistente.
export default function Consumo() {
  const saldo = useQuery({ queryKey: QUERY_SALDO, queryFn: getSaldo });

  return (
    <div className="space-y-6 animate-fade-up">
      <Cabecalho />

      <SecaoSaldo saldo={saldo} />
      <SecaoRecarga />
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
          Consumo &amp; custos
        </h1>
        <p className="mt-1 max-w-xl text-sm text-slate-500">
          Acompanhe o saldo das APIs pagas e o histórico de consultas. O saldo é por controle
          interno: você registra quanto comprou e o sistema desconta o consumo real de cada pesquisa.
        </p>
      </div>
    </div>
  );
}

// ---- SALDO POR SERVIÇO ------------------------------------------------
function SecaoSaldo({ saldo }) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
          <Coins className="h-4 w-4" />
        </span>
        <h2 className="font-display text-lg font-600 text-ink-900">Saldo por serviço</h2>
      </div>

      {saldo.isError ? (
        <ErroConsulta error={saldo.error} />
      ) : saldo.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <CardSaldoEsqueleto />
          <CardSaldoEsqueleto />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {SERVICOS.map((s) => {
            const item = (saldo.data?.itens ?? []).find((i) => i.servico === s.id) ?? null;
            return <CardSaldo key={s.id} meta={s} item={item} />;
          })}
        </div>
      )}
    </section>
  );
}

function CardSaldo({ meta, item }) {
  const comprados = Math.trunc(Number(item?.creditos_comprados) || 0);
  const consumidos = Math.trunc(Number(item?.creditos_consumidos) || 0);
  const restantes = Math.trunc(Number(item?.creditos_restantes) || 0);
  // preco_por_credito vem como string decimal EM CENTAVOS (ex "2.499"). Para
  // exibir em reais por crédito, divide por 100 e mantém casas (fração de centavo).
  const precoCreditoCent = precoPorCreditoParaCentavos(item?.preco_por_credito);
  const custoRestanteCent = Math.max(0, Math.trunc(Number(item?.custo_restante_centavos) || 0));

  const semConfig = comprados <= 0;
  const negativo = restantes < 0;
  const zerado = !semConfig && restantes === 0;

  // Tom do estado: verde saudável, âmbar zerado, vermelho negativo, neutro sem config.
  const tom = semConfig
    ? { card: "border-slate-200", anel: "text-slate-400", valor: "text-ink-900", chip: null }
    : negativo
      ? {
          card: "border-signal-200 bg-signal-50/40",
          anel: "text-signal-500",
          valor: "text-signal-700",
          chip: { classe: "bg-signal-50 text-signal-700 border-signal-200", Icone: AlertTriangle, texto: "Saldo negativo" },
        }
      : zerado
        ? {
            card: "border-amber-200 bg-amber-50/40",
            anel: "text-amber-500",
            valor: "text-amber-700",
            chip: { classe: "bg-amber-50 text-amber-700 border-amber-200", Icone: AlertTriangle, texto: "Saldo zerado" },
          }
        : {
            card: "border-slate-200",
            anel: "text-jade-500",
            valor: "text-jade-700",
            chip: { classe: "bg-jade-50 text-jade-700 border-jade-200", Icone: CheckCircle2, texto: "Saldo disponível" },
          };

  return (
    <article className={`rounded-2xl border bg-white p-5 shadow-panel ${tom.card}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-50 ${tom.anel}`}>
            <meta.Icone className="h-[1.1rem] w-[1.1rem]" strokeWidth={2.1} />
          </span>
          <div>
            <p className="font-display text-base font-600 text-ink-900">{meta.nome}</p>
            <p className="text-xs text-slate-500">{meta.descricao}</p>
          </div>
        </div>
        {tom.chip && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-500 ${tom.chip.classe}`}
          >
            <tom.chip.Icone className="h-3.5 w-3.5" />
            {tom.chip.texto}
          </span>
        )}
      </div>

      {semConfig ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/60 px-4 py-3.5 text-sm text-slate-500">
          Nenhuma recarga registrada para este serviço. Use o formulário abaixo para informar quanto
          você comprou.
        </div>
      ) : (
        <>
          <div className="mt-4 flex items-baseline gap-2">
            <span className={`tnum font-display text-3xl font-600 ${tom.valor}`}>
              {numero(restantes)}
            </span>
            <span className="text-sm text-slate-500">
              crédito{restantes === 1 ? "" : "s"} restante{restantes === 1 ? "" : "s"}
            </span>
          </div>
          <p className="tnum mt-0.5 text-sm text-slate-500">
            Custo restante: <strong className={tom.valor}>{moeda(custoRestanteCent / 100)}</strong>
          </p>

          <dl className="mt-4 grid grid-cols-3 gap-2.5 border-t border-slate-100 pt-4 text-center">
            <Metrica rotulo="Comprados" valor={numero(comprados)} />
            <Metrica rotulo="Consumidos" valor={numero(consumidos)} />
            <Metrica rotulo="Preço/crédito" valor={moedaPreciso(precoCreditoCent / 100)} />
          </dl>
        </>
      )}
    </article>
  );
}

function Metrica({ rotulo, valor }) {
  return (
    <div>
      <dt className="text-[0.7rem] font-600 uppercase tracking-wide text-slate-400">{rotulo}</dt>
      <dd className="tnum mt-0.5 text-sm font-500 text-ink-900">{valor}</dd>
    </div>
  );
}

function CardSaldoEsqueleto() {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel">
      <div className="flex items-center gap-2.5">
        <div className="h-9 w-9 rounded-xl bg-slate-100" />
        <div className="space-y-1.5">
          <div className="h-3.5 w-24 rounded bg-slate-100" />
          <div className="h-2.5 w-36 rounded bg-slate-50" />
        </div>
      </div>
      <div className="mt-4 h-8 w-28 rounded bg-slate-100" />
      <div className="mt-3 grid grid-cols-3 gap-2.5 border-t border-slate-100 pt-4">
        <div className="h-8 rounded bg-slate-50" />
        <div className="h-8 rounded bg-slate-50" />
        <div className="h-8 rounded bg-slate-50" />
      </div>
    </div>
  );
}

// ---- RECARGA (registro de compra de créditos) -------------------------
function SecaoRecarga() {
  const queryClient = useQueryClient();
  const [servico, setServico] = useState(SERVICO.CADASTRO);
  const [creditos, setCreditos] = useState("");
  const [valorTexto, setValorTexto] = useState("");

  // A recarga é por VALOR TOTAL PAGO pelo pacote (não por preço unitário): o
  // crédito custa fração de centavo e não cabe em centavo inteiro. O valor do
  // pacote é exato e é como a compra realmente acontece.
  const valorTotalCent = reaisParaCentavos(valorTexto);
  const qtd = Math.max(0, Math.trunc(Number(creditos) || 0));
  // Preço por crédito derivado, só para feedback (em reais/crédito). Mantém a
  // fração de centavo dividindo o valor total pela quantidade.
  const precoCreditoReais = qtd > 0 ? valorTotalCent / 100 / qtd : 0;
  const valido = qtd > 0 && valorTotalCent > 0;

  const recarga = useMutation({
    mutationFn: () =>
      recarregar({ servico, creditos: qtd, valor_total_centavos: valorTotalCent }),
    onSuccess: () => {
      setCreditos("");
      setValorTexto("");
      // Invalida o saldo: cards e SaldoInline (M01/M02) refletem a compra na hora.
      queryClient.invalidateQueries({ queryKey: QUERY_SALDO });
    },
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
      <div className="flex items-center gap-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-900 text-jade-400">
          <PlusCircle className="h-4 w-4" />
        </span>
        <h2 className="font-display text-lg font-600 text-ink-900">Registrar recarga</h2>
      </div>
      <p className="mt-1.5 text-sm text-slate-500">
        Informe quantos créditos você comprou e o valor total pago pelo pacote. As recargas acumulam
        e definem o preço real por crédito usado nas estimativas de custo. Ex: 1.000 créditos por
        R$ 24,99.
      </p>

      <form
        className="mt-4 grid gap-3.5 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (valido) recarga.mutate();
        }}
      >
        <div>
          <label htmlFor="recarga-servico" className="mb-1.5 block text-sm font-500 text-ink-800">
            Serviço
          </label>
          <select
            id="recarga-servico"
            value={servico}
            onChange={(e) => setServico(e.target.value)}
            className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-ink-900 transition-colors focus:border-jade-500"
          >
            {SERVICOS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nome}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="recarga-creditos" className="mb-1.5 block text-sm font-500 text-ink-800">
            Créditos comprados
          </label>
          <input
            id="recarga-creditos"
            type="text"
            inputMode="numeric"
            value={creditos}
            onChange={(e) => setCreditos(e.target.value.replace(/[^\d]/g, ""))}
            placeholder="1000"
            aria-describedby="recarga-exemplo"
            className="w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm tnum text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500"
          />
        </div>

        <div>
          <label htmlFor="recarga-valor" className="mb-1.5 block text-sm font-500 text-ink-800">
            Valor total pago (R$)
          </label>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">
              R$
            </span>
            <input
              id="recarga-valor"
              type="text"
              inputMode="decimal"
              value={valorTexto}
              onChange={(e) => setValorTexto(e.target.value)}
              placeholder="24,99"
              aria-describedby="recarga-exemplo"
              className="w-full rounded-xl border border-slate-300 bg-white py-2.5 pl-9 pr-3.5 text-sm tnum text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500"
            />
          </div>
        </div>

        <div className="sm:col-span-3 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={!valido || recarga.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-2.5 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
          >
            {recarga.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Registrando...
              </>
            ) : (
              <>
                <PlusCircle className="h-4 w-4" /> Registrar recarga
              </>
            )}
          </button>
          {valido && !recarga.isPending ? (
            <span className="text-sm text-slate-500">
              {numero(qtd)} créditos por{" "}
              <strong className="tnum text-ink-700">{moeda(valorTotalCent / 100)}</strong> ≈{" "}
              <span className="tnum">{moedaPreciso(precoCreditoReais)}</span>/crédito
            </span>
          ) : (
            <span id="recarga-exemplo" className="text-sm text-slate-400">
              Ex: 1.000 créditos por R$ 24,99.
            </span>
          )}
        </div>
      </form>

      <ErroConsulta error={recarga.error} className="mt-4" />
      {recarga.isSuccess && (
        <div
          className="mt-4 flex items-start gap-2.5 rounded-xl border border-jade-200 bg-jade-50 p-3.5 text-sm text-jade-700"
          role="status"
        >
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Recarga registrada. O saldo foi atualizado.</span>
        </div>
      )}
    </section>
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
