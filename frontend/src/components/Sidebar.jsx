import { useEffect } from "react";
import {
  ShieldCheck,
  FilePlus2,
  Database,
  Gauge,
  Wallet,
  Receipt,
  Lock,
  X,
} from "lucide-react";

// Itens transversais (não pertencem a um módulo específico).
const TRANSVERSAIS = [{ view: "consumo", rotulo: "Consumo & custos", Icone: Receipt }];

// Estrutura de navegação modular do Lumen. Itens "em breve" ficam bloqueados,
// servem como roadmap visível dentro do próprio produto.
const MODULOS = [
  {
    id: "m01",
    numero: "01",
    titulo: "Análise de Crédito",
    Icone: Gauge,
    ativo: true,
    subitens: [
      { view: "analise", rotulo: "Nova análise", Icone: FilePlus2 },
      { view: "fornecedores", rotulo: "Banco de fornecedores", Icone: Database },
    ],
  },
  {
    id: "m02",
    numero: "02",
    titulo: "Score Fiscal de Fornecedores",
    Icone: Wallet,
    ativo: true,
    subitens: [{ view: "score", rotulo: "Score & monitoramento", Icone: Gauge }],
  },
  {
    id: "m03",
    numero: "03",
    titulo: "Recuperação de Créditos",
    Icone: Wallet,
    ativo: false,
    tooltip: "Disponível após a validação do Módulo 01",
  },
];

export default function Sidebar({ view, onNavegar, aberto, onFechar }) {
  // Fecha o drawer com Esc no mobile (acessibilidade de teclado).
  useEffect(() => {
    if (!aberto) return;
    const onKey = (e) => e.key === "Escape" && onFechar();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aberto, onFechar]);

  return (
    <>
      {/* Overlay do drawer (mobile) */}
      {aberto && (
        <div
          className="fixed inset-0 z-30 bg-ink-950/60 backdrop-blur-sm lg:hidden"
          onClick={onFechar}
          aria-hidden="true"
        />
      )}

      <aside
        className={[
          "fixed inset-y-0 left-0 z-40 flex w-72 flex-col bg-ink-950 text-white",
          "transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
          aberto ? "translate-x-0" : "-translate-x-full",
          "lg:translate-x-0",
        ].join(" ")}
        aria-label="Navegação principal"
      >
        {/* Grade de medição discreta: assinatura sutil, sem ruído nem glow */}
        <div className="pointer-events-none absolute inset-0 reticle opacity-60" aria-hidden="true" />

        {/* Marca */}
        <div className="relative flex items-center justify-between gap-3 border-b border-white/5 px-5 py-5">
          <div className="flex items-center gap-3">
            <LumenMark />
            <div>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-xl font-600 leading-none tracking-tight">
                  Lumen
                </span>
                <span className="text-[0.65rem] font-500 uppercase tracking-[0.18em] text-jade-400">
                  Fiscal
                </span>
              </div>
              <p className="mt-1 text-[0.7rem] text-slate-400">Inteligência tributária</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onFechar}
            className="grid h-8 w-8 place-items-center rounded-lg text-ink-600 transition-colors hover:bg-white/5 hover:text-white lg:hidden"
            aria-label="Fechar menu"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </div>

        {/* Navegação */}
        <nav className="relative flex-1 overflow-y-auto scroll-thin px-3 py-5">
          <ul className="space-y-1.5">
            {MODULOS.map((mod) => (
              <li key={mod.id}>
                {mod.ativo ? (
                  <ModuloAtivo mod={mod} view={view} onNavegar={onNavegar} />
                ) : (
                  <ModuloEmBreve mod={mod} />
                )}
              </li>
            ))}
          </ul>

          {/* Seção transversal: ferramentas que valem para todos os módulos */}
          <div className="mt-5 border-t border-white/5 pt-4">
            <p className="px-3 pb-1.5 text-[0.65rem] font-600 uppercase tracking-[0.16em] text-slate-500">
              Geral
            </p>
            <ul className="space-y-0.5">
              {TRANSVERSAIS.map((item) => {
                const atual = view === item.view;
                return (
                  <li key={item.view}>
                    <button
                      type="button"
                      onClick={() => onNavegar(item.view)}
                      aria-current={atual ? "page" : undefined}
                      className={[
                        "group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                        atual
                          ? "bg-jade-500/12 font-500 text-jade-300"
                          : "text-slate-300 hover:bg-white/5 hover:text-white",
                      ].join(" ")}
                    >
                      {atual && (
                        <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-jade-400" />
                      )}
                      <item.Icone
                        className={[
                          "h-4 w-4 shrink-0 transition-colors",
                          atual ? "text-jade-400" : "text-slate-500 group-hover:text-jade-400",
                        ].join(" ")}
                      />
                      {item.rotulo}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </nav>

        {/* Rodapé */}
        <div className="relative border-t border-white/5 px-5 py-4">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-jade-500/30 bg-jade-500/10 px-2.5 py-1 text-[0.7rem] font-500 text-jade-400">
            <ShieldCheck className="h-3.5 w-3.5" strokeWidth={2.2} />
            Documento confidencial
          </span>
          <p className="mt-2.5 text-[0.7rem] leading-relaxed text-ink-600/80">
            Módulo 01 — Crédito de ICMS &amp; Regularidade Fiscal
          </p>
        </div>
      </aside>
    </>
  );
}

function ModuloAtivo({ mod, view, onNavegar }) {
  const algumAtivo = mod.subitens.some((s) => s.view === view);
  return (
    <div>
      <div className="flex items-center gap-2.5 px-3 pb-1.5 pt-1">
        <span
          className={[
            "grid h-7 w-7 place-items-center rounded-lg text-xs font-600 tnum transition-colors",
            algumAtivo ? "bg-jade-500 text-ink-950" : "bg-white/5 text-jade-400",
          ].join(" ")}
        >
          {mod.numero}
        </span>
        <span className="text-sm font-500 text-white">{mod.titulo}</span>
      </div>
      <ul className="ml-3.5 space-y-0.5 border-l border-white/10 pl-3">
        {mod.subitens.map((sub) => {
          const atual = view === sub.view;
          return (
            <li key={sub.view}>
              <button
                type="button"
                onClick={() => onNavegar(sub.view)}
                aria-current={atual ? "page" : undefined}
                className={[
                  "group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  atual
                    ? "bg-jade-500/12 font-500 text-jade-300"
                    : "text-slate-300 hover:bg-white/5 hover:text-white",
                ].join(" ")}
              >
                {/* Faixa indicadora do item ativo */}
                {atual && (
                  <span className="absolute -left-[15px] top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-jade-400" />
                )}
                <sub.Icone
                  className={[
                    "h-4 w-4 shrink-0 transition-colors",
                    atual ? "text-jade-400" : "text-slate-500 group-hover:text-jade-400",
                  ].join(" ")}
                />
                {sub.rotulo}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ModuloEmBreve({ mod }) {
  return (
    <div
      className="flex cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2"
      title={mod.tooltip}
      aria-disabled="true"
    >
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/5 text-xs font-600 tnum text-slate-400">
        {mod.numero}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-500 text-slate-300">{mod.titulo}</span>
        <span className="mt-0.5 inline-flex items-center gap-1 text-[0.65rem] font-500 uppercase tracking-wide text-slate-500">
          <Lock className="h-2.5 w-2.5" strokeWidth={2.4} />
          Em breve
        </span>
      </span>
    </div>
  );
}

// Marca: glifo de "lente" — anel com núcleo luminoso. Distintivo do Lumen.
function LumenMark() {
  return (
    <span
      className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-jade-500 to-jade-700 shadow-lift ring-1 ring-white/10"
      aria-hidden="true"
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="8.5" stroke="white" strokeOpacity="0.85" strokeWidth="1.6" />
        <circle cx="12" cy="12" r="3.4" fill="white" />
        <path
          d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"
          stroke="white"
          strokeOpacity="0.6"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}
