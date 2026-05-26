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
} from "lucide-react";
import {
  moeda,
  percentual,
  CORES_GRUPO,
  statusCndMeta,
  riscoMeta,
  formatarCnpj,
} from "../utils/format.js";
import { buscarFornecedores } from "../services/api.js";

// Tabela de fornecedores classificados. Linhas de risco ALTO ganham faixa
// vermelha à esquerda; CNPJ pendente abre edição inline (razão social + CNPJ,
// o backend valida o dígito verificador). Busca client-side por nome/CNPJ.
export default function FornecedoresTable({ fornecedores, onSalvarCnpj, salvando }) {
  const [editando, setEditando] = useState(null);
  const [cnpj, setCnpj] = useState("");
  const [razao, setRazao] = useState("");
  const [busca, setBusca] = useState("");
  const [soRisco, setSoRisco] = useState(false);

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return fornecedores.filter((f) => {
      if (soRisco && f.risco_2027 !== "ALTO") return false;
      if (!q) return true;
      return (
        (f.nome_forn ?? "").toLowerCase().includes(q) ||
        (f.cnpj ?? "").toLowerCase().includes(q)
      );
    });
  }, [fornecedores, busca, soRisco]);

  const totalRiscoAlto = fornecedores.filter((f) => f.risco_2027 === "ALTO").length;

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
      <div className="flex flex-col gap-3 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-display text-lg font-600 text-ink-900">Fornecedores</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {filtrados.length} de {fornecedores.length} exibidos
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {totalRiscoAlto > 0 && (
            <button
              type="button"
              onClick={() => setSoRisco((v) => !v)}
              className={[
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-500 transition-colors",
                soRisco
                  ? "border-signal-300 bg-signal-600 text-white"
                  : "border-signal-200 bg-signal-50 text-signal-700 hover:bg-signal-100",
              ].join(" ")}
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              Risco alto ({totalRiscoAlto})
            </button>
          )}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar fornecedor ou CNPJ"
              aria-label="Buscar fornecedor"
              className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-3 text-sm placeholder:text-slate-400 focus:border-jade-400 sm:w-64"
            />
          </div>
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
              <th className="px-4 py-3 text-right font-600">Compras</th>
              <th className="px-4 py-3 text-right font-600">Alíq. máx.</th>
              <th className="px-4 py-3 text-right font-600">ICMS aprov.</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {filtrados.map((f) => (
              <LinhaFornecedor
                key={f.cod_forn}
                f={f}
                emEdicao={editando === f.cod_forn}
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
    </section>
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

function LinhaFornecedor({ f, emEdicao, cnpj, razao, setCnpj, setRazao, salvando, onAbrir, onSalvar, onCancelar }) {
  const cnd = statusCndMeta(f.status_cnd);
  // Status de CND consultado em análise anterior (registrado por CNPJ no banco).
  // Informativo: a CND é volátil e pode ser reconsultada; isto só mostra o que é recente.
  const cndCache = !cnd ? statusCndMeta(f.cnd_status_cache) : null;
  const risco = riscoMeta(f.risco_2027);
  const riscoAlto = f.risco_2027 === "ALTO";

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
    <tr className={["relative transition-colors hover:bg-slate-50/70", riscoAlto ? "bg-signal-50/40" : ""].join(" ")}>
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

      {/* CND */}
      <td className="px-4 py-3 align-top">
        {cnd ? (
          <div className="flex flex-col gap-0.5">
            <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-500 ${cnd.classe}`}>
              {cnd.rotulo}
            </span>
            {f.cnd_ultima_consulta && (
              <span className="text-[0.65rem] text-slate-400">em {dataCurta(f.cnd_ultima_consulta)}</span>
            )}
          </div>
        ) : cndCache ? (
          <div
            className="flex flex-col gap-0.5"
            title={`Última CND consultada em ${dataCurta(f.cnd_ultima_consulta)}. A CND é volátil; consulte de novo para o status atual.`}
          >
            <span className={`inline-block rounded-md border px-2 py-0.5 text-xs font-500 opacity-70 ${cndCache.classe}`}>
              {cndCache.rotulo}
            </span>
            <span className="text-[0.65rem] text-slate-400">consultada em {dataCurta(f.cnd_ultima_consulta)}</span>
          </div>
        ) : (
          <span className="text-xs text-slate-300">—</span>
        )}
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
