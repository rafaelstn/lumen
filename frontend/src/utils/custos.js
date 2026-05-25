import { useCallback, useEffect, useState } from "react";

// Custos de consulta paga do Módulo 02. Toda aritmética é feita em CENTAVOS
// inteiros (nunca float) para não perder precisão em valores monetários; a
// conversão para reais só acontece na formatação final.
//
// Uma avaliação de fornecedor faz duas consultas pagas independentes:
//   - cadastro: dados cadastrais + Simples (CNPJá)
//   - cnd: certidão de regularidade fiscal (Infosimples)
// Os valores variam conforme o plano contratado de cada API, por isso são
// editáveis pelo usuário e ficam persistidos no navegador.

const CHAVE_STORAGE = "lumen:custos-consulta:v1";

// Padrões iniciais (em centavos), editáveis pelo usuário:
//   - cadastro: consulta CNPJá /office?simples=true = 2 créditos (Receita Federal +
//     Simples Nacional). No plano de R$ 24,99 por 1.000 créditos, 1 crédito = R$ 0,02499,
//     logo 2 créditos ≈ R$ 0,05. Com cache (CACHE_IF_FRESH) pode custar menos.
//   - cnd: R$ 0,26, preço de referência da Infosimples.
export const CUSTO_PADRAO = {
  cadastroCent: 5,
  cndCent: 26,
};

// Converte uma string de reais digitada ("0,26", "1.234,56", "R$ 3") em
// centavos inteiros. Tolera vírgula ou ponto como separador decimal.
export function reaisParaCentavos(texto) {
  if (texto == null) return 0;
  let s = String(texto).trim().replace(/[^\d.,-]/g, "");
  if (!s) return 0;
  // Com vírgula presente, ela é o separador decimal e os pontos são milhar.
  if (s.includes(",")) {
    s = s.replace(/\./g, "").replace(",", ".");
  }
  const n = Number.parseFloat(s);
  if (Number.isNaN(n) || n < 0) return 0;
  return Math.round(n * 100);
}

// Centavos inteiros -> string editável "0,26" para preencher o input.
export function centavosParaInput(cent) {
  return (Math.max(0, Math.trunc(cent)) / 100).toFixed(2).replace(".", ",");
}

// Orçamento de uma quantidade de fornecedores, em centavos. Retorna o total
// sem CND (só cadastro) e com CND (cadastro + CND).
export function orcamento(quantidade, cadastroCent, cndCent) {
  const q = Math.max(0, Math.trunc(Number(quantidade) || 0));
  const cad = Math.max(0, Math.trunc(cadastroCent || 0));
  const cnd = Math.max(0, Math.trunc(cndCent || 0));
  return {
    quantidade: q,
    unitarioSemCndCent: cad,
    unitarioComCndCent: cad + cnd,
    totalSemCndCent: q * cad,
    totalComCndCent: q * (cad + cnd),
  };
}

function ler() {
  try {
    const bruto = localStorage.getItem(CHAVE_STORAGE);
    if (!bruto) return { ...CUSTO_PADRAO };
    const dados = JSON.parse(bruto);
    return {
      cadastroCent: Math.max(0, Math.trunc(Number(dados.cadastroCent) || 0)),
      cndCent: Math.max(0, Math.trunc(Number(dados.cndCent) || 0)),
    };
  } catch {
    return { ...CUSTO_PADRAO };
  }
}

// Hook que mantém os custos unitários persistidos no navegador.
export function useCustosConsulta() {
  const [custos, setCustos] = useState(ler);

  useEffect(() => {
    try {
      localStorage.setItem(CHAVE_STORAGE, JSON.stringify(custos));
    } catch {
      // Sem persistência (modo privado/sem storage): segue só em memória.
    }
  }, [custos]);

  const definirCadastro = useCallback(
    (reais) => setCustos((c) => ({ ...c, cadastroCent: reaisParaCentavos(reais) })),
    [],
  );
  const definirCnd = useCallback(
    (reais) => setCustos((c) => ({ ...c, cndCent: reaisParaCentavos(reais) })),
    [],
  );

  return { ...custos, definirCadastro, definirCnd };
}
