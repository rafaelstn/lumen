import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Search, Database, Loader2, AlertCircle, Building2 } from "lucide-react";
import { buscarFornecedores } from "../services/api.js";

// Formata CNPJ (14 dígitos) no padrão 00.000.000/0000-00; se não bater, devolve cru.
function formatarCnpj(valor) {
  const so = String(valor ?? "").replace(/\D/g, "");
  if (so.length !== 14) return valor ?? "—";
  return so.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

const ROTULO_ORIGEM = {
  manual: { texto: "Manual", classe: "bg-amber-50 text-amber-700 border-amber-200" },
  enriquecimento: { texto: "Automático", classe: "bg-jade-50 text-jade-700 border-jade-200" },
  api: { texto: "API", classe: "bg-jade-50 text-jade-700 border-jade-200" },
};

function origemMeta(origem) {
  return (
    ROTULO_ORIGEM[origem] ?? {
      texto: origem || "—",
      classe: "bg-slate-100 text-slate-600 border-slate-300",
    }
  );
}

// Banco de fornecedores: busca gratuita no cache local (CNPJ ↔ razão social).
// Não consome créditos da API paga.
export default function BancoFornecedores() {
  const [termo, setTermo] = useState("");
  const [buscou, setBuscou] = useState(false);

  const busca = useMutation({
    mutationFn: (q) => buscarFornecedores(q),
    onSettled: () => setBuscou(true),
  });

  const resultados = busca.data ?? [];

  function submeter(e) {
    e.preventDefault();
    busca.mutate(termo.trim());
  }

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Cabeçalho da view */}
      <div className="flex items-start gap-3.5">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-ink-900 text-jade-400">
          <Database className="h-5 w-5" />
        </span>
        <div>
          <h1 className="font-display text-2xl font-600 tracking-tight text-ink-900">
            Banco de fornecedores
          </h1>
          <p className="mt-1 max-w-xl text-sm text-slate-500">
            Cache local de CNPJ e razão social, alimentado conforme você resolve os fornecedores nas
            análises. A busca é gratuita e não consome créditos da API.
          </p>
        </div>
      </div>

      {/* Busca */}
      <form
        onSubmit={submeter}
        className="rounded-2xl border border-slate-200 bg-white p-4 shadow-panel sm:p-5"
      >
        <label htmlFor="busca-forn" className="mb-2 block text-sm font-500 text-ink-800">
          Buscar por CNPJ ou razão social
        </label>
        <div className="flex flex-col gap-2.5 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              id="busca-forn"
              type="text"
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              placeholder="Ex.: 12.345.678/0001-90 ou Comercial Aurora"
              className="w-full rounded-xl border border-slate-300 bg-white py-3 pl-10 pr-3 text-sm text-ink-900 placeholder:text-slate-400 transition-colors focus:border-jade-500"
            />
          </div>
          <button
            type="submit"
            disabled={busca.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-jade-600 px-5 py-3 text-sm font-600 text-white shadow-lift transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
          >
            {busca.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Buscando...
              </>
            ) : (
              <>
                <Search className="h-4 w-4" /> Buscar
              </>
            )}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Deixe o campo vazio e busque para listar todos os fornecedores salvos.
        </p>
      </form>

      {/* Erro */}
      {busca.isError && (
        <div
          className="flex items-start gap-2.5 rounded-xl border border-signal-200 bg-signal-50 p-3.5 text-sm text-signal-700"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {busca.error?.response?.data?.detail ??
              "Não foi possível consultar o banco de fornecedores. Tente novamente."}
          </span>
        </div>
      )}

      {/* Resultados / estados */}
      {busca.isPending ? (
        <EstadoCarregando />
      ) : !buscou ? (
        <EstadoInicial />
      ) : resultados.length === 0 ? (
        <EstadoVazio />
      ) : (
        <Tabela resultados={resultados} />
      )}
    </div>
  );
}

function Tabela({ resultados }) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <h2 className="text-sm font-600 text-ink-900">
          {resultados.length} fornecedor{resultados.length > 1 ? "es" : ""} encontrado
          {resultados.length > 1 ? "s" : ""}
        </h2>
      </div>
      <div className="overflow-x-auto scroll-thin">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-500">CNPJ</th>
              <th className="px-5 py-3 font-500">Razão social</th>
              <th className="px-5 py-3 font-500">Origem</th>
            </tr>
          </thead>
          <tbody>
            {resultados.map((f, i) => {
              const origem = origemMeta(f.origem);
              return (
                <tr
                  key={`${f.cnpj}-${i}`}
                  className="border-b border-slate-50 last:border-0 transition-colors hover:bg-slate-50/60"
                >
                  <td className="whitespace-nowrap px-5 py-3.5 font-mono tnum text-ink-800">
                    {formatarCnpj(f.cnpj)}
                  </td>
                  <td className="px-5 py-3.5 text-ink-900">{f.razao_social || "—"}</td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-500 ${origem.classe}`}
                    >
                      {origem.texto}
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

function EstadoCarregando() {
  return (
    <div className="grid place-items-center rounded-2xl border border-slate-200 bg-white py-16 shadow-panel">
      <Loader2 className="h-7 w-7 animate-spin text-slate-300" />
      <p className="mt-3 text-sm text-slate-500">Consultando o banco de fornecedores...</p>
    </div>
  );
}

function EstadoInicial() {
  return (
    <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white/60 py-16 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Search className="h-6 w-6" />
      </span>
      <p className="mt-4 text-sm font-500 text-ink-800">Pronto para consultar</p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">
        Digite um CNPJ ou parte da razão social e clique em buscar. Para ver o banco completo, busque
        com o campo vazio.
      </p>
    </div>
  );
}

function EstadoVazio() {
  return (
    <div className="grid place-items-center rounded-2xl border border-dashed border-slate-300 bg-white/60 py-16 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
        <Building2 className="h-6 w-6" />
      </span>
      <p className="mt-4 text-sm font-500 text-ink-800">Nenhum fornecedor no banco ainda</p>
      <p className="mt-1 max-w-sm text-sm text-slate-500">
        Os fornecedores são salvos automaticamente conforme você resolve os CNPJ nas análises do
        Módulo 01. Conforme você usa o sistema, este banco cresce.
      </p>
    </div>
  );
}
