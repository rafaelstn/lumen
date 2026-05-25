"""Modelo do banco de fornecedores: cache persistente e global de CNPJ ↔ razão social.

Guarda só a identidade (estável). A CND/regularidade NÃO é persistida aqui porque é
volátil — sempre consultada fresca. Reuso entre análises evita reconsultar API paga.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Fornecedor(Base):
    __tablename__ = "fornecedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(255))
    # Nome normalizado (uppercase, sem acento/pontuação) para casamento por razão social.
    nome_normalizado: Mapped[str] = mapped_column(String(255), index=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | cnpja | importado
    # Metadado de CONTROLE da última consulta de CND deste CNPJ. NÃO é fonte de verdade:
    # a CND continua volátil e sempre reconsultável. Guardamos só quando/qual foi a última
    # consulta concluída para a UI sinalizar "CND consultada em X, estava Y" e o usuário
    # decidir se vale gastar reconsultando. FALHA não atualiza (não mascara o que é recente).
    cnd_ultima_consulta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cnd_ultimo_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FornecedorAlias(Base):
    """Mapeia uma grafia de nome de entrada (do Livro de Entradas) para um CNPJ já resolvido.

    Um mesmo CNPJ pode ter várias grafias de entrada (arquivos/clientes diferentes escrevem
    o nome diferente do nome oficial da Receita). Sem o alias, a re-análise não casa pelo
    nome do arquivo contra a razão social salva e o sistema reconsulta a API paga à toa.
    Casar pelo alias é de graça: nome de entrada normalizado -> cnpj.
    """

    __tablename__ = "fornecedor_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nome de entrada normalizado (uppercase, sem acento/pontuação). UNIQUE: uma grafia -> um CNPJ.
    nome_normalizado: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
