import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { processarArquivos } from "../services/api.js";
import { moeda } from "../utils/format.js";
import FileUpload from "../components/FileUpload.jsx";
import ResultCard from "../components/ResultCard.jsx";
import FornecedoresTable from "../components/FornecedoresTable.jsx";

// Fluxo do Módulo 01: upload dos XLS → classificação → resumo + tabela.
// A consulta CND, o risco 2027 e o download do PDF entram com as fases 3 a 5.
export default function Modulo01() {
  const [entradas, setEntradas] = useState(null);
  const [cadastro, setCadastro] = useState(null);

  const mutation = useMutation({ mutationFn: processarArquivos });
  const { data, error, isPending, isSuccess, reset } = mutation;

  function processar() {
    if (entradas) mutation.mutate({ entradas, cadastro });
  }

  const detalheErro =
    error?.response?.data?.detail ?? error?.message ?? "Falha ao processar os arquivos.";

  return (
    <div className="space-y-6">
      {!isSuccess && (
        <section className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FileUpload label="Livro de Entradas (XLS) *" file={entradas} onChange={setEntradas} />
            <FileUpload
              label="Cadastro de Fornecedores (XLS, opcional)"
              file={cadastro}
              onChange={setCadastro}
            />
          </div>
          <button
            type="button"
            onClick={processar}
            disabled={!entradas || isPending}
            className="px-4 py-2 rounded-md bg-slate-900 text-white text-sm disabled:opacity-40"
          >
            {isPending ? "Processando..." : "Processar"}
          </button>
          {isPending && (
            <p className="text-sm text-slate-500">Lendo e classificando fornecedores...</p>
          )}
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {detalheErro}
            </div>
          )}
        </section>
      )}

      {isSuccess && data && (
        <section className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ResultCard titulo="Fornecedores" valor={data.resumo.total_fornecedores} />
            <ResultCard titulo="Crédito ICMS aproveitado" valor={moeda(data.resumo.total_credito_aproveitado)} />
            <ResultCard titulo="Compras sem crédito" valor={moeda(data.resumo.total_compras_sem_credito)} />
            <ResultCard
              titulo="Verificação manual (ST)"
              valor={data.resumo.caso_especial}
              destaque={data.resumo.caso_especial > 0}
            />
          </div>

          <div className="flex flex-wrap gap-2 text-xs text-slate-500">
            <span>Grupo A: {data.resumo.grupo_a}</span>
            <span>·</span>
            <span>Grupo B: {data.resumo.grupo_b}</span>
            <span>·</span>
            <span>Grupo C: {data.resumo.grupo_c}</span>
            {data.resumo.grupo_indefinido > 0 && (
              <>
                <span>·</span>
                <span className="text-slate-400">Indefinido: {data.resumo.grupo_indefinido}</span>
              </>
            )}
            <span>·</span>
            <span>CNPJ pendentes: {data.resumo.cnpj_pendentes}</span>
          </div>

          <FornecedoresTable fornecedores={data.fornecedores} />

          <button
            type="button"
            onClick={() => {
              reset();
              setEntradas(null);
              setCadastro(null);
            }}
            className="px-4 py-2 rounded-md border border-slate-300 text-sm text-slate-700"
          >
            Processar outro arquivo
          </button>
        </section>
      )}
    </div>
  );
}
