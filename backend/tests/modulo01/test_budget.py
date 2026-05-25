"""Teto diário de consultas pagas: reserva, estorno e clamp em zero."""
from app.config import settings
from app.modules.modulo01 import budget


def test_consumir_e_devolver(monkeypatch):
    monkeypatch.setattr(settings, "cnpj_max_diario", 5)
    budget._contadores.clear()

    assert budget.restante("cnpj") == 5
    assert budget.consumir("cnpj") is True
    assert budget.restante("cnpj") == 4

    # Estorna a reserva que não chegou a virar consulta (ex.: 429 antes da chamada).
    budget.devolver("cnpj")
    assert budget.restante("cnpj") == 5


def test_devolver_nao_fica_negativo(monkeypatch):
    monkeypatch.setattr(settings, "cnpj_max_diario", 5)
    budget._contadores.clear()
    budget.devolver("cnpj")  # nada reservado
    assert budget.restante("cnpj") == 5


def test_consumir_recusa_ao_estourar(monkeypatch):
    monkeypatch.setattr(settings, "cnpj_max_diario", 2)
    budget._contadores.clear()
    assert budget.consumir("cnpj") is True
    assert budget.consumir("cnpj") is True
    assert budget.consumir("cnpj") is False  # teto atingido
