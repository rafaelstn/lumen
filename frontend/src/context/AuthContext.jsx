import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  getHealth,
  getMe,
  login as apiLogin,
  signup as apiSignup,
  lerToken,
  gravarToken,
  registrarHandlerSessaoExpirada,
} from "../services/api.js";

const AuthContext = createContext(null);

// Provider de autenticação do Lumen.
//
// A decisão do MODO é do backend, via /health -> auth_enabled:
//   - auth_enabled === false  -> app ANÔNIMO (estado atual): nenhuma tela de
//     login, nenhum controle de papel. Tudo funciona como hoje.
//   - auth_enabled === true    -> exige login. Sem usuário -> tela de Login.
//
// Estado exposto: { authEnabled, token, usuario, carregando, login, signup,
//   logout, role, ehAdmin }.
export function AuthProvider({ children }) {
  const [authEnabled, setAuthEnabled] = useState(false);
  const [token, setToken] = useState(() => lerToken());
  const [usuario, setUsuario] = useState(null);
  const [carregando, setCarregando] = useState(true); // verificando /health + /me no boot
  const iniciou = useRef(false);

  const limparSessao = useCallback(() => {
    gravarToken(null);
    setToken(null);
    setUsuario(null);
  }, []);

  // Registra o handler de 401 do axios: em modo ligado, sessão expirada cai aqui.
  useEffect(() => {
    registrarHandlerSessaoExpirada(() => limparSessao());
  }, [limparSessao]);

  // Boot: consulta /health para decidir o modo. Em modo ligado com token salvo,
  // hidrata o usuário via /me. Token inválido é descartado em silêncio.
  useEffect(() => {
    if (iniciou.current) return;
    iniciou.current = true;

    (async () => {
      let ligado = false;
      try {
        const health = await getHealth();
        ligado = Boolean(health?.auth_enabled);
      } catch {
        // /health indisponível: assume modo anônimo para não travar o app atual.
        ligado = false;
      }
      setAuthEnabled(ligado);

      if (ligado && lerToken()) {
        try {
          const me = await getMe();
          setUsuario(me);
        } catch {
          limparSessao();
        }
      } else if (!ligado) {
        // Modo anônimo: garante que nenhum token residual atrapalhe.
        limparSessao();
      }
      setCarregando(false);
    })();
  }, [limparSessao]);

  const login = useCallback(async ({ email, senha }) => {
    const resp = await apiLogin({ email, senha });
    gravarToken(resp.access_token);
    setToken(resp.access_token);
    const me = await getMe();
    setUsuario(me);
    return me;
  }, []);

  const signup = useCallback(async ({ nome_escritorio, email, senha }) => {
    const resp = await apiSignup({ nome_escritorio, email, senha });
    // Cadastro já loga: o token vem aninhado em resp.token.access_token.
    const accessToken = resp?.token?.access_token;
    gravarToken(accessToken);
    setToken(accessToken ?? null);
    // O signup já devolve o usuário; evita um /me redundante.
    const u = resp?.usuario ?? (accessToken ? await getMe() : null);
    setUsuario(u);
    return u;
  }, []);

  const logout = useCallback(() => {
    limparSessao();
  }, [limparSessao]);

  const role = usuario?.role ?? null;

  const valor = {
    authEnabled,
    token,
    usuario,
    carregando,
    login,
    signup,
    logout,
    role,
    ehAdmin: role === "admin",
  };

  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth precisa estar dentro de <AuthProvider>.");
  return ctx;
}
