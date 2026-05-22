import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getModulo01Status } from "../services/api.js";
import FileUpload from "../components/FileUpload.jsx";

// Fase 1: tela carrega e confirma conexão com o backend.
// O fluxo completo (upload → progresso → download) é implementado na Fase 6.
export default function Modulo01() {
  const [entradas, setEntradas] = useState(null);
  const [cadastro, setCadastro] = useState(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["modulo01-status"],
    queryFn: getModulo01Status,
    retry: 1,
  });

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <span className="font-medium">Status do backend: </span>
        {isLoading && <span className="text-slate-500">verificando...</span>}
        {isError && <span className="text-red-600">offline</span>}
        {data && <span className="text-emerald-600">online (módulo {data.modulo})</span>}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <FileUpload label="Livro de Entradas (XLS)" file={entradas} onChange={setEntradas} />
        <FileUpload label="Cadastro de Fornecedores (XLS)" file={cadastro} onChange={setCadastro} />
      </section>

      <button
        type="button"
        disabled
        className="px-4 py-2 rounded-md bg-slate-900 text-white text-sm disabled:opacity-40"
        title="Processamento implementado na Fase 6"
      >
        Processar
      </button>
    </div>
  );
}
