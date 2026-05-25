import { Wallet, AlertTriangle } from "lucide-react";
import { moeda, numero } from "../utils/format.js";
import { useSaldoConsulta, itemSaldo, saldoConfigurado } from "../utils/custos.js";

// Linha compacta de saldo de um serviço, para colar ao lado do custo estimado
// nos pontos de consulta paga (M01/M02). Mostra créditos restantes e o valor em
// R$, e avisa em âmbar/vermelho quando a operação vai consumir mais que o saldo.
// Não bloqueia: é informativo (o controle de saldo é interno do usuário).
//
// props:
//   servico: "cnpj" | "cnd"
//   consumoPrevisto: créditos que a operação vai consumir (opcional)
export default function SaldoInline({ servico, consumoPrevisto = 0 }) {
  const { data: saldo, isLoading, isError } = useSaldoConsulta();
  const item = itemSaldo(saldo, servico);

  // Sem saldo configurado ainda: não polui a UI, só convida a configurar.
  if (isLoading) {
    return <p className="text-xs text-slate-400">Verificando saldo...</p>;
  }
  if (isError || !saldoConfigurado(item)) {
    return (
      <p className="text-xs text-slate-400">
        Saldo não configurado. Registre uma recarga em Consumo &amp; custos para acompanhar o gasto.
      </p>
    );
  }

  const restantes = Math.trunc(Number(item.creditos_restantes) || 0);
  const custoRestanteCent = Math.max(0, Math.trunc(Number(item.custo_restante_centavos) || 0));
  const previsto = Math.max(0, Math.trunc(Number(consumoPrevisto) || 0));
  const insuficiente = previsto > 0 && previsto > restantes;
  const zerado = restantes <= 0;
  const alerta = insuficiente || zerado;

  return (
    <p
      className={[
        "inline-flex flex-wrap items-center gap-1.5 text-xs",
        alerta ? "text-signal-700" : "text-slate-500",
      ].join(" ")}
    >
      {alerta ? (
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-signal-600" />
      ) : (
        <Wallet className="h-3.5 w-3.5 shrink-0 text-jade-600" />
      )}
      <span>
        Saldo:{" "}
        <strong className={`tnum ${alerta ? "text-signal-700" : "text-ink-700"}`}>
          {numero(restantes)}
        </strong>{" "}
        crédito{restantes === 1 ? "" : "s"} (≈{" "}
        <span className="tnum">{moeda(custoRestanteCent / 100)}</span>)
      </span>
      {insuficiente && (
        <span className="font-500">· consumo previsto ({numero(previsto)}) acima do saldo</span>
      )}
      {!insuficiente && zerado && <span className="font-500">· saldo zerado</span>}
    </p>
  );
}
