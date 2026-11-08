// Thin client for the Hookline HTTP API (docs/SPEC.md §3).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function errorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => (d && d.msg) || String(d)).join("; ");
  }
  return `Request failed (${status})`;
}

async function request(method, path, { json, form } = {}) {
  const init = { method, headers: { Accept: "application/json" } };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError("Can't reach the Hookline server — is it still running?", 0);
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status);
  return data;
}

const q = (params) => {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null && v !== "") usp.set(k, v);
  const str = usp.toString();
  return str ? `?${str}` : "";
};

export const api = {
  config: () => request("GET", "/api/config"),
  settings: () => request("GET", "/api/settings"),
  saveSettings: (patch) => request("PUT", "/api/settings", { json: patch }),
  shows: () => request("GET", "/api/shows"),
  promos: (show) => request("GET", `/api/promos${q({ show })}`),
  promo: (id) => request("GET", `/api/promos/${encodeURIComponent(id)}`),
  deletePromo: (id) => request("DELETE", `/api/promos/${encodeURIComponent(id)}`),
  episodes: () => request("GET", "/api/episodes"),
  retryEpisode: (id) => request("POST", `/api/episodes/${encodeURIComponent(id)}/retry`),
  deleteEpisode: (id) => request("DELETE", `/api/episodes/${encodeURIComponent(id)}`),
  upload(files, showTitle) {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    if (showTitle) form.append("show_title", showTitle);
    return request("POST", "/api/upload", { form });
  },
  exportUrl: (format, show) => `/api/export${q({ format, show })}`,
};
