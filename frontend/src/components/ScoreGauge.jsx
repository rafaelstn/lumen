import { faixaMeta } from "../utils/format.js";

// Gauge radial de score (0-100) — anchor visual do M02. Ecoa o glifo de "lente"
// do Lumen: anel de medição com o número no núcleo. Cor pela faixa.
// tamanho: "lg" (card de ranking) | "sm" (linha de carteira).
export default function ScoreGauge({ score, faixa, tamanho = "lg" }) {
  const n = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const meta = faixaMeta(faixa, n);

  const dim = tamanho === "sm" ? 56 : 92;
  const stroke = tamanho === "sm" ? 5 : 7;
  const r = (dim - stroke) / 2;
  const c = 2 * Math.PI * r;
  const preenchido = (n / 100) * c;

  return (
    <div
      className="relative grid shrink-0 place-items-center"
      style={{ width: dim, height: dim }}
      role="img"
      aria-label={`Score ${n} de 100, faixa ${meta.rotulo}`}
    >
      <svg width={dim} height={dim} className="-rotate-90">
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-slate-200"
        />
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${preenchido} ${c}`}
          className={meta.anel}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span
          className={[
            "tnum font-display font-600 leading-none tracking-tight",
            meta.texto,
            tamanho === "sm" ? "text-base" : "text-2xl",
          ].join(" ")}
        >
          {n}
        </span>
      </div>
    </div>
  );
}
