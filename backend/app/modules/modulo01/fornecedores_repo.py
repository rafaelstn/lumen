"""Acesso ao banco de fornecedores (cache persistente de CNPJ ↔ razão social).

Casamento por nome normalizado: análises futuras reusam CNPJ já resolvido, de graça,
sem reconsultar API paga. Toda operação é tolerante (o chamador trata indisponibilidade).
"""
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fornecedor import (
    EnriquecimentoTentativa,
    EscritorioFornecedor,
    Fornecedor,
    FornecedorAlias,
    FornecedorSocio,
)
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


async def buscar(
    session: AsyncSession, q: str, limite: int = 10, escritorio_id: str | None = None
) -> list[Fornecedor]:
    """Busca textual (campo de pesquisa manual gratuita).

    `escritorio_id`=None -> sem filtro de tenant (admin ou flag de auth desligada).
    Com um escritorio_id, restringe aos fornecedores associados a esse escritório (visão
    isolada sobre o cache global).
    """
    norm = _normalizar(q)
    if len(norm) < 3:
        return []
    stmt = select(Fornecedor).where(Fornecedor.nome_normalizado.ilike(f"%{norm}%"))
    stmt = _restringe_por_escritorio(stmt, escritorio_id)
    res = await session.execute(stmt.limit(limite))
    return list(res.scalars())


def _restringe_por_escritorio(stmt, escritorio_id: str | None):
    """Aplica a visão isolada: só os CNPJs associados ao escritório.

    None = sem filtro (admin ou auth desligada). Caso contrário, restringe aos CNPJs
    presentes em escritorio_fornecedor para o escritorio_id (subquery, sem duplicar linhas).
    """
    if escritorio_id is None:
        return stmt
    cnpjs_do_escritorio = (
        select(EscritorioFornecedor.cnpj)
        .where(EscritorioFornecedor.escritorio_id == escritorio_id)
    )
    return stmt.where(Fornecedor.cnpj.in_(cnpjs_do_escritorio))


async def listar_paginado(
    session: AsyncSession, offset: int, limite: int, q: str = "", escritorio_id: str | None = None
) -> tuple[list[Fornecedor], int]:
    """Lista paginada de fornecedores do cache global, com visão isolada por escritório.

    `escritorio_id`=None -> vê TODOS (admin, ou flag de auth desligada = comportamento atual).
    Com um escritorio_id, vê só os fornecedores que ESSE escritório pesquisou (associação em
    escritorio_fornecedor).

    `q` filtra por razão social (nome normalizado) OU por dígitos de CNPJ. Devolve (linhas, total),
    onde total é a contagem do MESMO filtro. NÃO toca em sócios (LGPD): o quadro societário só
    sai no detalhe sob demanda. Ordena por cadastro mais recente primeiro.
    """
    filtros = []
    termo = (q or "").strip()
    if termo:
        norm = _normalizar(termo)
        digitos = "".join(c for c in termo if c.isdigit())
        ors = []
        if norm:
            ors.append(Fornecedor.nome_normalizado.ilike(f"%{norm}%"))
        if digitos:
            ors.append(Fornecedor.cnpj.ilike(f"%{digitos}%"))
        if ors:
            from sqlalchemy import or_

            filtros.append(or_(*ors))

    base = select(Fornecedor)
    cont = select(func.count()).select_from(Fornecedor)
    for f in filtros:
        base = base.where(f)
        cont = cont.where(f)
    base = _restringe_por_escritorio(base, escritorio_id)
    cont = _restringe_por_escritorio(cont, escritorio_id)

    total = (await session.execute(cont)).scalar_one()
    res = await session.execute(
        base.order_by(
            Fornecedor.cadastro_atualizado_em.desc().nullslast(), Fornecedor.id.desc()
        )
        .offset(offset)
        .limit(limite)
    )
    return list(res.scalars()), int(total)


async def associar_escritorio(session: AsyncSession, escritorio_id: str, cnpj: str) -> None:
    """Registra (idempotente) que um escritório pesquisou/usou um CNPJ.

    É o que dá a VISÃO ISOLADA sobre o cache global: o cadastro fica compartilhado, mas a
    listagem do escritório só mostra os CNPJs que ele associou. Tolerante: vazio é no-op;
    par já existente é no-op (UNIQUE escritorio_id+cnpj).
    """
    escritorio_id = (escritorio_id or "").strip()
    cnpj = (cnpj or "").strip()
    if not escritorio_id or not cnpj:
        return
    existe = await session.execute(
        select(EscritorioFornecedor.id).where(
            EscritorioFornecedor.escritorio_id == escritorio_id,
            EscritorioFornecedor.cnpj == cnpj,
        )
    )
    if existe.scalar_one_or_none() is not None:
        return
    session.add(EscritorioFornecedor(escritorio_id=escritorio_id, cnpj=cnpj))
    await session.commit()


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


async def registrar_tentativa(
    session: AsyncSession, escritorio_id: str, nome_entrada: str, resultado: str
) -> None:
    """Upsert idempotente de uma tentativa de enriquecimento SEM sucesso, por escritório.

    Chave de negócio: (escritorio_id, nome_normalizado). Se já existe, incrementa `tentativas`
    e atualiza `ultima_tentativa`/`resultado` (não duplica). Tolerante: campo vazio é no-op.
    Só registrar para 'nao_encontrado'/'ambiguo' (caminho de sucesso vira alias, não passa aqui).
    """
    escritorio_id = (escritorio_id or "").strip()
    if not escritorio_id or not nome_entrada or not resultado:
        return
    norm = _normalizar(nome_entrada)
    if not norm:
        return
    res = await session.execute(
        select(EnriquecimentoTentativa).where(
            EnriquecimentoTentativa.escritorio_id == escritorio_id,
            EnriquecimentoTentativa.nome_normalizado == norm,
        )
    )
    existente = res.scalar_one_or_none()
    if existente:
        existente.tentativas += 1
        existente.resultado = resultado
        existente.ultima_tentativa = datetime.now(timezone.utc)
    else:
        session.add(
            EnriquecimentoTentativa(
                escritorio_id=escritorio_id,
                nome_normalizado=norm,
                resultado=resultado,
                tentativas=1,
                ultima_tentativa=datetime.now(timezone.utc),
            )
        )
    await session.commit()


async def nomes_ja_tentados(session: AsyncSession, escritorio_id: str) -> set[str]:
    """Conjunto de nomes normalizados já tentados SEM sucesso por um escritório.

    Usado pelo enriquecimento para PULAR esses nomes (não queimar crédito repesquisando).
    Isolado por escritório: a lista de um tenant não vaza para outro. Vazio se escritório
    inválido. Tolerante: o chamador trata indisponibilidade de banco.
    """
    escritorio_id = (escritorio_id or "").strip()
    if not escritorio_id:
        return set()
    res = await session.execute(
        select(EnriquecimentoTentativa.nome_normalizado).where(
            EnriquecimentoTentativa.escritorio_id == escritorio_id
        )
    )
    return {row for row in res.scalars()}


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
