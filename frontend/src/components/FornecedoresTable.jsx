import { useState } from "react";
import { moeda, percentual, CORES_GRUPO } from "../utils/format.js";

// Tabela de fornecedores classificados. Pros que estão sem CNPJ, permite
// inserir razão social + CNPJ manualmente (o backend valida o dígito verificador).
export default function FornecedoresTable({ fornecedores, onSalvarCnpj, salvando }) {
  const [editando, setEditando] = useState(null);
  const [cnpj, setCnpj] = useState("");
  const [razao, setRazao] = useState("");

  function abrir(f) {
    setEditando(f.cod_forn);
    setCnpj("");
    setRazao(f.nome_forn || "");
  }

  function salvar(f) {
    onSalvarCnpj(f.cod_forn, { cnpj, razaoSocial: razao });
    setEditando(null);
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Grupo</th>
            <th className="px-3 py-2 text-left font-medium">Fornecedor</th>
            <th className="px-3 py-2 text-left font-medium">CNPJ</th>
            <th className="px-3 py-2 text-right font-medium">Compras</th>
            <th className="px-3 py-2 text-right font-medium">Alíq. máx.</th>
            <th className="px-3 py-2 text-right font-medium">ICMS aprov.</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {fornecedores.map((f) => {
            const emEdicao = editando === f.cod_forn;
            return (
              <tr key={f.cod_forn} className={f.verificar_st ? "bg-amber-50/50" : ""}>
                <td className="px-3 py-2 align-top">
                  <span
                    className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${
                      CORES_GRUPO[f.grupo] ?? CORES_GRUPO.INDEFINIDO
                    }`}
                  >
                    {f.grupo}
                  </span>
                </td>
                <td className="px-3 py-2 align-top">
                  {emEdicao ? (
                    <input
                      value={razao}
                      onChange={(e) => setRazao(e.target.value)}
                      placeholder="Razão social"
                      className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
                    />
                  ) : (
                    <>
                      <span className="text-slate-800">{f.nome_forn}</span>
                      {f.verificar_st && (
                        <span className="ml-2 text-xs text-amber-600">⚠ verificar ST</span>
                      )}
                      {!f.cnpj_pendente && !f.cnpj_confirmado && f.cnpj && (
                        <span className="ml-2 text-xs text-slate-400">(CNPJ não confirmado)</span>
                      )}
                    </>
                  )}
                </td>
                <td className="px-3 py-2 align-top text-slate-500">
                  {emEdicao ? (
                    <div className="flex items-center gap-1">
                      <input
                        value={cnpj}
                        onChange={(e) => setCnpj(e.target.value)}
                        placeholder="00.000.000/0000-00"
                        className="w-40 rounded border border-slate-300 px-2 py-1 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => salvar(f)}
                        disabled={salvando}
                        className="rounded bg-slate-900 px-2 py-1 text-xs text-white disabled:opacity-40"
                      >
                        Salvar
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditando(null)}
                        className="rounded border border-slate-300 px-2 py-1 text-xs"
                      >
                        Cancelar
                      </button>
                    </div>
                  ) : f.cnpj ? (
                    <span className={f.cnpj_confirmado ? "text-emerald-700" : "text-slate-600"}>
                      {f.cnpj}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => abrir(f)}
                      className="text-xs text-sky-600 underline"
                    >
                      inserir manualmente
                    </button>
                  )}
                </td>
                <td className="px-3 py-2 text-right align-top tabular-nums">{moeda(f.total_compras)}</td>
                <td className="px-3 py-2 text-right align-top tabular-nums">{percentual(f.aliquota_max)}</td>
                <td className="px-3 py-2 text-right align-top tabular-nums">{moeda(f.total_valor_icms)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
