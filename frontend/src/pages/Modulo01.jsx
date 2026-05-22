import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { processarArquivos, definirCnpjManual } from "../services/api.js";
import { moeda } from "../utils/format.js";
import FileUpload from "../components/FileUpload.jsx";
import ResultCard from "../components/ResultCard.jsx";
import FornecedoresTable from "../components/FornecedoresTable.jsx";

// Fluxo do Módulo 01: upload dos XLS → classificação → resumo + tabela.
// Permite corrigir CNPJ manualmente. CND, risco 2027 e PDF entram nas fases 3 a 5.
export default function Modulo01() {
  const [entradas, setEntradas] = useState(null);
  const [cadastro, setCadastro] = useState(null);
  const [resultado, setResultado] = useState(null);
  const [erroCnpj, setErroCnpj] = useState(null);

  const processar = useMutation({
    mutationFn: processarArquivos,
    onSuccess: (data) => setResultado(data),
  });

  const salvarCnpj = useMutation({
    mutationFn: ({ codForn, cnpj, razaoSocial }) =>
      definirCnpjManual(resultado.job_id, {
        cod_forn: codForn,
        cnpj,
        razao_social: razaoSocial,
      }),
    onSuccess: (fornAtualizado) => {
      setErroCnpj(null);
      setResultado((r) => ({
        ...r,
        fornecedores: r.fornecedores.map((f) =>
          f.cod_forn === fornAtualizado.cod_forn ? fornAtualizado : f
        ),
      }));
    },
    onError: (e) =>
      setErroCnpj(e?.response?.data?.detail ?? "Não foi possível salvar o CNPJ."),
  });

  function onSalvarCnpj(codForn, { cnpj, razaoSocial }) {
    salvarCnpj.mutate({ codForn, cnpj, razaoSocial });
  }

  const detalheErro =
    processar.error?.response?.data?.detail ??
    processar.error?.message ??
    "Falha ao processar os arquivos.";

  return (
    <div className="space-y-6">
      {!resultado && (
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
            onClick={() => entradas && processar.mutate({ entradas, cadastro })}
            disabled={!entradas || processar.isPending}
            className="px-4 py-2 rounded-md bg-slate-900 text-white text-sm disabled:opacity-40"
          >
            {processar.isPending ? "Processando..." : "Processar"}
          </button>
          {processar.isPending && (
            <p className="text-sm text-slate-500">Lendo e classificando fornecedores...</p>
          )}
          {processar.error && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {detalheErro}
            </div>
          )}
        </section>
      )}

      {resultado && (
        <section className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ResultCard titulo="Fornecedores" valor={resultado.resumo.total_fornecedores} />
            <ResultCard titulo="Crédito ICMS aproveitado" valor={moeda(resultado.resumo.total_credito_aproveitado)} />
            <ResultCard titulo="Compras sem crédito" valor={moeda(resultado.resumo.total_compras_sem_credito)} />
            <ResultCard
              titulo="Verificação manual (ST)"
              valor={resultado.resumo.caso_especial}
              destaque={resultado.resumo.caso_especial > 0}
            />
          </div>

          <div className="flex flex-wrap gap-2 text-xs text-slate-500">
            <span>Grupo A: {resultado.resumo.grupo_a}</span>
            <span>·</span>
            <span>Grupo B: {resultado.resumo.grupo_b}</span>
            <span>·</span>
            <span>Grupo C: {resultado.resumo.grupo_c}</span>
            {resultado.resumo.grupo_indefinido > 0 && (
              <>
                <span>·</span>
                <span className="text-slate-400">Indefinido: {resultado.resumo.grupo_indefinido}</span>
              </>
            )}
            <span>·</span>
            <span>CNPJ pendentes: {resultado.resumo.cnpj_pendentes}</span>
          </div>

          {erroCnpj && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {erroCnpj}
            </div>
          )}

          <FornecedoresTable
            fornecedores={resultado.fornecedores}
            onSalvarCnpj={onSalvarCnpj}
            salvando={salvarCnpj.isPending}
          />

          <button
            type="button"
            onClick={() => {
              setResultado(null);
              processar.reset();
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
