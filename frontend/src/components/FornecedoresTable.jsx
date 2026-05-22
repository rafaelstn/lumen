import { moeda, percentual, CORES_GRUPO } from "../utils/format.js";

// Tabela de fornecedores classificados. Destaca caso especial (ST) e CNPJ pendente.
export default function FornecedoresTable({ fornecedores }) {
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
          {fornecedores.map((f) => (
            <tr key={f.cod_forn} className={f.verificar_st ? "bg-amber-50/50" : ""}>
              <td className="px-3 py-2">
                <span
                  className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${
                    CORES_GRUPO[f.grupo] ?? CORES_GRUPO.INDEFINIDO
                  }`}
                >
                  {f.grupo}
                </span>
              </td>
              <td className="px-3 py-2">
                <span className="text-slate-800">{f.nome_forn}</span>
                {f.verificar_st && (
                  <span className="ml-2 text-xs text-amber-600">⚠ verificar ST</span>
                )}
              </td>
              <td className="px-3 py-2 text-slate-500">
                {f.cnpj ?? <span className="italic text-slate-400">pendente</span>}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{moeda(f.total_compras)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{percentual(f.aliquota_max)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{moeda(f.total_valor_icms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
