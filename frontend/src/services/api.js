import axios from "axios";

// Em dev, VITE_API_URL fica vazio e o Vite faz proxy de /api e /health.
// Em produção (Railway), VITE_API_URL aponta para a URL pública do backend.
const API_BASE = import.meta.env.VITE_API_URL ?? "";

const api = axios.create({
  baseURL: `${API_BASE}/api`,
});

export async function getHealth() {
  const { data } = await axios.get(`${API_BASE}/health`);
  return data;
}

export async function getModulo01Status() {
  const { data } = await api.get("/modulo01/status");
  return data;
}

export async function processarArquivos({ entradas, cadastro }) {
  const form = new FormData();
  form.append("entradas", entradas);
  if (cadastro) form.append("cadastro", cadastro);
  const { data } = await api.post("/modulo01/processar", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export default api;
