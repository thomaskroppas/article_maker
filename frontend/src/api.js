// Тонкая обёртка над fetch с HTTP Basic Auth (креды из localStorage).

export function getCreds() {
  return localStorage.getItem("seo_auth") || "";
}

export function setCreds(user, pass) {
  localStorage.setItem("seo_auth", btoa(`${user}:${pass}`));
}

export function clearCreds() {
  localStorage.removeItem("seo_auth");
}

async function req(method, path, body) {
  const headers = { Authorization: `Basic ${getCreds()}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const resp = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401) {
    clearCreds();
    window.location.hash = "#/login";
    throw new Error("Не авторизован");
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (resp.status === 204) return null;
  const ct = resp.headers.get("content-type") || "";
  return ct.includes("application/json") ? resp.json() : resp.text();
}

export const api = {
  get: (p) => req("GET", p),
  post: (p, b) => req("POST", p, b),
  put: (p, b) => req("PUT", p, b),
  del: (p) => req("DELETE", p),
  runPipeline: (input) => req("POST", "/pipeline/run", input),
  stop: (id) => req("POST", `/pipeline/${id}/stop`),
  resume: (id, outline) => req("POST", `/pipeline/${id}/resume`, outline),
  status: (id) => req("GET", `/pipeline/${id}/status`),
  events: (id) => req("GET", `/pipeline/${id}/events`),
  result: (id) => req("GET", `/articles/${id}/result`),
  articles: () => req("GET", "/articles"),
};

// WebSocket URL с токеном (тот же base64, что в Basic Auth).
export function wsUrl(articleId) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/pipeline/${articleId}?token=${getCreds()}`;
}
