import { useState } from "react";
import { Loader2, AlertCircle, Mail, Lock, Building2, ShieldCheck, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";

// Tela de acesso do Lumen: alterna entre Login e Cadastro no mesmo card.
// Só é renderizada quando authEnabled === true e não há usuário logado.
export default function Login() {
  const [modo, setModo] = useState("login"); // "login" | "cadastro"
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <PainelMarca />
      <div className="flex items-center justify-center bg-[#f4f6f5] px-5 py-10 sm:px-8">
        <div className="w-full max-w-sm animate-fade-up">
          {/* Marca compacta: aparece no mobile, onde o painel da esquerda some */}
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <LumenMark />
            <div className="flex items-baseline gap-2">
              <span className="font-display text-2xl font-600 tracking-tight text-ink-900">
                Lumen
              </span>
              <span className="text-[0.65rem] font-500 uppercase tracking-[0.18em] text-jade-600">
                Fiscal
              </span>
            </div>
          </div>

          {modo === "login" ? (
            <FormLogin aoTrocar={() => setModo("cadastro")} />
          ) : (
            <FormCadastro aoTrocar={() => setModo("login")} />
          )}
        </div>
      </div>
    </div>
  );
}

// Mapeia o erro do axios para uma mensagem clara em pt-BR conforme o contrato.
function mensagemErro(err, contexto) {
  const status = err?.response?.status;
  const detalhe = err?.response?.data?.detail;
  if (status === 401) return "E-mail ou senha incorretos.";
  if (status === 409) return "Este e-mail já está em uso.";
  if (status === 422) {
    if (contexto === "cadastro") return "Dados inválidos. A senha precisa ter ao menos 8 caracteres.";
    return "Dados inválidos. Confira os campos e tente novamente.";
  }
  if (typeof detalhe === "string") return detalhe;
  if (err?.code === "ERR_NETWORK") return "Sem conexão com o servidor. Tente novamente.";
  return "Não foi possível concluir. Tente novamente em instantes.";
}

function FormLogin({ aoTrocar }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);

  async function aoEnviar(e) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await login({ email: email.trim(), senha });
      // Sucesso: o gate em App troca para o app automaticamente.
    } catch (err) {
      setErro(mensagemErro(err, "login"));
      setEnviando(false);
    }
  }

  return (
    <Cartao titulo="Acessar a conta" subtitulo="Entre com suas credenciais para continuar.">
      <form onSubmit={aoEnviar} className="space-y-4" noValidate>
        {erro && <Alerta>{erro}</Alerta>}

        <Campo
          id="login-email"
          rotulo="E-mail"
          tipo="email"
          Icone={Mail}
          valor={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="voce@escritorio.com.br"
          required
        />
        <Campo
          id="login-senha"
          rotulo="Senha"
          tipo="password"
          Icone={Lock}
          valor={senha}
          onChange={setSenha}
          autoComplete="current-password"
          placeholder="Sua senha"
          required
        />

        <BotaoEnviar enviando={enviando} rotulo="Entrar" rotuloEnviando="Entrando..." />
      </form>

      <Alternar
        texto="Ainda não tem conta?"
        acao="Criar escritório"
        onClick={aoTrocar}
      />
    </Cartao>
  );
}

function FormCadastro({ aoTrocar }) {
  const { signup } = useAuth();
  const [nomeEscritorio, setNomeEscritorio] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);

  // Validação client-side: feedback imediato antes de bater na API.
  const senhaCurta = senha.length > 0 && senha.length < 8;

  async function aoEnviar(e) {
    e.preventDefault();
    setErro(null);
    if (senha.length < 8) {
      setErro("A senha precisa ter ao menos 8 caracteres.");
      return;
    }
    setEnviando(true);
    try {
      await signup({
        nome_escritorio: nomeEscritorio.trim(),
        email: email.trim(),
        senha,
      });
    } catch (err) {
      setErro(mensagemErro(err, "cadastro"));
      setEnviando(false);
    }
  }

  return (
    <Cartao
      titulo="Criar escritório"
      subtitulo="Cadastre seu escritório para começar a usar o Lumen."
    >
      <form onSubmit={aoEnviar} className="space-y-4" noValidate>
        {erro && <Alerta>{erro}</Alerta>}

        <Campo
          id="cad-nome"
          rotulo="Nome do escritório"
          tipo="text"
          Icone={Building2}
          valor={nomeEscritorio}
          onChange={setNomeEscritorio}
          autoComplete="organization"
          placeholder="Contabilidade Exemplo"
          required
        />
        <Campo
          id="cad-email"
          rotulo="E-mail"
          tipo="email"
          Icone={Mail}
          valor={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="voce@escritorio.com.br"
          required
        />
        <Campo
          id="cad-senha"
          rotulo="Senha"
          tipo="password"
          Icone={Lock}
          valor={senha}
          onChange={setSenha}
          autoComplete="new-password"
          placeholder="Mínimo de 8 caracteres"
          ajuda={senhaCurta ? "A senha precisa ter ao menos 8 caracteres." : "Use 8 caracteres ou mais."}
          ajudaErro={senhaCurta}
          required
        />

        <BotaoEnviar enviando={enviando} rotulo="Criar conta" rotuloEnviando="Criando..." />
      </form>

      <Alternar texto="Já tem conta?" acao="Acessar" onClick={aoTrocar} />
    </Cartao>
  );
}

// ---- Blocos de UI reaproveitados ---------------------------------------

function Cartao({ titulo, subtitulo, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel sm:p-7">
      <h1 className="font-display text-xl font-600 tracking-tight text-ink-900">{titulo}</h1>
      <p className="mt-1 text-sm text-slate-500">{subtitulo}</p>
      <div className="mt-6">{children}</div>
    </div>
  );
}

function Campo({ id, rotulo, tipo, Icone, valor, onChange, ajuda, ajudaErro, ...rest }) {
  const descId = ajuda ? `${id}-ajuda` : undefined;
  // Campo de senha ganha o "olhinho" para mostrar/ocultar o que foi digitado.
  const ehSenha = tipo === "password";
  const [mostrar, setMostrar] = useState(false);
  const tipoInput = ehSenha && mostrar ? "text" : tipo;
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-500 text-ink-800">
        {rotulo}
      </label>
      <div className="relative mt-1.5">
        <Icone className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          id={id}
          type={tipoInput}
          value={valor}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={descId}
          aria-invalid={ajudaErro ? "true" : undefined}
          className={[
            "w-full rounded-lg border bg-white py-2.5 pl-9 text-sm text-ink-900 outline-none transition-colors",
            ehSenha ? "pr-10" : "pr-3",
            "placeholder:text-slate-400 focus:ring-2 focus:ring-jade-500/30",
            ajudaErro
              ? "border-signal-400 focus:border-signal-500"
              : "border-slate-300 focus:border-jade-500",
          ].join(" ")}
          {...rest}
        />
        {ehSenha && (
          <button
            type="button"
            onClick={() => setMostrar((v) => !v)}
            aria-label={mostrar ? "Ocultar senha" : "Mostrar senha"}
            title={mostrar ? "Ocultar senha" : "Mostrar senha"}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 transition-colors hover:text-ink-700 focus:outline-none focus:text-ink-700"
          >
            {mostrar ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>
      {ajuda && (
        <p id={descId} className={`mt-1 text-xs ${ajudaErro ? "text-signal-600" : "text-slate-400"}`}>
          {ajuda}
        </p>
      )}
    </div>
  );
}

function Alerta({ children }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-signal-200 bg-signal-50 px-3 py-2.5 text-sm text-signal-700"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function BotaoEnviar({ enviando, rotulo, rotuloEnviando }) {
  return (
    <button
      type="submit"
      disabled={enviando}
      className="flex w-full items-center justify-center gap-2 rounded-lg bg-ink-900 px-4 py-2.5 text-sm font-500 text-white transition-colors hover:bg-ink-800 focus:outline-none focus:ring-2 focus:ring-jade-500/40 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {enviando && <Loader2 className="h-4 w-4 animate-spin" />}
      {enviando ? rotuloEnviando : rotulo}
    </button>
  );
}

function Alternar({ texto, acao, onClick }) {
  return (
    <p className="mt-5 text-center text-sm text-slate-500">
      {texto}{" "}
      <button
        type="button"
        onClick={onClick}
        className="font-500 text-jade-700 underline-offset-2 transition-colors hover:text-jade-600 hover:underline focus:outline-none focus:underline"
      >
        {acao}
      </button>
    </p>
  );
}

// Painel lateral institucional (desktop): marca + proposta de valor.
function PainelMarca() {
  return (
    <div className="relative hidden flex-col justify-between overflow-hidden bg-ink-950 p-10 text-white lg:flex">
      <div className="pointer-events-none absolute inset-0 reticle opacity-60" aria-hidden="true" />
      <div className="relative flex items-center gap-3">
        <LumenMark />
        <div className="flex items-baseline gap-2">
          <span className="font-display text-2xl font-600 leading-none tracking-tight">Lumen</span>
          <span className="text-[0.65rem] font-500 uppercase tracking-[0.18em] text-jade-400">
            Fiscal
          </span>
        </div>
      </div>

      <div className="relative max-w-md">
        <h2 className="font-display text-3xl font-600 leading-tight tracking-tight">
          Inteligência tributária para créditos e regularidade fiscal.
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-slate-400">
          Análise de crédito de ICMS, score fiscal de fornecedores e controle de consumo,
          em um só painel.
        </p>
      </div>

      <div className="relative">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-jade-500/30 bg-jade-500/10 px-2.5 py-1 text-[0.7rem] font-500 text-jade-400">
          <ShieldCheck className="h-3.5 w-3.5" strokeWidth={2.2} />
          Ambiente confidencial
        </span>
      </div>
    </div>
  );
}

function LumenMark() {
  return (
    <span
      className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-jade-500 to-jade-700 shadow-lift ring-1 ring-white/10"
      aria-hidden="true"
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
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
