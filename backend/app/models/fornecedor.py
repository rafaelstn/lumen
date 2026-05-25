"""Modelo do banco de fornecedores: cache persistente e global do cadastro de CNPJ.

Guarda a identidade (estável) MAIS o cadastro completo da Receita Federal que o provedor
(CNPJá /office) retorna por 1 crédito já pago na consulta: endereço, contato, atividade,
porte, situação cadastral, capital social e o quadro societário (tabela separada). Gravar
em vez de descartar evita reconsultar API paga para reusar o cadastro.

A CND/regularidade NÃO é persistida aqui porque é volátil (sempre consultada fresca); só
guardamos um metadado de controle da última consulta. Sócios são dado pessoal de terceiros
(LGPD): ficam em FornecedorSocio, fora de logs e fora de respostas amplas/listagens.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Fornecedor(Base):
    __tablename__ = "fornecedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(255))
    # Nome normalizado (uppercase, sem acento/pontuação) para casamento por razão social.
    nome_normalizado: Mapped[str] = mapped_column(String(255), index=True)
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | cnpja | importado | cnd
    # Nome fantasia (alias comercial), quando o provedor retorna.
    nome_fantasia: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Endereço (bloco 1) ---
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # --- Contato (bloco 2) ---
    # Principais como escalares consultáveis; o restante em JSON tolerante (múltiplos).
    telefone_principal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_principal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # {"telefones": ["1133334444", ...], "emails": ["a@x.com", ...]} — todos os contatos.
    contatos: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Atividade / porte / situação (bloco 3) ---
    cnae_principal_codigo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cnae_principal_descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # [{"codigo": "...", "descricao": "..."}, ...] — CNAEs secundários.
    cnaes_secundarios: Mapped[list | None] = mapped_column(JSON, nullable=True)
    porte: Mapped[str | None] = mapped_column(String(40), nullable=True)
    natureza_juridica: Mapped[str | None] = mapped_column(String(255), nullable=True)
    situacao_cadastral: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_abertura: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO YYYY-MM-DD
    # Capital social em centavos (inteiro) — dinheiro nunca em float (regra financeiro.md).
    capital_social_centavos: Mapped[int | None] = mapped_column(Numeric(18, 0), nullable=True)

    # Carimbo da última gravação do cadastro completo (controle de frescor do cache).
    cadastro_atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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


class FornecedorSocio(Base):
    """Quadro societário de um fornecedor (1 fornecedor : N sócios).

    ATENÇÃO LGPD: nome de sócio é DADO PESSOAL DE TERCEIRO. Esta tabela é deliberadamente
    separada do Fornecedor para que o endpoint de detalhe a devolva sob demanda e as
    listagens/buscas amplas NÃO a toquem. Nunca logar nome de sócio.
    """

    __tablename__ = "fornecedor_socios"

    id: Mapped[int] = mapped_column(primary_key=True)
    # FK lógica por CNPJ (a chave de negócio do cadastro). Idempotência: o conjunto de
    # sócios de um CNPJ é substituído inteiro a cada regravação (não acumula histórico).
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    nome: Mapped[str] = mapped_column(String(255))
    qualificacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desde: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ISO YYYY-MM-DD, se vier


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


class EscritorioFornecedor(Base):
    """Associação escritório <-> CNPJ pesquisado (visão isolada sobre o cache global).

    O cadastro de CNPJ continua num cache GLOBAL e compartilhado (tabela `fornecedores`):
    se um escritório já pesquisou um CNPJ, outro reusa sem repagar a API. Mas cada
    escritório só VÊ os fornecedores que ele mesmo pesquisou. Esta tabela registra esse
    vínculo (quem viu o quê). O admin enxerga todos, então não depende dela.

    Idempotente pelo par (escritorio_id, cnpj): registrar de novo é no-op.
    """

    __tablename__ = "escritorio_fornecedor"
    __table_args__ = (
        UniqueConstraint("escritorio_id", "cnpj", name="uq_escritorio_fornecedor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    escritorio_id: Mapped[str] = mapped_column(String(36), index=True)
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
