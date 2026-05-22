"""Leitura e join dos arquivos XLS (Livro de Entradas + Cadastro). Fase 2."""
import pandas as pd

CFOPS_INTERESSE = ["1101", "1102", "1124", "1122"]


def parse_entradas(filepath: str) -> pd.DataFrame:
    raise NotImplementedError("Implementado na Fase 2")


def parse_cadastro(filepath: str) -> pd.DataFrame:
    raise NotImplementedError("Implementado na Fase 2")


def merge_fornecedores(df_entradas: pd.DataFrame, df_cadastro: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError("Implementado na Fase 2")
