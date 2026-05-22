import Modulo01 from "./pages/Modulo01.jsx";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="bg-slate-900 text-white px-6 py-4">
        <h1 className="text-lg font-semibold">
          Sistema de Análise Fiscal de Fornecedores
        </h1>
        <p className="text-sm text-slate-300">Módulo 01 — Análise de Crédito ICMS e Regularidade Fiscal</p>
      </header>
      <main className="max-w-4xl mx-auto p-6">
        <Modulo01 />
      </main>
    </div>
  );
}
