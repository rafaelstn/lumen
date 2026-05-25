import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSaldo } from "../services/api.js";

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

// Centavos -> string editável "0,26" para preencher o input. Arredonda para o
// centavo (ROUND_HALF_UP via Math.round) porque o custo por consulta derivado do
// backend pode ser fracionário (ex.: 4,998 centavos = R$ 0,05) e o campo só
// comporta 2 casas. A fração não se perde no cálculo: o total usa o valor cheio.
export function centavosParaInput(cent) {
  return (Math.max(0, Math.round(Number(cent) || 0)) / 100).toFixed(2).replace(".", ",");
}

// Converte o preco_por_credito do backend (string decimal EM CENTAVOS, ex
// "2.499" = 2,499 centavos por crédito) num número de centavos para o cálculo.
// Mantém a fração (não arredonda aqui): o arredondamento só acontece na
// formatação final, ao multiplicar pela quantidade. Tolera null/vazio/lixo.
export function precoPorCreditoParaCentavos(valor) {
  if (valor == null) return 0;
  const n = Number.parseFloat(String(valor).replace(",", "."));
  if (!Number.isFinite(n) || n < 0) return 0;
  return n;
}

// Orçamento de uma quantidade de fornecedores, em centavos. Retorna o total
// sem CND (só cadastro) e com CND (cadastro + CND).
//
// Os custos unitários podem chegar fracionados (preço derivado do backend, ex
// 4,998 centavos por cadastro quando o crédito custa fração de centavo). A
// fração é preservada na multiplicação e o arredondamento (ROUND_HALF_UP via
// Math.round) só acontece no valor final exibido, evitando perder centavos.
// Os unitários expostos são arredondados apenas para exibição.
export function orcamento(quantidade, cadastroCent, cndCent) {
  const q = Math.max(0, Math.trunc(Number(quantidade) || 0));
  const cad = Math.max(0, Number(cadastroCent) || 0);
  const cnd = Math.max(0, Number(cndCent) || 0);
  return {
    quantidade: q,
    unitarioSemCndCent: Math.round(cad),
    unitarioComCndCent: Math.round(cad + cnd),
    totalSemCndCent: Math.round(q * cad),
    totalComCndCent: Math.round(q * (cad + cnd)),
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

// Mapeamento entre os "tipos de consulta" da UI e os serviços do backend.
//   cadastro (dados cadastrais + Simples) -> serviço "cnpj" (CNPJá)
//   cnd      (certidão de regularidade)   -> serviço "cnd"  (Infosimples)
export const SERVICO = { CADASTRO: "cnpj", CND: "cnd" };

// Créditos consumidos por UMA consulta de cada tipo. O cadastro (CNPJá
// /office?simples=true) consome 2 créditos (Receita + Simples); a CND, 1.
// Usado para converter o preço POR CRÉDITO do backend em custo POR CONSULTA.
export const CREDITOS_POR_CONSULTA = { [SERVICO.CADASTRO]: 2, [SERVICO.CND]: 1 };

// Chave de cache compartilhada do saldo (react-query).
export const QUERY_SALDO = ["consultas", "saldo"];

// Hook do saldo das APIs pagas. O backend é a fonte da verdade do saldo e do
// preço REAL pago (definido na recarga).
export function useSaldoConsulta() {
  return useQuery({ queryKey: QUERY_SALDO, queryFn: getSaldo });
}

// Localiza o item de saldo de um serviço dentro da resposta de getSaldo().
export function itemSaldo(saldo, servico) {
  return saldo?.itens?.find((i) => i.servico === servico) ?? null;
}

// Há saldo CONFIGURADO para o serviço quando o usuário já registrou alguma
// compra (creditos_comprados > 0). Só nesse caso o preço do backend é confiável.
export function saldoConfigurado(item) {
  return !!item && Math.trunc(Number(item.creditos_comprados) || 0) > 0;
}

// Resolve os custos POR CONSULTA EFETIVOS (em centavos) combinando duas fontes:
//   - backend (preco_por_credito por serviço, string decimal em centavos): fonte
//     da verdade quando há compra registrada (preço realmente pago). O custo por
//     consulta é preco_por_credito × créditos por consulta (2 no cadastro, 1 na CND).
//     A fração de centavo é PRESERVADA aqui; o arredondamento só ocorre no total.
//   - localStorage (useCustosConsulta): fallback inicial e edição rápida.
// Retorna { cadastroCent, cndCent, origemCadastro, origemCnd } onde origem ∈
// {"backend","local"}, útil para sinalizar ao usuário de onde veio o preço.
// Os valores podem ser fracionários quando vêm do backend; quem exibe arredonda.
export function useCustosEfetivos() {
  const local = useCustosConsulta();
  const { data: saldo } = useSaldoConsulta();

  const efetivos = useMemo(() => {
    const itemCad = itemSaldo(saldo, SERVICO.CADASTRO);
    const itemCnd = itemSaldo(saldo, SERVICO.CND);
    const usaBackCad = saldoConfigurado(itemCad);
    const usaBackCnd = saldoConfigurado(itemCnd);
    return {
      cadastroCent: usaBackCad
        ? precoPorCreditoParaCentavos(itemCad.preco_por_credito) *
          CREDITOS_POR_CONSULTA[SERVICO.CADASTRO]
        : local.cadastroCent,
      cndCent: usaBackCnd
        ? precoPorCreditoParaCentavos(itemCnd.preco_por_credito) *
          CREDITOS_POR_CONSULTA[SERVICO.CND]
        : local.cndCent,
      origemCadastro: usaBackCad ? "backend" : "local",
      origemCnd: usaBackCnd ? "backend" : "local",
    };
  }, [saldo, local.cadastroCent, local.cndCent]);

  // Preserva os setters do localStorage (edição rápida segue funcionando).
  return { ...efetivos, definirCadastro: local.definirCadastro, definirCnd: local.definirCnd };
}
