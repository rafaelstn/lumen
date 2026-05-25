"""Acesso ao banco de fornecedores (cache persistente de CNPJ ↔ razão social).

Casamento por nome normalizado: análises futuras reusam CNPJ já resolvido, de graça,
sem reconsultar API paga. Toda operação é tolerante (o chamador trata indisponibilidade).
"""
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fornecedor import Fornecedor, FornecedorAlias, FornecedorSocio
from app.modules.modulo01.cnpj_lookup import _normalizar

# Campos escalares do cadastro completo que o salvar_cadastro persiste no Fornecedor.
# (sócios vão em tabela separada; razao_social/origem/nome_normalizado têm tratamento próprio.)
_CAMPOS_CADASTRO = (
    "nome_fantasia", "logradouro", "numero", "complemento", "bairro", "municipio", "uf", "cep",
    "telefone_principal", "email_principal", "contatos",
    "cnae_principal_codigo", "cnae_principal_descricao", "cnaes_secundarios",
    "porte", "natureza_juridica", "situacao_cadastral", "data_abertura", "capital_social_centavos",
)


async def buscar_exato(session: AsyncSession, nome: str) -> Fornecedor | None:
    """Casa pela razão social normalizada (uso automático no processamento)."""
    norm = _normalizar(nome)
    if not norm:
        return None
    res = await session.execute(
        select(Fornecedor).where(Fornecedor.nome_normalizado == norm).limit(1)
    )
    return res.scalar_one_or_none()


async def _fornecedor_por_cnpj(session: AsyncSession, cnpj: str) -> Fornecedor | None:
    res = await session.execute(select(Fornecedor).where(Fornecedor.cnpj == cnpj).limit(1))
    return res.scalar_one_or_none()


async def casar(session: AsyncSession, nome_entrada: str) -> Fornecedor | None:
    """Resolve um nome de entrada para um Fornecedor, de graça (sem API).

    1. Procura PRIMEIRO no alias (grafia de entrada -> cnpj). É o caminho que evita
       reconsulta: o nome do arquivo casa mesmo divergindo do nome oficial salvo.
    2. Fallback: casa pela razão social normalizada do próprio Fornecedor.

    A razão social de exibição sempre vem do Fornecedor (pelo CNPJ).
    """
    norm = _normalizar(nome_entrada)
    if not norm:
        return None
    res = await session.execute(
        select(FornecedorAlias).where(FornecedorAlias.nome_normalizado == norm).limit(1)
    )
    alias = res.scalar_one_or_none()
    if alias:
        forn = await _fornecedor_por_cnpj(session, alias.cnpj)
        if forn:
            return forn
        # Alias sem Fornecedor correspondente (caso raro): ainda casa pelo CNPJ do alias.
        return Fornecedor(cnpj=alias.cnpj, razao_social=nome_entrada, nome_normalizado=norm)
    return await buscar_exato(session, nome_entrada)


async def registrar_alias(session: AsyncSession, nome_entrada: str, cnpj: str) -> None:
    """Upsert idempotente do alias (grafia de entrada normalizada -> cnpj).

    Tolerante: nome/cnpj vazio é no-op. Se a grafia já existe, atualiza o CNPJ
    (não duplica). É o que torna a re-análise gratuita para nomes já vistos.
    """
    if not nome_entrada or not cnpj:
        return
    norm = _normalizar(nome_entrada)
    if not norm:
        return
    res = await session.execute(
        select(FornecedorAlias).where(FornecedorAlias.nome_normalizado == norm)
    )
    existente = res.scalar_one_or_none()
    if existente:
        existente.cnpj = cnpj
    else:
        session.add(FornecedorAlias(nome_normalizado=norm, cnpj=cnpj))
    await session.commit()


async def buscar(session: AsyncSession, q: str, limite: int = 10) -> list[Fornecedor]:
    """Busca textual (campo de pesquisa manual gratuita)."""
    norm = _normalizar(q)
    if len(norm) < 3:
        return []
    res = await session.execute(
        select(Fornecedor).where(Fornecedor.nome_normalizado.ilike(f"%{norm}%")).limit(limite)
    )
    return list(res.scalars())


async def registrar_cnd(
    session: AsyncSession,
    cnpj: str,
    status: str,
    quando: datetime | None = None,
    razao_social: str | None = None,
) -> None:
    """Registra, por CNPJ, quando e qual foi a última consulta de CND concluída.

    Metadado de controle (não é fonte de verdade da regularidade). Idempotente por CNPJ.
    Tolerante: cnpj/status vazio é no-op. Não chamar com FALHA: o chamador só registra
    quando obteve um status real, para não mascarar o que é recente.

    Se o CNPJ ainda não existe no banco de fornecedores (ex.: CND consultada antes de o
    cadastro ter sido salvo), cria um registro mínimo. Não sobrescreve uma razão social
    boa já existente: só preenche a razão se vier uma e o registro ainda não tiver.
    """
    if not cnpj or not status:
        return
    quando = quando or datetime.now(timezone.utc)
    existente = await _fornecedor_por_cnpj(session, cnpj)
    if existente:
        existente.cnd_ultima_consulta = quando
        existente.cnd_ultimo_status = status
    else:
        nome = (razao_social or "").strip() or f"CNPJ {cnpj}"
        session.add(
            Fornecedor(
                cnpj=cnpj,
                razao_social=nome,
                nome_normalizado=_normalizar(nome),
                origem="cnd",
                cnd_ultima_consulta=quando,
                cnd_ultimo_status=status,
            )
        )
    await session.commit()


async def upsert(session: AsyncSession, cnpj: str, razao_social: str, origem: str = "manual") -> None:
    """Salva/atualiza o fornecedor no cache (idempotente por CNPJ)."""
    if not cnpj or not razao_social:
        return
    res = await session.execute(select(Fornecedor).where(Fornecedor.cnpj == cnpj))
    existente = res.scalar_one_or_none()
    if existente:
        existente.razao_social = razao_social
        existente.nome_normalizado = _normalizar(razao_social)
        existente.origem = origem
    else:
        session.add(
            Fornecedor(
                cnpj=cnpj,
                razao_social=razao_social,
                nome_normalizado=_normalizar(razao_social),
                origem=origem,
            )
        )
    await session.commit()


def _aplicar_escalares(forn: Fornecedor, cadastro: dict) -> None:
    """Copia os campos escalares do cadastro para o Fornecedor, sem apagar bom dado existente.

    Só sobrescreve quando o cadastro novo traz valor não-vazio (None/"" não apaga o que já
    estava bom). Mantém o cache resiliente a retornos parciais do provedor.
    """
    for campo in _CAMPOS_CADASTRO:
        novo = cadastro.get(campo)
        if novo not in (None, "", [], {}):
            setattr(forn, campo, novo)


async def salvar_cadastro(session: AsyncSession, cadastro: dict, origem: str = "cnpja") -> None:
    """Persiste o cadastro COMPLETO de um CNPJ (fornecedor + sócios), idempotente por CNPJ.

    Re-gravar atualiza (não duplica). O conjunto de sócios do CNPJ é SUBSTITUÍDO inteiro
    (delete + insert) para refletir o quadro societário atual sem acumular. Tolerante:
    cadastro sem CNPJ é no-op. Não loga sócios (dado pessoal de terceiros, LGPD).

    Espera o dict de cnpj_lookup.extrair_cadastro: chaves escalares + 'razao_social' +
    'socios': [{'nome','qualificacao','desde'}, ...].
    """
    if not cadastro:
        return
    cnpj = (cadastro.get("cnpj") or "").strip()
    if not cnpj:
        return

    forn = await _fornecedor_por_cnpj(session, cnpj)
    razao = (cadastro.get("razao_social") or "").strip()
    if forn is None:
        nome = razao or f"CNPJ {cnpj}"
        forn = Fornecedor(cnpj=cnpj, razao_social=nome, nome_normalizado=_normalizar(nome), origem=origem)
        session.add(forn)
    else:
        if razao:  # não sobrescreve uma razão boa por vazio
            forn.razao_social = razao
            forn.nome_normalizado = _normalizar(razao)
        forn.origem = origem

    _aplicar_escalares(forn, cadastro)
    forn.cadastro_atualizado_em = datetime.now(timezone.utc)

    # Sócios: substitui o conjunto inteiro do CNPJ (idempotente, sem duplicar).
    socios = cadastro.get("socios") or []
    await session.execute(delete(FornecedorSocio).where(FornecedorSocio.cnpj == cnpj))
    for s in socios:
        nome_socio = (s.get("nome") or "").strip()
        if not nome_socio:
            continue
        session.add(
            FornecedorSocio(
                cnpj=cnpj,
                nome=nome_socio,
                qualificacao=(s.get("qualificacao") or None),
                desde=(s.get("desde") or None),
            )
        )
    await session.commit()


async def obter_cadastro_completo(session: AsyncSession, cnpj: str) -> dict | None:
    """Lê o cadastro completo de um CNPJ (escalares + sócios) para o endpoint de detalhe.

    Retorna None se o CNPJ não existir no banco. Os sócios (dado pessoal de terceiros) só
    são devolvidos aqui, no detalhe sob demanda — nunca em listagens/buscas amplas.
    """
    cnpj = (cnpj or "").strip()
    if not cnpj:
        return None
    forn = await _fornecedor_por_cnpj(session, cnpj)
    if forn is None:
        return None
    res = await session.execute(
        select(FornecedorSocio).where(FornecedorSocio.cnpj == cnpj).order_by(FornecedorSocio.id)
    )
    socios = list(res.scalars())
    return {
        "cnpj": forn.cnpj,
        "razao_social": forn.razao_social,
        "nome_fantasia": forn.nome_fantasia,
        "origem": forn.origem,
        "endereco": {
            "logradouro": forn.logradouro,
            "numero": forn.numero,
            "complemento": forn.complemento,
            "bairro": forn.bairro,
            "municipio": forn.municipio,
            "uf": forn.uf,
            "cep": forn.cep,
        },
        "contato": {
            "telefone_principal": forn.telefone_principal,
            "email_principal": forn.email_principal,
            "telefones": (forn.contatos or {}).get("telefones", []) if forn.contatos else [],
            "emails": (forn.contatos or {}).get("emails", []) if forn.contatos else [],
        },
        "atividade": {
            "cnae_principal_codigo": forn.cnae_principal_codigo,
            "cnae_principal_descricao": forn.cnae_principal_descricao,
            "cnaes_secundarios": forn.cnaes_secundarios or [],
            "porte": forn.porte,
            "natureza_juridica": forn.natureza_juridica,
            "situacao_cadastral": forn.situacao_cadastral,
            "data_abertura": forn.data_abertura,
            "capital_social_centavos": (
                int(forn.capital_social_centavos) if forn.capital_social_centavos is not None else None
            ),
        },
        "cadastro_atualizado_em": (
            forn.cadastro_atualizado_em.isoformat() if forn.cadastro_atualizado_em else None
        ),
        "cnd": {
            "ultima_consulta": forn.cnd_ultima_consulta.isoformat() if forn.cnd_ultima_consulta else None,
            "ultimo_status": forn.cnd_ultimo_status,
        },
        "socios": [
            {"nome": s.nome, "qualificacao": s.qualificacao, "desde": s.desde} for s in socios
        ],
    }
