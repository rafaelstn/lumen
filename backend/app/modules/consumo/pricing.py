"""Preço por crédito (Decimal em centavos) e créditos estimados por operação.

Verdade financeira (financeiro.md):
- A recarga é comprada por PACOTE: o usuário informa `creditos` e `valor_total_centavos`
  (o que pagou pelo pacote). Isso é exato em centavos e espelha como o provider vende.
  Ex.: CNPJá = R$24,99 por 1000 créditos -> creditos=1000, valor_total_centavos=2499.
- O preço por crédito é DERIVADO: valor_total_pago / creditos_comprados, mantido em
  Decimal só para cálculo (nunca float, nunca arredondado para inteiro antes de multiplicar).
- custo de uma operação = ROUND_HALF_UP(creditos_consumidos * preco_por_credito_decimal),
  gravado como inteiro em centavos no ConsultaLog (snapshot imutável).

Tabela de referência (default quando o serviço ainda não teve recarga):
- CNPJá: R$24,99 / 1000 créditos = 2,499 centavos por crédito (fração de centavo preservada).
- CND (Infosimples): R$0,26 por consulta concluída = 26 centavos. 1 consulta = 1 crédito.
"""
from decimal import ROUND_HALF_UP, Decimal

from app.modules.consumo.models import SERVICO_CND, SERVICO_CNPJ

# Preço de referência por crédito, em CENTAVOS (Decimal), usado quando o serviço ainda não
# tem recarga registrada (saldo derivado de valor_total_pago / creditos não existe ainda).
# Preserva a fração de centavo do pacote CNPJá.
PRECO_POR_CREDITO_CENTAVOS: dict[str, Decimal] = {
    SERVICO_CNPJ: Decimal("2499") / Decimal("1000"),  # 2,499 centavos/crédito
    SERVICO_CND: Decimal("26"),                        # 26 centavos/crédito (= consulta)
}

# Créditos estimados por unidade de operação (consumo real não é exposto pela origem).
CREDITOS_POR_CONSULTA_CNPJ = 2  # /office com simples=true consome 2 créditos
CREDITOS_POR_CONSULTA_CND = 1   # cada CND concluída = 1 consulta = 1 crédito


def preco_referencia_por_credito(servico: str) -> Decimal:
    """Preço por crédito de referência (Decimal, centavos). 0 se serviço desconhecido."""
    return PRECO_POR_CREDITO_CENTAVOS.get(servico, Decimal("0"))


def preco_por_credito_derivado(
    creditos_comprados: int, valor_total_pago_centavos: int, servico: str
) -> Decimal:
    """Preço por crédito DERIVADO do acumulado de recargas, em Decimal (centavos).

    valor_total_pago / creditos_comprados. Sem float, sem arredondar aqui (fração mantida
    para o cálculo do custo). Cai no preço de referência enquanto não houver recarga.
    """
    if creditos_comprados <= 0:
        return preco_referencia_por_credito(servico)
    return Decimal(valor_total_pago_centavos) / Decimal(creditos_comprados)


def custo_centavos_por_preco(creditos: int, preco_por_credito: Decimal) -> int:
    """Custo em centavos inteiros: arredonda só no fim (ROUND_HALF_UP). Nunca negativo."""
    if creditos <= 0:
        return 0
    total = (preco_por_credito * Decimal(creditos)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(total)


def preco_unitario_centavos_snapshot(servico: str) -> int:
    """Snapshot inteiro do preço de referência por crédito (compat: campo *_centavos do log).

    É só um indicador inteiro para exibição; a fonte de custo é custo_centavos, calculado
    sobre o preço Decimal (de referência ou derivado) sem perder a fração.
    """
    preco = preco_referencia_por_credito(servico)
    return int(preco.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def custo_centavos(servico: str, creditos: int) -> int:
    """Custo total em centavos a partir do preço de REFERÊNCIA do serviço.

    Ex.: 1000 créditos CNPJá * 2,499 = 2499 centavos exatos (R$24,99), sem perda.
    Usado quando não há preço derivado (default/estimativa).
    """
    return custo_centavos_por_preco(creditos, preco_referencia_por_credito(servico))
