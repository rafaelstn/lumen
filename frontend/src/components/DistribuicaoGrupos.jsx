import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { HEX_GRUPO, ROTULO_GRUPO, numero } from "../utils/format.js";

// Donut da distribuição de fornecedores por grupo (A/B/C/Indefinido).
// Centro mostra o total; legenda lateral lista cada grupo com contagem.
export default function DistribuicaoGrupos({ resumo }) {
  const dados = [
    { chave: "A", nome: ROTULO_GRUPO.A, valor: resumo.grupo_a },
    { chave: "B", nome: ROTULO_GRUPO.B, valor: resumo.grupo_b },
    { chave: "C", nome: ROTULO_GRUPO.C, valor: resumo.grupo_c },
    { chave: "INDEFINIDO", nome: ROTULO_GRUPO.INDEFINIDO, valor: resumo.grupo_indefinido },
  ].filter((d) => d.valor > 0);

  const total = dados.reduce((s, d) => s + d.valor, 0);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-panel sm:p-6">
      <h2 className="font-display text-lg font-600 text-ink-900">Distribuição por grupo</h2>
      <p className="mt-0.5 text-xs text-slate-500">Classificação fiscal dos fornecedores analisados</p>

      <div className="mt-5 flex flex-col items-center gap-6 sm:flex-row sm:gap-2">
        <div className="relative h-44 w-44 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={dados}
                dataKey="valor"
                nameKey="nome"
                innerRadius={56}
                outerRadius={80}
                paddingAngle={dados.length > 1 ? 2 : 0}
                stroke="none"
              >
                {dados.map((d) => (
                  <Cell key={d.chave} fill={HEX_GRUPO[d.chave]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(v, n) => [numero(v) + " fornecedor(es)", n]}
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #e2e8f0",
                  fontSize: 12,
                  boxShadow: "0 8px 24px -12px rgba(15,24,29,0.25)",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 grid place-items-center">
            <div className="text-center">
              <p className="tnum font-display text-2xl font-600 leading-none text-ink-900">{numero(total)}</p>
              <p className="mt-1 text-[0.65rem] uppercase tracking-wider text-slate-400">total</p>
            </div>
          </div>
        </div>

        <ul className="w-full space-y-2.5 sm:flex-1">
          {dados.map((d) => {
            const pct = total ? (d.valor / total) * 100 : 0;
            return (
              <li key={d.chave} className="flex items-center gap-3">
                <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: HEX_GRUPO[d.chave] }} />
                <span className="flex-1 text-sm text-ink-700">{d.nome}</span>
                <span className="tnum text-sm font-600 text-ink-900">{numero(d.valor)}</span>
                <span className="tnum w-12 text-right text-xs text-slate-400">{pct.toFixed(0)}%</span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
