import { ShieldCheck } from "lucide-react";
import Modulo01 from "./pages/Modulo01.jsx";

export default function App() {
  return (
    <div className="min-h-screen bg-[#f4f6f5] text-ink-800">
      <header className="relative overflow-hidden bg-ink-950 text-white">
        <div className="absolute inset-0 reticle" aria-hidden="true" />
        <div className="absolute inset-0 noise" aria-hidden="true" />
        {/* Halo esmeralda no canto: assinatura de "lente / luz" do Lumen */}
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-jade-500/20 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative mx-auto flex max-w-7xl flex-col gap-4 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8 sm:py-7">
          <div className="flex items-center gap-3.5">
            <LumenMark />
            <div>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-2xl font-600 leading-none tracking-tight">
                  Lumen
                </span>
                <span className="hidden text-xs font-500 uppercase tracking-[0.18em] text-jade-400 sm:inline">
                  Fiscal
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-600/90 sm:text-sm">
                Análise de crédito de ICMS e regularidade fiscal de fornecedores
              </p>
            </div>
          </div>
          <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-jade-500/30 bg-jade-500/10 px-3 py-1.5 text-xs font-500 text-jade-400">
            <ShieldCheck className="h-3.5 w-3.5" strokeWidth={2.2} />
            Documento confidencial
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-7 sm:px-8 sm:py-10">
        <Modulo01 />
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-10 pt-2 text-center text-xs text-ink-600/60 sm:px-8">
        Lumen · Módulo 01 — Crédito de ICMS &amp; Regularidade Fiscal
      </footer>
    </div>
  );
}

// Marca: um glifo de "lente" — anel com núcleo luminoso. Vetorial, leve, distintivo.
function LumenMark() {
  return (
    <span
      className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-jade-500 to-jade-700 shadow-lift ring-1 ring-white/10"
      aria-hidden="true"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="8.5" stroke="white" strokeOpacity="0.85" strokeWidth="1.6" />
        <circle cx="12" cy="12" r="3.4" fill="white" />
        <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" stroke="white" strokeOpacity="0.6" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    </span>
  );
}
