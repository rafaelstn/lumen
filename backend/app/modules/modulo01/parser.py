"""Leitura e join dos arquivos XLS (Livro de Entradas + Cadastro). Fase 2.

Estrutura real do arquivo de Entradas (validada com idesan.xls):
- 5 linhas de cabeçalho; dados a partir da linha 6 (índice 5).
- Linha de dado válida: coluna 0 (código do lançamento) é numérica.
- Linhas ignoradas: totalizadores ("Total Fornecedor"), em branco, subtotais.

Valores monetários são tratados como Decimal (nunca float) para precisão fiscal.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd

from app.config import settings

CFOPS_INTERESSE = ["1101", "1102", "1124", "1122"]

# Índices de coluna no arquivo de Entradas (base 0).
COL_COD_LANCAMENTO = 0
COL_DATA = 2
COL_COD_FORN = 10
COL_FORNECEDOR = 12
COL_CFOP = 14
COL_VALOR_CONTABIL = 20
COL_TIPO_IMPOSTO = 23
COL_BASE_CALCULO = 25
COL_ALIQUOTA = 27
COL_VALOR_ICMS = 28

HEADER_ROWS = 5
_EXCEL_EPOCH = datetime(1899, 12, 30)  # sistema de datas 1900 do Excel


class ParserError(Exception):
    """Erro de parsing com mensagem legível para o usuário."""


def _to_decimal(value) -> Decimal:
    """Converte um valor de célula em Decimal com 2 casas (ROUND_HALF_UP).

    Célula vazia/NaN vira 0.00. Célula com texto não-numérico (dado sujo) também
    vira 0.00 em vez de derrubar todo o processamento.
    """
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


# Valores monetários e alíquotas usam a mesma conversão tolerante.
_money = _to_decimal
_rate = _to_decimal


def _cfop_str(value) -> str:
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value).strip()


def _cod_forn_str(value) -> str:
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value).strip()


def _excel_date_iso(serial):
    # bool é subclasse de int; exclui para não virar data espúria.
    if isinstance(serial, bool) or not isinstance(serial, (int, float)) or pd.isna(serial):
        return None
    return (_EXCEL_EPOCH + timedelta(days=float(serial))).date().isoformat()


def _read_excel(filepath: str) -> pd.DataFrame:
    """Lê o arquivo escolhendo o engine pela extensão: .xls (xlrd) ou .xlsx (openpyxl)."""
    engine = "openpyxl" if filepath.lower().endswith(".xlsx") else "xlrd"
    raw = pd.read_excel(filepath, header=None, engine=engine, dtype=object)
    if len(raw) > settings.max_linhas_planilha:
        raise ParserError(
            f"Planilha excede o limite de {settings.max_linhas_planilha} linhas. "
            "Verifique se o arquivo corresponde ao relatório esperado."
        )
    return raw


def parse_entradas(filepath: str) -> pd.DataFrame:
    """Lê o Livro de Entradas e devolve os lançamentos de ICMS dos CFOPs de interesse.

    Colunas retornadas: cod_forn, nome_forn, data, cfop, valor_contabil,
    base_calculo, aliquota, valor_icms.
    """
    raw = _read_excel(filepath)

    registros = []
    for i in range(HEADER_ROWS, len(raw)):
        row = raw.iloc[i]
        cod_lanc = row[COL_COD_LANCAMENTO]
        # Linha de dado válida exige código de lançamento numérico.
        if not isinstance(cod_lanc, (int, float)) or pd.isna(cod_lanc):
            continue

        tipo = str(row[COL_TIPO_IMPOSTO]).strip() if pd.notna(row[COL_TIPO_IMPOSTO]) else ""
        cfop = _cfop_str(row[COL_CFOP])
        if tipo != "ICMS" or cfop not in CFOPS_INTERESSE:
            continue

        registros.append(
            {
                "cod_forn": _cod_forn_str(row[COL_COD_FORN]),
                "nome_forn": str(row[COL_FORNECEDOR]).strip(),
                "data": _excel_date_iso(row[COL_DATA]),
                "cfop": cfop,
                "valor_contabil": _money(row[COL_VALOR_CONTABIL]),
                "base_calculo": _money(row[COL_BASE_CALCULO]),
                "aliquota": _rate(row[COL_ALIQUOTA]),
                "valor_icms": _money(row[COL_VALOR_ICMS]),
            }
        )

    if not registros:
        raise ParserError(
            "Nenhum lançamento de ICMS encontrado nos CFOPs de interesse "
            f"({', '.join(CFOPS_INTERESSE)}). Verifique se o arquivo é o Livro de Entradas correto."
        )

    return pd.DataFrame(registros)


def parse_cadastro(filepath: str) -> pd.DataFrame:
    """Lê o Cadastro de Fornecedores e devolve cod_forn, nome_forn e cnpj (14 dígitos).

    O layout exato do relatório de cadastro do ERP será confirmado quando o arquivo
    for disponibilizado; esta função detecta as colunas de código e CNPJ de forma
    tolerante. Retorna DataFrame vazio padronizado se nada for reconhecido.
    """
    raw = _read_excel(filepath)

    registros = []
    for i in range(len(raw)):
        row = raw.iloc[i]
        cod = None
        cnpj = None
        nome = None
        for value in row:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            texto = str(value).strip()
            digitos = re.sub(r"\D", "", texto)
            if len(digitos) == 14 and cnpj is None:
                cnpj = digitos
            # Código do fornecedor: aceita número inteiro OU string de dígitos curta
            # (o ERP pode exportar o código como texto), normalizado igual às Entradas.
            elif cod is None and isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer():
                cod = str(int(value))
            elif cod is None and texto.isdigit() and 0 < len(texto) <= 6:
                cod = str(int(texto))
            elif nome is None and any(c.isalpha() for c in texto):
                nome = texto
        if cod and cnpj:
            registros.append({"cod_forn": cod, "nome_forn": nome or "", "cnpj": cnpj})

    return pd.DataFrame(registros, columns=["cod_forn", "nome_forn", "cnpj"])


def merge_fornecedores(df_entradas: pd.DataFrame, df_cadastro: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agrega os lançamentos por fornecedor e anexa o CNPJ do cadastro (se houver).

    Um registro por fornecedor com: cod_forn, nome_forn, cnpj, total_compras,
    total_valor_icms, aliquota_max, aliquota_efetiva_pct, n_lancamentos, cnpj_pendente.
    """
    cnpj_por_cod = {}
    if df_cadastro is not None and not df_cadastro.empty:
        cnpj_por_cod = dict(zip(df_cadastro["cod_forn"], df_cadastro["cnpj"]))

    cadastro_fornecido = df_cadastro is not None and not df_cadastro.empty

    fornecedores = []
    for cod_forn, grupo in df_entradas.groupby("cod_forn"):
        total_compras = sum((v for v in grupo["valor_contabil"]), Decimal("0.00"))
        total_icms = sum((v for v in grupo["valor_icms"]), Decimal("0.00"))
        aliquota_max = max(grupo["aliquota"])
        # Estorno/devolução aparece como lançamento negativo; sinaliza para revisão.
        tem_estorno = any(v < Decimal("0.00") for v in grupo["valor_contabil"]) or any(
            v < Decimal("0.00") for v in grupo["valor_icms"]
        )
        if total_compras > 0:
            aliquota_efetiva = (total_icms / total_compras * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            aliquota_efetiva = Decimal("0.00")

        cnpj = cnpj_por_cod.get(cod_forn)
        fornecedores.append(
            {
                "cod_forn": cod_forn,
                "nome_forn": grupo["nome_forn"].iloc[0],
                "cnpj": cnpj,
                # Distingue "não houve cadastro" de "havia cadastro mas não casou".
                "cnpj_pendente": cnpj is None,
                "cnpj_nao_casado": cadastro_fornecido and cnpj is None,
                "total_compras": total_compras,
                "total_valor_icms": total_icms,
                "aliquota_max": aliquota_max,
                "aliquota_efetiva_pct": aliquota_efetiva,
                "tem_estorno": tem_estorno,
                "n_lancamentos": len(grupo),
            }
        )

    return pd.DataFrame(fornecedores)
