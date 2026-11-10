// Small fetch wrapper: JSON in, JSON out, errors carry the server's message.
async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data && data.detail;
    const message = Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail;
    throw new Error(message || res.statusText);
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body || {}),
  put: (path, body) => request("PUT", path, body),
  del: (path) => request("DELETE", path),
};
