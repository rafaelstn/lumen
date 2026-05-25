"""Modelos de consumo de APIs pagas (audit trail imutável).

Regras financeiras (rules/financeiro.md):
- Valor monetário SEMPRE inteiro em CENTAVOS. NUNCA float.
- FONTE DE VERDADE do custo: ConsultaLog.custo_centavos (inteiro, snapshot imutável).
  É calculado no momento da operação como ROUND_HALF_UP(creditos_consumidos *
  preco_por_credito_decimal), arredondando SÓ no fim (não arredonda o preço unitário antes).
- preco_unitario_centavos no log é apenas um indicador inteiro de exibição (arredondado do
  preço de referência); NÃO é a fonte do custo e pode não bater com custo/creditos quando o
  preço por crédito tem fração de centavo (ex.: CNPJá 2,499 c/crédito).
- Audit trail imutável: ConsultaLog nunca é atualizado/apagado, só inserido.
- contexto NUNCA carrega dado sensível em claro (CNPJ vai mascarado ou só job_id/descrição).

Multi-tenant desde o schema: escritorio_id em todo registro (MVP usa o default).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Serviços pagos rastreados. Mantidos como literais simples (não Enum no banco) para não
# travar migration ao adicionar um serviço novo; a validação de valor fica na borda (schemas).
SERVICO_CNPJ = "cnpj"   # CNPJá (dados cadastrais / Simples)
SERVICO_CND = "cnd"     # Infosimples (certidão de regularidade fiscal)
SERVICOS_VALIDOS = (SERVICO_CNPJ, SERVICO_CND)


def _uuid() -> str:
    return str(uuid.uuid4())


class ConsultaLog(Base):
    """Audit trail imutável: um registro por operação paga (ou tentativa com custo).

    Append-only. O custo já vem calculado e gravado em centavos. O saldo restante de
    cada serviço é derivado da soma de creditos_consumidos destes registros.
    """

    __tablename__ = "consulta_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    modulo: Mapped[str] = mapped_column(String(20))      # modulo01 | modulo02
    servico: Mapped[str] = mapped_column(String(10), index=True)  # cnpj | cnd
    operacao: Mapped[str] = mapped_column(String(40))    # due_diligence | enriquecimento | cnd_lote | ...
    quantidade: Mapped[int] = mapped_column(Integer, default=1)   # nº de itens (ex.: CNPJs consultados)
    creditos_consumidos: Mapped[int] = mapped_column(Integer, default=0)
    # Indicador inteiro do preço por crédito (exibição). NÃO é a fonte do custo: quando o
    # preço tem fração de centavo, custo_centavos != creditos_consumidos * este valor.
    preco_unitario_centavos: Mapped[int] = mapped_column(Integer, default=0)
    # FONTE DE VERDADE do custo: ROUND_HALF_UP(creditos_consumidos * preco_por_credito_decimal),
    # arredondado só no fim. Snapshot imutável em centavos.
    custo_centavos: Mapped[int] = mapped_column(Integer, default=0)
    # True quando o nº de créditos é estimado (a origem não devolve o consumo real).
    consumo_estimado: Mapped[bool] = mapped_column(Boolean, default=True)
    # Contexto curto, SEM dado sensível em claro: job_id, descrição, CNPJ mascarado.
    contexto: Mapped[str | None] = mapped_column(String(120), default=None)
