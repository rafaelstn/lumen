import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  History,
  Building2,
  Calendar,
  Users,
  Clock,
  FolderOpen,
  Trash2,
  Loader2,
  AlertCircle,
  RotateCcw,
} from "lucide-react";
import { listarAnalises, apagarAnalise } from "../services/api.js";
import { numero, dataHora } from "../utils/format.js";

const QUERY_KEY = ["m01", "analises"];

// Histórico de acesso rápido: lista análises já processadas para reabrir sem
// re-subir a planilha. Renderizado abaixo do card de upload (estado !resultado).
// Cobre carregando, vazio, erro. O reabrir é delegado ao pai via onAbrir(id);
// o estado de loading do reabrir vem de abrindoId (id em processo) para travar
// só o item clicado.
export default function HistoricoAnalises({ onAbrir, abrindoId }) {
  const queryClient = useQueryClient();
  const [confirmandoId, setConfirmandoId] = useState(null);

  const {
    data: analises,
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: QUERY_KEY,
    queryFn: listarAnalises,
  });

  const apagar = useMutation({
    mutationFn: apagarAnalise,
    onSuccess: () => {
      setConfirmandoId(null);
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });

  return (
    <section
      className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6"
      aria-labelledby="historico-titulo"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-ink-700">
            <History className="h-4 w-4" />
          </span>
          <h2 id="historico-titulo" className="font-display text-lg font-600 text-ink-900">
            Análises recentes
          </h2>
        </div>
        {isFetching && !isLoading && (
          <Loader2 className="h-4 w-4 animate-spin text-slate-300" aria-hidden="true" />
        )}
      </div>

      <div className="mt-4">
        {isLoading ? (
          <ListaEsqueleto />
        ) : isError ? (
          <div
            className="flex flex-col items-start gap-3 rounded-xl border border-signal-200 bg-signal-50 p-4 text-sm text-signal-700"
            role="alert"
          >
            <span className="flex items-start gap-2.5">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              Não foi possível carregar o histórico de análises.
            </span>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-signal-300 px-3 py-1.5 text-xs font-500 text-signal-700 transition-colors hover:bg-signal-100"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Tentar de novo
            </button>
          </div>
        ) : !analises?.length ? (
          <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-8 text-center text-sm text-slate-500">
            Nenhuma análise salva ainda. As análises processadas aparecem aqui para reabrir sem
            subir a planilha de novo.
          </p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {analises.map((a) => (
              <ItemAnalise
                key={a.id}
                analise={a}
                abrindo={abrindoId === a.id}
                abrindoOutro={abrindoId != null && abrindoId !== a.id}
                confirmando={confirmandoId === a.id}
                apagando={apagar.isPending && apagar.variables === a.id}
                erroApagar={
                  apagar.isError && apagar.variables === a.id
                    ? apagar.error?.response?.data?.detail ?? "Falha ao apagar."
                    : null
                }
                onAbrir={() => onAbrir(a.id)}
                onPedirApagar={() => setConfirmandoId(a.id)}
                onConfirmarApagar={() => apagar.mutate(a.id)}
                onCancelarApagar={() => setConfirmandoId(null)}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function ItemAnalise({
  analise,
  abrindo,
  abrindoOutro,
  confirmando,
  apagando,
  erroApagar,
  onAbrir,
  onPedirApagar,
  onConfirmarApagar,
  onCancelarApagar,
}) {
  const { cliente, periodo, total_fornecedores, atualizado_em, criado_em } = analise;

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-slate-300">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="flex items-center gap-2 truncate font-600 text-ink-900">
            <Building2 className="h-4 w-4 shrink-0 text-jade-600" strokeWidth={1.8} aria-hidden="true" />
            <span className="truncate">{cliente ?? "Cliente sem nome"}</span>
          </p>
          <dl className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
            <Meta Icone={Calendar} rotulo="Período" valor={periodo ?? "—"} />
            <Meta Icone={Users} rotulo="Fornecedores" valor={numero(total_fornecedores)} />
            <Meta Icone={Clock} rotulo="Atualizada em" valor={dataHora(atualizado_em ?? criado_em)} />
          </dl>
        </div>

        {confirmando ? (
          <div className="flex shrink-0 flex-col gap-2 sm:items-end">
            <p className="text-xs text-slate-500 sm:text-right">Apagar esta análise do histórico?</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onConfirmarApagar}
                disabled={apagando}
                className="inline-flex items-center gap-1.5 rounded-lg bg-signal-600 px-3 py-1.5 text-xs font-600 text-white transition-colors hover:bg-signal-700 disabled:opacity-50"
              >
                {apagando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                {apagando ? "Apagando..." : "Sim, apagar"}
              </button>
              <button
                type="button"
                onClick={onCancelarApagar}
                disabled={apagando}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-500 text-ink-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={onAbrir}
              disabled={abrindo || abrindoOutro}
              className="inline-flex items-center gap-1.5 rounded-lg bg-jade-600 px-3.5 py-2 text-sm font-600 text-white transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {abrindo ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderOpen className="h-4 w-4" />}
              {abrindo ? "Abrindo..." : "Abrir"}
            </button>
            <button
              type="button"
              onClick={onPedirApagar}
              disabled={abrindo || abrindoOutro}
              aria-label={`Apagar análise de ${cliente ?? "cliente sem nome"}`}
              className="inline-flex items-center justify-center rounded-lg border border-slate-300 px-2.5 py-2 text-slate-500 transition-colors hover:border-signal-300 hover:bg-signal-50 hover:text-signal-600 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {erroApagar && (
        <p className="mt-2.5 flex items-center gap-1.5 text-xs text-signal-700" role="alert">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {erroApagar}
        </p>
      )}
    </li>
  );
}

function Meta({ Icone, rotulo, valor }) {
  return (
    <span className="flex items-center gap-1.5">
      <Icone className="h-3.5 w-3.5 text-slate-400" strokeWidth={1.8} aria-hidden="true" />
      <span className="sr-only">{rotulo}:</span>
      <span className="tnum">{valor}</span>
    </span>
  );
}

function ListaEsqueleto() {
  return (
    <ul className="flex flex-col gap-2.5" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <li key={i} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between gap-4">
            <div className="w-full space-y-2">
              <div className="h-4 w-40 animate-pulse rounded bg-slate-100" />
              <div className="h-3 w-60 animate-pulse rounded bg-slate-100" />
            </div>
            <div className="h-9 w-20 shrink-0 animate-pulse rounded-lg bg-slate-100" />
          </div>
        </li>
      ))}
    </ul>
  );
}
