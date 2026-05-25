"""Testes de precificação em centavos inteiros — sem perda de fração (financeiro.md)."""
from app.modules.consumo import pricing
from app.modules.consumo.models import SERVICO_CND, SERVICO_CNPJ


def test_preco_unitario_snapshot_arredonda_para_centavo_inteiro():
    # CNPJá: 2,499 centavos/crédito -> ROUND_HALF_UP -> 2 centavos (snapshot inteiro).
    assert pricing.preco_unitario_centavos_snapshot(SERVICO_CNPJ) == 2
    # CND: 26 centavos/crédito exatos.
    assert pricing.preco_unitario_centavos_snapshot(SERVICO_CND) == 26


def test_custo_cnpja_1000_creditos_bate_exatamente_o_plano():
    # 1000 créditos a R$0,024990 = R$24,99 = 2499 centavos. Sem perda da fração de centavo.
    assert pricing.custo_centavos(SERVICO_CNPJ, 1000) == 2499


def test_custo_cnpja_uma_consulta_dois_creditos():
    # 2 créditos * 2,499 = 4,998 -> ROUND_HALF_UP -> 5 centavos (R$0,05, como o frontend mostra).
    assert pricing.custo_centavos(SERVICO_CNPJ, 2) == 5


def test_custo_cnd_por_consulta():
    # 1 consulta CND = 1 crédito = 26 centavos (R$0,26).
    assert pricing.custo_centavos(SERVICO_CND, 1) == 26
    assert pricing.custo_centavos(SERVICO_CND, 10) == 260


def test_custo_zero_ou_negativo_e_zero():
    assert pricing.custo_centavos(SERVICO_CNPJ, 0) == 0
    assert pricing.custo_centavos(SERVICO_CNPJ, -5) == 0


def test_custo_acumulado_nao_perde_fracao_em_muitas_operacoes():
    # 500 operações de 2 créditos = 1000 créditos. Somar o custo por operação (5 centavos)
    # daria 2500, mas o cálculo correto sobre o total é 2499. Validamos o total exato.
    total_creditos = 500 * 2
    assert pricing.custo_centavos(SERVICO_CNPJ, total_creditos) == 2499
