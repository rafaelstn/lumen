import { useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./components/Sidebar.jsx";
import Modulo01 from "./pages/Modulo01.jsx";
import Modulo02 from "./pages/Modulo02.jsx";
import BancoFornecedores from "./pages/BancoFornecedores.jsx";
import Consumo from "./pages/Consumo.jsx";

// Título contextual da topbar conforme a view ativa.
const TITULOS = {
  analise: "Análise de Crédito",
  fornecedores: "Banco de fornecedores",
  score: "Score Fiscal de Fornecedores",
  consumo: "Consumo & custos",
};

// Shell de dashboard: sidebar fixa (drawer no mobile) + área de conteúdo.
// A navegação usa estado local de "view ativa" — sem router, são poucas views.
export default function App() {
  const [view, setView] = useState("analise");
  const [menuAberto, setMenuAberto] = useState(false);

  function navegar(novaView) {
    setView(novaView);
    setMenuAberto(false); // fecha o drawer ao escolher no mobile
  }

  return (
    <div className="min-h-screen bg-[#f4f6f5] text-ink-800">
      <Sidebar
        view={view}
        onNavegar={navegar}
        aberto={menuAberto}
        onFechar={() => setMenuAberto(false)}
      />

      {/* Coluna de conteúdo: deslocada pela sidebar fixa em desktop */}
      <div className="lg:pl-72">
        {/* Topbar: só hambúrguer + título no mobile; em desktop fica enxuta */}
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-[#f4f6f5]/85 px-4 py-3.5 backdrop-blur sm:px-6 lg:px-8">
          <button
            type="button"
            onClick={() => setMenuAberto(true)}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white text-ink-700 transition-colors hover:bg-slate-50 lg:hidden"
            aria-label="Abrir menu"
          >
            <Menu className="h-[18px] w-[18px]" />
          </button>
          <h1 className="font-display text-base font-600 tracking-tight text-ink-900 sm:text-lg">
            {TITULOS[view]}
          </h1>
        </header>

        <main className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-9 lg:px-8 lg:py-10">
          {view === "analise" && <Modulo01 />}
          {view === "fornecedores" && <BancoFornecedores />}
          {view === "score" && <Modulo02 />}
          {view === "consumo" && <Consumo />}
        </main>
      </div>
    </div>
  );
}
