import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  Pencil,
  X,
  ShieldAlert,
  ShieldCheck,
  Search,
  Database,
  Loader2,
  CornerDownLeft,
  ChevronDown,
  ChevronUp,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  FileText,
  ExternalLink,
  RotateCcw,
} from "lucide-react";
import {
  moeda,
  percentual,
  CORES_GRUPO,
  statusCndMeta,
  riscoMeta,
  validadeCnd,
  formatarCnpj,
} from "../utils/format.js";
import { buscarFornecedores } from "../services/api.js";

// Opções de filtro. O valor "" significa "todos".
const OPCOES_GRUPO = [
  { valor: "", rotulo: "Todos os grupos" },
  { valor: "A", rotulo: "Grupo A" },
  { valor: "B", rotulo: "Grupo B" },
  { valor: "C", rotulo: "Grupo C" },
  { valor: "INDEFINIDO", rotulo: "Indefinido" },
];

const OPCOES_CND = [
  { valor: "", rotulo: "Toda CND" },
  { valor: "NEGATIVA", rotulo: "Negativa / regular" },
  { valor: "POSITIVA_EFEITO_NEGATIVA", rotulo: "Positiva c/ efeito negativo" },
  { valor: "POSITIVA", rotulo: "Positiva (devedor)" },
  { valor: "FALHA", rotulo: "Falha na consulta" },
  { valor: "SEM_CONSULTA", rotulo: "Sem consulta" },
];

const OPCOES_RISCO = [
  { valor: "", rotulo: "Todo risco" },
  { valor: "ALTO", rotulo: "Risco alto" },
  { valor: "MEDIO", rotulo: "Risco médio" },
  { valor: "BAIXO", rotulo: "Risco baixo" },
];

// Colunas ordenáveis: cada uma extrai o número comparável do fornecedor.
const ORDENAVEIS = {
  total_compras: (f) => Number(f.total_compras) || 0,
  aliquota_max: (f) => Number(f.aliquota_max) || 0,
  total_valor_icms: (f) => Number(f.total_valor_icms) || 0,
};

const FILTRO_VAZIO = { grupo: "", cnd: "", risco: "" };

// Tamanhos de página oferecidos no seletor. 20 é o padrão.
const TAMANHOS_PAGINA = [10, 20, 50, 100];
const TAMANHO_PADRAO = 20;

// Tabela de fornecedores classificados. Linhas de risco ALTO ganham faixa
// vermelha à esquerda; CNPJ pendente abre edição inline (razão social + CNPJ,
// o backend valida o dígito verificador). Busca, filtros (grupo/CND/risco) e
// ordenação por coluna são combináveis e rodam client-side.
export default function FornecedoresTable({ fornecedores, onSalvarCnpj, salvando }) {
  const [editando, setEditando] = useState(null);
  const [cnpj, setCnpj] = useState("");
  const [razao, setRazao] = useState("");
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState(FILTRO_VAZIO);
  // ordem: { coluna, dir }. coluna null = ordem natural (como veio do backend).
  const [ordem, setOrdem] = useState({ coluna: null, dir: "desc" });
  const [expandido, setExpandido] = useState(null);
  // Paginação client-side, opera sobre a lista já filtrada/ordenada.
  const [pagina, setPagina] = useState(1);
  const [tamanhoPagina, setTamanhoPagina] = useState(TAMANHO_PADRAO);

  // Status efetivo de CND para filtrar: usa o status atual, cai pro cache, e
  // classifica como SEM_CONSULTA quando não há nenhum dos dois.
  function statusCndEfetivo(f) {
    return f.status_cnd || f.cnd_status_cache || "SEM_CONSULTA";
  }

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const base = fornecedores.filter((f) => {
      if (filtro.grupo && (f.grupo ?? "INDEFINIDO") !== filtro.grupo) return false;
      if (filtro.risco && (f.risco_2027 ?? "") !== filtro.risco) return false;
      if (filtro.cnd && statusCndEfetivo(f) !== filtro.cnd) return false;
      if (!q) return true;
      return (
        (f.nome_forn ?? "").toLowerCase().includes(q) ||
        (f.cnpj ?? "").toLowerCase().includes(q)
      );
    });

    if (!ordem.coluna) return base;
    const get = ORDENAVEIS[ordem.coluna];
    const fator = ordem.dir === "asc" ? 1 : -1;
    // Cópia antes de ordenar para não mutar o array do pai.
    return [...base].sort((a, b) => (get(a) - get(b)) * fator);
  }, [fornecedores, busca, filtro, ordem]);

  // Reset para a página 1 sempre que muda o que determina o conjunto exibido:
  // busca, filtros, ordenação ou tamanho de página. Evita parar numa página
  // que deixou de existir.
  useEffect(() => {
    setPagina(1);
  }, [busca, filtro, ordem, tamanhoPagina]);

  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / tamanhoPagina));
  // Clamp defensivo: se a lista filtrada encolheu por outro caminho, garante
  // que a página atual ainda é válida sem aguardar um novo render.
  const paginaAtual = Math.min(pagina, totalPaginas);
  const inicio = (paginaAtual - 1) * tamanhoPagina;
  const fim = inicio + tamanhoPagina;
  const paginados = useMemo(() => filtrados.slice(inicio, fim), [filtrados, inicio, fim]);

  // Índices 1-based para o indicador "X a Y de N" (0 a 0 quando vazio).
  const primeiroItem = filtrados.length === 0 ? 0 : inicio + 1;
  const ultimoItem = Math.min(fim, filtrados.length);

  const totalRiscoAlto = fornecedores.filter((f) => f.risco_2027 === "ALTO").length;
  const temFiltro = busca.trim() !== "" || filtro.grupo || filtro.cnd || filtro.risco;

  function limpar() {
    setBusca("");
    setFiltro(FILTRO_VAZIO);
  }

  // Clique no cabeçalho: 1º clique ordena desc, 2º alterna asc, 3º volta ao natural.
  function ordenarPor(coluna) {
    setOrdem((o) => {
      if (o.coluna !== coluna) return { coluna, dir: "desc" };
      if (o.dir === "desc") return { coluna, dir: "asc" };
      return { coluna: null, dir: "desc" };
    });
  }

  function abrir(f) {
    setEditando(f.cod_forn);
    // Pré-preenche com o CNPJ atual (caso de revisar/confirmar um não confirmado);
    // vazio quando ainda não há CNPJ (caso de resolver do zero).
    setCnpj(f.cnpj || "");
    setRazao(f.nome_forn || "");
  }

  function salvar(f) {
    onSalvarCnpj(f.cod_forn, { cnpj, razaoSocial: razao });
    setEditando(null);
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-panel">
      <div className="flex flex-col gap-3 border-b border-slate-100 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-display text-lg font-600 text-ink-900">Fornecedores</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {filtrados.length} de {fornecedores.length} exibidos
            </p>
          </div>
          <div className="relative sm:w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar fornecedor ou CNPJ"
              aria-label="Buscar fornecedor"
              className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-3 text-sm placeholder:text-slate-400 focus:border-jade-400"
            />
          </div>
        </div>

        {/* Linha de filtros e ordenação, combinável com a busca acima. */}
        <div className="flex flex-wrap items-center gap-2">
          <FiltroSelect
            label="Grupo"
            value={filtro.grupo}
            onChange={(v) => setFiltro((s) => ({ ...s, grupo: v }))}
            opcoes={OPCOES_GRUPO}
          />
          <FiltroSelect
            label="CND"
            value={filtro.cnd}
            onChange={(v) => setFiltro((s) => ({ ...s, cnd: v }))}
            opcoes={OPCOES_CND}
          />
          <FiltroSelect
            label="Risco 2027"
            value={filtro.risco}
            onChange={(v) => setFiltro((s) => ({ ...s, risco: v }))}
            opcoes={OPCOES_RISCO}
          />

          {totalRiscoAlto > 0 && (
            <button
              type="button"
              aria-pressed={filtro.risco === "ALTO"}
              onClick={() =>
                setFiltro((s) => ({ ...s, risco: s.risco === "ALTO" ? "" : "ALTO" }))
              }
              className={[
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-500 transition-colors",
                filtro.risco === "ALTO"
                  ? "border-signal-300 bg-signal-600 text-white"
                  : "border-signal-200 bg-signal-50 text-signal-700 hover:bg-signal-100",
              ].join(" ")}
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              Risco alto ({totalRiscoAlto})
            </button>
          )}

          {temFiltro && (
            <button
              type="button"
              onClick={limpar}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-xs font-500 text-slate-600 transition-colors hover:bg-slate-50"
            >
              <X className="h-3.5 w-3.5" /> Limpar filtros
            </button>
          )}
        </div>
      </div>

      <div className="scroll-thin overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[0.7rem] uppercase tracking-wider text-slate-500">
              <th className="px-4 py-3 font-600">Grupo</th>
              <th className="px-4 py-3 font-600">Fornecedor</th>
              <th className="px-4 py-3 font-600">CNPJ</th>
              <th className="px-4 py-3 font-600">CND</th>
              <th className="px-4 py-3 font-600">Risco 2027</th>
              <ThOrdenavel
                rotulo="Compras"
                coluna="total_compras"
                ordem={ordem}
                onOrdenar={ordenarPor}
              />
              <ThOrdenavel
                rotulo="Alíq. máx."
                coluna="aliquota_max"
                ordem={ordem}
                onOrdenar={ordenarPor}
              />
              <ThOrdenavel
                rotulo="ICMS aprov."
                coluna="total_valor_icms"
                ordem={ordem}
                onOrdenar={ordenarPor}
              />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {paginados.map((f) => (
              <LinhaFornecedor
                key={f.cod_forn}
                f={f}
                emEdicao={editando === f.cod_forn}
                expandido={expandido === f.cod_forn}
                onToggleDetalhe={() =>
                  setExpandido((id) => (id === f.cod_forn ? null : f.cod_forn))
                }
                cnpj={cnpj}
                razao={razao}
                setCnpj={setCnpj}
                setRazao={setRazao}
                salvando={salvando}
                onAbrir={() => abrir(f)}
                onSalvar={() => salvar(f)}
                onCancelar={() => setEditando(null)}
              />
            ))}
            {filtrados.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-12 text-center text-sm text-slate-400">
                  Nenhum fornecedor corresponde ao filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {filtrados.length > 0 && (
        <PaginacaoRodape
          primeiroItem={primeiroItem}
          ultimoItem={ultimoItem}
          total={filtrados.length}
          pagina={paginaAtual}
          totalPaginas={totalPaginas}
          tamanhoPagina={tamanhoPagina}
          onTamanho={setTamanhoPagina}
          onAnterior={() => setPagina((p) => Math.max(1, p - 1))}
          onProximo={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
        />
      )}
    </section>
  );
}

// Rodapé de paginação. Seletor de tamanho de página (com label), indicador
// "X a Y de N" e página atual / total, e os botões Anterior / Próximo
// (desabilitados nos extremos). Empilha no mobile, distribui no desktop.
function PaginacaoRodape({
  primeiroItem,
  ultimoItem,
  total,
  pagina,
  totalPaginas,
  tamanhoPagina,
  onTamanho,
  onAnterior,
  onProximo,
}) {
  const naPrimeira = pagina <= 1;
  const naUltima = pagina >= totalPaginas;
  return (
    <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-4 text-xs text-slate-600 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        <label className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-500">
          <span className="uppercase tracking-wide text-[0.65rem] text-slate-400">Por página</span>
          <select
            value={tamanhoPagina}
            onChange={(e) => onTamanho(Number(e.target.value))}
            aria-label="Itens por página"
            className="cursor-pointer bg-transparent pr-1 font-500 focus:outline-none"
          >
            {TAMANHOS_PAGINA.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <p aria-live="polite" className="tnum text-slate-500">
          <span className="font-600 text-ink-700">{primeiroItem}</span> a{" "}
          <span className="font-600 text-ink-700">{ultimoItem}</span> de{" "}
          <span className="font-600 text-ink-700">{total}</span>
        </p>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onAnterior}
            disabled={naPrimeira}
            aria-label="Página anterior"
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 font-500 text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> Anterior
          </button>
          <span className="tnum px-1 tabular-nums text-slate-500">
            Página <span className="font-600 text-ink-700">{pagina}</span> de{" "}
            <span className="font-600 text-ink-700">{totalPaginas}</span>
          </span>
          <button
            type="button"
            onClick={onProximo}
            disabled={naUltima}
            aria-label="Próxima página"
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 font-500 text-slate-600 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
          >
            Próximo <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// Select de filtro com rótulo embutido. O rótulo fica visível dentro do botão
// para o usuário sempre saber qual eixo está filtrando.
function FiltroSelect({ label, value, onChange, opcoes }) {
  const ativo = value !== "";
  return (
    <label
      className={[
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-500 transition-colors",
        ativo
          ? "border-jade-300 bg-jade-50 text-jade-700"
          : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
      ].join(" ")}
    >
      <span className="uppercase tracking-wide text-[0.65rem] text-slate-400">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={`Filtrar por ${label}`}
        className="cursor-pointer bg-transparent pr-1 text-xs font-500 focus:outline-none"
      >
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.rotulo}
          </option>
        ))}
      </select>
    </label>
  );
}

// Cabeçalho clicável de coluna numérica. Mostra seta de direção quando ativo,
// e um ícone neutro de ordenação quando inativo. Alinhado à direita (números).
function ThOrdenavel({ rotulo, coluna, ordem, onOrdenar }) {
  const ativo = ordem.coluna === coluna;
  const asc = ativo && ordem.dir === "asc";
  return (
    <th className="px-4 py-3 text-right font-600">
      <button
        type="button"
        onClick={() => onOrdenar(coluna)}
        aria-label={`Ordenar por ${rotulo}`}
        className={[
          "inline-flex items-center gap-1 uppercase tracking-wider transition-colors",
          ativo ? "text-ink-800" : "text-slate-500 hover:text-ink-700",
        ].join(" ")}
      >
        {rotulo}
        {ativo ? (
          asc ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-50" />
        )}
      </button>
    </th>
  );
}

// Tooltip no hover/foco (acessível). Mostra o texto ao passar o mouse ou focar,
// sem depender do title nativo do navegador (que é lento e nem sempre aparece).
function Tooltip({ children, texto }) {
  return (
    <span className="group/tip relative inline-flex" tabIndex={0}>
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-50 mt-1 hidden w-64 rounded-lg bg-ink-900 px-3 py-2 text-left text-[0.7rem] font-400 leading-snug text-white shadow-lift group-hover/tip:block group-focus/tip:block"
      >
        {texto}
      </span>
    </span>
  );
}

// Data curta pt-BR (DD/MM/AA); tolera valor ausente/ inválido.
function dataCurta(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

// Data/hora pt-BR completa para a ficha de detalhe (DD/MM/AAAA HH:mm).
function dataHoraLonga(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function LinhaFornecedor({
  f,
  emEdicao,
  expandido,
  onToggleDetalhe,
  cnpj,
  razao,
  setCnpj,
  setRazao,
  salvando,
  onAbrir,
  onSalvar,
  onCancelar,
}) {
  const cnd = statusCndMeta(f.status_cnd);
  // Status de CND consultado em análise anterior (registrado por CNPJ no banco).
  // Informativo: a CND é volátil e pode ser reconsultada; isto só mostra o que é recente.
  const cndCache = !cnd ? statusCndMeta(f.cnd_status_cache) : null;
  const risco = riscoMeta(f.risco_2027);
  const riscoAlto = f.risco_2027 === "ALTO";
  // Tem ficha de CND para expandir quando há qualquer dado consultado (status
  // atual, cache, ou motivo de falha registrado).
  const temFicha = Boolean(
    f.status_cnd || f.cnd_status_cache || f.cnd_falha_motivo || f.cnd_consulta_datahora
  );

  // Em edição: a linha vira um painel de resolução de CNPJ ocupando a largura toda,
  // com a cascata grátis (busca no banco) → manual. Mantém o contexto do fornecedor.
  if (emEdicao) {
    return (
      <tr className="bg-jade-50/40">
        <td colSpan={8} className="relative px-4 py-4">
          <span className="absolute inset-y-0 left-0 w-1 bg-jade-500" aria-hidden="true" />
          <ResolverCnpj
            f={f}
            cnpj={cnpj}
            razao={razao}
            setCnpj={setCnpj}
            setRazao={setRazao}
            salvando={salvando}
            onSalvar={onSalvar}
            onCancelar={onCancelar}
          />
        </td>
      </tr>
    );
  }

  return (
    <>
      <tr
        className={[
          "relative transition-colors hover:bg-slate-50/70",
          riscoAlto ? "bg-signal-50/40" : "",
          expandido ? "bg-slate-50/70" : "",
        ].join(" ")}
      >
        {/* Grupo */}
        <td className="relative px-4 py-3 align-top">
          {riscoAlto && <span className="absolute inset-y-0 left-0 w-1 bg-signal-600" aria-hidden="true" />}
          <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-600 ${CORES_GRUPO[f.grupo] ?? CORES_GRUPO.INDEFINIDO}`}>
            {f.grupo}
          </span>
        </td>

        {/* Fornecedor */}
        <td className="px-4 py-3 align-top">
          <div className="flex flex-col gap-1">
            <span className="font-500 text-ink-800">{f.nome_forn}</span>
            <div className="flex flex-wrap items-center gap-1.5">
              {f.verificar_st && (
                <Tooltip texto="Alíquota cheia cadastrada, mas o ICMS veio zerado nas notas deste fornecedor. Provável Substituição Tributária (o ICMS já foi recolhido antes na cadeia, então não gera crédito), ou erro de lançamento. Confira a nota de entrada: CFOP de ST (ex. 1403, 1411) e o campo ICMS ST. Se for ST, essas compras não dão crédito.">
                  <span className="inline-flex cursor-help items-center gap-1 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[0.65rem] font-500 text-amber-700">
                    <AlertTriangle className="h-3 w-3" /> Verificar ST
                  </span>
                </Tooltip>
              )}
              {f.tem_estorno && (
                <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[0.65rem] font-500 text-slate-600">
                  Estorno
                </span>
              )}
              {!f.cnpj_pendente && !f.cnpj_confirmado && f.cnpj && (
                <span className="text-[0.65rem] text-slate-400">CNPJ não confirmado</span>
              )}
            </div>
          </div>
        </td>

        {/* CNPJ */}
        <td className="whitespace-nowrap px-4 py-3 align-top">
          {f.cnpj ? (
            <div className="flex flex-col items-start gap-1">
              <span className={`tnum inline-flex items-center gap-1.5 whitespace-nowrap ${f.cnpj_confirmado ? "text-jade-700" : "text-slate-600"}`}>
                {f.cnpj_confirmado && <ShieldCheck className="h-3.5 w-3.5 shrink-0" />}
                {formatarCnpj(f.cnpj)}
              </span>
              {!f.cnpj_confirmado && (
                <button
                  type="button"
                  onClick={onAbrir}
                  className="inline-flex items-center gap-1 rounded-lg border border-dashed border-amber-300 px-2 py-0.5 text-[0.7rem] font-500 text-amber-700 hover:border-amber-400 hover:bg-amber-50"
                >
                  <Pencil className="h-3 w-3" /> revisar e confirmar
                </button>
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={onAbrir}
              className="inline-flex items-center gap-1 rounded-lg border border-dashed border-slate-300 px-2 py-1 text-xs font-500 text-jade-700 hover:border-jade-400 hover:bg-jade-50"
            >
              <Pencil className="h-3 w-3" /> resolver CNPJ
            </button>
          )}
        </td>

        {/* CND — chip + botão de detalhe expansível */}
        <td className="px-4 py-3 align-top">
          <div className="flex items-start gap-2">
            <div className="flex flex-col gap-0.5">
              {cnd ? (
                <>
                  <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-500 ${cnd.classe}`}>
                    {cnd.rotulo}
                  </span>
                  {f.cnd_ultima_consulta && (
                    <span className="text-[0.65rem] text-slate-400">em {dataCurta(f.cnd_ultima_consulta)}</span>
                  )}
                </>
              ) : cndCache ? (
                <>
                  <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-500 opacity-70 ${cndCache.classe}`}>
                    {cndCache.rotulo}
                  </span>
                  <span className="text-[0.65rem] text-slate-400">consultada em {dataCurta(f.cnd_ultima_consulta)}</span>
                </>
              ) : (
                <span className="text-xs text-slate-300">—</span>
              )}
            </div>
            {temFicha && (
              <button
                type="button"
                onClick={onToggleDetalhe}
                aria-expanded={expandido}
                aria-label={expandido ? "Fechar detalhes da CND" : "Ver detalhes da CND"}
                className={[
                  "mt-0.5 inline-flex shrink-0 items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-[0.65rem] font-500 transition-colors",
                  expandido
                    ? "border-jade-300 bg-jade-50 text-jade-700"
                    : "border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-ink-700",
                ].join(" ")}
              >
                <FileText className="h-3 w-3" />
                detalhes
                {expandido ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>
            )}
          </div>
        </td>

        {/* Risco 2027 */}
        <td className="px-4 py-3 align-top">
          {risco ? (
            <span
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-600 ${risco.classe}`}
              title={f.motivo_risco ?? undefined}
            >
              {riscoAlto && <ShieldAlert className="h-3.5 w-3.5" />}
              {risco.rotulo}
            </span>
          ) : (
            <span className="text-xs text-slate-300">—</span>
          )}
        </td>

        <td className="tnum px-4 py-3 text-right align-top text-ink-700">{moeda(f.total_compras)}</td>
        <td className="tnum px-4 py-3 text-right align-top text-slate-600">{percentual(f.aliquota_max)}</td>
        <td className="tnum px-4 py-3 text-right align-top font-500 text-ink-800">{moeda(f.total_valor_icms)}</td>
      </tr>

      {/* Ficha de detalhe da CND, ocupando a largura toda abaixo da linha. */}
      {expandido && (
        <tr className="bg-slate-50/60">
          <td colSpan={8} className="px-4 pb-4 pt-1">
            <FichaCnd f={f} />
          </td>
        </tr>
      )}
    </>
  );
}

// Item rótulo/valor da ficha de CND. Layout em coluna, valor em destaque.
function Campo({ rotulo, children }) {
  return (
    <div className="min-w-0">
      <dt className="text-[0.65rem] font-500 uppercase tracking-wide text-slate-400">{rotulo}</dt>
      <dd className="mt-0.5 break-words text-sm text-ink-800">{children}</dd>
    </div>
  );
}

// Chip sim/não para os débitos (Receita Federal e PGFN). Vermelho quando há
// débito (true), jade quando não há (false), neutro quando indefinido (null).
function ChipDebito({ rotulo, valor }) {
  let classe = "border-slate-200 bg-slate-50 text-slate-500";
  let texto = "Sem informação";
  if (valor === true) {
    classe = "border-signal-200 bg-signal-50 text-signal-700";
    texto = "Com débito";
  } else if (valor === false) {
    classe = "border-jade-200 bg-jade-50 text-jade-700";
    texto = "Sem débito";
  }
  return (
    <div className={`rounded-lg border px-3 py-2 ${classe}`}>
      <p className="text-[0.65rem] font-500 uppercase tracking-wide opacity-70">{rotulo}</p>
      <p className="mt-0.5 text-sm font-600">{texto}</p>
    </div>
  );
}

// Ficha completa de regularidade fiscal (CND) de um fornecedor. Mostra todos os
// campos do contrato do Lucas. Quando FALHA, destaca o motivo em âmbar e deixa
// claro que falha de consulta não é sinônimo de débito.
function FichaCnd({ f }) {
  const cnd = statusCndMeta(f.status_cnd) ?? statusCndMeta(f.cnd_status_cache);
  const ehFalha = f.status_cnd === "FALHA";
  const validade = validadeCnd(f.cnd_validade);
  // Reforço visual: quando o motivo da falha indica que a fonte oficial está
  // fora do ar (Receita Federal/PGFN), deixa explícito que é indisponibilidade
  // da origem, não defeito do sistema nem débito do fornecedor.
  const origemFora =
    ehFalha &&
    /receita|pgfn|fora do ar|indispon|inst[áa]vel|timeout|tempo esgotado|502|503|504/i.test(
      f.cnd_falha_motivo || "",
    );

  return (
    <div className="animate-fade-up rounded-xl border border-slate-200 bg-white p-4 shadow-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-slate-500" />
          <span className="text-sm font-600 text-ink-800">Certidão Negativa de Débitos</span>
          {cnd && (
            <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-500 ${cnd.classe}`}>
              {cnd.rotulo}
            </span>
          )}
        </div>
        {f.cnd_comprovante_url && (
          <a
            href={f.cnd_comprovante_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-jade-200 bg-jade-50 px-3 py-1.5 text-xs font-600 text-jade-700 transition-colors hover:bg-jade-100"
          >
            <ExternalLink className="h-3.5 w-3.5" /> Ver certidão (PDF)
          </a>
        )}
      </div>

      {/* Falha: destaca o motivo e esclarece que não significa débito. */}
      {ehFalha && (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div>
              <p className="text-sm font-600 text-amber-800">
                {origemFora
                  ? "A Receita Federal/PGFN está fora do ar"
                  : "Não foi possível consultar a CND"}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-amber-700">
                Motivo: {f.cnd_falha_motivo || "não informado pelo serviço de consulta."}
              </p>
              <p className="mt-1.5 flex items-center gap-1 text-xs leading-relaxed text-amber-700">
                <RotateCcw className="h-3 w-3 shrink-0" />
                {origemFora
                  ? "É a fonte oficial fora do ar, não defeito do sistema nem débito do fornecedor. Tente consultar de novo em alguns minutos."
                  : "Isto é uma falha na consulta, não significa que o fornecedor tem débito. Você pode tentar consultar de novo."}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Débitos lado a lado — o coração da regularidade. */}
      {!ehFalha && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <ChipDebito rotulo="Receita Federal (RFB)" valor={f.cnd_debitos_rfb} />
          <ChipDebito rotulo="Dívida Ativa (PGFN)" valor={f.cnd_debitos_pgfn} />
        </div>
      )}

      {/* Demais dados da certidão. */}
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
        {f.cnd_tipo && <Campo rotulo="Tipo da certidão">{f.cnd_tipo}</Campo>}

        <Campo rotulo="Emissão">{dataHoraLonga(f.cnd_emissao_data)}</Campo>

        <Campo rotulo="Validade">
          {f.cnd_validade ? (
            <span className="flex flex-col">
              <span
                className={
                  validade.estado === "VENCIDA"
                    ? "font-600 text-signal-700"
                    : validade.estado === "PERTO"
                    ? "font-600 text-amber-700"
                    : "text-ink-800"
                }
              >
                {dataHoraLonga(f.cnd_validade)}
              </span>
              {validade.estado === "VENCIDA" && (
                <span className="text-[0.65rem] font-500 text-signal-600">Vencida</span>
              )}
              {validade.estado === "PERTO" && (
                <span className="text-[0.65rem] font-500 text-amber-600">
                  Vence em {validade.dias} {validade.dias === 1 ? "dia" : "dias"}
                </span>
              )}
            </span>
          ) : (
            "—"
          )}
        </Campo>

        <Campo rotulo="Consultada em">{dataHoraLonga(f.cnd_consulta_datahora || f.cnd_ultima_consulta)}</Campo>

        {f.cnd_certidao_codigo && (
          <Campo rotulo="Código de controle">
            <span className="tnum">{f.cnd_certidao_codigo}</span>
          </Campo>
        )}
      </dl>

      {f.cnd_descricao && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
          {f.cnd_descricao}
        </p>
      )}
    </div>
  );
}

// Painel inline de resolução de CNPJ de um fornecedor pendente.
// Cascata de opções: (1) buscar no banco de fornecedores — GRÁTIS, clique aplica;
// (2) inserir manualmente razão social + CNPJ. Salva via definirCnpjManual (no pai).
function ResolverCnpj({ f, cnpj, razao, setCnpj, setRazao, salvando, onSalvar, onCancelar }) {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-600 uppercase tracking-wider text-jade-700">Resolver CNPJ</p>
          <p className="mt-0.5 text-sm font-500 text-ink-800">{f.nome_forn}</p>
        </div>
        <button
          type="button"
          onClick={onCancelar}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
        >
          <X className="h-3.5 w-3.5" /> Fechar
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* OPÇÃO 1 — busca no banco (grátis) */}
        <BuscaBanco
          termoInicial={f.nome_forn || ""}
          onSelecionar={(item) => {
            setRazao(item.razao_social || f.nome_forn || "");
            setCnpj(item.cnpj || "");
          }}
        />

        {/* OPÇÃO 2 — manual */}
        <div className="rounded-xl border border-slate-200 bg-white p-3.5">
          <div className="flex items-center gap-2">
            <Pencil className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-600 text-ink-800">Inserir manualmente</span>
          </div>
          <div className="mt-3 space-y-2">
            <label className="block">
              <span className="mb-1 block text-xs font-500 text-slate-500">Razão social</span>
              <input
                value={razao}
                onChange={(e) => setRazao(e.target.value)}
                placeholder="Razão social"
                aria-label="Razão social"
                className="w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-jade-400"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-500 text-slate-500">CNPJ</span>
              <input
                value={cnpj}
                onChange={(e) => setCnpj(e.target.value)}
                placeholder="00.000.000/0000-00"
                aria-label="CNPJ"
                className="tnum w-full rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-jade-400"
              />
            </label>
          </div>
        </div>
      </div>

      {/* Ação de salvar (vale para ambas as opções, pois ambas preenchem cnpj/razao) */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onSalvar}
          disabled={salvando || !cnpj.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-jade-600 px-3.5 py-2 text-sm font-600 text-white transition-colors hover:bg-jade-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {salvando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Aplicar CNPJ
        </button>
        {!cnpj.trim() && (
          <span className="text-xs text-slate-400">Selecione no banco ou digite um CNPJ.</span>
        )}
      </div>
    </div>
  );
}

// Campo de busca gratuita no banco de fornecedores. Debounce de 350ms,
// lista sugestões clicáveis. Selo "grátis" reforça que não consome créditos.
function BuscaBanco({ termoInicial, onSelecionar }) {
  const [q, setQ] = useState(termoInicial);
  const [resultados, setResultados] = useState([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState(null);
  const [escolhido, setEscolhido] = useState(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    const termo = q.trim();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (termo.length < 2) {
      setResultados([]);
      setCarregando(false);
      setErro(null);
      return;
    }
    setCarregando(true);
    let cancelado = false;
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await buscarFornecedores(termo);
        if (!cancelado) {
          setResultados(res ?? []);
          setErro(null);
        }
      } catch {
        if (!cancelado) {
          setResultados([]);
          setErro("Não foi possível buscar no banco agora.");
        }
      } finally {
        if (!cancelado) setCarregando(false);
      }
    }, 350);
    return () => {
      cancelado = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [q]);

  const termoCurto = q.trim().length > 0 && q.trim().length < 2;

  return (
    <div className="rounded-xl border border-jade-200 bg-jade-50/50 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-jade-600" />
          <span className="text-sm font-600 text-ink-800">Buscar no banco</span>
        </div>
        <span className="rounded-md bg-jade-600 px-2 py-0.5 text-[0.65rem] font-600 uppercase tracking-wide text-white">
          grátis
        </span>
      </div>

      <div className="relative mt-3">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setEscolhido(null);
          }}
          placeholder="Razão social do fornecedor"
          aria-label="Buscar fornecedor no banco"
          className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-3 text-sm placeholder:text-slate-400 focus:border-jade-400"
        />
        {carregando && (
          <Loader2 className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-jade-500" />
        )}
      </div>

      <div className="mt-2 max-h-44 overflow-y-auto scroll-thin">
        {termoCurto && <p className="px-1 py-2 text-xs text-slate-400">Digite ao menos 2 caracteres.</p>}
        {erro && <p className="px-1 py-2 text-xs text-signal-700">{erro}</p>}
        {!erro && !carregando && !termoCurto && q.trim().length >= 2 && resultados.length === 0 && (
          <p className="px-1 py-2 text-xs text-slate-400">Nenhum CNPJ no banco para esse termo. Use a opção manual.</p>
        )}
        <ul className="divide-y divide-jade-100">
          {resultados.map((item) => {
            const ativo = escolhido === item.cnpj;
            return (
              <li key={`${item.cnpj}-${item.razao_social}`}>
                <button
                  type="button"
                  onClick={() => {
                    setEscolhido(item.cnpj);
                    onSelecionar(item);
                  }}
                  className={[
                    "flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left transition-colors",
                    ativo ? "bg-jade-100" : "hover:bg-jade-100/60",
                  ].join(" ")}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-500 text-ink-800">{item.razao_social}</span>
                    <span className="tnum block text-xs text-slate-500">
                      {formatarCnpj(item.cnpj)}
                      {item.origem && <span className="ml-1.5 text-slate-400">· {item.origem}</span>}
                    </span>
                  </span>
                  {ativo ? (
                    <Check className="h-4 w-4 shrink-0 text-jade-600" />
                  ) : (
                    <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-slate-300" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
